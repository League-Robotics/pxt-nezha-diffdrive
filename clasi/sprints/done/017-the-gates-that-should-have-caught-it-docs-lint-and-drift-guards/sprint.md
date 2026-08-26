---
id: '017'
title: "The gates that should have caught it \u2014 docs, lint, and drift guards"
status: done
branch: sprint/017-the-gates-that-should-have-caught-it-docs-lint-and-drift-guards
use-cases: []
issues:
- design-doc-set-fails-validation.md
- travel-calib-not-propagated-to-docs-and-tools.md
- design-docs-assert-fixed-limitations.md
- src-design-md-is-half-sprint-history.md
- stale-paths-survived-the-sprint-013-sweep.md
- comment-standard-and-archaeology-ratchet.md
- no-lint-or-typecheck-gate.md
- host-harness-masks-include-path-errors.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 017: The gates that should have caught it — docs, lint, and drift guards

## Goals

The 2026-08-26 review found a green 597-test suite sitting on top of a Critical
geometry defect, a failing design-doc validator, a calibration constant that
never propagated, and 40+ stale paths from a sprint whose final ticket was a
stale-path sweep. **Every item in this sprint ships the guard that would have
caught it.** A fix without a guard is a fix that gets redone.

## Problem

- `clasi design validate` **fails**: sprint 013's five `src/` subdirectories have
  no `DESIGN.md`, and sprint 013's own final-sweep ticket did not run the
  validator.
- `travelCalib` 0.7878 never reached three design docs or two bench tools —
  `tour_watch.py` and `tour_chart.py` now mis-scale by 2.8%, in the two tools
  used to *measure* accuracy.
- `src/DESIGN.md` S10 asserts three limitations that sprints 005 and 010 fixed.
  Three status headers are stale by 2 to 10 sprints; `overview.md` still tells a
  reader the radio command plane is "planned, not built".
- `src/DESIGN.md` is **44% sprint-history appendix** (902 of 2045 lines), and
  something in the sprint-close path appends one section per sprint.
- 40+ stale `main.ts` and pre-013 paths in live source, plus five comment
  references to functions that no longer exist.
- Comment volume is **1.22 lines per code line** in project-owned `src/` against
  **0.05** in the vendored kernel beside it. Sprint 009's dedicated cleanup
  bought 8%, and every file touched since has grown back past its pre-cleanup
  count.
- `ruff` reports 211 findings with no configuration; six are real.
  `tsconfig.json` cannot run — `typescript` is not installed — so 1149 lines of
  student-facing TypeScript have no standalone check.
- The host harness passes `-I src`, so it cannot see include-path errors the
  real cloud build fails on.

## Solution

Fix each, and pair each with a mechanical guard in the
`test_pxt_manifest_completeness.py` style — no compiler, reads files as text,
cheap, and that pattern has held where prose sweeps have not:

| Fix | Guard |
|---|---|
| Five subsystem `DESIGN.md` | `clasi design validate` on the sprint-close checklist |
| `travelCalib` propagation | a drift test, or delete the mirrored copies outright |
| Stale paths and dangling refs | a test that greps `src/`/`docs/` for `src/<file>` paths not on disk |
| Comment volume | the archaeology-marker budget, ratcheting down from 363 |
| Lint noise | a `[tool.ruff.lint]` block so `ruff check` means something |
| No TS check | add `typescript` + a pytest wrapper, or delete `tsconfig.json` |
| `-I src` blind spot | compile the harness the way the real build does |

Two items are decisions rather than fixes. **The comment standard should land
before any cleanup pass**, or sprints 018+ refill it exactly as 010–013 refilled
sprint 009's. And `tsconfig.json` should be made real or deleted; maintaining a
file nothing reads is the worst of the three options.

## Success Criteria

- [ ] `clasi design validate` returns `ok: true`, and the validator is on the
      sprint-close checklist.
