# Claude Code assets

The ResearchForge Claude skills live **inside the Python package** — at
[`src/researchforge/claude/skills/`](../src/researchforge/claude/skills/) —
so that `pip install researchforge` carries them and
`researchforge init --claude` (or `researchforge claude install`) can copy
them into a project's `.claude/skills/`.

This directory exists only as a pointer for people who expect the spec's
`claude-plugin/` layout. See [docs/claude-mode.md](../docs/claude-mode.md)
for how the skills work and what they are (and are not) allowed to do.

No hooks ship in Phase 1: the spec defines no hook behavior, and skills are
deliberately not a security boundary — enforcement lives in the Python
engine.
