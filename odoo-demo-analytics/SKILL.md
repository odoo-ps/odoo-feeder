---
name: odoo-demo-analytics
description: >
  Spread orders and invoices across a rolling 90-day window so trend charts
  show a line instead of a single spike. Use only when the 'analytics'
  workflow was selected for this demo.
---

# Analytics workflow

Runs last, after every record that should appear on a trend chart already
exists (sale orders, invoices, leads from `odoo-demo-csv` and any workflow
that added more). Dating them is the only step here — never create new
records just to date them.

## The tool

`odoo-crud-analytics spread-dates <model> --ids <ids> --field <field> --start
<date> --end <date>` — installed alongside `odoo-crud`, only for this
workflow. `odoo-crud-analytics spread-dates --help` is the flag reference.

It computes an even, deterministic spread of dates across the window and
writes one per record in a single call — the arithmetic this exists to avoid
doing by hand across dozens of records. Check
`odoo-crud fields <model> --filter <field>` first: pass `--datetime` for a
datetime field (e.g. `date_order`), omit it for a bare date field (e.g.
`invoice_date`) — writing the wrong shape either fails outright or silently
truncates.

## Run

1. Pick a 90-day window ending today (or the date the sales person implied).
2. For each model you populated that has a natural date — `sale.order`
   (`date_order`), `account.move` (`invoice_date`), `crm.lead`
   (`create_date` is not writable; use a custom date field if the version has
   one, otherwise skip leads) — `search-read` its ids, then run
   `spread-dates` with that window.
3. Re-run `search-read` sorted by the field to eyeball the spread: it should
   cover the window edge to edge, not cluster at one end.

*Done when* every populated, date-bearing model has been spread and the
re-read confirms it.
