---
name: odoo-demo-csv
description: >
  Populate a connected Odoo demo database with data researched from a real
  company's website, or from a named industry. Use whenever a sales demo needs a
  database filled with realistic records.
---

# Odoo demo data

A sales person names a company and its website — or just an industry — plus a
dataset size. You research the target, write Odoo-import-ready CSVs, import them
into the connected database, and verify the result: one continuous pass ending
with a `SUMMARY:` line.

Two words govern every step below.

**Ground truth** — every record traces back to something you found on the target
site: real product names, real prices, real photos. Where the site is silent,
stay silent — price `0.00`, no image, and one line saying the data was thin. A
demo built on invented products is the one failure this run cannot recover from.

**Narrate** — one line before each step saying what you are about to do, one line
after each `odoo-crud` call carrying its result ("Imported 25 partners",
"Preview found 1 bad column, fixing"). The sales person watches this output and
sees nothing else of the run.

## The tool

`odoo-crud <command> [options]` reaches Odoo over XML-RPC. It is the only shell
command available to you, and it reads its credentials from the environment.

- **Blocking** — every call, `install-modules` included, returns once the work is
  done. Chain straight into the next command: there is nothing to wait for and
  nothing to poll.
- Every call prints JSON `{"ok": true|false, ...}`. Read `ok` before moving on.
- `odoo-crud <command> --help` is the flag reference: the exact JSON shape of
  `--domain`, `--values`, `--args`, `--context`, `--filter` lives there. Read it
  rather than guess a shape.

Use your own file tools to write the CSVs and your browsing tools to research —
writing CSV into the chat instead of into a file imports nothing.

When a call fails, a record you know exists comes back missing, a number reads
zero after a green import, or **a green call changed nothing** — a document
still empty, a picking still not done, a date that would not move — the cause is
almost always one of the Odoo behaviours collected in
[`ODOO-TRAPS.md`](ODOO-TRAPS.md) — read it then.

## Run

### 1. Research the target

Browse the site and collect: the trade it is in, the *real* products or services
and their prices, the company's location (it drives country and currency), and
the URLs of the logo and the product photos. Make each URL absolute — some sites
emit protocol-relative `//cdn.example.com/…`, which needs an `https:` prefix.

With no website given, generate coherent generic data for the stated industry
instead. If website scraping fails or is blocked, do NOT halt or ask questions —
immediately fall back to rich, synthetic industry data matching the sector.

*Done when* you can name the trade the business is in, the products you will
import, and the country you will set on the company.

### 2. Probe the database

This database's version decides which models, fields and apps exist — read them,
never assume them. Install before you read: a model's fields only exist once the
module defining them is in, so these run in order.

- `odoo-crud auth-check` — first command of the run. If it fails, stop and say
  why; nothing downstream can work.
- `odoo-crud install-industry bakery` — the **industry** module for the trade the
  target is in, which configures the database for that business and brings its
  sample records. Match step 1's research against
  [`INDUSTRY-MODULES.md`](INDUSTRY-MODULES.md) and install the one that fits. It
  takes exactly one, and it is its own command because these modules are
  downloaded from apps.odoo.com rather than found on the addons path —
  `install-modules` cannot see them at all. It fails when the download is
  refused, or when the industry needs modules this database does not have — a
  Community database being asked for Enterprise ones, which it names.
  Either way, carry on with the base modules: the run works without it. Say
  what was lost rather than passing it off as cosmetic — no industry-specific
  chart of accounts, no configured screens, none of its sample records — and
  leave the SUMMARY's industry line reading `none (<name> unavailable)` rather
  than naming a module that never installed.
- `odoo-crud install-modules crm stock sale_management account purchase mrp` —
  every module behind step 5's import order, in ONE call. Read the list straight
  off that order: `res.partner` → `contacts`, `product.template` → `product` and
  `sale_management`, stock on hand → `stock`, `crm.lead` → `crm`, `account` for
  invoicing, `purchase` for the PO chain, and `mrp` when the target manufactures
  (harmless on a pure trader). It installs *and* confirms before returning, and
  its JSON lists `not_installed` for anything that failed.
- `odoo-crud models --filter crm` — which models the install actually gave you.
- `odoo-crud fields product.template --filter 'name,list_price,barcode'` — one
  compact line per field (`many2one required -> res.partner`), including a
  selection field's allowed values. Filter by the columns you plan to write;
  dumping every field of `res.partner` or `product.template` buries the answer.

