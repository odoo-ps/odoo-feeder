#!/usr/bin/env python3
"""Odoo Demo Feeder — sales & purchasing (trading) workflow tool.

Installed as `odoo-crud-trading`, only when the 'trading' workflow is selected
(see odoo-demo-feeder and the odoo-demo-trading skill). Reuses odoo_crud_lib
for the connection; odoo-crud itself never imports this.

Every command prints a single JSON object to stdout, same envelope as
odoo-crud: {"ok": true, "result": ...} / {"ok": false, "error"/"result": ...}.
"""

import argparse

from odoo_crud_lib import OdooError, add_context_arg, apply_context_arg, execute, ok


def cmd_confirm_so(args):
    """Confirm sale orders, then report whatever each confirmation generated.

    Confirming a sale.order can, depending on the routes configured on its
    products, generate a purchase.order (buy route) and/or a mrp.production
    (manufacture route), plus a stock.picking (delivery) either way. Finding
    those afterwards would otherwise cost the agent a search-read per order
    per generated document; this does it in the same call, keyed by the
    order's own name (Odoo links generated documents back to it via
    'origin').

    An order whose lines carry no route at all was never going to raise
    anything — that's a normal, plain delivery. But an order that *does* have
    a routed line and still comes back with neither a purchase_orders nor a
    manufacturing_orders entry means the route/vendor/BoM setup is wrong, not
    that this order was supposed to be silent. Rather than making the agent
    notice that on its own, such an order gets a `no_replenishment: true`
    flag so it's immediately visible in the result — the fix is to re-check
    that setup (see ODOO-TRAPS.md), never to invent the PO/MO by hand.
    """
    confirmed, failed = [], []
    for record_id in args.ids:
        try:
            order = execute(
                "sale.order", "read", [[record_id]], {"fields": ["name"]}
            )[0]
            execute("sale.order", "action_confirm", [[record_id]])
            name = order["name"]
            purchase_orders = execute(
                "purchase.order", "search_read",
                [[["origin", "=", name]]], {"fields": ["id", "name", "state"]},
            )
            manufacturing_orders = execute(
                "mrp.production", "search_read",
                [[["origin", "=", name]]], {"fields": ["id", "name", "state"]},
            )
            pickings = execute(
                "stock.picking", "search_read",
                [[["origin", "=", name]]], {"fields": ["id", "name", "state"]},
            )
            has_routed_line = execute(
                "sale.order.line", "search_count",
                [[["order_id", "=", record_id],
                  ["product_id.product_tmpl_id.route_ids", "!=", False]]],
            )
            result = {
                "id": record_id, "name": name,
                "purchase_orders": purchase_orders,
                "manufacturing_orders": manufacturing_orders,
                "pickings": pickings,
            }
            if has_routed_line and not purchase_orders and not manufacturing_orders:
                result["no_replenishment"] = True
            confirmed.append(result)
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"confirmed": confirmed, "failed": failed})


def cmd_invoice_so(args):
    """Create the customer invoice(s) for already-confirmed sale orders.

    The "Create Invoice" button on a sale.order does not call
    sale.order._create_invoices() directly — private methods can't be called
    over RPC anyway — it opens the sale.advance.payment.inv wizard, which is
    what actually calls it server-side. This creates that wizard with
    advance_payment_method='delivered' (a full, regular invoice, not a down
    payment) and calls its public create_invoices(), one order at a time so a
    bad order doesn't stop the rest. The wizard doesn't hand back the invoice
    ids it created, so they're read off the order's own invoice_ids before
    and after.

    create_invoices() itself returns an ir.actions.act_window dict (to open
    the new invoice in the UI), and on some servers that dict's XML-RPC
    marshalling fails on a None field inside it — after the invoice has
    already been created. That specific failure is swallowed here; any other
    error still fails the order.
    """
    invoiced, failed = [], []
    for record_id in args.ids:
        try:
            before = set(execute(
                "sale.order", "read", [[record_id]], {"fields": ["invoice_ids"]}
            )[0]["invoice_ids"])
            wizard_id = execute("sale.advance.payment.inv", "create", [[{
                "sale_order_ids": [(6, 0, [record_id])],
                "advance_payment_method": "delivered",
                "consolidated_billing": False,
            }]])[0]
            try:
                execute("sale.advance.payment.inv", "create_invoices", [[wizard_id]])
            except OdooError as exc:
                if "cannot marshal None" not in str(exc):
                    raise
            after = execute(
                "sale.order", "read", [[record_id]], {"fields": ["invoice_ids"]}
            )[0]["invoice_ids"]
            invoiced.append({
                "id": record_id,
                "invoice_ids": [i for i in after if i not in before],
            })
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"invoiced": invoiced, "failed": failed})


