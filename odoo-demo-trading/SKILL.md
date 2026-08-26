---
name: odoo-demo-trading
description: >
  Build the sales & purchasing flow on top of an odoo-demo-csv import: a
  confirmed sale order that raises the purchase order to the vendor, with the
  customer invoice and vendor bill created and linked back. Use only when the
  'trading' workflow was selected for this demo.
---

# Trading workflow

Runs after `odoo-demo-csv` has imported partners, products and stock. Its
`res.partner` and `product.template` external ids are what you pick orders
from here — reread that skill's records with `search-read` rather than
re-importing them.

## The tool

`odoo-crud-trading <command> [options]` — installed alongside `odoo-crud`,
only for this workflow. `odoo-crud-trading <command> --help` is the flag
reference.

- **`confirm-so --ids <ids>`** — confirms sale orders and reports, per order,
  the purchase orders, manufacturing orders and deliveries Odoo generated for
  it. Confirming is what triggers the buy/manufacture route (if the ordered
  products are set up for it — see the Run section below), so read the report
  to know which orders actually raised something rather than assuming every
  one did. An order whose products carry a route but that raised neither a PO
  nor an MO comes back with `no_replenishment: true` — that's the setup being
  wrong, not the order being an exception; re-check it rather than creating
  the PO/MO by hand.
- **`invoice-so --ids <ids>`** — creates the customer invoice for confirmed
  sale orders.
- **`create-bill --ids <ids>`** — creates the vendor bill for confirmed
  purchase orders. Validates any pending receipt first, so the bill's lines
  carry the real ordered quantity instead of zero, and backfills a line still
  at `price_unit: 0` from `product.supplierinfo` before invoicing.

All three isolate failures per record: one bad order in the batch does not
stop the rest from confirming/invoicing/billing. Still use plain `odoo-crud`
for everything else (picking order lines, reading back state, posting).

## Run

1. Pick 2–5 confirmed-worthy sale orders — `search-read sale.order` for
   `state = 'draft'` orders imported by the base run (or create a few first if
   none exist, with lines against real products). Each order's products need
   a vendor (`product.supplierinfo`) and the MTO route to actually raise a PO
   on confirm — see step 2 and [`ODOO-TRAPS.md`](../odoo-demo-csv/ODOO-TRAPS.md#confirming-a-sale-order-doesnt-raise-a-purchase-or-manufacturing-order)
   for why it's MTO and not a "Buy" checkbox.
2. Activate the MTO route once, then set it on the products you picked:
   ```
   odoo-crud search-read stock.route --domain '[["name","like","Replenish on Order"]]' --context '{"active_test": false}'
   odoo-crud write stock.route --ids '[<mto id>]' --values '{"active": true}'
   odoo-crud write product.template --ids '[...]' --values '{"route_ids": [[6, 0, [<mto id>]]]}'
   ```
3. `odoo-crud-trading confirm-so --ids [...]`. Read the result: orders whose
   products carry the MTO route and a vendor will list a `purchase_orders`
   entry — those are the ones actually demonstrating "SO raises the PO". Any
   order flagged `no_replenishment` had a routed product but raised nothing;
   re-check step 2 for it rather than inventing a PO by hand.
4. For orders that did raise a purchase order, confirm the vendor side too:
   `odoo-crud call purchase.order button_confirm --args '[[<po_id>]]'`.
5. `odoo-crud-trading invoice-so --ids [...]` on the confirmed sale orders.
6. `odoo-crud-trading create-bill --ids [...]` on the purchase orders step 4
   just confirmed, to raise the matching vendor bill(s).
7. If the `accounting` workflow is also selected, hand the resulting invoice
   and vendor bill ids to `odoo-crud-accounting post` — this skill only
   creates them in draft.

*Done when* every targeted sale order is confirmed, its report has been read
(not assumed), its customer invoice exists, and every purchase order it
raised has its vendor bill.
