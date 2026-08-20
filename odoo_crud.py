#!/usr/bin/env python3
"""Odoo Demo Feeder — CRUD & introspection tool.

This is the *only* gateway the AI agent uses to talk to the target Odoo
database. It connects through Odoo's external API (XML-RPC) using credentials
read from the environment, so secrets never appear on the command line.

Environment variables (set by the launcher):
    ODOO_URL      e.g. https://mycompany.odoo.com
    ODOO_LOGIN    the user login (often an email)
    ODOO_SECRET   the API key or password

Optional:
    ODOO_DB              database name, when it is not the URL's first label
    ODOO_CRUD_SESSION    where the authenticated uid is cached between
                         processes; set it empty to authenticate every time

Every command prints a single JSON object to stdout:
    {"ok": true,  "result": <data>}
    {"ok": false, "error": "<message>"}

Exit code is 0 on success, 1 on failure — so the agent gets structured,
machine-readable feedback it can reason about (e.g. to debug a failing import).
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import tempfile
import xmlrpc.client


def fail(message):
    """Print a JSON error and exit non-zero."""
    print(json.dumps({"ok": False, "error": str(message)}))
    sys.exit(1)


def ok(result):
    """Print a JSON success payload and exit zero."""
    print(json.dumps({"ok": True, "result": result}, default=str))
    sys.exit(0)


def fail_result(result):
    """Print a structured failure payload and exit non-zero.

    Same shape as ok(), but ok=false and exit 1. Used where the failure has more
    to say than one error string — a rolled-back import carries per-row
    messages. Reporting those through ok() made a failed import indistinguishable
    from a successful one to anything reading the exit code.
    """
    print(json.dumps({"ok": False, "result": result}, default=str))
    sys.exit(1)


def get_config():
    url = (os.environ.get("ODOO_URL") or "").rstrip("/")
    login = os.environ.get("ODOO_LOGIN") or ""
    secret = os.environ.get("ODOO_SECRET") or ""
    if not url or not login or not secret:
        fail("Missing ODOO_URL, ODOO_LOGIN or ODOO_SECRET in the environment.")
    return url, login, secret


_CONNECTION = None
_FROM_SESSION = False


def _session_path():
    """Where the uid is cached between processes, or None if disabled.

    ODOO_CRUD_SESSION overrides the location; set it empty to turn the cache
    off. Defaults under XDG_CACHE_HOME, which the sandbox binds read-write.
    """
    if "ODOO_CRUD_SESSION" in os.environ:
        return os.environ["ODOO_CRUD_SESSION"] or None
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "odoo-crud", "session.json")


def _fingerprint(url, db, login, secret):
    """Identify the credentials a cached uid belongs to, without storing them.

    The secret is in there so that rotating the API key misses the cache
    instead of replaying a uid the new key never earned.
    """
    material = "\0".join((url, db, login, secret)).encode()
    return hashlib.sha256(material).hexdigest()[:32]


def _load_session(fingerprint):
    path = _session_path()
    if not path:
        return None
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception:  # noqa: BLE001 - a missing or corrupt cache is just a miss
        return None
    if not isinstance(data, dict) or data.get("fingerprint") != fingerprint:
        return None
    uid = data.get("uid")
    return (uid, data.get("version")) if isinstance(uid, int) and uid else None


def _save_session(fingerprint, uid, version):
    path = _session_path()
    if not path:
        return
    payload = {"fingerprint": fingerprint, "uid": uid, "version": version}
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
        # Written whole-then-renamed: two odoo-crud processes can overlap, and a
        # half-written file would be read back as a corrupt cache.
        handle, tmp = tempfile.mkstemp(dir=directory)
        with os.fdopen(handle, "w") as stream:
            json.dump(payload, stream)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 - caching is an optimisation, never fatal
        pass


def _forget_session():
    global _FROM_SESSION
    _FROM_SESSION = False
    path = _session_path()
    if not path:
        return
    try:
        os.remove(path)
    except Exception:  # noqa: BLE001
        pass


def connect(force=False):
    """Authenticate and return (uid, models_proxy, url, db, login, secret, version).

    Memoized for the life of the process, and the uid is cached on disk between
    processes. Authenticating once per RPC cost two extra round trips (version +
    authenticate) on every call — install-modules alone paid that five times.
    XML-RPC is stateless per request, so the uid and the proxies stay valid for
    the whole run; reusing the ServerProxy also keeps its HTTP connection alive
    between calls, which saves the TLS handshake too.

    The on-disk half matters because the agent gets one process per odoo-crud
    invocation, so in-process memoization alone still left a full login — and
    Odoo hashes the password on every authenticate(), around half a second — in
    front of every single command. execute_kw's own credential check is cached
    server-side, so replaying a known uid skips the login entirely.

    Pass force=True to drop both caches and authenticate again (see execute(),
    which does that if the kept-alive socket has gone stale or the server
    rejects the replayed uid).
    """
    global _CONNECTION, _FROM_SESSION
    if _CONNECTION is not None and not force:
        return _CONNECTION
    _CONNECTION = None
    _FROM_SESSION = False

    url, login, secret = get_config()
    # The database name is usually the host's first label for SaaS, but it can
    # be set explicitly via ODOO_DB. authenticate() needs a db name.
    db = os.environ.get("ODOO_DB") or _guess_db(url)
    fingerprint = _fingerprint(url, db, login, secret)

    cached = None if force else _load_session(fingerprint)
    if cached:
        uid, version = cached
        _FROM_SESSION = True
    else:
        common = xmlrpc.client.ServerProxy(
            f"{url}/xmlrpc/2/common", allow_none=True
        )
        try:
            version = common.version()
        except Exception as exc:  # noqa: BLE001 - report transport errors verbatim
            fail(f"Cannot reach Odoo at {url}: {exc}")
        try:
            uid = common.authenticate(db, login, secret, {})
        except Exception as exc:  # noqa: BLE001
            fail(f"Authentication call failed: {exc}")
        if not uid:
            fail(
                "Authentication failed: wrong login/API key, or wrong database "
                f"name '{db}'. Set ODOO_DB if the database name differs from the host."
            )
        _save_session(fingerprint, uid, version)

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    _CONNECTION = (uid, models, url, db, login, secret, version)
    return _CONNECTION


def _guess_db(url):
    """Best-effort database name from the URL host (works for *.odoo.com)."""
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return host.split(".", 1)[0]


def _stale_uid(fault, uid):
    """Does this Fault say the acting uid itself is no longer valid?

    Two shapes, depending on what happened to the user behind a cached uid:
    a wrong password for an existing one raises AccessDenied, a deleted one
    (database rebuilt underneath us) raises MissingError naming res.users. The
    res.users(uid,) match is what keeps this from swallowing an ordinary
    MissingError about the records the command was actually working on.
    """
    text = str(fault.faultString)
    return "access denied" in text.lower() or f"res.users({uid}," in text


_CONTEXT = {}


def execute(model, method, args=None, kwargs=None):
    # The --context flag rides on every call made by this process. Odoo behaviour
    # that is only reachable through the context was simply unreachable through
    # this tool before: chiefly 'active_test', without which search-read hides
    # every archived record, so the inactive currency the demo actually needs
    # reads as "does not exist in this database".
    kwargs = dict(kwargs or {})
    if _CONTEXT and "context" not in kwargs:
        kwargs["context"] = _CONTEXT

    # Two attempts: the connection is now reused across calls, so its kept-alive
    # socket can go cold when the server reloads its registry (which is exactly
    # what button_immediate_install does). xmlrpc's own Transport already
    # re-opens a merely-dropped socket; this outer retry covers the case it does
    # not — the server still refusing when that immediate retry runs — by
    # authenticating again from scratch. An Odoo Fault is an application error,
    # never a connection problem, so it is reported as-is without a retry.
    for attempt in (0, 1):
        uid, models, _url, db, _login, secret, _version = connect(force=bool(attempt))
        try:
            return models.execute_kw(
                db, uid, secret, model, method, args or [], kwargs
            )
        except xmlrpc.client.Fault as fault:
            # One kind of Fault is not an application error: a uid replayed from
            # the session cache that the server no longer accepts. Drop the
            # cache and earn a fresh uid before believing it. Retrying is safe
            # precisely because these are raised by the credential check, before
            # the method itself runs — so the first attempt wrote nothing.
            if attempt == 0 and _FROM_SESSION and _stale_uid(fault, uid):
                _forget_session()
                continue
            fail(f"Odoo error in {model}.{method}: {fault.faultString}")
        except Exception as exc:  # noqa: BLE001
            if attempt == 0:
                continue
            fail(f"Call {model}.{method} failed: {exc}")


def parse_json(value, what):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON for {what}: {exc}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_auth_check(_args):
    # The one command whose job is to prove the credentials work, so it always
    # logs in for real rather than trusting a cached uid — and, being the first
    # command of the run, it is what fills the cache for every command after it.
    uid, _models, url, db, login, _secret, version = connect(force=True)
    ok({"uid": uid, "url": url, "database": db, "login": login, "version": version})


def _unknown_fields(meta, names):
    """Names (first dotted path segment, so 'partner_id.name' checks
    'partner_id') absent from the model's own fields.

    A guessed field name that belongs to a different model (e.g. requesting
    'team_id' on crm.stage, or filtering uom.uom on 'category_id' — both only
    exist on other models) fails deep inside Odoo's ORM with a raw traceback in
    the server log instead of a clean RPC error. Catching it here turns that
    into one clear line before the call is even made.
    """
    unknown = set()
    for name in names:
        base = str(name).split(".", 1)[0]
        if base not in meta and base != "id":
            unknown.add(name)
    return sorted(unknown)


def _unknown_domain_fields(meta, domain):
    leaves = [leaf[0] for leaf in domain if isinstance(leaf, (list, tuple)) and len(leaf) == 3]
    return _unknown_fields(meta, leaves)


def cmd_search_read(args):
    domain = parse_json(args.domain, "--domain") or []
    fields = parse_json(args.fields, "--fields")
    kwargs = {}
    if fields:
        kwargs["fields"] = fields
    if args.limit:
        kwargs["limit"] = args.limit
    if domain or fields:
        meta = execute(args.model, "fields_get", [], {"attributes": []})
        unknown = _unknown_domain_fields(meta, domain) + _unknown_fields(meta, fields or [])
        if unknown:
            fail(
                f"Unknown field(s) for {args.model}: {', '.join(sorted(set(unknown)))}. "
                f"Check 'odoo-crud fields {args.model}' for the exact field names — "
                "nothing was searched."
            )
    ok(execute(args.model, "search_read", [domain], kwargs))


def cmd_create(args):
    values = parse_json(args.values, "--values")
    if values is None:
        fail("--values is required (a JSON object, or a JSON array of objects to batch-create).")
    # Odoo's create() natively batches: a JSON array of objects creates every
    # record in one call instead of one round-trip per record.
    if not isinstance(values, list):
        values = [values]
    ok(execute(args.model, "create", [values]))


def cmd_write(args):
    ids = parse_json(args.ids, "--ids")
    values = parse_json(args.values, "--values")
    if ids is None or values is None:
        fail("--ids and --values are required.")
    ok(execute(args.model, "write", [ids, values]))


def cmd_unlink(args):
    ids = parse_json(args.ids, "--ids")
    if ids is None:
        fail("--ids is required (a JSON list).")
    ok(execute(args.model, "unlink", [ids]))


def cmd_call(args):
    method_args = parse_json(args.args, "--args") or []
    method_kwargs = parse_json(args.kwargs, "--kwargs") or {}
    ok(execute(args.model, args.method, method_args, method_kwargs))


def cmd_models(args):
    domain = []
    if args.filter:
        domain = [["model", "like", args.filter]]
    result = execute(
        "ir.model", "search_read", [domain], {"fields": ["model", "name"]}
    )
    ok(result)


_COMPACT_ATTRS = ["string", "type", "required", "readonly", "store",
                  "relation", "selection"]


def _compact_field(info):
    """One line per field: type, flags, target model, selection values."""
    parts = [info.get("type") or "?"]
    if info.get("required"):
        parts.append("required")
    if info.get("readonly"):
        parts.append("readonly")
    if not info.get("store", True):
        parts.append("not-stored")
    if info.get("relation"):
        parts.append(f"-> {info['relation']}")
    selection = info.get("selection")
    if selection:
        values = [str(pair[0]) for pair in selection
                  if isinstance(pair, (list, tuple)) and pair]
        shown = "|".join(values[:12])
        if len(values) > 12:
            shown += f"|+{len(values) - 12} more"
        parts.append(f"= {shown}")
    return " ".join(parts)


def cmd_fields(args):
    """Describe a model's fields (introspection).

    A raw fields_get is enormous — a few hundred fields on res.partner, each
    carrying a multi-sentence 'help' — and every byte of it lands in the agent's
    context and is re-sent on every following turn, which costs far more than
    the data being imported. So the default is one compact line per field
    ("many2one required -> res.partner"), which is all that is needed to write a
    CSV. --filter narrows to a name or label substring; --full returns the raw
    fields_get, help text included, when the description really is needed.
    """
    if args.full:
        ok(execute(args.model, "fields_get", [],
                   {"attributes": _COMPACT_ATTRS + ["help"]}))

    meta = execute(args.model, "fields_get", [], {"attributes": _COMPACT_ATTRS})
    names = sorted(meta)
    if args.filter:
        # Comma-separated: asking for several named fields at once is the common
        # case ('name,list_price,barcode'), and treating that as one literal
        # substring matched nothing — which sent the caller back to dumping every
        # field, the exact output this command exists to avoid.
        needles = [part.strip().lower() for part in args.filter.split(",") if part.strip()]
        names = [
            name for name in names
            if any(needle in name.lower()
                   or needle in str(meta[name].get("string") or "").lower()
                   for needle in needles)
        ]
    result = {
        "model": args.model,
        "total_fields": len(meta),
        "shown": len(names),
        "fields": {name: _compact_field(meta[name]) for name in names},
    }
    if not args.filter and len(meta) > 60:
        result["hint"] = (
            f"{len(meta)} fields. Narrow the next lookup with "
            f"'odoo-crud fields {args.model} --filter <text>'."
        )
    ok(result)


# def _disable_demo_data():
#     """Stop Odoo from loading demo data for modules installed from here on.