- [ ] No file in `src/`, `docs/design/` or `tools/` cites `travelCalib` 0.8102.
- [ ] `src/DESIGN.md` S10 contains no claim contradicted by the code; the three
      status headers are current; `overview.md` describes what exists.
- [ ] `src/DESIGN.md` S12–S16 removed, and nothing re-appends them at close.
- [ ] Zero `main.ts` references and zero non-existent `src/<file>` paths in live
      source, **pinned by a test**.
- [ ] The archaeology-marker budget test exists, starts at or below 363, and the
      comment standard is in `docs/code-review/guidelines.md`.
- [ ] `ruff check tools tests` is clean under a committed config.
- [ ] The TypeScript decision is made and executed.
- [ ] The harness compiles with the real build's include paths.

## Scope

### In Scope

`docs/design/*`, `src/**/DESIGN.md`, `tools/DESIGN.md`,
`docs/code-review/guidelines.md`, `pyproject.toml`, `package.json`,
`tsconfig.json`, `tests/host/` (new guard tests and the harness include paths),
`tools/tour_watch.py`, `tools/tour_chart.py`.

### Out of Scope

**The comment cleanup itself.** This sprint lands the standard and the ratchet;
the ~470-line work order in
[`comment-audit.md`](../../../docs/code-review/2026-08-26/raw/comment-audit.md)
is a later sprint, deliberately after the guard exists. Exception: the two
comments in `blocks/motion.ts` that are *wrong* rather than merely long — the
namespace docstring's fiber claim and `isMoving()`'s "checks state only" — are
corrected in sprint 015 with the code they describe.

No firmware behaviour changes in this sprint. That is what makes it safe to run
in parallel with hardware work if the branch situation allows.

## Test Strategy

This sprint *is* test strategy. The pattern to follow is
`tests/host/test_pxt_manifest_completeness.py`: it reads `pxt.json` and the
filesystem as text, invokes no compiler, runs in milliseconds, and has caught
real manifest drift twice. Every guard here should look like it.

The one item needing care is the `-I src` fix: changing the harness's include
paths may surface latent include errors across the whole tree. That is the
point, but it should be its own ticket so the fallout is isolated.

## Architecture

N/A — no production code changes. The one structural decision is what
`src/DESIGN.md` is *for*: S1–S11 describe the system, S12–S16 narrate sprints.
Removing the latter and stopping the append is a decision about the document's
contract, recorded in `docs/design/design.md`.

## Use Cases

### SUC-001: A reader trusts the design docs
Parent: UC-013
- **Acceptance**: no claim in `src/DESIGN.md` S10 or the status headers is
  contradicted by the code; the validator is green.

### SUC-002: A sprint cannot silently leave stale paths behind
Parent: N/A (process)
- **Acceptance**: a test fails when a `src/<file>` path in source or docs does
  not exist on disk.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] Architecture review passed (or skipped — no production code)
- [ ] **Stakeholder has ruled on the comment standard** (write-time rule + budget)
- [ ] **Stakeholder has ruled on `tsconfig.json`**: make it real, or delete it

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Five subsystem `DESIGN.md`; validator green; validator on the sprint-close checklist | — |
| 002 | Propagate `travelCalib` 0.7878; single-source or drift-test what remains | — |
| 003 | `src/DESIGN.md` S10 truthfulness pass; three status headers; `overview.md` | — |
| 004 | Remove S12–S16; stop the per-sprint append | 003 |
| 005 | Stale-path sweep **with** the guard test | — |
| 006 | Comment standard in `guidelines.md` + the archaeology-marker ratchet test | — |
| 007 | `ruff` config; the six real findings | — |
| 008 | `tsconfig.json` decision executed | — |
| 009 | Harness include paths match the real build (`host-harness-masks-include-path-errors`) | — |
| 010 | **Build checkpoint** (standing convention, always last) | 001–009 |

Tickets execute serially in the order listed.

**Sizing note.** Ten tickets, but every one is small, independent, and
doc/test-only. If it needs trimming, 007/008/009 are a coherent "tooling gates"
split.
