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

**Never wait or pause.** Every `odoo-crud` call is synchronous — when it returns,
the operation is done. Do not "wait for it to finish". Run the whole job in one
continuous pass and only stop once you have printed the final `SUMMARY:` line.

Work in this order:

1. **Inspect the database first — never assume a model or app is available.**
   - Check the modules you will need are installed:
     `odoo-crud search-read ir.module.module --domain '[["name","in",["contacts","product","stock","crm","sale_management","account"]]]' --fields '["name","state"]'`
   - **Install ALL the modules you need in ONE blocking call** before importing
     (crm → crm.lead, stock → stock.quant, product/sale → product.template):
     `odoo-crud install-modules crm stock sale_management account`
     This command installs the modules AND confirms their final state before it
     returns (its JSON lists `not_installed` if any failed). There is **nothing to
     wait for** — as soon as it returns, move straight on to the next step.
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

## Dataset size (how many records)

The prompt gives a size — **small**, **medium**, or **big**. Treat it as the
**overall scale of the business** and apply it **consistently to every model you
populate** (partners, products, stock, leads, and anything else you add such as
sale.order, account.move or mrp.bom) using realistic ratios. Don't size one model
richly and leave the others almost empty.

Anchor on the number of **customers**, then derive everything else in proportion:

| size   | customers (anchor) | feel                                 |
|--------|--------------------|--------------------------------------|
| small  | ~8                 | a small shop — just enough to demo   |
| medium | ~25                | an established SMB                    |
| big    | ~80                | a large company, rich data           |

Derive the rest from that anchor with sensible, sector-adjusted ratios, e.g.:
- **vendors** ≈ customers ÷ 6 (always just a handful).
- **products** ≈ a catalogue smaller than the customer base (fewer for a services
  business). If the site has fewer genuine products than that, stay truthful: use
  the real ones and reach the number with real **variants** (sizes, flavours,
  formats) — never invent unrelated products.
- **stock.quant** — one line per storable (`detailed_type = product`) product.
- **leads** ≈ half to one× the number of customers.
- **any other model you create** (sale orders, invoices, BoMs…) — scale to match
  and keep every reference valid via external IDs.

Keep the whole dataset internally consistent and proportional to the chosen size.

## Files to generate (default set)

1. **res.partner** — customers + vendors scaled per the size section.
   Columns: `id` (e.g. `partner_client_1`), `name`, `is_company`, `street`,
   `city`, `email`, `phone`.
2. **product.template** — real flagship products found on the site, scaled per the
   size section (see variant rule above).
   Columns: `id` (e.g. `product_1`), `name`, `list_price`, `standard_price`,
   `detailed_type` (`consu`, `product`, or `service`), `barcode`.
3. **stock.quant** — stock lines, only for items where `detailed_type = product`.
   Columns: `product_id/id` (must reuse the exact id from the product file, e.g.
   `product_1`), `inventory_quantity`, `location_id` (value: `WH/Stock`).
4. **crm.lead** — leads scaled per the size section.
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
