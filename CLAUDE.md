# odoo-feeder

A launcher that runs someone else's agent. Most changes here are changes to what
*that* agent reads at runtime, not to code that executes.

## Three agent-facing documents, synced by hand

Load the `writing-for-agents` skill before editing any of them — including the
`REQUEST` prompt and this file, which are agent documents that do not look like
skills.

- `odoo-demo-csv/SKILL.md` (+ `ODOO-TRAPS.md`) — the run the agent follows.
- The `REQUEST` prompt in `odoo-demo-feeder` — what the run is *this time*
  (target, size, tool name, `SUMMARY:` format). It defers everything else to the
  skill, and names the skill's `Dataset size` heading: renaming that heading
  breaks the reference.
- `odoo_crud.py`'s argparse help — the skill points the agent at
  `odoo-crud <command> --help` instead of restating flag shapes, so those help
  strings are agent-facing documentation. Changing a flag changes the docs.

Touch one, check the other two.

## Per-workflow skill + tool pairs

Each `ODOO_FLOWS` key (`trading`, `mrp`, `accounting`, `analytics`) is its own
triple, independent of the base one above and of each other: `odoo-demo-<flow>/
SKILL.md`, `odoo_crud_<flow>.py`, and that tool's own argparse `--help`. Tweaking
one flow's behaviour never touches `odoo-demo-csv`, `odoo_crud.py`, or another
flow's files — that isolation is the whole point of the split. Same
touch-one-check-the-others rule applies within a triple.

All four tool scripts import `odoo_crud_lib.py` for the XML-RPC connection
(auth, uid caching, retry-on-stale-uid) — the one thing genuinely shared
between them. `odoo_crud.py` itself does **not** import it; it stays exactly as
it was, on purpose, so it never gains a dependency on code written for a
workflow that might not even be selected.

`odoo-demo-feeder` only installs a flow's wrapper (`~/.local/bin/odoo-crud-
<flow>`), only allows it in each provider's permission rules, and only copies
its skill into the sandboxed workspace, when that flow's key is actually in
`ODOO_FLOWS` for this run — see `flow_skill_name` / `flow_tool_path` /
`flow_wrapper_name` and every call site that loops over `ODOO_FLOWS`. A
workflow nobody picked leaves no trace in that run's sandbox.

`CRUD_TOOL_TRADING` / `CRUD_TOOL_MRP` / `CRUD_TOOL_ACCOUNTING` /
`CRUD_TOOL_ANALYTICS` are env-overridable the same way `CRUD_TOOL` is, for
testing one flow's tool locally.

## A local skill edit does not reach a run

Every run does `npx skills add "$SKILLS_REPO" --global --agent <id> --copy` from
the public repo's **default branch** — `<id>` is the *skills-tool's own* id for
whichever `--ai-cli` is driving the run (`provider_skill_agent` in
`odoo-demo-feeder`; e.g. `claude-code`, not `claude`), so it lands under that
provider's own global skills dir, then gets copied into the sandbox workspace.
The working tree is never read. To try a skill change: push it to main, or
blank `SKILLS_REPO` (hardcoded near the top of `odoo-demo-feeder`) to keep the
installed copy and edit that copy directly.

`npx skills add` only ever places `SKILL.md` itself — it drops sibling
reference files. `odoo-demo-feeder` fetches `ODOO-TRAPS.md` separately right
after the `skills add` call to put it back beside `SKILL.md`; a new reference
file needs the same explicit fetch added, it will not "just" come along.

`CRUD_TOOL` is env-overridable, so `CRUD_TOOL=$PWD/odoo_crud.py odoo-demo-feeder`
does test a local CRUD tool. `REPO_REF` only affects what `feed.sh` downloads
during bootstrap — it does not steer the skill refresh.

`odoo-demo-feeder` also narrows the `--skill` flags passed to `npx skills add`
to the base skill plus whichever `ODOO_FLOWS` were selected — it no longer
pulls `--skill '*'`. A new flow skill needs no change there; it starts showing
up automatically once a flow key routes to it in `flow_skill_name`.

## The agent's box

Headless, inside bubblewrap, restricted to `odoo-crud` plus one
`odoo-crud-<flow>` wrapper per selected workflow (see above) — never more. It
has no shell, so a new capability for the agent is a new subcommand on
whichever tool it belongs to — never a shell one-liner in the prompt or skill.

## Verification

No CI, no test suite: the only real check is a run against a throwaway database.
`odoo-demo-feeder --plan` shows the agent's intended modules, counts and files
before it writes anything.

## Commit each atomic change

One behaviour change, one commit, staged from the files you touched and made the
moment the change stands on its own. Several changes stacked up in the tree lose
which one to revert.

The three synced documents make one change look like three: an edit that spans
`SKILL.md`, the `REQUEST` prompt and the argparse help is a single commit. Same
for a per-workflow triple: a change to `odoo-demo-mrp/SKILL.md` and
`odoo_crud_mrp.py`'s argparse help is one commit, not two.