#     A module's demo data is only loaded on install if the database is
#     flagged as "demo-enabled" (any ir.module.module record, typically
#     'base', has demo=True — set once at database creation). There is no
#     per-call RPC flag to skip it; clearing that flag on every module that
#     currently carries it is what stops button_immediate_install from
#     pulling in demo records for modules installed afterwards.
#     """
#     demo_recs = execute(
#         "ir.module.module", "search_read",
#         [[["demo", "=", True]]], {"fields": ["id"]},
#     )
#     if demo_recs:
#         execute(
#             "ir.module.module", "write",
#             [[r["id"] for r in demo_recs], {"demo": False}],
#         )


def cmd_install_modules(args):
    """Install modules by technical name and confirm — a single blocking call.

    button_immediate_install is synchronous server-side: when it returns, the
    modules are installed and the registry reloaded. We then re-query the states
    so the caller gets a definitive result and never needs to 'wait'. The re-read
    is a plain RPC — XML-RPC carries no client-side registry, so reusing the
    memoized connection still sees the post-install state.
    """
    names = args.modules
    recs = execute(
        "ir.module.module", "search_read",
        [[["name", "in", names]]], {"fields": ["name", "state"]},
    )
    found = {r["name"] for r in recs}
    missing = [n for n in names if n not in found]
    to_install = [r["id"] for r in recs if r.get("state") == "uninstalled"]

    if to_install:
        execute("ir.module.module", "button_immediate_install", [to_install])

    # Re-read the states after the install to report the final result.
    final = execute(
        "ir.module.module", "search_read",
        [[["name", "in", names]]], {"fields": ["name", "state"]},
    )
    states = {r["name"]: r["state"] for r in final}
    not_installed = [n for n, s in states.items() if s != "installed"]
    ok({
        "requested": names,
        "missing": missing,
        "installed_now": [r for r in states if states[r] == "installed"],
        "not_installed": not_installed,
        "states": states,
    })


