# odoo-feeder

A launcher that runs someone else's agent. Most changes here are changes to what
*that* agent reads at runtime, not to code that executes.

## Three agent-facing documents, synced by hand

Load the `writing-for-agents` skill before editing any of them — including the
`REQUEST` prompt and this file, which are agent documents that do not look like
skills.

- `odoo-demo-csv/SKILL.md` (+ `ODOO-TRAPS.md`, `INDUSTRY-MODULES.md`) — the run
  the agent follows.
- The `REQUEST` prompt in `odoo-demo-feeder` — what the run is *this time*
  (target, size, tool name, `SUMMARY:` format). It defers everything else to the
  skill, and names the skill's `Dataset size` heading: renaming that heading
  breaks the reference.
- `odoo_crud.py`'s argparse help — the skill points the agent at
  `odoo-crud <command> --help` instead of restating flag shapes, so those help
  strings are agent-facing documentation. Changing a flag changes the docs.

Touch one, check the other two.

## Which skill a run actually reads

Every run deploys a skill over `~/.agents/skills/odoo-demo-csv/` and copies that
into the sandbox workspace. Where it comes from depends on how the feeder was
launched, and the run prints which one won:

- **From a checkout** — `./odoo-demo-feeder` finds `odoo-demo-csv/` beside
  itself and deploys that. Your working tree *is* the run; no push, no
  `SKILLS_REPO=`.
- **A standalone install** — `feed.sh` puts the script in `~/.local/bin` with no
  skill directory beside it, so it pulls the public repo's **default branch**.
  This is the path every deployed machine takes: main is what they run.
- `SKILLS_REPO=` empty keeps whatever is installed, and only matters when there
  is no checkout to read.

The deploy replaces the whole directory rather than merging into it, so a
reference file you rename does not linger under its old name — and reference
files beside `SKILL.md` do reach the agent, so a pointer to one must survive any
rename.

`CRUD_TOOL` is env-overridable, so `CRUD_TOOL=$PWD/odoo_crud.py odoo-demo-feeder`
does test a local CRUD tool. `REPO_REF` only affects what `feed.sh` downloads
during bootstrap — it does not steer the skill deploy.

## The agent's box

Headless, inside bubblewrap, restricted to one command: an `odoo-crud` wrapper
installed by the feeder. It has no shell, so a new capability for the agent is a
new `odoo_crud.py` subcommand — never a shell one-liner in the prompt or skill.

## Verification

No CI, no test suite: the only real check is a run against a throwaway database.
`odoo-demo-feeder --plan` shows the agent's intended modules, counts and files
before it writes anything.

## Commit each atomic change

One behaviour change, one commit, staged from the files you touched and made the
moment the change stands on its own. Several changes stacked up in the tree lose
which one to revert.

The three synced documents make one change look like three: an edit that spans
`SKILL.md`, the `REQUEST` prompt and the argparse help is a single commit.
