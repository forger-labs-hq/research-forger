---
name: researchforge-ship
description: Ship a validated experiment — clean local branch reconstructed from the baseline, engineering report, and optional draft PR. Use when the user wants the winning change as a branch, a report, or a PR.
---

# Ship a validated result

Three steps, each more outward-facing than the last. Every one is gated by
the engine (contract flags + typed confirmations) and each gate exists for
the user to open, not you.

## 1. Local branch (never pushed)

```bash
researchforge ship branch --json
```

Requires `shipping.allow_branch_creation` in the approved contract and a
typed confirmation — ask the user to run it, or use `--yes` only with their
explicit go-ahead in this conversation. The engine re-runs the full
benchmark once (pre-ship confirmation) and refuses to ship on failure,
constraint violation, or unconfirmed improvement. The result is one clean
commit on the frozen baseline, as a **local branch only** — the user's
checkout and remotes are untouched. Report the branch name, commit, and
pre-ship metric from the JSON.

## 2. Engineering report

```bash
researchforge report build --json
```

Writes `.researchforge/reports/engineering-report.md` — the full evidence
chain (objective → baseline → experiments → rejected approaches →
validation → recommendation → exact reproduction steps), built from recorded
data only. Offer to walk the user through it.

## 3. Draft PR (opt-in, pushes to the remote)

```bash
researchforge ship pr --json
```

This **pushes one branch to the user's remote** and opens a draft PR via
`gh`. It is double opt-in: `shipping.allow_draft_pr` must be true in the
approved contract AND a typed `push` confirmation is required. Confirm with
the user in chat before this step every time; never use `--yes` here unless
they just told you to push. If the contract flag is off, tell the user how
to enable it (edit `researchforge.yaml`, re-approve the contract) — do not
look for another way to push.

Also mention: `researchforge paper package` (researchforge-paper skill)
builds the research bundle from the same recorded data.

## Rules

- The Python engine is the boundary: never work around a validation error, a
  protected path, or an approval gate — fix the artifact or ask the user.
- Approvals belong to the user: never pass `--yes` or type a confirmation
  unless the user explicitly approved that step in this conversation.
- Ground every summary in stored data: quote only numbers returned by
  `--json` output or files under `.researchforge/` — never invent metrics.