def cmd_resolve(args):
    """Map external ids to the database ids every later call needs.

    Records go in by external id, and everything afterwards — action_confirm,
    set-image, an order line referencing a product — needs the integer Odoo
    assigned. Nothing about the import reveals those: an external id's position
    in the CSV is not its database id, and a single record already sitting in
    the model shifts every one of them. Guessing writes order lines against the
    wrong products and still returns ok: true, so it is only found by reading
    the finished demo.

    import-csv files its ids under the '__import__' module, Odoo's prefix for an
    external id with no dot in it. Each entry carries the record's display name
    so a wrong pairing can be seen rather than deduced.
    """
    model = args.model
    domain = [["model", "=", model]]
    if args.module:
        domain.append(["module", "=", args.module])

    bare = None
    if args.xmlids:
        names = parse_json(args.xmlids, "--xmlids")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            fail("--xmlids must be a JSON array of external id strings.")
        # Accept 'product_1' and '__import__.product_1' alike.
        bare = [n.split(".", 1)[-1] for n in names]
        domain.append(["name", "in", bare])

    recs = execute(
        "ir.model.data", "search_read", [domain],
        {"fields": ["module", "name", "res_id"]},
    )

    # search_read rather than read: a stale ir.model.data row pointing at a
    # deleted record is skipped instead of failing the whole call.
    labels = {}
    if recs:
        rows = execute(
            model, "search_read", [[["id", "in", [r["res_id"] for r in recs]]]],
            {"fields": ["display_name"]},
        ) or []
        labels = {row["id"]: row.get("display_name") for row in rows}

    entries = sorted(
        (
            {
                "external_id": "%s.%s" % (r["module"], r["name"]),
                "xmlid": r["name"],
                "db_id": r["res_id"],
                "name": labels.get(r["res_id"]),
            }
            for r in recs
        ),
        key=lambda e: e["db_id"],
    )
    result = {
        "model": model,
        "count": len(entries),
        "map": {e["xmlid"]: e["db_id"] for e in entries},
        "records": entries,
    }
    if bare is not None:
        found = {e["xmlid"] for e in entries}
        result["missing"] = [n for n in bare if n not in found]
        if result["missing"]:
            fail_result(result)
    ok(result)


