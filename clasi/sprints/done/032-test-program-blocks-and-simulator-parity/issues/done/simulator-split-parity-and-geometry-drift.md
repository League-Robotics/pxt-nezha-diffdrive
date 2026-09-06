---
status: done
sprint: '032'
tickets:
- 032-005
- 032-006
---

# Simulator: mirror the 50 deg pivot-then-straight split; drift-test sim geometry; honour set geometry

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: BT-06, BT-20 ([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)). Triage #9.

## Description

`sim.ts:129-146` blends every `(distance, yaw)` into one arc; hardware
splits `|yaw| >= 50 deg` into pivot-then-straight (`motion_engine.cpp:393`).
`move 47 cm turning 90 deg` ends 30 cm forward / 30 cm left in the browser
and 0 forward / 47 cm left on the robot; the block's own JSDoc ("both at
once makes an arc") is true only in the browser.

`sim.ts:89-90` mirrors `trackWidth` 114.2 and `rotationalSlip` 0.952 with
no drift test, and `_setGeometry`/`_setKernelValue` are ignored, so a
student who pastes the calibration block the open calibration-skill issue
proposes gets a browser robot that turns 12 % faster than theirs.

## Remedy

- Mirror the split in `_startMove` (two phases on the existing
  `simMoveRemain*` machinery), threshold from one constant drift-tested
  against `kTurnFirstAngleRad`.
- Fix `move()`'s JSDoc.
- Drift test for the two sim geometry constants; make the sim honour
  `_setGeometry` and `RotationalSlip`.

## Related

- `calibration-skill-emits-a-paste-able-makecode-block.md` (open, high).
