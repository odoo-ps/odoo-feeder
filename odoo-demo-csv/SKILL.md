---
name: odoo-demo-csv
description: >
  Research a prospect's company website and generate Odoo-import-ready CSV files
  (customers/vendors, products, stock, CRM leads), then import them into the
  connected Odoo database with strict external-ID and CSV-safety rules. Use
  whenever populating an Odoo demo database from a real company or industry.
---

# Odoo Demo Data — website-driven CSV generation

## Context & method

The sales person gives you a company name and its website (and may ask for
additional files).

1. **Research first.** Use your web search / browsing tools to analyze the site:
   understand the sector, find the *real* products/services, and identify the
   location (for currency and address). If no website is given, generate coherent
   generic data for the provided industry/scope instead.
2. **Then generate** the Odoo-import-ready CSV files described below.

## How to run in this environment (important)

You run **headless** with a single tool, `odoo-crud` (the only shell command you
may run). Do **not** just print CSV code blocks — write files and import them.

**Be verbose.** Before each step, say what you are about to do; after each
`odoo-crud` call, print a one-line result (e.g. "Installing crm… done", "Imported
5 partners", "Preview found 1 bad column, fixing"). The sales person is watching
this output, so narrate your progress.

Work in this order:

1. **Inspect the database first — never assume a model or app is available.**
   - Check the modules you will need are installed:
     `odoo-crud search-read ir.module.module --domain '[["name","in",["contacts","product","stock","crm","sale_management","account"]]]' --fields '["name","state"]'`
   - **Install any missing module before importing to its models** (crm → crm.lead,
     stock → stock.quant, product/sale → product.template). Find the id and install:
     `odoo-crud call ir.module.module button_immediate_install --args '[[<module_id>]]'`
     then re-check its state is `installed`.
   - Confirm each target model and its fields exist, and adapt your CSV columns to
     what this database/version actually has:
     `odoo-crud models --filter crm` and `odoo-crud fields crm.lead`.
2. **Configure the company** from your research: set the country and currency on
   `res.company` to match the company's real location (find the id with
   `search-read`, then `call res.company write`).
3. **Generate & import** each CSV: write it to a file (e.g. `res_partner.csv`),
   then `odoo-crud import-csv <model> --file <path>`.
4. If an import reports errors, diagnose with
   `odoo-crud import-preview <model> --file <path>`, `odoo-crud fields <model>` and
   `odoo-crud models`, fix the CSV, and retry.

Import in **dependency order** — partners → products → stock → leads — because of
the ID references below.

## Files to generate (default set)

1. **res.partner** — 5 customers + 2 vendors.
   Columns: `id` (e.g. `partner_client_1`), `name`, `is_company`, `street`,
   `city`, `email`, `phone`.
2. **product.template** — 5–7 real flagship products found on the site.
   Columns: `id` (e.g. `product_1`), `name`, `list_price`, `standard_price`,
   `detailed_type` (`consu`, `product`, or `service`), `barcode`.
3. **stock.quant** — stock lines, only for items where `detailed_type = product`.
   Columns: `product_id/id` (must reuse the exact id from the product file, e.g.
   `product_1`), `inventory_quantity`, `location_id` (value: `WH/Stock`).
4. **crm.lead** — 3 leads.
   Columns: `id` (e.g. `lead_1`), `name`, `partner_id/id` (reuse an id from file 1),
   `expected_revenue`, `stage_id` (value: `New`, `Qualified`, or `Proposition`).

If the sales person asks for extra files (`mrp.bom`, employees, chart of accounts,
etc.), generate them too, keeping the same relational logic.

## Strict formatting & content rules

- **ZERO HALLUCINATION** — use only real product/service names found on the site.
  If there is no public price, use `0.00` (do not block the import). If the data
  found is too thin, say so briefly before importing.
- **CSV SAFETY** — wrap every text value in double quotes `"` so internal commas
  (e.g. `"Company, Inc."`) do not break columns. The column separator is a comma `,`.
- **ODOO INTEGRITY (External IDs)** — always use the `id` column to create records,
  and reference them with `field_id/id`. This is non-negotiable: it prevents
  duplicates across successive imports.
- **LANGUAGE** — generate the data in the target website's language, or the
  language requested by the sales person.
- **EFFICIENCY** — no long explanations; get straight to the point.
