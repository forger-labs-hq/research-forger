# Claude mode — driving ResearchForge from Claude Code

Phase 1E packages the whole workflow as project-level Claude Code skills, so
neither you nor Claude has to remember CLI details. The division of labor is
unchanged from [research mode](research-mode.md) and
[experiment mode](experiment-mode.md): **Claude proposes; the Python engine
enforces.** Skills are instructions, not a security boundary — every gate
they describe (path guard, contract drift, approval state, schema
validation, execution limits) is enforced by Python code and holds no matter
what a skill, a prompt, or Claude itself says.

## Install

```bash
pip install "researchforge[serve]"   # (or from source: pip install -e ".[dev]")
researchforge claude install --user  # recommended: skills in EVERY session
```

With `--user`, the skills live in `~/.claude/skills/` and every Claude Code
session sees them — start any conversation with `/researchforge-start` and
name the folder to work in. Prefer per-project skills? In the project
folder, `researchforge init --claude` copies them into `.claude/skills/`
(and initializes `.researchforge/`) — then open Claude Code in that folder.
Skills can also be managed directly:

```bash
researchforge claude install     # install/refresh (never clobbers your edits)
researchforge claude status      # installed / modified / missing per skill
researchforge claude uninstall   # removes only what ResearchForge installed
```

Installation is manifest-based (`.researchforge/claude-skills-manifest.json`
records a sha256 per installed file): a skill you edited — or any other
content in `.claude/skills/` — is never overwritten or removed without
`--force`.

Add `--user` to any of those commands to target `~/.claude/skills/` instead
of the repository — the skills then load in **every** project on this
machine (manifest: `~/.claude/researchforge-claude-skills-manifest.json`).

## Skills not showing up?

The skills are plain files — nothing about them is tied to a Claude
account. If `/researchforge-…` doesn't appear:

1. **Right directory?** Project-level skills only load when the session is
   opened **in** the repository that contains `.claude/skills/` — starting
   a new session from the app home screen (no project folder) or from
   another directory won't show them, even though the install succeeded.
   Open the session in the repo (terminal: `cd <repo> && claude`; desktop
   app: open the folder as the session's project). Verify the files with
   `researchforge claude status` from that directory.
2. **Switched Claude accounts?** Claude Code tracks workspace trust and
   settings per account — after switching, the project may need to be
   re-trusted in a fresh session before its `.claude/` content loads.
   Restart the session in the repo and accept the trust prompt.
3. **Want them everywhere, account-proof?** `researchforge claude install
   --user` puts them in `~/.claude/skills/`, which applies to all projects
   regardless of per-project state.

## The skills

| Skill | What it drives |
|---|---|
| `/researchforge-start` | new project (either journey) or status-based resume |
| `/researchforge-doctor` | dependency checks, environment limitations |
| `/researchforge-papers` | arXiv search, stored-paper review |
| `/researchforge-landscape` | synthesis handshake: context → landscape.yaml → validated import |
| `/researchforge-hypotheses` | evidence-linked hypotheses → validated import |
| `/researchforge-baseline` | contract draft/validate/approve + frozen baseline |
| `/researchforge-plan` | experiment variants: patches → 6-layer import → approval |
| `/researchforge-run` | screening → full funnel execution, resume |
| `/researchforge-results` | grounded summaries: ranking, Pareto, rejections, the HTML dashboard |
| `/researchforge-validate` | repeated finalist runs → `validated` |
| `/researchforge-ship` | local branch → engineering report → opt-in draft PR |
| `/researchforge-paper` | research package (BibTeX, outline, data) |

Each skill follows the same loop:

1. gather intent from the user;
2. call deterministic CLI commands with `--json`;
3. read the structured output (never parse prose);
4. synthesize or implement **within the exported schema** — the
   landscape/hypotheses/plan handshakes embed `model_json_schema()` in their
   context files;
5. pass the artifact back through the importer, which validates
   transactionally and returns field-level errors as a `--json` payload the
   skill uses to self-correct;
6. ask the user before anything consequential — contract approval, plan
   approval, validation runs, shipping — because typed confirmations belong
   to the user, and `--yes` requires their explicit go-ahead in chat;
7. summarize progress strictly from recorded data.

## What Claude cannot do (by construction)

These hold even if a skill file is edited to say otherwise:

- **run an unapproved plan** — execution checks approval state in the
  database, not the conversation;
- **touch protected paths** — patches are checked at import *and* re-checked
  after apply in the worktree; a protected-path patch is recorded as
  rejected and never runs;
- **make a metric look better by editing the benchmark** — benchmarks belong
  in `permissions.protected_paths`, and changed files are extracted by git
  from the patch itself, never trusted from a description;
- **call a one-off result validated** — `validated` structurally requires
  the full benchmark plus repeated validation runs;
- **push anything silently** — `ship branch` is local-only; `ship pr` needs
  the contract flag *and* a typed `push` confirmation.

Failed validation is explained in Claude: importers return structured
field-level errors, and the skills instruct Claude to fix exactly those
fields and re-import rather than working around the gate.

The CLI remains fully usable without Claude — every skill step is a plain
command documented in [research-mode.md](research-mode.md) and
[experiment-mode.md](experiment-mode.md).
