#!/usr/bin/env python3
"""Odoo Demo Feeder — accounting workflow tool.

Installed as `odoo-crud-accounting`, only when the 'accounting' workflow is
selected (see odoo-demo-feeder and the odoo-demo-accounting skill). Reuses
odoo_crud_lib for the connection; odoo-crud itself never imports this.

Every command prints a single JSON object to stdout, same envelope as
odoo-crud: {"ok": true, "result": ...} / {"ok": false, "error"/"result": ...}.
"""

import argparse

from odoo_crud_lib import OdooError, add_context_arg, apply_context_arg, execute, ok


def cmd_post(args):
    """Post account.move records one at a time, not in a single batch call.

    account.move.action_post() on a list of ids is all-or-nothing: one move
    that fails validation (an unbalanced entry, a missing partner on a
    customer invoice) rolls back the whole batch, and the RPC error names only
    the first failure — leaving every other move unposted with no indication
    that they, individually, were fine. Looping isolates each id.
    """
    posted, failed = [], []
    for record_id in args.ids:
        try:
            execute("account.move", "action_post", [[record_id]])
            posted.append(record_id)
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"posted": posted, "failed": failed})


def build_parser():
    parser = argparse.ArgumentParser(
        prog="odoo_crud_accounting.py",
        description="Accounting workflow tool for the Odoo Demo Feeder — "
                     "bulk-posts invoices/bills with per-record error isolation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "post",
        help="Post a batch of account.move records (invoices/bills), "
             "isolating failures per record instead of failing the whole batch.",
    )
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the account.move records to post.")
    add_context_arg(p)

    return parser


HANDLERS = {"post": cmd_post}


def main():
    args = build_parser().parse_args()
    apply_context_arg(args)
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
