# Agent Team

This project is built by a team of AI subagents coordinated by a Project Manager. You (the user) talk to the Project Manager; the PM delegates to specialists. Every agent reads documentation before it acts, and updates documentation when it changes anything.

The goal of this structure is **minimum token waste**, **maximum doc adherence**, and **zero scope drift**.

## The Team

| Agent | Role | Primary Docs (Must Read) | Tools |
| --- | --- | --- | --- |
| `project-manager` | Single point of contact for the user. Decides which specialist to delegate to. Updates `MASTER_PLAN.md` after every meaningful change. | `PROJECT_CHARTER.md`, `MASTER_PLAN.md`, `PHASED_IMPLEMENTATION.md`, `DECISIONS.md`, `AGENT_RULES.md`, `RISKS.md`, `VERSIONING.md` | Read, Glob, Grep, Edit, Write, TodoWrite, Agent |
| `doc-guardian` | Owns documentation integrity. Reviews every change for doc drift. Updates docs after code changes. Enforces versioning policy. | All `docs/*.md`, `schemas/*.json`, `CONTRIBUTING.md` | Read, Glob, Grep, Edit, Write |
| `cv-detection` | Implements detection pipeline (Phases 5, 5.5, 6, 7). Lives inside the CV hot path. Also owns hand and board-clear detection (Phase 5.5). | `DETECTION_PIPELINE.md`, `LATENCY_BUDGET.md`, `ARCHITECTURE.md`, `RISKS.md`, `GLOSSARY.md` | Read, Glob, Grep, Edit, Write, Bash |
| `calibration-scoring` | Implements calibration (Phases 3, 3.5), scoring (Phase 4), and the throw lifecycle state machine (Phase 7.5). Owns the mm coordinate boundary and the only-module-that-updates-baseline rule. | `CALIBRATION_SYSTEM.md`, `SCORING_ENGINE.md`, `DETECTION_PIPELINE.md` (Phase 7.5), `DECISIONS.md` (`D-004`, `D-008`, `D-015`, `D-016`), `GLOSSARY.md` | Read, Glob, Grep, Edit, Write, Bash |
| `test-qa` | Writes unit, integration, and replay tests. Owns the smoke test for every phase. Reports accuracy and latency against `LATENCY_BUDGET.md`. Enforces backwards-compat tests per `VERSIONING.md`. | `ACCURACY_AND_TESTING.md`, `DEBUG_AND_REPLAY.md`, `LATENCY_BUDGET.md`, `RISKS.md`, `VERSIONING.md` | Read, Glob, Grep, Edit, Write, Bash |

## Interaction Model

```text
USER
 │
 ▼
PROJECT MANAGER  ← single point of contact
 │
 ├──► doc-guardian      (docs)
 ├──► cv-detection      (detection pipeline)
 ├──► calibration-scoring (calibration + scoring)
 └──► test-qa           (tests + smoke tests + metrics)
```

The user only speaks to the Project Manager. The PM delegates. Specialists report back to the PM, who summarises for the user.

Specialists do not call each other directly. If a specialist needs cross-cutting work, it reports back to the PM, who decides whether to spawn another specialist.

## Token-Efficiency Rules

These rules exist to keep the project moving fast on a token budget:

1. **Read narrowly.** Each agent reads only the docs in its "Primary Docs" column unless the PM explicitly says otherwise.
2. **Refer, don't quote.** Agents cite document paths (e.g. `DECISIONS.md D-004`) instead of pasting doc content into responses.
3. **Use `Grep` and `Glob` before `Read`.** Find the section before reading the file.
4. **No speculative exploration.** If a task doesn't need a file, don't open it.
5. **Tight summaries.** Specialists report under 300 words unless code review requires more.
6. **One specialist per delegated task.** PM does not double-delegate. Parallel delegation only when two tasks are genuinely independent.
7. **Tests come from `test-qa`, not from implementers.** Avoids implementer-writes-its-own-test bias.

## Drift Prevention Rules

These rules exist to keep accuracy high and avoid silent contract breakage:

1. **Read `MASTER_PLAN.md` and `AGENT_RULES.md` before any work.** Mandatory first step for every agent.
2. **No code changes without reading the phase doc.** Implementation agents read the relevant `docs/*.md` for the phase they're working on before editing code.
3. **Schema is authoritative.** Any change to the Dart event shape MUST update `schemas/dart-event.schema.json` first, then code.
4. **Doc Guardian reviews contract-touching changes.** PM routes any change affecting `API_AND_WEBSOCKET_CONTRACT.md`, `SCORING_ENGINE.md`, `DETECTION_PIPELINE.md`, or `CALIBRATION_SYSTEM.md` through `doc-guardian` before declaring done.
5. **Decisions are immutable without ADR.** No agent edits `DECISIONS.md` to change an existing decision; it appends a new entry that supersedes the old.
6. **Latency budget is enforced.** `test-qa` flags any stage that exceeds 150% of its budget; merges blocked at 200%.
7. **No accuracy claims without measured data.** `test-qa` rejects any PR description with "99%" or similar unless backed by a labelled dataset run.

## When To Spawn What

| User Says | PM Delegates To | Why |
| --- | --- | --- |
| "Start Phase 1" | `cv-detection` (orchestrates capture) + `test-qa` (smoke test) | Phase 1 is capture-focused; smoke test runs in parallel. |
| "Build the scoring engine" | `calibration-scoring` → `test-qa` | Implementation then validation. |
| "Why is detection slow?" | `cv-detection` (profile) → `test-qa` (verify) | Profiling and verification. |
| "Update the JSON contract" | `doc-guardian` → `calibration-scoring` (scoring impact) → `cv-detection` (latency block impact) | Doc change first, then code. |
| "Run the labelled dataset" | `test-qa` | Owns metrics. |
| "Is the plan still on track?" | PM answers directly from `MASTER_PLAN.md` | No specialist needed. |

## How To Invoke

Once the agents are installed under `.claude/agents/`, you talk to the project manager in two ways:

1. **Mention by name:** "Hand this to the project-manager."
2. **By task:** Claude Code's automatic delegation will route based on the agent description.

You can also bypass the PM and call a specialist directly if you know exactly who you need, but the PM model is the recommended path because it preserves coordination.