*Done when* the industry module is installed or you have said in one line why it
could not be, `install-modules` has come back with `not_installed` empty, and
every column of every CSV you are about to write has appeared in a `fields`
output, with its type and — for selection fields — its allowed values copied
verbatim.

### 3. Configure the company & activate MTO route

- Set country, company name, and currency on `res.company` to the real location (find the id with `search-read`, then `odoo-crud write res.company --ids '[1]' --values '{"name": "...", "country_id": 241, "currency_id": 23}'` — an absent currency is archived, see `ODOO-TRAPS.md`).
- In the same pass, unarchive the default MTO ("Replenish on Order") route so on-demand purchasing and manufacturing flows work out of the box: query its id with `odoo-crud search-read stock.route --domain '[["name","ilike","Replenish on Order"],["active","in",[True,False]]]' --fields '["id"]'`, then run `odoo-crud write stock.route --ids '[<mto_route_id>]' --values '{"active": true}'`.

### 4. Size the dataset

The prompt gives **small**, **medium** or **big**. It is the scale of the whole
business, so it applies to every model you populate. Anchor on the customer
count and derive the rest in trade-adjusted proportion:

| size   | customers (anchor) | feel                               |
|--------|--------------------|------------------------------------|
| small  | ~8                 | a small shop — just enough to demo |
| medium | ~25                | an established SMB                 |
| big    | ~80                | a large company, rich data         |

- **vendors** ≈ customers ÷ 6 — always a handful.
- **products** ≈ a catalogue smaller than the customer base, fewer still for a
  services business. When the site has fewer genuine products than that, reach
  the number with real **variants** (sizes, flavours, formats) — ground truth
  outranks the target count.
- **stock on hand** — a quantity for every storable product.
- **leads** ≈ half to one× the customers.
- **anything else you create** — sale orders, invoices, BoMs — scaled to match.

Sizing one model richly and leaving its neighbours empty is what makes a demo
look fake.

### 5. Generate and import

Write each CSV to a file, then `odoo-crud import-csv <model> --file <path>`.
Import in **dependency order** so every reference resolves:

1. **`res.partner`** — customers + vendors.
   Columns: `id` (e.g. `partner_client_1`), `name`, `is_company`, `street`,
   `city`, `email`, `phone`.
2. **`product.template`** — the flagship products you found.
   Columns: `id` (e.g. `product_1`), `name`, `list_price`, `standard_price`,
   `barcode`, plus this database's product-type and storability columns —
   whatever step 2's `fields product.template --filter 'type,storable'` showed,
   with the selection values verbatim. Whether storability is one of those
   values or its own boolean flag varies by version.
3. **stock on hand** — a *second pass over `product.template`*, one row per
   product you marked storable, carrying just `id` (the same external id as
   above) and `qty_available`. The ids already exist, so Odoo runs the same code
   path as typing a quantity on the product form: it creates the quant and
   applies it, and the goods really are on hand.
4. **`crm.lead`** — columns: `id` (e.g. `lead_1`), `name`, `partner_id/id`
   (an id from file 1), `expected_revenue`, `description`, `stage_id` (`New`,
   `Qualified` or `Proposition`). Write every `description` in the **customer's
   voice** — the two or three lines that prospect sent in, naming the real
   product they are asking about and what they need it for.
Before wiring anything to anything, **read the id map**:

```
odoo-crud resolve product.template --module __import__
odoo-crud resolve res.partner --module __import__
```

Everything above went in by external id. Every call from here on — an order
line, `action_confirm`, `set-image` — takes the database id Odoo assigned, and
`product_1` is not database id 1. One record already sitting in the model
shifts the whole sequence: a seeded `Booking Fees` product takes id 1 and every
product you imported is one further along than its name suggests. An order line
built on the guess still imports, still returns `ok: true`, and sells the wrong
product. Check two entries in the map against their `name` before you use it.

