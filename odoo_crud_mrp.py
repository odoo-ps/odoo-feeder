#!/usr/bin/env python3
"""Odoo Demo Feeder — manufacturing (mrp) workflow tool.

Installed as `odoo-crud-mrp`, only when the 'mrp' workflow is selected (see
odoo-demo-feeder and the odoo-demo-mrp skill). Reuses odoo_crud_lib for the
connection; odoo-crud itself never imports this.

Every command prints a single JSON object to stdout, same envelope as
odoo-crud: {"ok": true, "result": ...} / {"ok": false, "error"/"result": ...}.
"""

import argparse
import json

from odoo_crud_lib import OdooError, add_context_arg, apply_context_arg, execute, fail, ok


def cmd_create_bom(args):
    """Create a mrp.bom with its component lines in one call.

    A BoM's lines are a one2many (bom_line_ids), which the ORM only accepts as
    a list of (0, 0, values) "create" command tuples nested inside the create()
    call — not as separate mrp.bom.line records pointed back at the BoM by id.
    Getting that tuple shape right (and remembering the leading 0, 0 pair) is
    exactly the kind of Odoo-specific trap this tool exists to hide.
    """
    lines = [(0, 0, component) for component in args.components]
    values = {
        "product_tmpl_id": args.product_template_id,
        "product_qty": args.quantity,
        "bom_line_ids": lines,
    }
    if args.product_id:
        values["product_id"] = args.product_id
    bom_id = execute("mrp.bom", "create", [[values]])
    ok({"bom_id": bom_id[0] if isinstance(bom_id, list) else bom_id})


def cmd_confirm(args):
    """Confirm mrp.production records one at a time.

    Same reasoning as odoo-crud-accounting's 'post': a batch action_confirm
    call is all-or-nothing, so one manufacturing order missing a component
    with enough stock rolls back the whole list. Looping isolates each id.
    """
    confirmed, failed = [], []
    for record_id in args.ids:
        try:
            execute("mrp.production", "action_confirm", [[record_id]])
            confirmed.append(record_id)
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"confirmed": confirmed, "failed": failed})


def build_parser():
    parser = argparse.ArgumentParser(
        prog="odoo_crud_mrp.py",
        description="Manufacturing workflow tool for the Odoo Demo Feeder — "
                     "creates BoMs with their component lines in one call, and "
                     "bulk-confirms manufacturing orders with per-record error "
                     "isolation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "create-bom",
        help="Create a mrp.bom for a product template, with its component "
             "lines, in a single call.",
    )
    p.add_argument("--product-template-id", type=int, required=True,
                    help="Database id of the product.template the BoM is for.")
    p.add_argument("--product-id", type=int,
                    help="Database id of the specific product.product variant, "
                         "if the BoM is variant-specific. Omit for a "
                         "template-level BoM shared by every variant.")
    p.add_argument("--quantity", type=float, default=1.0,
                    help="Quantity of the finished product this BoM produces "
                         "(default 1).")
    p.add_argument(
        "--components", required=True, type=str,
        help="JSON array of component lines, e.g. "
             "'[{\"product_id\": 12, \"product_qty\": 2}, "
             "{\"product_id\": 13, \"product_qty\": 1}]'. Each product_id is a "
             "product.product database id (a component is always a variant, "
             "never a template).",
    )
    add_context_arg(p)

    p = sub.add_parser(
        "confirm",
        help="Confirm a batch of mrp.production records, isolating failures "
             "per record instead of failing the whole batch.",
    )
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the mrp.production records to confirm.")
    add_context_arg(p)

    return parser


HANDLERS = {"create-bom": cmd_create_bom, "confirm": cmd_confirm}


def main():
    args = build_parser().parse_args()
    apply_context_arg(args)
    if args.command == "create-bom":
        try:
            args.components = json.loads(args.components)
        except json.JSONDecodeError as exc:
            fail(f"Invalid JSON for --components: {exc}")
        if not isinstance(args.components, list) or not args.components:
            fail("--components must be a non-empty JSON array of objects.")
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
