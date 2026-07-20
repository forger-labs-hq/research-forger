# Security model and honest limitations

ResearchForge Phase 1 provides **local experiment isolation, not a hardened
sandbox for hostile code**. Run it only on repositories you own or trust —
the contract records this acknowledgement (`execution.trusted_repository`).

## What isolation you get

- **Git worktrees, always.** Every baseline, experiment, and validation
  attempt runs in its own detached worktree under
  `.researchforge/worktrees/` — your checkout, branches, and HEAD are never
  touched, and experiment state can be deleted safely.
- **The path guard.** Patches may only touch the contract's
  `editable_paths`; `protected_paths` plus the always-protected set
  (`.researchforge/`, `.git/`, `researchforge.yaml`) are enforced at import
  *and* re-checked after apply at run time, with symlink refusal. Changed
  files are extracted by git from the patch, never trusted from a
  description.
- **Resource limits.** The contract's timeout, CPU, and memory limits are
  enforced outside the benchmark process; timeouts kill the whole process
  group (SIGTERM, then SIGKILL).
- **The immutable contract.** Approval hashes `researchforge.yaml`; any
  edit is detected as drift and execution refuses until re-approval.
  Execution always uses the stored snapshot, never the disk file.

## Docker mode (preferred when available)

Containers run with the locked-down defaults from the spec: `--rm`,
`--network=none` (unless the contract opts into network), CPU/memory/pids
limits, `--security-opt=no-new-privileges`, `--cap-drop=ALL`, a non-root
user, and only the experiment worktree + artifact directory mounted. The
Docker socket, your home directory, SSH keys, cloud credentials, and other
repositories are **never** mounted.

Docker is still not a guarantee against hostile code, and behavior differs
across Linux/macOS/Windows. Rootless Docker is recommended where supported.

## `.venv` mode

A Python virtualenv is **dependency isolation only** — benchmark code runs
as your user with your filesystem access. ResearchForge prints this warning
before venv runs; take it seriously and prefer Docker for anything you did
not write yourself.

## Network and secrets

- Experiments default to `network.mode: none`.
- Only environment variables named in
  `secrets.forward_environment_variables` are forwarded; values are never
  stored, and logs redact them as `<redacted:NAME>`.
- Results produced with network access depend on external services and are
  marked accordingly.

## What Claude cannot do

The Claude skills are UX, not a security boundary (spec principle 6). Every
gate above is enforced in Python regardless of any prompt or skill text:
unapproved plans cannot run, protected-path patches are rejected and never
executed, one-off results cannot be called validated, and nothing is pushed
without the contract flag plus a typed confirmation. Details in
[claude-mode.md](claude-mode.md).

## Honest limitations (read before trusting a result)

- Results are measured on one machine in one environment mode; they may not
  generalize beyond the tested conditions — reports say so explicitly.
- ResearchForge does not guarantee novelty, patentability, or
  publishability; hypothesis evidence is graded (published claim vs
  interpretation vs speculation) and weak evidence is labeled as such.
- A failed baseline blocks experiments rather than producing numbers that
  mean nothing; invalid benchmark output is rejected, not coerced.
- Analytics are opt-in and local-only (`researchforge analytics`);
  nothing is ever transmitted. See the collection notice printed by
  `researchforge analytics enable`.
- The monitoring server (`researchforge serve`) opens the database with
  sqlite's read-only mode and exposes no mutating routes; it binds
  127.0.0.1 by default and warns loudly if you bind anything else, because
  anyone who can reach it can read your research notes and results. Its
  pages carry one small inline script (no external resources) that
  remembers which sections you opened across auto-refreshes; the static
  `dashboard.html` file remains script-free.

Report security issues via GitHub issues (or privately to the maintainer
for anything sensitive).
