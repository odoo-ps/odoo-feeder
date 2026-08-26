"""Shared XML-RPC plumbing for odoo_crud.py and the per-workflow tools
(odoo_crud_trading.py, odoo_crud_mrp.py, odoo_crud_accounting.py,
odoo_crud_analytics.py).

Every one of those tools is a separate, independently-installed executable
(see odoo-demo-feeder) so a workflow's own tool can be tweaked without
touching odoo_crud.py or any other workflow's tool. What they all still share
is: reading ODOO_URL/LOGIN/SECRET from the environment, authenticating once
and caching the uid across processes, retrying a stale cached uid, and
printing the {"ok": ...} JSON envelope. That plumbing lives here so it is
written, and fixed, exactly once.
"""

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

    Same shape as ok(), but ok=false and exit 1. Used where the failure has
    more to say than one error string.
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
    Shared across every workflow tool (not namespaced per-tool) since they all
    authenticate against the same database with the same credentials.
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
        # Written whole-then-renamed: two odoo-crud* processes can overlap, and
        # a half-written file would be read back as a corrupt cache.
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

    Memoized for the life of the process, and the uid is cached on disk
    between processes (see _session_path). Pass force=True to drop both caches
    and authenticate again (execute() does this if the kept-alive socket has
    gone stale or the server rejects the replayed uid).
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


def set_context(context):
    """Set the Odoo context every execute() call rides on for this process."""
    global _CONTEXT
    _CONTEXT = context or {}


class OdooError(Exception):
    """A call reached Odoo and Odoo (or the transport) reported a failure.

    Raised rather than printed, so a caller looping over many records (see the
    accounting/mrp/trading tools' per-record posting and confirming) can catch
    it and keep going instead of the whole process exiting on the first bad
    record.
    """


def execute(model, method, args=None, kwargs=None):
    """Call model.method over XML-RPC, or raise OdooError.

    Single-shot commands that should just fail the whole process on error
    should use execute_or_fail() instead — this one is for callers (loops)
    that need to catch the failure themselves.
    """
    kwargs = dict(kwargs or {})
    if _CONTEXT and "context" not in kwargs:
        kwargs["context"] = _CONTEXT

    # Two attempts: the connection is reused across calls, so its kept-alive
    # socket can go cold when the server reloads its registry (e.g. after
    # button_immediate_install). xmlrpc's own Transport already re-opens a
    # merely-dropped socket; this outer retry covers the case it does not — the
    # server still refusing when that immediate retry runs — by authenticating
    # again from scratch. An Odoo Fault is an application error, never a
    # connection problem, so it is reported as-is without a retry.
    for attempt in (0, 1):
        uid, models, _url, db, _login, secret, _version = connect(force=bool(attempt))
        try:
            return models.execute_kw(
                db, uid, secret, model, method, args or [], kwargs
            )
        except xmlrpc.client.Fault as fault:
            if attempt == 0 and _FROM_SESSION and _stale_uid(fault, uid):
                _forget_session()
                continue
            raise OdooError(f"Odoo error in {model}.{method}: {fault.faultString}") from fault
        except OdooError:
            raise
        except Exception as exc:  # noqa: BLE001
            if attempt == 0:
                continue
            raise OdooError(f"Call {model}.{method} failed: {exc}") from exc


def execute_or_fail(model, method, args=None, kwargs=None):
    """Like execute(), but prints the {"ok": false, ...} envelope and exits.

    What every single-shot command (one call, no per-record isolation needed)
    should use.
    """
    try:
        return execute(model, method, args=args, kwargs=kwargs)
    except OdooError as exc:
        fail(str(exc))


def parse_json(value, what):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON for {what}: {exc}")


def add_context_arg(parser):
    parser.add_argument(
        "--context",
        help="JSON object merged into the Odoo context for this call. Mainly "
             "'{\"active_test\": false}', which also returns archived records — "
             "most currencies ship inactive, so without it a perfectly real "
             "currency looks like it does not exist.",
    )


def apply_context_arg(args):
    """Read args.context (added by add_context_arg) and set it for execute()."""
    context = parse_json(getattr(args, "context", None), "--context")
    if context is not None:
        if not isinstance(context, dict):
            fail("--context must be a JSON object, e.g. '{\"inventory_mode\": true}'.")
        set_context(context)