def cmd_create_bill(args):
    """Create the vendor bill(s) for confirmed purchase orders.

    action_create_invoice() bills whatever quantity the PO line is set to
    invoice on: for a product whose purchase_method is 'receive' (the
    default), that's qty_received, not the quantity ordered — so calling it
    before the incoming receipt is validated raises a bill with every line at
    quantity 0, even though price_unit is fine. This validates any of the
    order's incoming pickings still short of 'done' first, so qty_received
    catches up to what was ordered.

    A line can also come out at price_unit 0 for an unrelated reason: a
    purchase.order.line created directly (not through the procurement engine,
    which looks up the vendor's price itself) never had product.supplierinfo
    applied to it the way the "Create Invoice" button's own onchange would.
    Any such line still at 0 gets backfilled from supplierinfo, matched on
    the line's product and the order's vendor, before the bill is raised.

    Like invoice-so, action_create_invoice() returns an ir.actions.act_window
    dict rather than the bill's id, so the created ids are read off the
    order's own invoice_ids before and after.
    """
    created, failed = [], []
    for record_id in args.ids:
        try:
            order = execute(
                "purchase.order", "read", [[record_id]],
                {"fields": ["name", "state", "partner_id", "invoice_ids"]},
            )[0]
            if order["state"] not in ("purchase", "done"):
                raise OdooError(
                    f"purchase.order {record_id} is '{order['state']}', not "
                    "confirmed — button_confirm it before creating its bill."
                )
            before = set(order["invoice_ids"])

            pending_pickings = execute(
                "stock.picking", "search",
                [[["origin", "=", order["name"]],
                  ["state", "not in", ["done", "cancel"]]]],
            )
            if pending_pickings:
                execute("stock.picking", "button_validate", [pending_pickings])

            zero_lines = execute(
                "purchase.order.line", "search_read",
                [[["order_id", "=", record_id],
                  ["price_unit", "=", 0], ["product_id", "!=", False]]],
                {"fields": ["id", "product_id"]},
            )
            for line in zero_lines:
                product_tmpl_id = execute(
                    "product.product", "read", [[line["product_id"][0]]],
                    {"fields": ["product_tmpl_id"]},
                )[0]["product_tmpl_id"][0]
                supplierinfo = execute(
                    "product.supplierinfo", "search_read",
                    [[["product_tmpl_id", "=", product_tmpl_id],
                      ["partner_id", "=", order["partner_id"][0]]]],
                    {"fields": ["price"], "limit": 1, "order": "sequence"},
                )
                if supplierinfo and supplierinfo[0]["price"]:
                    execute(
                        "purchase.order.line", "write",
                        [[line["id"]], {"price_unit": supplierinfo[0]["price"]}],
                    )

            execute("purchase.order", "action_create_invoice", [[record_id]])
            after = execute(
                "purchase.order", "read", [[record_id]], {"fields": ["invoice_ids"]}
            )[0]["invoice_ids"]
            created.append({
                "id": record_id,
                "invoice_ids": [i for i in after if i not in before],
            })
        except OdooError as exc:
            failed.append({"id": record_id, "error": str(exc)})
    ok({"created": created, "failed": failed})


def build_parser():
    parser = argparse.ArgumentParser(
        prog="odoo_crud_trading.py",
        description="Sales & purchasing workflow tool for the Odoo Demo "
                     "Feeder — confirms sale orders and reports the purchase "
                     "orders/manufacturing orders/deliveries they generated, "
                     "creates customer invoices from confirmed sale orders, "
                     "and creates vendor bills from confirmed purchase orders.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "confirm-so",
        help="Confirm a batch of sale orders, reporting the purchase orders, "
             "manufacturing orders and deliveries each one generated, and "
             "flagging (no_replenishment) any order whose products carry a "
             "route but raised neither a PO nor an MO. Isolates failures per "
             "order.",
    )
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the sale.order records to confirm.")
    add_context_arg(p)

    p = sub.add_parser(
        "invoice-so",
        help="Create the customer invoice for a batch of confirmed sale "
             "orders. Isolates failures per order.",
    )
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the sale.order records to invoice.")
    add_context_arg(p)

    p = sub.add_parser(
        "create-bill",
        help="Create the vendor bill for a batch of confirmed purchase "
             "orders, validating any pending receipt first so quantities "
             "aren't billed as zero. Isolates failures per order.",
    )
    p.add_argument("--ids", required=True, type=int, nargs="+",
                    help="Database ids of the purchase.order records to bill.")
    add_context_arg(p)

    return parser


HANDLERS = {
    "confirm-so": cmd_confirm_so,
    "invoice-so": cmd_invoice_so,
    "create-bill": cmd_create_bill,
}


def main():
    args = build_parser().parse_args()
    apply_context_arg(args)
    HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
