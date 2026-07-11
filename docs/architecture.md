# Architecture — Phase 0

> This document describes the codebase as it exists after **Phase 0**
> (repository foundation) only. See
> [RESEARCHFORGE_PHASED_BUILD_SPEC.md](RESEARCHFORGE_PHASED_BUILD_SPEC.md)
> for the full product spec and phase-by-phase plan.

## Module layout

```
src/researchforge/
├── cli.py       # Typer app: doctor / init / status
├── config/      # path conventions for .researchforge/
├── domain/      # framework-agnostic pydantic models
├── storage/     # sqlite persistence boundary
└── utils/       # small helpers not tied to a specific domain concept
```

**`cli.py`** is a thin presentation layer. It parses arguments, calls into
`config`/`storage`/`domain`/`utils`, and prints human or `--json` output. It
contains no business logic of its own.

**`domain/`** holds pydantic models with no dependency on the CLI or on
storage. Phase 0 defines only `Project` (`domain/project.py`) — the minimum
entity needed for `init`/`status` to have something to persist. The spec's
full future domain model (`Paper`, `EvidenceClaim`, `Hypothesis`,
`ExperimentContract`, `ExperimentRun`, `Finding`, `Deliverable` — see spec
§12) is introduced incrementally as each entity's phase is implemented, not
stubbed out ahead of time.

**`storage/`** is the sqlite persistence boundary (`db.py` for
connection/schema, `project_repository.py` for `Project` CRUD). Row↔model
conversion is centralized here so no other module writes raw SQL. JSON/JSONL
is reserved (per the spec's technical choices) for portable *run artifacts*
in later phases — Phase 0 doesn't produce any run artifacts yet, so it isn't
used here.

**`config/paths.py`** is the single place that knows the on-disk layout of
`.researchforge/`. Everything else asks it for paths rather than
constructing them inline.

**`utils/`** holds helpers not owned by a specific domain concept — currently
just `system_checks.py` backing `doctor`.

## Deferred modules

The following directories from the spec's eventual full layout (§22) are
intentionally **not** created yet: `research/`, `hypotheses/`, `contracts/`,
`execution/`, `evaluation/`, `reporting/`, `shipping/`, `claude/`,
`claude-plugin/`, `project/`, `repository/`. Each arrives with the phase that
needs it (Phase 1A onward).

## The `.researchforge/` on-disk contract, today vs. eventually

Today, `.researchforge/` contains exactly one file:

```
.researchforge/
└── researchforge.db     # sqlite: meta(schema_version), projects(...)
```

`researchforge init` creates this and nothing else. It is idempotent — running
it again when already initialized is a no-op that reports the existing state.

The eventual full layout (spec §9.2) also includes `worktrees/`, `artifacts/`,
`papers/`, and `reports/`. Phase 0 deliberately does not pre-create these:
they have no consumer yet, and creating empty directories today risks the
layout drifting before it's exercised by real code. **Future Phase 1C
execution code (e.g. `execution/worktrees.py`) is responsible for creating
these lazily on first use** — it must not assume `init` already created them.

## Storage assumptions

Phase 0 assumes exactly one `Project` row per `.researchforge/` directory —
there is no multi-project support yet. The `projects` table is still keyed by
`id` (not a singleton file), so adding multi-project support later is
additive rather than a schema rewrite.