def cmd_bill_po(args):
    """Turn purchase orders into posted vendor bills.

    action_create_invoice on its own gives a draft with every quantity at 0 and
    a total of 0, because a product's Control Policy defaults to billing on
    *received* quantities and a demo never receives the goods. Odoo is right to
    refuse; the bill is simply not a bill. Getting a real one took switching the
    policy, writing each line's quantity, adding a vendor reference and an
    invoice date, and only then posting — five steps between a green call and a
    document worth showing.

    All of it, in order:
      1. confirm any order still a draft RFQ — only a confirmed one bills;
      2. switch its products to bill on ordered quantities, so Odoo fills the
         quantities itself rather than being patched afterwards;
      3. action_create_invoice;
      4. fill anything still at 0 from its purchase order line;
      5. set ref and invoice_date, both of which posting requires;
      6. post, unless asked not to.
    """
    ids = parse_json(args.ids, "--ids")
    if not isinstance(ids, list) or not ids:
        fail("--ids must be a non-empty JSON array of purchase.order ids.")

    orders = execute(
        "purchase.order", "search_read", [[["id", "in", ids]]],
        {"fields": ["name", "state"]},
    )
    if not orders:
        fail(f"No purchase.order found for ids {ids}.")
    found = {o["id"] for o in orders}
    missing = [i for i in ids if i not in found]

    # 1. A draft RFQ cannot be billed.
    to_confirm = [o["id"] for o in orders if o["state"] in ("draft", "sent")]
    if to_confirm:
        execute("purchase.order", "button_confirm", [to_confirm])

    # 2. Bill control. Left on 'receive', step 3 produces the zero-quantity
    #    draft; flipping it first means Odoo computes the quantities.
    lines = execute(
        "purchase.order.line", "search_read", [[["order_id", "in", ids]]],
        {"fields": ["product_id", "product_qty", "order_id"]},
    )
    policy_changed = []
    if lines and not args.keep_bill_control:
        product_ids = sorted({l["product_id"][0] for l in lines if l.get("product_id")})
        prods = execute(
            "product.product", "search_read", [[["id", "in", product_ids]]],
            {"fields": ["product_tmpl_id", "purchase_method"]},
        )
        tmpl_ids = sorted({
            p["product_tmpl_id"][0] for p in prods
            if p.get("product_tmpl_id") and p.get("purchase_method") != "purchase"
        })
        if tmpl_ids:
            execute("product.template", "write",
                    [tmpl_ids, {"purchase_method": "purchase"}])
            policy_changed = tmpl_ids

    # 3. Create the drafts.
    execute("purchase.order", "action_create_invoice", [ids])

    after = execute(
        "purchase.order", "search_read", [[["id", "in", ids]]],
        {"fields": ["name", "state", "invoice_ids"]},
    )
    move_ids = sorted({m for o in after for m in (o.get("invoice_ids") or [])})
    if not move_ids:
        fail_result({
            "orders": after, "bills": [],
            "error": "action_create_invoice produced no bill. Every line may "
                     "already be invoiced, or the orders were not confirmed.",
        })

    # 4. Anything still at zero gets its quantity from the order line it came
    #    from — the case step 2 cannot reach, e.g. a partly-invoiced line.
    qty_by_line = {l["id"]: l["product_qty"] for l in lines}
    mlines = execute(
        "account.move.line", "search_read",
        [[["move_id", "in", move_ids], ["purchase_line_id", "!=", False]]],
        {"fields": ["quantity", "purchase_line_id", "move_id"]},
    )
    patched = 0
    for ml in mlines:
        if ml.get("quantity"):
            continue
        want = qty_by_line.get((ml.get("purchase_line_id") or [None])[0])
        if want:
            execute("account.move.line", "write", [[ml["id"]], {"quantity": want}])
            patched += 1

    # 5. Posting refuses a vendor bill with no date, and a bill with no vendor
    #    reference is not one a customer would accept either.
    moves = execute(
        "account.move", "search_read", [[["id", "in", move_ids]]],
        {"fields": ["name", "state", "ref", "invoice_date", "partner_id"]},
    )
    today = datetime.date.today().isoformat()
    order_name = {o["id"]: o["name"] for o in after}
    for mv in moves:
        vals = {}
        if not mv.get("ref"):
            vals["ref"] = args.ref or "BILL-%s" % (
                order_name.get(ids[0], mv.get("name") or "PO")
            )
        if not mv.get("invoice_date"):
            vals["invoice_date"] = args.date or today
        if vals and mv.get("state") == "draft":
            execute("account.move", "write", [[mv["id"]], vals])

    # 6. Post.
    if not args.no_post:
        draft = [m["id"] for m in moves if m.get("state") == "draft"]
        if draft:
            execute("account.move", "action_post", [draft])

    final = execute(
        "account.move", "search_read", [[["id", "in", move_ids]]],
        {"fields": ["name", "state", "ref", "invoice_date", "amount_total"]},
    )
    result = {
        "orders_confirmed": to_confirm,
        "bill_control_switched": policy_changed,
        "lines_patched": patched,
        "bills": final,
        "missing_orders": missing,
        "posted": not args.no_post,
    }
    unposted = [m for m in final if not args.no_post and m.get("state") != "posted"]
    zero = [m for m in final if not m.get("amount_total")]
    if unposted or zero:
        result["error"] = (
            "Bills came back unposted or with a zero total — the demo would show "
            "an empty document."
        )
        fail_result(result)
    ok(result)