5. **Linked Workflows (SO -> MO -> PO)** — wire and trigger the full supply chain so the demo is fully interactive with zero duplicate records.
   - **Vendor on the product first (`product.supplierinfo`).** Every purchased product/raw material needs a supplier link — without it, Odoo cannot auto-generate RFQs. Create `product.supplierinfo` records with `partner_id/id` (vendor), `product_tmpl_id/id`, `price` (`standard_price`), and delivery delay.
   - **`mrp.bom` (When manufacturing):**
      - Raw components: Set `route_ids/id` to include `stock.route_warehouse0_buy` and ensure `product.supplierinfo` is set.
      - Finished goods: Set `route_ids/id` to include `mrp.route_warehouse0_manufacture` and the unarchived `stock.route_warehouse0_mto`.
      - **Read the routes back.** They do not always stick: a write of both has
        come back holding MTO alone, with no error. `search-read
        product.template --fields '["route_ids"]'` says what is really there.
        MTO plus a BoM is enough to raise the MO, so a missing Manufacture route
        is worth a narrated line rather than a fight.
      - Import `mrp.bom` and `mrp.bom.line` linking components to the finished product.
   - **`sale.order` + `sale.order.line`:** Import draft SOs linked to partner (`partner_id/id`) and CRM opportunity (`opportunity_id/id`), referencing the finished product variant in lines (`product_id/id`).
   - **Confirm the orders, then read what appeared.**
      ```bash
      odoo-crud confirm-so --ids '[<so_ids>]'
      ```
      It confirms and reports the manufacturing orders and purchase orders that
      resulted, which is not the same as the ones you expected:
      - The **MO does** appear, linked, with the SO in its `origin`. That is the
        smart button the demo is shown through.
      - The **component PO usually does not.** Stock on hand is why: the MO
        consumes what step 5.3 imported, so procurement has nothing left to buy.
        Every run that imports stock lands here, routes correctly set or not.
      - To get one anyway, `confirm-so --ensure-po` puts a reorder point on each
        component and runs the scheduler. The PO that follows is raised by the
        orderpoint, **not** by the order, so its `origin` is empty and no smart
        button ties it back to the SO. Say that in one line rather than claiming
        a link the database does not have.
      - *A missing MO* is the real fault to chase: `mrp` not installed, no BoM,
        or the `Manufacture` and `MTO` routes not active.

   *Done when* each confirmed SO reports `state: sale` with a manufacturing
   order carrying its name in `origin`, and you have said in one line what the
   purchase side did — a PO from a reorder point, or none because the components
   were in stock.

6. **Invoices and vendor bills** — the accounting half of the chain, and what
   fills the P&L, balance sheet and cashflow. Nothing here is imported: each
   document is created *by* the order it belongs to, which is what wires the
   smart buttons.
   - **Customer invoices from the SOs.** `_create_invoices` is private and so
     unreachable over RPC; the way in is the wizard the SO form's Create Invoice
     button opens. Create it against the orders, then run it:
      ```bash
      odoo-crud create sale.advance.payment.inv --values '{"advance_payment_method": "delivered", "sale_order_ids": [[6, 0, [<so_ids>]]]}'
      odoo-crud call sale.advance.payment.inv create_invoices --args '[[<wizard_id>]]'
      ```
     `delivered` is the wizard's name for a regular invoice, not a down payment.
     It invoices what each line's policy says is invoiceable, so a product set
     to *Delivered quantities* invoices nothing until its delivery is validated.
     Check with `fields product.template --filter invoice_policy` back in step 2
     and write `order` **with the products**, before any order exists: changing
     the policy afterwards does not make existing orders invoiceable, and Odoo
     means it that way — see `ODOO-TRAPS.md` under nothing-to-invoice. Past that
     point the honest route is validating the delivery, which is what the policy
     is asking for and is its own trap entry.
   - **Vendor bills from the POs.** One call, because doing it by hand is five
     steps and the middle three are invisible until you read the document:
      ```bash
      odoo-crud bill-po --ids '[<po_ids>]'
      ```
     It confirms the RFQ, switches the products to bill on ordered quantities,
     creates the bill, fills any line still at zero, sets the vendor reference
     and invoice date, and posts. `action_create_invoice` on its own returns a
     draft with every quantity `0.0` and a total of `0` — a product's Control
     Policy bills on *received* quantities and a demo receives nothing — and
     posting then fails on the missing invoice date. A green call and an empty
     document look identical from here, so `bill-po` fails rather than reporting
     a zero-total bill.
   - **Post the customer invoices.** The wizard leaves drafts, and a draft moves
     no money: the reports stay empty until the entries are posted.
      ```bash
      odoo-crud search-read account.move --domain '[["state","=","draft"],["move_type","=","out_invoice"]]' --fields '["name","amount_total"]'
      odoo-crud call account.move action_post --args '[[<move_ids>]]'
      ```
     A draft refusing to post is almost always missing `invoice_date`.

   *Done when* every SO has an invoice and every confirmed PO a bill, all of
   them `state: posted` with a non-zero `amount_total` — a zero-total or draft
   document sits on the order looking correct and contributes nothing to a
   single report.

