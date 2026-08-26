#!/usr/bin/env python3
"""Odoo Demo Feeder — analytics workflow tool.

Installed as `odoo-crud-analytics`, only when the 'analytics' workflow is
selected (see odoo-demo-feeder and the odoo-demo-analytics skill). Reuses
odoo_crud_lib for the connection; odoo-crud itself never imports this.

Every command prints a single JSON object to stdout, same envelope as
odoo-crud: {"ok": true, "result": ...} / {"ok": false, "error"/"result": ...}.
"""

import argparse
import datetime

from odoo_crud_lib import OdooError, add_context_arg, apply_context_arg, execute, fail, ok


def _parse_date(value, what):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        fail(f"{what} must be an ISO date (YYYY-MM-DD), got '{value}'.")


def cmd_spread_dates(args):
    """Write an even, deterministic spread of dates across a range, one write
    per record.

    Trend charts need orders/invoices dated across the window, not clustered
    on the day the demo was built. Computing N evenly-spaced (with a small
    fixed jitter so the chart doesn't look like a ruler) dates by hand, then
    issuing one write per record, is exactly the kind of client-side
    arithmetic this tool exists to do instead of asking the agent to.
    """
    start = _parse_date(args.start, "--start")
    end = _parse_date(args.end, "--end")
    if end < start:
        fail("--end must not be before --start.")
    span_days = (end - start).days
    ids = args.ids
    count = len(ids)

    written, failed = [], []
    for index, record_id in enumerate(ids):
        # Evenly spaced across the window (index/count fraction of the span),
        # plus a small deterministic jitter derived from the record id itself
        # so re-running with the same ids reproduces the same dates.
        fraction = index / count if count > 1 else 0.5
        jitter_days = (record_id % 5) - 2  # -2..+2, deterministic per id
        offset = max(0, min(span_days, round(fraction * span_days) + jitter_days))
        date_value = start + datetime.timedelta(days=offset)
        field_value = date_value.isoformat()
        if args.datetime:
            field_value += " 12:00:00"
        try:
            execute(args.model, "write", [[record_id], {args.field: field_value}])
            written.append({"id": record_id, args.field: field_value})
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"model": args.model, "field": args.field, "written": written, "failed": failed})


def build_parser():
    parser = argparse.ArgumentParser(
        prog="odoo_crud_analytics.py",
        description="Analytics workflow tool for the Odoo Demo Feeder — "
                     "spreads a date field across a rolling window over a "
                     "batch of records, so trend charts show a line instead "
                     "of a single spike.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "spread-dates",
        help="Write an even, deterministic spread of dates across a date "
             "range, one per record.",
    )
    p.add_argument("model", help="e.g. sale.order, account.move, crm.lead")
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the records to date.")
    p.add_argument("--field", required=True,
                    help="The date/datetime field to write, e.g. date_order, "
                         "invoice_date.")
    p.add_argument("--start", required=True, help="ISO date, e.g. 2026-05-01")
    p.add_argument("--end", required=True, help="ISO date, e.g. 2026-08-01")
    p.add_argument(
        "--datetime", action="store_true",
        help="Write a datetime value (date + ' 12:00:00') instead of a bare "
             "date — use for datetime fields like date_order; check "
             "'odoo-crud fields <model> --filter <field>' first if unsure.",
    )
    add_context_arg(p)

    return parser


HANDLERS = {"spread-dates": cmd_spread_dates}


def main():
    args = build_parser().parse_args()
    apply_context_arg(args)
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
