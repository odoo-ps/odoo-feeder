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

When a call fails, a record you know exists comes back missing, or a number
reads zero after a green import, the cause is almost always one of the Odoo
behaviours collected in [`ODOO-TRAPS.md`](ODOO-TRAPS.md) — read it then.

## Run

### 1. Research the target

Browse the site and collect: the trade it is in, the *real* products or services
and their prices, the company's location (it drives country and currency), and
the URLs of the logo and the product photos. Make each URL absolute — some sites
emit protocol-relative `//cdn.example.com/…`, which needs an `https:` prefix.

With no website given, generate coherent generic data for the stated industry
instead.

*Done when* you can name the trade the business is in, the products you will
import, and the country you will set on the company.

### 2. Probe the database

This database's version decides which models, fields and apps exist — read them,
never assume them. Install before you read: a model's fields only exist once the
module defining them is in, so these run in order.

- `odoo-crud auth-check` — first command of the run. If it fails, stop and say
  why; nothing downstream can work.
- The **industry** module configures the database for the trade the target is
  in — its apps, its reports, its own sample records — and one of them fits
  almost every business a sales person will name. Match step 1's research
  against [`INDUSTRY-MODULES.md`](INDUSTRY-MODULES.md) and pick the one that
  fits.
- `odoo-crud install-modules bakery crm stock sale_management account` — that
  industry module plus every module behind step 5's import order, in ONE call.
  Read the base list straight off that order: `res.partner` → `contacts`,
  `product.template` → `product` and `sale_management`, stock on hand →
  `stock`, `crm.lead` → `crm`, plus `account` for invoicing. It installs *and*
  confirms before returning, and its JSON lists `not_installed` for anything
  that failed.
- `odoo-crud models --filter crm` — which models the install actually gave you.
- `odoo-crud fields product.template --filter 'name,list_price,barcode'` — one
  compact line per field (`many2one required -> res.partner`), including a
  selection field's allowed values. Filter by the columns you plan to write;
  dumping every field of `res.partner` or `product.template` buries the answer.

*Done when* `install-modules` has come back with `not_installed` empty — the
industry module among them — and every column of every CSV you are about to
write has appeared in a `fields` output, with its type and — for selection
fields — its allowed values copied verbatim.

### 3. Configure the company

Set country, company name and currency on `res.company` to the real location:
find the id with `search-read`, then

```
odoo-crud write res.company --ids '[1]' --values '{"country_id": 241, "currency_id": 23}'
```

A currency that seems absent is archived, not missing — see the traps file.

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

Three rules bind every CSV:

- **External IDs** — every row carries an `id` column and every reference is
  `field_id/id` pointing at one. This is what makes a re-import update the
  record instead of duplicating it, and it is non-negotiable.
- **Quoting** — comma separator, and every text value wrapped in double quotes
  so `"Company, Inc."` stays one column.
- **Language** — the site's language, or the one the sales person asked for.

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
the `SUMMARY:` line.
