# Contributing To The Darts Detector

Thank you for considering contributing. This project is intended as a **long-lived community project** modelled after OBS Studio and Blender. We optimise for stability and maintainability over rapid feature additions.

Before contributing, please read:

1. [docs/PROJECT_CHARTER.md](docs/PROJECT_CHARTER.md) — what this project is and is not.
2. [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md) — current phase and scope.
3. [docs/DECISIONS.md](docs/DECISIONS.md) — locked architectural decisions you cannot violate.
4. [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — how we treat each other.

## Quick Start

```bash
git clone <repo-url>
cd darts-detector
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest tests/unit            # fast unit tests, no hardware needed
```

## Ways To Contribute

| Contribution | What's involved |
| --- | --- |
| **Bug report** | Open an issue using the bug template. Include OS, Pi or dev machine, reproduction steps, expected vs actual. |
| **Feature request** | Open an issue using the feature template. Explain the use case BEFORE proposing the implementation. |
| **Documentation fix** | PR directly. No issue needed for typos or small clarifications. |
| **Small bug fix** | PR directly. Include a regression test. |
| **New feature** | Open an issue first. Wait for maintainer feedback before opening a PR. |
| **Architecture change** | Submit an RFC issue. See "RFC Process" below. |
| **New plugin** | Plugins live outside this repo. Add a link to the community plugin index. |

## Before You Open A PR

- [ ] Read the relevant docs in `docs/` for the area you're touching.
- [ ] Make sure your change is in scope for the current phase (see [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md)).
- [ ] Make sure your change does not violate any locked decision in [docs/DECISIONS.md](docs/DECISIONS.md).
- [ ] Add or update tests. Detection-related changes MUST have replay tests.
- [ ] Update docs in the same PR. A change without doc updates is incomplete.
- [ ] Run `pytest tests/unit tests/integration` locally. All must pass.
- [ ] Validate your changes against the schema if you touched the wire format: `python -m darts_detector.tools.validate_events <event-file>`.
- [ ] Write a clear PR description: motivation, what changed, what's NOT in scope.

## Branch And Commit Conventions

- Branch names: `<type>/<short-description>`, e.g. `fix/triple-ring-boundary`, `feat/calibration-self-test`, `docs/clarify-coordinate-units`.
- Commit messages: imperative present tense, under 72 chars on the subject line.
- One logical change per commit. Squash before merge if your branch has noisy WIP commits.

## RFC Process (Big Changes)

A change is "big" if it:

- Adds a new public API surface.
- Removes or breaks an existing public API or wire-format field.
- Adds a new top-level module.
- Bumps the major version of any contract.
- Changes a locked decision in [docs/DECISIONS.md](docs/DECISIONS.md).

Big changes require an RFC:

1. Open an issue with the `rfc` label.
2. Use the RFC template: motivation, proposal, alternatives considered, migration plan, open questions.
3. Minimum discussion period: 14 days.
4. Architecture Owner accepts, rejects, or requests revisions.
5. On acceptance: add an ADR to [docs/DECISIONS.md](docs/DECISIONS.md) and reference it from the implementation PR.

Don't open a PR for an architecture-level change before its RFC is accepted. It will be closed.

## Code Style

- **Python 3.11+.**
- **Formatter**: `black` (default config).
- **Linter**: `ruff` (config in `pyproject.toml`).
- **Type hints** required on all public functions. `mypy --strict` clean for `src/darts_detector/api_public/`. Best-effort elsewhere.
- **Docstrings** required on public functions and modules. Include stability tier as the first line: `@public-stable`, `@public-experimental`, `@internal`, or `@plugin`.

## Testing Expectations

- Detection or scoring change → replay dataset test required.
- Wire-format change → schema validation test required, schema file updated in the same PR.
- Config or calibration profile change → migration test required if it's a major bump.
- Performance-sensitive change → before/after latency numbers in the PR description.
- All changes → unit tests for the affected module.

See [docs/ACCURACY_AND_TESTING.md](docs/ACCURACY_AND_TESTING.md) for the full testing philosophy.

## Performance Awareness

Performance on Raspberry Pi 5 4GB is a **hard requirement**, not a "nice to have". Per-stage budgets are in [docs/LATENCY_BUDGET.md](docs/LATENCY_BUDGET.md). A PR that pushes a stage past 150% of its budget is a warning; past 200% blocks merge.

If you don't have Pi 5 hardware, say so in your PR. A maintainer will verify on hardware before merging detection-path changes.

## Backwards Compatibility

This is non-negotiable. See [docs/VERSIONING.md](docs/VERSIONING.md). A PR that breaks a stable contract without going through the deprecation cycle will be closed.

## License Of Contributions

By submitting a contribution, you agree that your contribution is licensed under the **GNU General Public License v3.0 or later** ([LICENSE](LICENSE)), and that you have the right to submit it.

We do not require a CLA. We do enforce GPL-3.0 compatibility for any code in this repository, including code in `plugins/` and `research/`.

## Working With AI Agents

Parts of this project are developed with the help of AI subagents defined in `.claude/agents/`. If you submit a PR generated with AI assistance:

- It's fine, and it's increasingly common.
- The same rules apply: tests, docs, scope, decisions.
- The Project Manager subagent reads `MASTER_PLAN.md` first; if you're using AI yourself, point it at the relevant docs too.
- Disclosure is appreciated but not required.

## Getting Help

- Read the docs in `docs/` first; they cover most architectural questions.
- Open an issue with the `question` label for things not covered.
- Be patient with reviewers. We're optimising for stability over speed.

## Maintainer Response Times

- Bug reports with security implications: aim within 7 days.
- Other bug reports: aim within 30 days.
- PRs: aim within 30 days for first review. Architecture-touching PRs may take longer.
- RFCs: minimum 14-day discussion period; decisions within 60 days of opening.

These are aims, not guarantees. The project is maintained by volunteers.

## Anti-Patterns To Avoid

- Opening a giant PR with multiple unrelated changes — split it up.
- Adding a dependency without justifying it in the PR description.
- "Fixing" a comment or rename in passing while changing logic — keep changes focused.
- Claiming accuracy improvements without replay-dataset numbers.
- Disabling tests to make CI pass.
- Adding TODO/FIXME without an issue link.
- Skipping doc updates.

Thank you for contributing.
