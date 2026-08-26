---
id: '002'
title: Propagate travelCalib 0.7878 to three docs and two tools; drift-test or delete
  the mirrors
status: open
use-cases: [SUC-001]
depends-on: []
github-issue: ''
issue: travel-calib-not-propagated-to-docs-and-tools.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Propagate travelCalib 0.7878 to three docs and two tools; drift-test or delete the mirrors

## Description

`src/motion/motion_engine.h` now reads `travelCalib_ = 0.7878f` (commit
`fc84648`, 2026-08-25), backed by a strong measurement comment (twelve
`RUN:straight` legs, camera-bracketed, cross-checked against three fixed
tag pairs). Five other places in the repo still publish the superseded
**0.8102**:

| Site | Kind |
|---|---|
| `src/DESIGN.md:170` | doc |
| `docs/design/specification.md:694` | doc (authoritative constants table) |
| `docs/design/usecases.md:410` | doc (UC-013 calibration walkthrough) |
| `tools/tour_watch.py:175` | **code** -- `k = 0.8102/100` |
| `tools/tour_chart.py:61` | **code** -- `--travel-calib` default |

The two code sites are the ones that matter most: they mis-scale by 2.8% in
the two tools used to *measure* accuracy on a rig with three open accuracy
issues. Test-comment references at
`tests/host/test_wire_telemetry_projection.py:201` and
`tests/host/test_wire_motion_verbs.py:921` are comments only -- no assertion
depends on the value, update them for accuracy but they carry no test risk.

This ticket is doc/tool-only. It does not touch firmware C++ or TypeScript.

## What to change

1. **Docs** -- update `src/DESIGN.md:170`, `docs/design/specification.md:694`,
   and `docs/design/usecases.md:410` to `0.7878`.
2. **`tools/tour_chart.py:61`** -- update the `--travel-calib` default to
   `0.7878`.
3. **`tools/tour_watch.py:175`** -- before just updating the constant, check
   whether the conversion is even still needed. The v6 `vl`/`vr` telemetry
   columns already carry mm/s natively (`wheelSpeed()`'s own unit on the
   firmware side; `tools/tlm.py`'s `wheels_mms()` documents the 1:1
   relationship). If `tour_watch.py`'s `k = 0.8102/100` conversion is
   scaling a quantity that is already in the right unit, **delete the
   conversion** rather than update its constant -- a redundant mirror that's
   gone can't drift again. If it turns out the conversion is doing real
   work (confirm by reading how the converted value is used downstream and
   what unit the consumer expects), update it to `0.7878` instead and note
   in a comment why it's not redundant with the wire's native mm/s.
4. **Drift test or single-source, per the sprint's general rule** ("every
   mirrored constant gets a drift test, or gets merged"): whichever doc/tool
   sites survive step 3 and still hold a literal copy of the constant need
   either (a) a host test asserting the doc/tool value matches
   `src/motion/motion_engine.h`'s `travelCalib_` (grep both sides, compare as
   text -- same style as `test_wire_constants_drift.py`), or (b) elimination
   if there's a way to single-source instead. Given the doc sites are prose
   tables (not code), a full drift test may not be practical for all three --
   at minimum, drift-test the two tool sites that survive step 3, since
   those are code and directly affect measurement.
5. Update the two test-comment references for accuracy (no assertion
   changes needed).

## Acceptance Criteria

- [ ] No file in `src/`, `docs/design/`, or `tools/` cites `travelCalib`
      0.8102 (except historically, in a sprint-history section if one is
      kept -- but see ticket 004, which removes those anyway).
- [ ] `tools/tour_watch.py`'s conversion is either deleted (if redundant
      with the wire's native mm/s) or updated to 0.7878 with a comment
      explaining why it's not redundant.
- [ ] `tools/tour_chart.py --travel-calib` default is 0.7878.
- [ ] At least the surviving tool-side constant(s) have a drift test against
      `src/motion/motion_engine.h`'s `travelCalib_`.
- [ ] The two stale test-comment references are corrected.
- [ ] No firmware C++/TypeScript logic is changed.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` (covers
  `tour_watch.py`/`tour_chart.py`-adjacent logic if any exists),
  `uv run pytest tests/host/test_wire_telemetry_projection.py
  tests/host/test_wire_motion_verbs.py` (comment-only changes, confirm no
  assertion broke).
- **New tests to write**: a drift test for whichever tool-side
  `travelCalib` copy(ies) survive step 3, comparing against
  `src/motion/motion_engine.h`'s `travelCalib_ = 0.7878f` literal by
  reading both files as text (no compiler) -- model on
  `tests/host/test_wire_constants_drift.py`.
- **Verification command**: `uv run pytest tests/tools/ tests/host/test_wire_constants_drift.py`
  plus whichever new drift test file is added.
