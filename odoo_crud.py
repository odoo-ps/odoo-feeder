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
    uid, models, url, db, login, secret, _version = connect()
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


def cmd_search_read(args):
    domain = parse_json(args.domain, "--domain") or []
    fields = parse_json(args.fields, "--fields")
    kwargs = {}
    if fields:
        kwargs["fields"] = fields
    if args.limit:
        kwargs["limit"] = args.limit
    ok(execute(args.model, "search_read", [domain], kwargs))


def cmd_create(args):
    values = parse_json(args.values, "--values")
    if values is None:
        fail("--values is required (a JSON object).")
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


def _create_import(model, headers, body):
    """Create a base_import.import record and return (import_id, fields)."""
    import_id = execute(
        "base_import.import", "create", [{"res_model": model}]
    )
    return import_id, headers, body


def _import_options():
    return {
        "headers": True,
        "quoting": '"',
        "separator": ",",
        "date_format": "%Y-%m-%d",
        "datetime_format": "%Y-%m-%d %H:%M:%S",
        "float_thousand_separator": ",",
        "float_decimal_separator": ".",
        "encoding": "utf-8",
    }


def cmd_import_preview(args):
    headers, _body = _read_csv(args.file)
    import_id, headers, _body = _create_import(args.model, headers, _body)
    preview = execute(
        "base_import.import",
        "parse_preview",
        [import_id, _import_options()],
    )
    ok({"import_id": import_id, "csv_headers": headers, "preview": preview})


def cmd_import_csv(args):
    headers, body = _read_csv(args.file)
    import_id, headers, body = _create_import(args.model, headers, body)
    preview = execute(
        "base_import.import", "parse_preview", [import_id, _import_options()]
    )
    if isinstance(preview, dict) and preview.get("error"):
        fail(f"Import preview failed: {preview['error']}")

    # Map each CSV column to a field. The agent should pass --fields to override
    # auto-matching; otherwise we fall back to parse_preview's matches.
    fields = parse_json(args.fields, "--fields")
    if not fields:
        matches = preview.get("matches", {}) if isinstance(preview, dict) else {}
        fields = []
        for index in range(len(headers)):
            match = matches.get(str(index)) or matches.get(index)
            fields.append(match[0] if match else False)

    result = execute(
        "base_import.import",
        "execute_import",
        [import_id, fields, headers, _import_options()],
    )
    messages = result.get("messages", []) if isinstance(result, dict) else result
    if messages:
        ok({"status": "completed_with_messages", "messages": messages,
            "fields_used": fields})
    ok({"status": "imported", "ids": result.get("ids") if isinstance(result, dict)
        else result, "fields_used": fields})


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

    p = sub.add_parser("create", help="Create a record.")
    p.add_argument("model")
    p.add_argument("--values", required=True, help="JSON object of field values.")

    p = sub.add_parser("write", help="Update records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")
    p.add_argument("--values", required=True, help="JSON object of field values.")

    p = sub.add_parser("unlink", help="Delete records.")
    p.add_argument("model")
    p.add_argument("--ids", required=True, help="JSON list of ids.")

    p = sub.add_parser("call", help="Call an arbitrary model method.")
    p.add_argument("model")
    p.add_argument("method")
    p.add_argument("--args", help="JSON list of positional args.")
    p.add_argument("--kwargs", help="JSON object of keyword args.")

    p = sub.add_parser("models", help="List models (introspection).")
    p.add_argument("--filter", help="Substring to filter the technical name.")

    p = sub.add_parser("fields", help="Describe a model's fields (introspection).")
    p.add_argument("model")

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
    "import-preview": cmd_import_preview,
    "import-csv": cmd_import_csv,
}


def main():
    args = build_parser().parse_args()
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
