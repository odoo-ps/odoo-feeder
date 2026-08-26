---
name: odoo-demo-accounting
description: >
  Post the invoices and vendor bills an odoo-demo-csv import (and the trading
  / mrp workflows) left in draft, so P&L, balance sheet and cashflow reports
  fill in. Use only when the 'accounting' workflow was selected for this demo.
---

# Accounting workflow

Runs last, after every other workflow that creates invoices or bills
(`trading`'s `invoice-so`, any vendor bills from `mrp`'s purchase orders).
Draft entries don't appear in a single report; posted ones do.

## The tool

`account` must be installed. `odoo-crud-accounting post --ids <ids>` —
installed alongside `odoo-crud`, only for this workflow.
`odoo-crud-accounting post --help` is the flag reference.

`post` posts a batch of `account.move` records (invoices and bills share the
model, distinguished by `move_type`) and isolates failures per record: one
unbalanced or partner-less entry does not block the rest of the batch. Read
the `failed` list in the result — a demo entry that can't post usually means
a required field (partner, journal) was never set when it was created.

## Run

1. `odoo-crud search-read account.move --domain '[["state","=","draft"]]' --fields '["id","name","move_type"]'`
   to find everything waiting.
2. `odoo-crud-accounting post --ids [...]` with all of them.
3. For anything in `failed`, read the error, fix the underlying record with
   `odoo-crud write`, and re-run `post` on just that id.
4. Verify: `odoo-crud search-read account.move --domain '[["state","=","posted"]]'`
   should now include every id you targeted.

*Done when* `failed` is empty (or every failure has been fixed and re-posted)
and the posted count matches what step 1 found.