Four rules bind every CSV:
- **External IDs:** Use `id` for record creation and `field_id/id` for relational lookups.
- **Quoting:** Wrap every text value in double quotes `"`.
- **Language:** every text field in the demo language asked for.
- **Relational keying:** `field/id` matches an external id, a bare `field`
  matches by display name. Both work and they are not interchangeable —
  `uom_id` written bare resolves `"Units"` by name, while `partner_id/id` wants
  `partner_client_1`. Pick per column and stay consistent.

7. **Spread the dates** *(when trend reporting was asked for)* — every record so
   far is stamped with the moment it was created, so each dashboard shows one
   spike on today and nothing behind it. No CSV column fixes this: an order's
   date is set when it is confirmed, not when its row is read, so it is a pass
   over the finished records.
   ```bash
   odoo-crud spread-dates sale.order --days 90
   ```
   Run it **last**, after confirming and posting — both stamp fresh dates and
   would undo it.

   Posted invoices need unposting first: their date is readonly, so
   `spread-dates account.move` fails on exactly the records worth spreading.
   `button_draft` → spread → clear `name` → `action_post`, the sequence in
   [`ODOO-TRAPS.md`](ODOO-TRAPS.md) under the readonly-date symptom. Skipping the
   `name` reset makes the repost fail on a number that no longer matches its
   date.

   *Done when* a `search-read` of the spread model shows its dates ranging back
   across the window rather than clustered on today.

Asked for more than the default set (`mrp.bom`, employees, chart of accounts…)?
Build those the same way: sized to the anchor, wired with external IDs, imported
after whatever they reference.

*Done when* every import has returned `ok: true` and its record count matches
the number step 4 called for. On a failure, `ODOO-TRAPS.md` names the cause; fix
the CSV and re-import — external ids make the retry safe.



### 6. Set images

A product grid with real photos is what makes the demo land on screen.

```
odoo-crud set-image product.template --id <record_id> --url <image_url>
odoo-crud set-image res.company --id 1 --url <logo_url> --field logo
```

Two details decide whether these calls land:

- **Database id, not external id.** `--id` takes the integer Odoo assigned. Get
  them with one `search-read` on the model you just imported — it returns each
  record's `id` beside its `name`, which is what you match your photo URLs on.
- **The field.** It writes `image_1920` by default; the company logo lives on
  `logo`, so that call carries `--field logo`.

Records with no genuine image keep none — that is the only reason to skip one.

*Done when* every product whose photo URL you collected in step 1 has had a
`set-image` call return `ok: true`, and the logo is on the company.

### 7. Verify, then summarise

Read back what you wrote — a green import is not proof:

- `odoo-crud search-read product.template --fields '["name","qty_available"]'` —
  every storable product shows the quantity you imported. `qty_available` is the
  number that counts; `inventory_quantity` is not.
- A `search-read` per model you populated, confirming the counts from step 4.
  The industry module shipped records of its own, so a model total is its rows
  plus yours — count the ones you imported.

*Done when* every model you touched has been read back and matches. Then print
the `SUMMARY:` line:

```text
===================================================================
🚀 DEMO DATABASE READY FOR [COMPANY NAME]
===================================================================
• Industry Module: [Installed Industry App]
• Company Profile: Updated (Currency & Country configured)

📊 DATASET SUMMARY:
• Partners: X Customers, Y Vendors imported
• Catalog: Z Products populated (with real web images)
• Inventory: Stock initialized across storable items
• Pipeline: N Leads created (~$XXX,XXX expected revenue)

🎯 DEMO CHEAT SHEET FOR SALES PITCH:
1. Primary Customer to Demo: [Partner Name]
2. Flagship Product: [Product Name] ($XX.XX)
3. Top Pipeline Opportunity: [Lead Name] ($XX,XXX - Stage: Qualified)
===================================================================
SUMMARY: Imported X partners, Y products, Z leads into Odoo database successfully.
```
