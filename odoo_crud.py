#!/usr/bin/env python3
"""Odoo Demo Feeder — CRUD & introspection tool.

This is the *only* gateway the AI agent uses to talk to the target Odoo
database. It connects through Odoo's external API (XML-RPC) using credentials
read from the environment, so secrets never appear on the command line.

Environment variables (set by the launcher):
    ODOO_URL      e.g. https://mycompany.odoo.com
    ODOO_LOGIN    the user login (often an email)
    ODOO_SECRET   the API key or password

Every command prints a single JSON object to stdout:
    {"ok": true,  "result": <data>}
    {"ok": false, "error": "<message>"}

Exit code is 0 on success, 1 on failure — so the agent gets structured,
machine-readable feedback it can reason about (e.g. to debug a failing import).
"""

import argparse
import json
import os
import sys
import xmlrpc.client


def fail(message):
    """Print a JSON error and exit non-zero."""
    print(json.dumps({"ok": False, "error": str(message)}))
    sys.exit(1)


def ok(result):
    """Print a JSON success payload and exit zero."""
    print(json.dumps({"ok": True, "result": result}, default=str))
    sys.exit(0)


def get_config():
    url = (os.environ.get("ODOO_URL") or "").rstrip("/")
    login = os.environ.get("ODOO_LOGIN") or ""
    secret = os.environ.get("ODOO_SECRET") or ""
    if not url or not login or not secret:
        fail("Missing ODOO_URL, ODOO_LOGIN or ODOO_SECRET in the environment.")
    return url, login, secret


def connect():
    """Authenticate and return (uid, models_proxy, url, db, login, secret)."""
    url, login, secret = get_config()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    try:
        version = common.version()
    except Exception as exc:  # noqa: BLE001 - report any transport error verbatim
        fail(f"Cannot reach Odoo at {url}: {exc}")

    # The database name is usually the host's first label for SaaS, but it can
    # be set explicitly via ODOO_DB. authenticate() needs a db name.
    db = os.environ.get("ODOO_DB") or _guess_db(url)
    try:
        uid = common.authenticate(db, login, secret, {})
    except Exception as exc:  # noqa: BLE001
        fail(f"Authentication call failed: {exc}")
    if not uid:
        fail(
            "Authentication failed: wrong login/API key, or wrong database "
            f"name '{db}'. Set ODOO_DB if the database name differs from the host."
        )
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return uid, models, url, db, login, secret, version


def _guess_db(url):
    """Best-effort database name from the URL host (works for *.odoo.com)."""
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return host.split(".", 1)[0]


def execute(model, method, args=None, kwargs=None):
    uid, models, _url, db, _login, secret, _version = connect()
    try:
        return models.execute_kw(
            db, uid, secret, model, method, args or [], kwargs or {}
        )
    except xmlrpc.client.Fault as fault:
        fail(f"Odoo error in {model}.{method}: {fault.faultString}")
    except Exception as exc:  # noqa: BLE001
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
    uid, _models, url, db, login, _secret, version = connect()
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


def cmd_fields(args):
    attrs = ["string", "type", "required", "relation", "selection", "help"]
    ok(execute(args.model, "fields_get", [], {"attributes": attrs}))


def _disable_demo_data():
    """Stop Odoo from loading demo data for modules installed from here on.

    A module's demo data is only loaded on install if the database is
    flagged as "demo-enabled" (any ir.module.module record, typically
    'base', has demo=True — set once at database creation). There is no
    per-call RPC flag to skip it; clearing that flag on every module that
    currently carries it is what stops button_immediate_install from
    pulling in demo records for modules installed afterwards.
    """
    demo_recs = execute(
        "ir.module.module", "search_read",
        [[["demo", "=", True]]], {"fields": ["id"]},
    )
    if demo_recs:
        execute(
            "ir.module.module", "write",
            [[r["id"] for r in demo_recs], {"demo": False}],
        )


def cmd_install_modules(args):
    """Install modules by technical name and confirm — a single blocking call.

    button_immediate_install is synchronous server-side: when it returns, the
    modules are installed and the registry reloaded. We then re-query the states
    on a fresh connection (each execute() re-authenticates) so the caller gets a
    definitive result and never needs to 'wait'.
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
        _disable_demo_data()
        execute("ir.module.module", "button_immediate_install", [to_install])

    # Fresh connection (registry has reloaded) to report the final states.
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
        {"attributes": ["string", "type", "relation", "required"]},
    )
    columns = []
    for header in headers:
        base = _field_base(header)
        exists = base == "id" or base in meta
        columns.append({
            "header": header,
            "field": base,
            "exists": exists,
            "type": meta.get(base, {}).get("type"),
        })
    unknown = [c["header"] for c in columns if not c["exists"]]
    missing_required = _missing_required_fields(meta, headers)
    ok({
        "model": args.model,
        "rows": len(body),
        "columns": columns,
        "unknown_columns": unknown,
        "missing_required_columns": missing_required,
        "sample_rows": body[:3],
    })


def _missing_required_fields(meta, headers):
    """Model fields Odoo marks required but absent from the CSV headers.

    A missing required field (e.g. product_id on stock.quant) doesn't always
    surface as a clean load() message — it can slip through as NULL and crash
    at the SQL layer with a raw, uncaught 'not-null constraint' error instead.
    Catching it here, before load() ever runs, turns that into one clear line.
    """
    present = {_field_base(h) for h in headers}
    return sorted(
        name for name, info in meta.items()
        if info.get("required") and name not in present
    )


def cmd_import_csv(args):
    """Import a CSV via the model's low-level load() — handles external IDs and
    the 'field/id' relational syntax, and reports per-row error messages."""
    headers, body = _read_csv(args.file)
    fields = parse_json(args.fields, "--fields") or headers

    meta = execute(args.model, "fields_get", [], {"attributes": ["required"]})
    missing_required = _missing_required_fields(meta, fields)
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
        ok({"status": "failed", "messages": messages,
            "imported": 0, "fields_used": fields})
    ok({"status": "imported", "imported": len(ids or []),
        "ids": ids, "fields_used": fields})


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

    p = sub.add_parser("create", help="Create one or more records (batch: pass a JSON array).")
    p.add_argument("model")
    p.add_argument(
        "--values", required=True,
        help="JSON object of field values for one record, OR a JSON array of "
             "objects to create many records in a single call — e.g. "
             "'[{\"name\": \"A\"}, {\"name\": \"B\"}]'. Prefer batching over "
             "one create call per record.",
    )

    p = sub.add_parser("write", help="Update records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")
    p.add_argument("--values", required=True, help="JSON object of field values.")

    p = sub.add_parser("unlink", help="Delete records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")

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

    p = sub.add_parser("models", help="List models (introspection).")
    p.add_argument("--filter", help="Substring to filter the technical name.")

    p = sub.add_parser("fields", help="Describe a model's fields (introspection).")
    p.add_argument("model")

    p = sub.add_parser(
        "install-modules",
        help="Install modules by name and confirm, in one blocking call.",
    )
    p.add_argument("modules", nargs="+", help="Technical module names, e.g. crm stock.")

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
    "set-image": cmd_set_image,
    "import-preview": cmd_import_preview,
    "import-csv": cmd_import_csv,
}


def main():
    args = build_parser().parse_args()
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
