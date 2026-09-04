---
id: '005'
title: Strip units from identifier names in shims.cpp, comms/, blocks/, platform/
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['004']
github-issue: ''
issue: code-review/strip-units-from-identifier-names.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Strip units from identifier names in shims.cpp, comms/, blocks/, platform/

## Description

The identifier-naming cleanup for everything **outside** `src/motion/`
(that half rode with ticket 003, per the issue's own scope note).
Sequenced after ticket 004 so this doesn't rename fields that ticket
004's config-surface rewrite is simultaneously restructuring in the
same files (`shims.cpp`, `comms/wire_adapter.cpp`, `blocks/motion.ts`).

Per `.claude/rules/no-units-in-identifiers.md` and issue
`strip-units-from-identifier-names.md`'s inventory (~520 occurrences
outside `motion/`): `nowMs`/`nowMs_`/`wireNowMs` (78),
`timeoutMs`/`durationMs`/`deadlineUs`/`startMs`/`lastTickMs` (70),
`distanceMm`/`rotationRad`/`yawRad`/`omegaRad`/`angleRad` (69) where
they appear outside `motion/`, the `*Counts` locals (28), and the sim
`*Mm`/`*Rad`/`*Ms` state (42) in `blocks/sim.ts`. Every rename lands
with its `// [unit]` trailing comment — the unit is never simply
dropped. `src/core/` (the vendored kernel) and named conversion
functions (`mradToRad`, `countsPerMm`, `writePoseMm`) are excluded, per
the rule and the issue.

## Acceptance Criteria

- [ ] A source-pin test (new) fails the build on any new
      `MmS`/`Ms`/`Us`/`Mm`/`Rad`/`Deg`/`Counts`/`Pct` identifier suffix
      outside `src/core/` and outside a small, explicit allow-list of
      conversion functions.
- [ ] The pin test is green with an **empty** allow-list except the
      documented conversions (`mradToRad`, `countsPerMm`,
      `writePoseMm`, and any others named explicitly in the test).
- [ ] `shims.cpp`, `src/comms/*`, `src/blocks/*`, `src/platform/*` carry
      no unit-suffixed identifier; every renamed field/parameter/local
      keeps a trailing `// [unit]` comment.
- [ ] `src/core/` and `src/motion/` are unaffected by this ticket (core
      is excluded by rule; motion/ was already done in ticket 003 —
      this ticket does not re-touch it).
- [ ] Full existing test suite for the touched files stays green — this
      is a pure rename, no behavior change.

## Implementation Plan

**Approach**: File by file (`shims.cpp`, then `comms/` in dependency
order per `src/DESIGN.md` §1's layer table, then `platform/`, then
`blocks/`), rename identifiers and move the unit into a trailing `//
[unit]` comment, matching the kernel's existing style
(`src/core/diffdrive.h` is the reference). Write the source-pin test
first (mirroring `tests/host/test_vfp_guard_source_pin.py`'s pattern —
a grep-based pytest that fails the build on a forbidden pattern) so it
fails against today's ~520 occurrences, then rename until it's green.

**Files to create/modify**:
- `src/shims.cpp`
- `src/comms/wire_handler.{h,cpp}`, `wire_adapter.{h,cpp}`,
  `serial_transport.*`, `radio_transport.*`, `protocol.{h,cpp}`
- `src/platform/nezha_port.*`, `otos_port.*`, `platform_ports.h`
- `src/blocks/sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`,
  `motion.ts`
- `tests/host/test_no_units_in_identifiers_source_pin.py` (new)

**Testing plan**: The new source-pin test, plus the existing test suite
for every touched file, scoped run per `.claude/rules/source-code.md`.

**Documentation updates**: None expected — this is a pure identifier
rename with no behavioral or structural change, so it does not affect
`src/DESIGN.md`'s content (which describes behavior, not identifier
spelling). If a rename touches a name `src/DESIGN.md` quotes literally
in prose, update that one reference in the real file.
