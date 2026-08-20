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

## An import rejects a value

Selection fields accept their technical values only, and those move between
versions. `odoo-crud fields <model> --filter <field>` prints them
(`selection = consu|service|combo`); copy one verbatim rather than translate it.

## An import complains about a missing required field

The field has no default, so Odoo cannot fill it for you: add the column to the
CSV.

Probing with `fields <model> --filter '<your columns>'` will not find it. That
filter only covers the columns you already meant to write, and this is a field
you did not know you needed — `name`, `uom_id`, `document_tax_mode` and
`invoice_policy` have all failed imports this way. Ask the file instead:

```
odoo-crud import-preview <model> --file <path>
```

`required_blocking` is what load() will refuse over. `required_defaulted` is
what Odoo will fill in, with the value it intends to use — read it rather than
trust it, since a default that exists is not always the one that lands.
`required_readonly` explains a failure no column can fix.

## On-hand quantity reads zero after a green import

Stock is written as a **second import over `product.template`** carrying `id` +
`qty_available` (SKILL.md step 5). Three near-misses all report success and
leave the warehouse empty:

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

## A model or a field simply is not there

Its module is not installed. Install everything you need in one call, then probe
again:

```
odoo-crud install-modules crm stock sale_management account
odoo-crud models --filter crm
```

## "Cannot modify readonly Date on a posted move"

A posted entry's date is locked, so `spread-dates account.move` fails on exactly
the records worth spreading. Unpost, spread, then post again — and clear `name`
in between, because posting checks the number against the date and refuses a
January number on a March entry (the error says so):

```
odoo-crud call account.move button_draft --args '[[<move_ids>]]'
odoo-crud spread-dates account.move --ids '[<move_ids>]' --fields '["invoice_date","date"]' --days 90
odoo-crud write account.move --ids '[<move_ids>]' --values '{"name": "/"}'
odoo-crud call account.move action_post --args '[[<move_ids>]]'
```

`"/"` is Odoo's own "not numbered yet" marker, so posting assigns a number that
matches the new date.

## An invoice policy change leaves nothing to invoice

Switching a product to *Ordered quantities* after its sale orders exist does not
make them invoiceable: `qty_to_invoice` stays `0` and `invoice_status` stays
`no`, so the invoice wizard produces nothing. This is deliberate — the stored
field does not depend on the product's policy, so that changing a policy cannot
rewrite the history of orders already taken.

`invoice_policy` on `sale.order.line` is computed and cannot be written either.

So set the policy **before** creating the orders — `fields product.template
--filter invoice_policy` during step 2, and write it with the products. Already
past it? Touch a field the stored quantity does depend on (`product_uom_qty`,
`qty_delivered`, `state`) to force the recompute, or delete the orders and
re-import them. Validating the delivery works too, and is what the policy is
asking for.

## `button_validate` returns a dict and the delivery is still not done

`action_done` does not exist over RPC — the real one is `_action_done`, private.
`button_validate` is the public entry point and it does exist, but it returns a
*wizard action* whenever a pre-validation hook fires: a backorder to confirm, a
quantity to check. Nothing is validated, the call still reports `ok: true`, and
the returned value is an `ir.actions.act_window` rather than `true`.

Answer the wizards through the context instead:

```
odoo-crud call stock.picking action_confirm --args '[[<picking_ids>]]'
odoo-crud call stock.picking action_assign  --args '[[<picking_ids>]]'
odoo-crud call stock.picking button_validate --args '[[<picking_ids>]]' \
  --context '{"skip_backorder": true, "skip_sanity_check": true, "picking_ids_not_to_backorder": [<picking_ids>]}'
```

Read the result: `true` means done, a dict means a wizard you have not answered.
Confirm with `search-read stock.picking --fields '["name","state"]'` — `done` is
the only state that moved any stock. Moves with no quantity fail the sanity
check, so write `quantity` on `stock.move` if `action_assign` reserved nothing.

## A route write returns green and the route is not there

Manufacture and Buy refuse to stick while MTO does, from a `route_ids` write
that reported `ok: true` — CSV, `write` or `call` alike. Nothing was dropped at
random: `product.template.route_ids` carries
`domain=[('product_selectable','=',True)]`, so a route with that flag off cannot
be attached, and the write is not refused for it. Odoo stores what it is allowed
to store and returns success. MTO survived because its flag was on.

`odoo-crud write` and `import-csv` now switch the flag on for the routes you are
assigning before assigning them, and report which ones under
`routes_made_selectable`, so this should not recur. To check or repair it
directly:

```
odoo-crud search-read stock.route --domain '[["name","in",["Manufacture","Buy","Replenish on Order"]]]' --fields '["name","product_selectable"]'
odoo-crud write stock.route --ids '[<manufacture_id>,<buy_id>]' --values '{"product_selectable": true}'
```

The flag defaults to `True`, so finding it off means something in the database
turned it off — worth a narrated line, not a mystery.

## A write reports success and the value did not change

`write` returns `true` when the call ran, not when it took effect. A field
filtered by its own domain, computed over, or readonly all look identical from
here: green call, unchanged record.

`odoo-crud write` reads the record back and compares, so this arrives as a
`warning` with `unchanged` listing the field, what you asked for and what is
stored. Believe the read, not the `true`. Values Odoo legitimately reshapes — a
many2one read back as `[id, label]`, a bare date read back with a time — are not
reported.
