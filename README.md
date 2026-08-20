# odoo-feeder

AI-driven tool to populate an Odoo **demo database** with realistic, industry-specific
data — built for sales, no technical setup required.

## Launch (one line)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
# ...or, if you have wget instead of curl:
bash <(wget -qO- https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
```

It installs what's missing (bubblewrap, Node.js, Python, and optionally gum for
nicer prompts), asks which AI CLI should drive the agent and installs just that
one, fetches the feeder, and runs it. You can pass the details as flags to skip
the prompts:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh) \
  --url https://mycompany.odoo.com --login admin --secret <api-key> \
  --scope "Bakery" --company "Maison Rorive" --website https://www.maisonrorive.be
```

> First run only: sign in to the CLI you picked (`agy` with Google, `claude` with
> Anthropic). The default copilot-on-OpenRouter setup needs no sign-in — just the
> keyring key below.
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

## AI CLI providers

Three are supported: `copilot` (GitHub Copilot CLI),
[`agy`](https://antigravity.google) (Antigravity) and `claude` (Claude Code).
The bootstrap asks which one you want and installs only that one, offering
`copilot` first; `--ai-cli agy` or `AI_CLI=agy` answers ahead of time, and
`copilot` is the fallback when there is no terminal to ask on.

The default run is **copilot routed through [OpenRouter](https://openrouter.ai)**
on `deepseek/deepseek-v4-flash-latest`, via Copilot's BYOK support — so no GitHub
sign-in is needed at all. The API key is never passed as a flag or plaintext env
var; store it once in the OS keyring:

```bash
keyring set odoo-feeder openrouter-api-key
```

To use a different model, or GitHub's own routing:

```bash
odoo-demo-feeder --openrouter-model anthropic/claude-sonnet-4.5 ...
odoo-demo-feeder --openrouter-model ''    # GitHub's routing, needs a GitHub login
```

(`OPENROUTER_MODEL` works the same way.) The model applies to `copilot` only; with
another `--ai-cli` the default is ignored rather than being an error.

## Debugging a run

Headless runs only print whatever the model chooses to narrate — which can look
like progress even when nothing actually happened (e.g. a weak model fabricating
tool calls, or a real tool call that failed and got glossed over). Every run's
full transcript + a ground-truth audit trail of every real `odoo-crud` call
(and its exit code) is saved to `~/.local/share/odoo-demo-feeder/logs/`; the
feeder prints a `file://` link to it at the end of every run, success or
failure. If the summary claims success but no write actually succeeded, the
feeder catches that itself and reports failure instead of "✔ Done!".

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
