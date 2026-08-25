---
id: '007'
title: 'Final build checkpoint: hex and block-surface parity, flashable hex, handoff
  notes'
status: open
use-cases: [SUC-001, SUC-003]
depends-on: ['006']
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Final build checkpoint: hex and block-surface parity, flashable hex, handoff notes

## Description

Standing per-sprint build-checkpoint-ticket convention (established
sprint 008, followed by sprints 004/005/009), and the single most
important ticket in this sprint specifically: this sprint's entire
claim is "not one line of student-visible behavior... changes," and a
build succeeding — which every ticket 001-006 already required — is
not the same claim as "the blocks still work" or "the hex is the
robot's own prior behavior, not a new one." This ticket produces the
comprehensive, end-to-end evidence tickets 001-006's per-ticket checks
were each individually necessary but not, together, sufficient for.

Compares the **final** state (all six modules in place, `main.ts`
gone) against the **pre-split baseline** ticket 001 archived before
touching any code:

1. **Hex comparison.** Build the final tree; diff the resulting `.hex`
   against ticket 001's archived baseline. Byte-identical (or
   differing only in source-map/file-path debug metadata with no
   runtime effect) is the strongest available evidence.
2. **Block-surface comparison.** If the hex isn't byte-identical (a
   likely, harmless cause: source paths embedded in debug info now
   name six files instead of one), generate and compare the block
   metadata instead — captions, `group=` values, parameter ranges,
   toolbox order — against ticket 001's archived listing. This is the
   sprint's actual minimum bar, not the hex diff: "the refactor
   compiled" is a weaker claim than "the blocks still work."
3. **Simulator/test-program parity.** Run `test/test.ts` and
   `test/testrig.ts` in the PXT simulator one more time against the
   fully-split tree and confirm output matches the baseline — these
   are the load-bearing surface the no-initialiser constraint exists
   to protect.
4. **Full host suite.** Run `tests/host/` in full — this sprint never
   touches C++, so this is a regression fence, not new coverage.
5. **Flashable hex + handoff notes.** Package the final build's `.hex`
   as a handoff artifact (per sprint 008's convention) — this ticket
   does **not** flash it to a physical robot or otherwise require
   hardware; that validation is sprint 011's job. Write brief handoff
   notes: what was compared, what matched, and any of this sprint's
   Open Questions (overlay §15) that resolved differently than
   planned during tickets 001-006 (e.g. if the non-exported cross-file
   reference question needed the export fallback anywhere — name
   which symbols, if so).

## Acceptance Criteria

- [ ] A real, final build (all six new modules, `main.ts` gone)
      succeeds via the project's existing `tools/make_deploy.py` /
      scratch-build workflow.
- [ ] Resulting `.hex` compared against ticket 001's archived
      pre-split baseline; outcome (byte-identical, or the specific
      differences found and why they're judged harmless) stated
      explicitly in this ticket's completion notes — not asserted, not
      omitted.
- [ ] Generated block-surface listing (captions, `group=` values,
      parameter ranges, toolbox order) compared against ticket 001's
      archived baseline listing; any difference is a finding this
      ticket must explain or treat as a sprint-blocking regression, not
      wave through.
- [ ] `test/test.ts` and `test/testrig.ts` simulator runs match the
      baseline exactly.
- [ ] Full `tests/host/` suite passes (regression fence).
- [ ] `test_pxt_manifest_completeness.py` passes.
- [ ] A flashable `.hex` is produced and named as this sprint's
      handoff artifact; **not flashed or run on hardware as part of
      this ticket's acceptance** — that's out of scope here (sprint
      011's job).
- [ ] Handoff notes written per the Description's item 5, including an
      explicit statement of whether the cross-file non-exported-
      reference question (overlay §15's central Open Question) needed
      its export fallback anywhere, and if so, exactly which symbols.
- [ ] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: this ticket runs no new code changes of its own beyond
what tickets 001-006 already produced — it is verification and
packaging. If any comparison in the Description surfaces a real
regression, that is an exception this ticket throws (per the
sprint-planner's Exception Protocol, surfaced back through the
programmer's own equivalent path) rather than something this ticket
silently patches — a behavior-neutrality claim that needed a fix
during its own proof ticket is a finding worth a stakeholder's
attention, not a footnote.

**Files to create**: none (a packaged `.hex` artifact and this
ticket's own completion/handoff notes, not new source).

**Files to modify**: none.

**Testing plan**: as enumerated in Acceptance Criteria — hex diff,
block-surface diff, simulator/testrig parity, full host suite,
manifest completeness.

**Documentation updates**: this ticket's own completion notes serve as
the sprint's handoff record; no `docs/design/` content changes beyond
what ticket 006 already made.

## C++11 Gate Coverage

Not applicable — this ticket runs builds and comparisons; it changes
no C++ source (none of this sprint's tickets do). The full existing
C++11 gate (`test_cxx11_syntax_gate.py`, part of the `tests/host/` run
above) still executes as part of the regression fence, but nothing in
this ticket's own scope is C++. No robot required — a flashable hex is
produced as a handoff artifact only, not flashed or exercised on
hardware here.

## Testing

- **Existing tests to run**: full `pytest tests/host/`;
  `test_pxt_manifest_completeness.py` (included in the above);
  `tsc -p .`.
- **New tests to write**: none.
- **Verification command**: real PXT build via
  `tools/make_deploy.py` (or equivalent); `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`;
  manual hex/block-surface diff against ticket 001's archived
  baseline.
