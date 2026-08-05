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
CSV. `odoo-crud fields <model>` marks every `required` field, so a probe of the
columns you intend to write catches this before the import does.

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