def _ensure_base_import_module():
    """Make sure the module providing the industry download path is installed.

    button_immediate_install_app lives in base_import_module. Without it the
    call fails as a bare "no such method" fault, which says nothing about the
    cause. It ships with Odoo and installs like any other local module, so
    install it rather than report it.
    """
    recs = execute(
        "ir.module.module", "search_read",
        [[["name", "=", "base_import_module"]]], {"fields": ["state"]},
    )
    if not recs:
        fail("This database has no 'base_import_module', so industry modules "
             "cannot be downloaded from apps.odoo.com.")
    if recs[0]["state"] != "installed":
        execute("ir.module.module", "button_immediate_install", [[recs[0]["id"]]])


def cmd_install_industry(args):
    """Install an industry module, which does not live on the addons path.

    install-modules cannot reach these: there is no ir.module.module row to
    install, because the module is not local. It is downloaded from
    apps.odoo.com, and the Apps UI does that in three steps, which this mirrors:

      1. button_immediate_install_app downloads the zip for this Odoo version,
         checks its dependencies against this database and returns an action
         pointing at a base.import.module wizard;
      2. tick the wizard's "Load demo data" box;
      3. press its Install button (import_module).

    Step 2 is the one that matters for a demo. The industry's sample records —
    the products, partners and configured screens that make a database look
    like a going concern — ride on the wizard's with_demo field alone, so
    without it the module installs as bare configuration.

    Dependencies are validated before anything is installed, and an industry
    depending on modules this database does not have (typically Enterprise ones
    on a Community database) fails there, naming them.
    """
    name = args.module
    _ensure_base_import_module()

    existing = execute(
        "ir.module.module", "search_read",
        [[["name", "=", name]]], {"fields": ["state"]},
    )
    if existing and existing[0]["state"] == "installed":
        ok({"module": name, "state": "installed", "already_installed": True,
            "with_demo": None})

    action = execute(
        "ir.module.module", "button_immediate_install_app", [[]],
        {"context": {"module_name": name}},
    )
    wizard_id = action.get("res_id") if isinstance(action, dict) else None
    if not wizard_id:
        fail(f"Downloading industry '{name}' returned no install wizard. Check "
             f"the name against the industry list — it must be the technical "
             f"one, e.g. 'bakery'.")

    # Default on: this tool exists to fill a demo database, and the sample
    # records are the visible half of an industry module.
    with_demo = not args.no_demo
    if with_demo:
        execute("base.import.module", "write", [[wizard_id], {"with_demo": True}])
    execute("base.import.module", "import_module", [[wizard_id]])

    final = execute(
        "ir.module.module", "search_read",
        [[["name", "=", name]]], {"fields": ["name", "state"]},
    )
    state = final[0]["state"] if final else None
    result = {"module": name, "state": state, "already_installed": False,
              "with_demo": with_demo}
    if state != "installed":
        fail_result(result)
    ok(result)


