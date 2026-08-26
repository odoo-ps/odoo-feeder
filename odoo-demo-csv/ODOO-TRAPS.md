# Odoo traps

Odoo behaviours that make a correct-looking command do the wrong thing, indexed
by the symptom you are staring at. The run itself is in [`SKILL.md`](SKILL.md).

## A record you know exists comes back "not found"

It is archived, not absent. Most currencies ship inactive, so `search-read
res.currency` shows only the few already in use. Add the context to see them:

```
odoo-crud search-read res.currency --domain '[["name","=","CHF"]]' --context '{"active_test": false}'
odoo-crud write res.currency --ids '[<id>]' --values '{"active": true}'
```

Activate it *before* setting it on `res.company`, or the write is rejected.
`--context` rides on any command.

## An import rejects a column

```
odoo-crud import-preview <model> --file <path>
```

Preview commits nothing and names the columns that map to no field, each with a
near-miss hint. Confirm the real name with `odoo-crud fields <model> --filter
'<guess>'`, fix the CSV, re-import — external ids make the retry idempotent.

## An import errors "No matching record found for external id/name"

`field_id/id` only works for a `many2one` pointing at a record *this run's
own CSVs* created (`crm.lead`'s `partner_id/id` → a `res.partner` row's `id`
column). Point it at anything else — a category, a country, a stage, a UoM —
and the import fails outright, since no external id was ever created for it:
`No matching record found for external id '<value>' in field '<Field>'`.

The importer resolves those other `many2one` columns by the target's
**display name** instead — a plain column (no `/id`) holding the name, not an
id: `product.template`'s `categ_id` column holds `Goods`, `crm.lead`'s
`stage_id` column holds `New`. Get the spelling wrong there and the error
looks almost the same (`No matching record found for name '<value>' in field
'<Field>'`) but names the real fix: `odoo-crud search-read <target model>
--fields '["id","name"]'` to copy the exact text.

## An import rejects a value

Selection fields accept their technical values only, and those move between
versions. `odoo-crud fields <model> --filter <field>` prints them
(`selection = consu|service|combo`); copy one verbatim rather than translate it.

## An import complains about a missing required field

The field has no default, so Odoo cannot fill it for you: add the column to the
CSV. `odoo-crud fields <model>` marks every `required` field, so a probe of the
columns you intend to write catches this before the import does.

## On-hand quantity reads zero after a green import — or the import won't run at all

Stock is written as a **second import over `product.template`**, repeating
every column file 2 needed as `required` plus `qty_available` (SKILL.md step
5). Four near-misses either report success and leave the warehouse empty, or
refuse to run:

- **Dropping the first pass's required columns.** "It's just an update, the
  record already has a name" is wrong: `import-csv` re-validates every
  `required` field on each row, existing record or not, so a second pass
  carrying only `id` + `qty_available` fails outright ("missing required
  field(s): invoice_policy, name") — nothing gets imported, not even the
  quantity. Repeat `name`, `invoice_policy`, and anything else file 2 needed;
  only the optional columns are safe to trim.
- **A `stock.quant` CSV.** Its `product_id` points at product *variants*, so a
  `product_id/id` holding a `product.template` external id is rejected outright
  ("Invalid external ID: expected model 'product.product'") — and matching
  variants by name instead throws away the external-id rule.
- **`stock.quant.inventory_quantity`.** That is a *counted* quantity awaiting
  application; importing it leaves on-hand at zero, and reads as a clean import
  right up until someone opens the warehouse.
- **`qty_available` inside the create CSV.** At create time the variant does not
  exist yet, so the write fails.

Verify with `qty_available`. `inventory_quantity` proves nothing.

## A write through `call` misbehaves

Use the dedicated `write` command — `odoo-crud write <model> --ids '[…]'
--values '{…}'`. Reaching the same method through `call` needs the whole
positional list nested into one array (`--args '[[ids], {values}]'`), which is
easy to get subtly wrong. Keep `call` for methods that have no dedicated
command, and read `odoo-crud call --help` before using it.

## Confirming a sale order doesn't raise a purchase or manufacturing order

`write product.template --values '{"route_ids": [...]}'` with the Buy or
Manufacture route's id returns success and then reads back as if nothing
happened — `route_ids` comes back empty (same for `product.category.route_ids`
with those two routes). This isn't a bug in the write, it's what these two
routes are: `stock.route`'s `product_selectable` (and
`product_categ_selectable`) is `False` on Buy and Manufacture out of the box,
and that flag isn't just a UI hint — every read of `route_ids` filters the
linked routes through it, so a route with the flag off can never appear on a
product no matter how it got linked there.

The route that *is* product-selectable (and sale-order-line-selectable) by
design is `Replenish on Order (MTO)` — but it ships `active: False`. Activate
it once, then set it (alone, not alongside Buy/Manufacture) on the finished
products:

```
odoo-crud search-read stock.route --domain '[["name","like","Replenish on Order"]]' --context '{"active_test": false}'
odoo-crud write stock.route --ids '[<mto id>]' --values '{"active": true}'
odoo-crud write product.template --ids '[...]' --values '{"route_ids": [[6, 0, [<mto id>]]]}'
```

MTO alone is enough: confirming the sale order then finds no route on the
product for the outgoing delivery, falls back to the warehouse's own routes
for the missing leg, and the warehouse already carries Buy and Manufacture
(from `buy_to_resupply`/`manufacture_to_resupply` on `stock.warehouse`) — so
the PO or MO comes out of that fallback, not from anything set on the
product. Needs a real vendor (`product.supplierinfo`) for the Buy case, or a
`mrp.bom` for the Manufacture case, same as without MTO.

## A model or a field simply is not there

Its module is not installed. Install everything you need in one call, then probe
again:

```
odoo-crud install-modules crm stock sale_management purchase account
odoo-crud models --filter crm
```

`purchase` belongs in that base list even when no purchasing workflow was
asked for: confirming a sale order on an MTO/buy route raises a
`purchase.order`, and skipping the module doesn't just skip the PO, it fails
the confirm itself ("purchase.order doesn't exist" or "No rule found to
replenish"). Add to the list, don't replace it, for whatever workflow is
running: `purchase_stock` once a warehouse is involved (trading), `mrp` for
the manufacturing flow.
