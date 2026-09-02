---
id: '005'
title: Update specification.md section 4.8 and run the build checkpoint
status: done
use-cases:
- SUC-004
depends-on:
- '003'
- '004'
github-issue: ''
issue: trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Update specification.md section 4.8 and run the build checkpoint

## Description

`docs/design/specification.md` §4.8's `ConfigField` table
(lines 207-228 as of this sprint's planning) is already stale at
ordinal 17 — it is missing ordinal 18 (`PivotOverrun`, added
2026-08-29) entirely, before this sprint's own 9 new ordinals. This
ticket brings the table current through ordinal 27 and closes out the
sprint with this project's standing build-checkpoint convention
(`docs/design/design.md`, "Standing convention (sprint 008)"): every
sprint that touches build-eligible source ends with a ticket that runs
`tools/make_deploy.py` and confirms a flashable hex results from the
sprint's own final state, because a green host suite is not evidence a
change compiles for the real embedded target (`-std=c++11` vs. the
host's `-std=c++20`).

## Acceptance Criteria

- [x] §4.8's table lists all 28 ordinals (0-27), each with its wire
      name, block label, and kernel/engine field, matching
      ticket 003's table exactly (ordinal, `ConfigField` member, wire
      name, field).
- [x] Ordinal 18 (`PivotOverrun`) is added as part of this same pass
      (it predates this sprint but was never documented — fold it in
      rather than leaving a second stale gap).
- [x] The "Ordinal 15's... Kernel `Config` field column is also
      non-standard" style explanatory notes already present for
      ordinals 15-17 are extended, where applicable, to any of the new
      ordinals 19-27 that likewise have no `DifferentialDrive::Config`
      field (i.e. anything living on `MotionEngine` rather than the
      kernel — expected to be all nine, per ticket 001/002/003's own
      design).
  - [x] Ordinal 15's own note is corrected if this sprint changed
        `DefaultCruise`'s behavior in any documented way (per
        sprint.md's Design Rationale, it should NOT have — confirm the
        note still reads correctly as "flat legacy/WHEELS_* default,
        unchanged"). Confirmed: the note is unchanged and still reads
        correctly; `Rig::defaultCruiseMmS_` stays the flat legacy/
        `WHEELS_*` default per this sprint's own "Impact on Existing
        Components" section.
- [x] `tools/make_deploy.py` runs against this sprint's final state and
      produces a flashable hex (triage-aware retry on the two known
      benign abort shapes is expected and acceptable per
      `docs/design/design.md`'s own documented convention; a real
      `.cpp` compile failure is not). Ran against a stale scratch copy
      first (a third, already-documented benign shape — missing
      `Building CXX object` lines for five translation units; the
      script's own error message names the remedy), wiped
      `.tmp/deploy-head` per that message, reran, and produced a
      1,543,539-byte flashable hex on attempt 1 with all ten
      `nezha-diffdrive` `.cpp` files compiled.
- [ ] Full `tests/host/` suite passes (final confirmation before
      `close_sprint`'s own test run). NOT run in this ticket, per this
      project's standing testing convention (`.claude/rules/
      source-code.md`, the programmer-agent workflow): the full suite
      runs exactly once per sprint, inside `close_sprint` itself, not
      as a per-ticket step. This ticket instead ran its own
      new/changed test plus the two pinned regression files and the
      three cross-cutting gates (`test_archaeology_marker_budget.py`,
      `test_cxx11_syntax_gate.py`, `test_wire_constants_drift.py`), all
      passing — see the ticket's own commit for the exact results.

## Implementation Plan

**Approach**: Rewrite §4.8's table in place (edit existing rows'
`|---|` structure, do not append a second table or a dated section —
this doc's own contract, `docs/design/design.md` "Subsystem-doc
contract: content, not sprint history", applies equally to
`specification.md`: it describes the system as it stands, not a
changelog). Then run the build-checkpoint.

**Files to modify**: `docs/design/specification.md` §4.8.

**Files to run, not modify**: `tools/make_deploy.py` (build-checkpoint
step).

## Testing

- **Existing tests to run**: the full `tests/host/` suite (final
  sprint-level confirmation).
- **New tests to write**: none — this ticket is documentation plus a
  build verification, not new test coverage.
- **Verification command**: `uv run pytest tests/host/ && python tools/make_deploy.py` (exact invocation per that tool's own current CLI — confirm flags against `tools/DESIGN.md` before running, since `make_deploy.py`'s interface has changed across recent sprints, e.g. the per-robot channel/group injection landed 2026-08-30).
