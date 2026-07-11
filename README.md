# ResearchForge

*From papers to proof.*

ResearchForge is an open-source, Claude-first research and experimentation
CLI. It studies relevant literature, maps promising methods to your idea or
repository, creates testable hypotheses, and benchmarks competing
implementations against a controlled baseline in local, isolated workspaces.

**Status:** Phase 0 — repository foundation. Only the `doctor`, `init`, and
`status` commands exist so far. See
[docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md](docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md)
for the full phased roadmap and [docs/architecture.md](docs/architecture.md)
for how the codebase is organized today.

## Install

No package is published yet. Install from source in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart

```bash
researchforge --help
researchforge doctor
researchforge init
researchforge status
```

Every command supports `--json` for machine-readable output.

## License

Apache-2.0 — see [LICENSE](LICENSE).
