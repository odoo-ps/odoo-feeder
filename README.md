# odoo-feeder — AI skills

Agent skills for the **Odoo Demo Database Feeder**, distributed via
[`npx skills`](https://github.com/vercel-labs/skills).

## Install

```bash
npx -y skills add odoo-ps/odoo-feeder --all
```

## Skills

- **odoo-demo-csv** — research a prospect's website and generate Odoo-import-ready
  CSV files (partners, products, stock, CRM leads), then import them into the
  connected database with strict external-ID and CSV-safety rules.
