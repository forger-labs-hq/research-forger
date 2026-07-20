# Experiment mode — contract, baseline, funnel, shipping

Phases 1B–1D turn a hypothesis into a validated, shippable change. The same
division of labor as [research mode](research-mode.md) applies: **Claude
proposes; the Python engine enforces.** Nothing an author writes reaches
execution or the database without passing code-side validation, and no
prompt can bypass the path guard, the contract, or the approval gates.

## The flow

```text
researchforge contract generate            # draft researchforge.yaml from project + scan
  (edit, especially execution.full_command)
researchforge contract validate            # schema + 14 semantic rules, repeat-safe
researchforge contract approve             # typed approval -> immutable contract version
        ▼
researchforge baseline run                 # frozen baseline in a detached worktree
        ▼
researchforge experiment plan hyp-001      # export context.json for Claude
Claude writes plan.yaml + patches/*.patch  # one unified diff per variant
researchforge experiment import ...        # 6-layer validation; protected patches
                                           #   are recorded as rejected, never run
researchforge experiment approve plan-001  # typed approval, worst-case wall time shown
researchforge experiment run plan-001      # screening baseline -> screening -> full,
                                           #   one experiment at a time
researchforge results show run-001         # ranking, Pareto trade-offs, rejected history
researchforge validate run-001             # repeated finalist runs -> validated
        ▼
researchforge ship branch                  # pre-ship confirmation, then a clean local
                                           #   branch on the frozen baseline (never pushed)
researchforge report build                 # engineering report (spec §16)
researchforge ship pr                      # OPT-IN: push that one branch + DRAFT PR
researchforge paper package                # research bundle (BibTeX, outline, data)
```

`researchforge status` shows the next step at every stage. All commands
support `--json`.

**Monitor live:** `researchforge serve --background` (after
`pip install "researchforge[serve]"`) starts a local, **read-only** web
monitor at `http://127.0.0.1:9000` (a free port is picked automatically if
that one is busy) — overview, research state, an experiments page that
refreshes as each funnel stage completes, and the live dashboard charts.
`experiment run`/`start` auto-start it on a TTY and print the URL; manage
it with `serve --status` / `serve --stop`. It binds 127.0.0.1 only by
default and opens the database in read-only mode, so watching can never
interfere with a run.

**Run lifecycle at a glance:**

| I want to… | Command |
|---|---|
| import + approve + run in one step | `experiment start plan.yaml` (one typed approval) |
| stop a running batch | Ctrl-C — safe; worktrees are isolated |
| continue an interrupted run | `experiment resume run-XXX` |
| discard an interrupted run | `experiment abandon run-XXX` (finished results are kept) |
| cancel a not-yet-run plan | `experiment cancel plan-XXX` |
| start the next batch | `experiment plan <hyp-id>` → `experiment start …` |

## The contract is the boundary

`researchforge.yaml` freezes the evaluation: primary metric + direction,
hard constraints, editable vs protected paths, commands, limits, network
mode, and the shipping flags. Approval hashes the file; any later edit is
detected as drift and execution refuses until re-approval creates the next
immutable version. Execution always uses the stored snapshot, never the
disk file.

## Isolation and honesty guarantees

- Every baseline/experiment/validation attempt runs in its own **detached
  git worktree** — the user's checkout and branches are never touched.
- Patches are validated with `git apply --check`; changed files are
  extracted by git, never trusted from the author; the **path guard**
  rejects protected/non-editable changes at import *and* re-checks after
  apply at run time (plus symlink refusal), before any command runs.
- Screening results are only compared to a **screening baseline** run with
  the same command; full/validation results compare to the frozen full
  baseline (same benchmark, same environment mode — enforced).
- `validated` structurally requires the full run plus repeated validation
  attempts: a one-off result can never be called validated.
- Rejected and failed experiments are first-class records; they appear in
  `results show`, the engineering report, and the research package.

## Shipping safety

- `ship branch` requires `shipping.allow_branch_creation` in the approved
  contract and a typed confirmation; it re-runs the full benchmark once
  (pre-ship confirmation) and refuses to ship on failure, constraint
  violation, or unconfirmed improvement. The branch is one clean commit on
  the frozen baseline (post-conditions asserted in code) and is **local
  only** — nothing is pushed.
- `ship pr` is opt-in twice: `shipping.allow_draft_pr` in the contract AND
  a typed `push` confirmation. It pushes exactly one ref and always opens
  a **draft** PR whose body is generated from recorded data.
- Tests: the contract's `test_command` runs before every evaluation; the
  commit and PR state explicitly that no new tests were authored (test
  authoring is a Claude-assisted step in Phase 1E).