def cmd_set_image(args):
    """Download an image (or read a local file) and set it on a record.

    Uses real images (e.g. product photos / the company logo found while
    researching the site) — no image generation, so no image-model quota.
    """
    field = args.field or "image_1920"
    if args.url:
        import urllib.request
        url = args.url
        if url.startswith("//"):
            # Protocol-relative URL (common on Shopify/Sapo storefronts) —
            # urllib refuses these outright, so assume https.
            url = "https:" + url
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "odoo-demo-feeder"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except Exception as exc:  # noqa: BLE001
            fail(f"Could not download image from {url}: {exc}")
    elif args.file:
        try:
            with open(args.file, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            fail(f"Cannot read image file '{args.file}': {exc}")
    else:
        fail("Provide --url or --file.")

    if len(raw) > 10 * 1024 * 1024:
        fail("Image is larger than 10 MB — pick a smaller one.")

    import base64
    encoded = base64.b64encode(raw).decode("ascii")
    result = execute(args.model, "write", [[args.id], {field: encoded}])
    ok({"model": args.model, "id": args.id, "field": field,
        "bytes": len(raw), "written": result})


def _read_csv(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            data = handle.read()
    except OSError as exc:
        fail(f"Cannot read CSV file '{path}': {exc}")
    import csv
    import io

    reader = csv.reader(io.StringIO(data))
    rows = list(reader)
    if not rows:
        fail(f"CSV file '{path}' is empty.")
    headers = rows[0]
    body = rows[1:]
    return headers, body


def _field_base(header):
    """The model field a CSV header maps to, e.g. 'partner_id/id' -> 'partner_id'."""
    base = header.split("/", 1)[0]
    if base.endswith(".id"):
        base = base[:-3]
    return base


def cmd_import_preview(args):
    """Introspection-only preview: match CSV headers against the model's fields.

    Does NOT touch base_import (its controller is unreliable over RPC on recent
    Odoo). It reports which columns map to real fields, which don't, and a sample,
    so the agent can see why an import would fail before running it.
    """
    headers, body = _read_csv(args.file)
    meta = execute(
        args.model, "fields_get", [],
        {"attributes": ["string", "relation"] + _REQUIRED_ATTRS},
    )
    # The same matcher import-csv refuses on, so a preview that reports no
    # unknown column is a promise that the import will not be rejected over one
    # — and a preview that reports one carries the same suggestion.
    unknown = _unknown_columns(meta, headers)
    suggestions = dict(unknown)
    columns = []
    for header in headers:
        base = _field_base(header)
        column = {
            "header": header,
            "field": base,
            "exists": header not in suggestions,
            "type": meta.get(base, {}).get("type"),
        }
        if suggestions.get(header):
            column["suggestion"] = suggestions[header]
        columns.append(column)
    missing_required = _missing_required_fields(args.model, meta, headers)
    ok({
        "model": args.model,
        "rows": len(body),
        "columns": columns,
        "unknown_columns": [
            {"header": header, "suggestion": suggestion}
            for header, suggestion in unknown
        ],
        "missing_required_columns": missing_required,
        "sample_rows": body[:3],
    })


_REQUIRED_ATTRS = ["type", "required", "readonly", "store"]


def _unknown_columns(meta, headers):
    """CSV columns that map to no field, each paired with a near-miss guess.

    Returns [(column, suggestion or None), ...], drawn from the model's real
    field names — usually enough to fix the CSV without another round trip.
    Callers do the wording: import-csv folds it into its refusal, import-preview
    reports it as JSON.
    """
    import difflib

    unknown = []
    for header in headers:
        base = _field_base(header)
        if base == "id" or base in meta:
            continue
        close = difflib.get_close_matches(base, meta, n=1, cutoff=0.6)
        if not close:
            # A renamed field often keeps the old name as a substring
            # ('detailed_type' -> 'type'), which scores too low for difflib but
            # is exactly the suggestion worth making. Shortest match wins, so
            # 'type' is preferred over 'service_tracking_type'.
            contained = sorted((f for f in meta if f in base or base in f), key=len)
            close = contained[:1]
        unknown.append((header, close[0] if close else None))
    return unknown


def _missing_required_fields(model, meta, headers):
    """Model fields that genuinely have to come from the CSV but are absent.

    A missing required field (e.g. product_id on stock.quant) doesn't always
    surface as a clean load() message — it can slip through as NULL and crash
    at the SQL layer with a raw, uncaught 'not-null constraint' error instead.
    Catching it here, before load() ever runs, turns that into one clear line.

    But 'required' in fields_get describes the field *definition*, not whether
    a value must be supplied, so it cannot be used on its own. product.template
    marks type, uom_id, service_tracking and base_unit_count required and every
    one of them has a default; product_variant_ids is required and is a
    one2many the ORM fills in itself. Reporting those refuses a perfectly good
    import, so narrow the list to fields that are writable, stored, not a
    x2many, and have no default — the last of which only Odoo can answer, via
    default_get.
    """
    present = {_field_base(header) for header in headers}
    candidates = [
        name for name, info in meta.items()
        if info.get("required")
        and name not in present
        and not info.get("readonly")
        and info.get("store", True)
        and info.get("type") not in ("one2many", "many2many")
    ]
    if not candidates:
        return []
    # default_get returns an entry only for the fields that do have a default.
    defaults = execute(model, "default_get", [sorted(candidates)]) or {}
    return sorted(name for name in candidates if name not in defaults)


def cmd_import_csv(args):
    """Import a CSV via the model's low-level load() — handles external IDs and
    the 'field/id' relational syntax, and reports per-row error messages."""
    headers, body = _read_csv(args.file)
    fields = parse_json(args.fields, "--fields") or headers

    meta = execute(args.model, "fields_get", [], {"attributes": _REQUIRED_ATTRS})

    # Reject columns the model does not have *before* load() runs. Otherwise a
    # single stale field name (detailed_type, renamed in Odoo 18) costs a failed
    # import plus a full fields_get dump to work out which column was wrong.
    unknown = _unknown_columns(meta, fields)
    if unknown:
        listed = ", ".join(
            f"{column} (did you mean '{suggestion}'?)" if suggestion else column
            for column, suggestion in unknown
        )
        fail(
            f"CSV for {args.model} has column(s) that are not fields of the "
            f"model: {listed}. "
            f"Check 'odoo-crud fields {args.model} --filter <text>' for the "
            "exact names — nothing was imported."
        )

    missing_required = _missing_required_fields(args.model, meta, fields)
    if missing_required:
        fail(
            f"CSV for {args.model} is missing required field(s): "
            f"{', '.join(missing_required)}. Add a '<field>/id' (relational) or "
            f"'<field>' column, or check 'odoo-crud fields {args.model}' for the "
            "exact names — nothing was imported."
        )

    result = execute(args.model, "load", [fields, body])

    # load() returns {'ids': [...] or False, 'messages': [...]}. A non-empty
    # 'messages' list means at least one row failed (the load is rolled back).
    messages = result.get("messages", []) if isinstance(result, dict) else []
    ids = result.get("ids") if isinstance(result, dict) else result
    if messages:
        fail_result({"status": "failed", "messages": messages,
                     "imported": 0, "fields_used": fields})
    ok({"status": "imported", "imported": len(ids or []),
        "ids": ids, "fields_used": fields})


def _add_context_arg(parser):
    parser.add_argument(
        "--context",
        help="JSON object merged into the Odoo context for this call. Mainly "
             "'{\"active_test\": false}', which also returns archived records — "
             "most currencies ship inactive, so without it a perfectly real "
             "currency looks like it does not exist.",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="odoo_crud.py",
        description="CRUD & introspection tool for the Odoo Demo Feeder.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-check", help="Verify the connection and credentials.")

    p = sub.add_parser("search-read", help="Search and read records.")
    p.add_argument("model")
    p.add_argument("--domain", help="JSON list, e.g. '[[\"name\",\"=\",\"X\"]]'")
    p.add_argument("--fields", help="JSON list of field names.")
    p.add_argument("--limit", type=int)
    _add_context_arg(p)

    p = sub.add_parser("create", help="Create one or more records (batch: pass a JSON array).")
    p.add_argument("model")
    p.add_argument(
        "--values", required=True,
        help="JSON object of field values for one record, OR a JSON array of "
             "objects to create many records in a single call — e.g. "
             "'[{\"name\": \"A\"}, {\"name\": \"B\"}]'. Prefer batching over "
             "one create call per record.",
    )
    _add_context_arg(p)

    p = sub.add_parser("write", help="Update records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")
    p.add_argument("--values", required=True, help="JSON object of field values.")
    _add_context_arg(p)

    p = sub.add_parser("unlink", help="Delete records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")
    _add_context_arg(p)

    p = sub.add_parser(
        "call",
        help="Call an arbitrary model method (prefer create/write/unlink/"
             "search-read when they fit — this is for anything else).",
        description="Call an arbitrary model method. --args is the method's "
                     "FULL positional argument list as ONE JSON array — e.g. "
                     "for write(ids, values) pass "
                     "--args '[[1], {\"name\": \"X\"}]', not --ids/--values "
                     "(those belong to the dedicated write command instead).",
    )
    p.add_argument("model")
    p.add_argument("method")
    p.add_argument("--args", help="JSON array of ALL positional args, e.g. '[[1], {\"name\": \"X\"}]' for write.")
    p.add_argument("--kwargs", help="JSON object of keyword args.")
    _add_context_arg(p)

    p = sub.add_parser("models", help="List models (introspection).")
    p.add_argument("--filter", help="Substring to filter the technical name.")

    p = sub.add_parser(
        "fields",
        help="Describe a model's fields, one compact line each (introspection).",
    )
    p.add_argument("model")
    p.add_argument(
        "--filter",
        help="Only fields whose technical name or label contains this text. "
             "Accepts a comma-separated list to look up several at once, e.g. "
             "--filter 'name,list_price,barcode'. Use it on big models "
             "(res.partner, product.template) instead of dumping every field.",
    )
    p.add_argument(
        "--full", action="store_true",
        help="Raw fields_get including every help text — very verbose, only "
             "when a field's description is genuinely needed.",
    )

    p = sub.add_parser(
        "install-modules",
        help="Install modules by name and confirm, in one blocking call.",
    )
    p.add_argument("modules", nargs="+", help="Technical module names, e.g. crm stock.")

    p = sub.add_parser(
        "install-industry",
        help="Install ONE industry module, downloaded from apps.odoo.com.",
        description=(
            "Industry modules (bakery, hotel, industry_lawyer...) are not on the addons "
            "path, so install-modules cannot see them. This downloads the one "
            "named, loads its demo data, and installs it — the same three steps "
            "the Apps screen takes. Blocking: it returns installed or failed. An "
            "industry needing modules this database lacks (often Enterprise ones) "
            "fails before installing anything, naming what is missing."
        ),
    )
    p.add_argument("module", help="ONE technical industry name, e.g. bakery.")
    p.add_argument(
        "--no-demo", action="store_true",
        help="Install the configuration without the industry's sample records. "
             "They are loaded by default: they are what makes the database look "
             "like a running business.",
    )

    p = sub.add_parser(
        "resolve",
        help="Map external ids to database ids for a model.",
        description=(
            "Everything is imported by external id; action_confirm, set-image "
            "and any order line need the database id instead. An external id's "
            "position in the CSV is NOT its database id — one record already in "
            "the model shifts every one — and referencing the wrong id still "
            "returns ok: true. Read the map here before wiring anything. Each "
            "entry carries the record's display name, so check a couple by eye."
        ),
    )
    p.add_argument("model")
    p.add_argument(
        "--xmlids",
        help="JSON array of external ids to resolve, e.g. '[\"product_1\"]'. "
             "Omitted, every external id known for the model comes back. "
             "Anything not found is listed in 'missing' and the call fails.",
    )
    p.add_argument(
        "--module",
        help="External-id module prefix to filter on. Use '__import__' for the "
             "records this run imported, which is where import-csv files them.",
    )

    p = sub.add_parser(
        "bill-po",
        help="Turn purchase orders into POSTED vendor bills.",
        description=(
            "action_create_invoice alone returns a draft with every quantity at "
            "0 and a total of 0: a product's Control Policy bills on RECEIVED "
            "quantities by default, and a demo receives nothing. This does the "
            "whole sequence — confirm the RFQ, switch the products to bill on "
            "ordered quantities, create, fill any line still at 0 from its "
            "order line, set the vendor reference and invoice date that posting "
            "requires, then post. It fails if a bill ends up unposted or at "
            "zero, because that document is empty on screen."
        ),
    )
    p.add_argument("--ids", required=True,
                   help="JSON array of purchase.order ids, e.g. '[3,4]'.")
    p.add_argument("--ref", help="Vendor reference for the bills. Defaults to "
                                "one derived from the order name.")
    p.add_argument("--date", help="Invoice date, YYYY-MM-DD. Defaults to today.")
    p.add_argument("--no-post", action="store_true",
                   help="Stop at a complete draft instead of posting. The "
                        "reports stay empty until it is posted.")
    p.add_argument("--keep-bill-control", action="store_true",
                   help="Leave each product's Control Policy alone. The bill "
                        "then covers only received quantities, which in a demo "
                        "is usually none of them.")

    p = sub.add_parser("set-image", help="Set a record image from a URL or file.")
    p.add_argument("model")
    p.add_argument("--id", type=int, required=True, help="Record id.")
    p.add_argument("--url", help="Image URL to download.")
    p.add_argument("--file", help="Local image file.")
    p.add_argument("--field", help="Image field (default image_1920).")

    p = sub.add_parser(
        "import-preview",
        help="Preview a CSV import without committing (introspection/debug).",
    )
    p.add_argument("model")
    p.add_argument("--file", required=True)

    p = sub.add_parser("import-csv", help="Import a CSV file into a model.")
    p.add_argument("model")
    p.add_argument("--file", required=True)
    p.add_argument("--fields", help="JSON list mapping each column to a field.")
    _add_context_arg(p)

    return parser


HANDLERS = {
    "auth-check": cmd_auth_check,
    "search-read": cmd_search_read,
    "create": cmd_create,
    "write": cmd_write,
    "unlink": cmd_unlink,
    "call": cmd_call,
    "models": cmd_models,
    "fields": cmd_fields,
    "install-modules": cmd_install_modules,
    "install-industry": cmd_install_industry,
    "resolve": cmd_resolve,
    "bill-po": cmd_bill_po,
    "set-image": cmd_set_image,
    "import-preview": cmd_import_preview,
    "import-csv": cmd_import_csv,
}


def main():
    global _CONTEXT
    args = build_parser().parse_args()
    context = parse_json(getattr(args, "context", None), "--context")
    if context is not None:
        if not isinstance(context, dict):
            fail("--context must be a JSON object, e.g. '{\"inventory_mode\": true}'.")
        _CONTEXT = context
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
