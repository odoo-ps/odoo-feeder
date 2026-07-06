# odoo-feeder

AI-driven tool to populate an Odoo **demo database** with realistic, industry-specific
data — built for sales, no technical setup required.

## Launch (one line)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
# ...or, if you have wget instead of curl:
bash <(wget -qO- https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
```

It installs what's missing (agy, bubblewrap, Node.js, Python, and optionally gum
for nicer prompts), fetches the feeder, and runs it. You can pass the details as flags to skip the prompts:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh) \
  --url https://mycompany.odoo.com --login admin --secret <api-key> \
  --scope "Bakery" --company "Maison Rorive" --website https://www.maisonrorive.be
```

> First run only: launch `agy` once and sign in with Google.
> The public `odoo.com` site is blocked as a target.

## Templates

Instead of answering the questions one by one, you can describe the whole demo in
a **template** — a free-text block the AI reads directly. Interactively, pick
*"Paste a template"* and paste it; non-interactively, pass `--template FILE`.

```
name: Maison Rorive demo
website: https://www.maisonrorive.be
company_name: Maison Rorive
country: BE
apps: [sale_management, crm, website, helpdesk]
data_size: big
override_model_size: {product.product: 100, crm.lead: 30}
configuration: enable pricelists, multi-currency, default sales team "Retail"
```

Any key you write is understood (`apps` → modules to install, `data_size` → scale,
`override_model_size` → exact per-model counts, `country` → company config, …), and
free text is followed as instructions. Connection details (URL / login / secret)
are always asked separately and never belong in a template.

The prompts use [`gum`](https://github.com/charmbracelet/gum) for a nicer interface
when it is available, and fall back to plain prompts otherwise.

## What's inside

- **feed.sh** — one-shot bootstrap (provision + launch).
- **odoo-demo-feeder** — the launcher: prompts/flags, refreshes the skill, runs the AI
  agent (headless by default, `-i` for interactive) inside a bubblewrap sandbox.
- **odoo_crud.py** — the only gateway the agent uses to reach Odoo (XML-RPC CRUD,
  method calls, CSV import, introspection).
- **odoo-demo-csv/** — the `npx skills` package the agent follows to research a
  website and generate/import Odoo CSVs.

## Safety

- The agent is restricted to a single tool (`odoo-crud`) via agy's permission
  allowlist, and confined by bubblewrap (read-only filesystem, secrets hidden,
  only the database credentials exposed).
