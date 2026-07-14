# Changelog

## 0.1.0 — Phase 1 open-source beta (unreleased)

The complete local pipeline, Claude-first.

- **Research intelligence**: arXiv discovery (dedup + deterministic
  ranking), the Claude↔CLI synthesis handshake (landscape + hypotheses with
  graded evidence), citation-backed research report.
- **Experiment contract**: `researchforge.yaml` wizard, 14 semantic
  validation rules, typed approval into immutable versions with drift
  detection.
- **Isolated execution**: detached git worktrees per attempt, Docker
  (locked-down defaults) and `.venv` runners, path guard with run-time
  re-check, process-group timeouts, secrets redaction.
- **Experiment funnel**: Claude-authored patch variants through screening →
  full benchmark → repeated validation; hard constraints; Pareto ranking
  with honesty caveats; rejected/failed experiments preserved.
- **Shipping**: clean branch reconstructed from the frozen baseline
  (pre-ship re-validation, post-conditions asserted), opt-in draft PR via
  gh, engineering report, research package (BibTeX, outline,
  reproducibility bundle).
- **Claude Code experience**: 12 installable project skills
  (`researchforge init --claude`), manifest-based installer that never
  clobbers user edits.
- **Beta tooling**: tested launch-demo examples, opt-in local-only
  analytics, security notes.
