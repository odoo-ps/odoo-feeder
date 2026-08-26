---
name: odoo-demo-mrp
description: >
  Build the manufacturing flow on top of an odoo-demo-csv import: bills of
  materials, and a confirmed sale order that triggers a manufacturing order
  plus the purchase order for its components. Use only when the 'mrp'
  workflow was selected for this demo.
---

# Manufacturing workflow

Runs after `odoo-demo-csv` has imported products and stock. A finished good
needs component products to build a BoM from — reuse the ones already
imported (raw materials, packaging) rather than inventing new ones unless the
catalogue is genuinely too thin.

## The tool

`mrp stock` must be installed (`odoo-crud install-modules mrp stock ...`)
before any of this. `odoo-crud-mrp <command> [options]` — installed alongside
`odoo-crud`, only for this workflow. `odoo-crud-mrp <command> --help` is the
flag reference.

- **`create-bom --product-template-id <id> --components <json>`** — creates a
  `mrp.bom` with its component lines in one call. A BoM's lines are a
  one2many the ORM only accepts as nested create-command tuples inside the
  same call; this hides that shape so you never have to reproduce it by hand.
- **`confirm --ids <ids>`** — confirms manufacturing orders, isolating
  failures per record (one MO short on stock does not block the rest).

## Run

1. Pick 1–3 storable finished products from the base import to be BoMs for.
   Pick 2–4 other storable products as their components (real ingredients or
   parts if the site named any; otherwise plausible ones for the industry).
2. `odoo-crud search-read product.product` to get the *variant* ids (not
   template ids) for every component — `create-bom`'s `--components` needs
   `product.product` ids, a BoM component is always a variant.
3. `odoo-crud-mrp create-bom --product-template-id <id> --components '[...]'`
   for each finished product.
4. Confirm stock on hand for the components exists (the base import's stock
   pass should already cover them) — a manufacturing order for a component
   with zero stock fails to confirm.
5. The finished good needs the MTO route to actually trigger a
   `mrp.production` on confirm — not a "Manufacture" checkbox, see
   [`ODOO-TRAPS.md`](../odoo-demo-csv/ODOO-TRAPS.md#confirming-a-sale-order-doesnt-raise-a-purchase-or-manufacturing-order)
   for why. Activate it once, then set it on the finished product(s):
   ```
   odoo-crud search-read stock.route --domain '[["name","like","Replenish on Order"]]' --context '{"active_test": false}'
   odoo-crud write stock.route --ids '[<mto id>]' --values '{"active": true}'
   odoo-crud write product.template --ids '[<finished good id>]' --values '{"route_ids": [[6, 0, [<mto id>]]]}'
   ```
6. Pick a confirmed sale order (from the `trading` workflow if selected, or
   confirm one here) whose product is one of the BoM'd finished goods.
   Confirming it should create a `mrp.production` — check with
   `odoo-crud search-read mrp.production --domain '[["origin","=","<so name>"]]'`.
   If none appears, re-check step 5 rather than creating the MO by hand.
7. `odoo-crud-mrp confirm --ids [...]` on the resulting manufacturing orders.

*Done when* every targeted finished product has a BoM, every targeted MO is
confirmed, and a `search-read mrp.production` shows the state you expect.
