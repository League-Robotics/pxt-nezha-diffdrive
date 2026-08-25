---
id: '002'
title: Per-leg believed-vs-target analysis tooling for tour telemetry
status: in-progress
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: intermittent-cw-pivot-abort-wheel-reversal.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Per-leg believed-vs-target analysis tooling for tour telemetry

## Description

The residual-fault issue's own first "next probe" is per-leg
believed-vs-target logging at move end: what did the move think it
hit, versus the commanded target and (where available) ground truth?
Today that comparison has to be done by hand from a raw pose CSV. This
ticket builds `tools/leg_analysis.py`, a new leaf consumer of
`tools/tlm.py`'s already-published `TlmStream`/`pose_cm`/`otos_cm`
interface (the same relationship sprint 005's six retrofitted consumers
already have — see `design/tools-root-DESIGN.md`'s "Campaign tooling"
section), that turns a `tour_capture.py` recording into a per-leg table:
commanded target, believed pose at move end, AprilCam ground truth
where available, and a classification per leg — on-target,
straight-overrun, or mid-leg-truncation, matching the issue's own
signature language ("a straight overrunning, or a tour truncating
mid-leg").

The issue's own distinguishing signal for the residual fault versus the
already-fixed class matters here: "heading usually still closes" for
the residual fault, versus the fixed class where heading also missed.
The classifier must surface this distinction, not just an aggregate
pass/fail.

## Acceptance Criteria

- [x] Given a synthetic CSV fixture with a known injected straight-leg
      overrun (distance traveled exceeds the commanded leg length by a
      set margin, heading close to target), the tool classifies that
      leg as `straight-overrun`.
- [x] Given a synthetic CSV fixture with a known injected mid-leg
      truncation (distance short of target, move ends before the
      commanded distance), the tool classifies that leg as
      `mid-leg-truncation`.
- [x] Given a synthetic CSV fixture where both distance and heading are
      within tolerance, the tool classifies that leg as `on-target`.
- [x] The per-leg output separately reports heading error and distance
      error, so "heading closed, distance didn't" (the residual
      signature) is distinguishable from "heading also missed" (the
      already-fixed class) — not collapsed into one pass/fail bit.
- [x] Host-tested (`tests/tools/test_leg_analysis.py`) against
      synthetic fixtures only — no robot, no real capture file,
      required to pass this ticket's tests.
- [x] The tool's CLI accepts a `tour_capture.py`-produced pose CSV
      (and, where present, the corresponding `_tlm.csv`/`.meta.json`
      sidecar from `tools/tlm.py`'s `write_tlm_csv()`) and a simple
      per-corner target list (matching `test.ts`'s own four-corner
      tour geometry, `CORNERS_X`/`CORNERS_Y` in `test/test.ts:38-39`,
      or an equivalent CLI-supplied target list for other tours).
- [x] `uv run pytest` (full suite) passes.

**Mid-implementation addendum (bench finding, folded in during this
ticket).** A real, camera-verified bench run on vevov found the
telemetry `ox`/`oy`/`oh` columns frozen (byte-identical) across a
whole move on at least one firmware build (older 12-column POSE
frame; not confirmed either way on current master's 20-column FULL
frame). `otos_cm()` is never trusted as ground truth here —
`classify_leg()`'s `believed` pose is always encoder-derived, and a
new pure `detect_otos_staleness()` cross-checks the OTOS columns
against the encoder movement over the same leg, flagging
(`otos_stale`, carried through to every `LegRow`, the CSV `--out`, and
the printed table) a leg whose OTOS pose is frozen at a genuine
(non-null) fix while the encoders clearly moved. A robot with no OTOS
fitted (`ox`/`oy`/`oh` legitimately `(0,0,0)`, per `tlm.py`'s own
documented contract) is explicitly NOT flagged — confirmed by a
dedicated regression test after an initial draft of the detector
falsely flagged every OTOS-less leg. Covered by
`tests/tools/test_leg_analysis.py`'s `detect_otos_staleness()` unit
tests and the `analyze_pose_csv()`/CLI-level OTOS-stale fixtures.

## Implementation Plan

**Approach:** A pure-function core (`classify_leg(commanded, believed,
ground_truth=None) -> LegResult`) with no I/O, unit-tested directly
against fixtures — the same "pure decision function, unit-tested
against synthetic fixtures" shape `tools/make_deploy.py`'s
`classify_attempt()` already established (sprint 008 precedent,
documented in `tools/DESIGN.md`'s "Build checkpoint triage" section) —
plus a thin CLI wrapper that reads a `tour_capture.py` CSV, segments it
into legs (reuse whatever leg-boundary detection `tour_chart.py`
already does, if any, rather than re-deriving it), and prints/writes a
per-leg table.

**Files to create:**
- `tools/leg_analysis.py`
- `tests/tools/test_leg_analysis.py`

**Files to modify:** none — this is a new, additive tool; no existing
tool's behavior changes.

**Testing plan:**
- New: `tests/tools/test_leg_analysis.py` — synthetic fixtures for
  each classification (on-target, straight-overrun, mid-leg-truncation),
  plus a test confirming heading-error and distance-error are reported
  separately.
- Existing: `uv run pytest tests/tools/` and the full `uv run pytest`.
- **Verification command:** `uv run pytest`.

**Documentation updates:** `design/tools-root-DESIGN.md`'s "Tour
family" section and "Campaign tooling" section already describe this
tool at planning time — confirm the shipped CLI/classification shape
matches; if it differs (e.g. a different classification name, a
different CLI flag shape), update the overlay copy and regenerate its
`.diff.md` by hand.

## C++11 Gate Coverage

Not applicable — pure Python, no C++ source touched.
