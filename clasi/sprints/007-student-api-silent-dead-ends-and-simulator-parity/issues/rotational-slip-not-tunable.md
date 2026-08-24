---
status: in-progress
sprint: '007'
tickets:
- 007-005
---

# rotationalSlip is tuned-but-untunable: hard-coded 0.952, no setter anywhere

Priority: **Low** — code review 2026-08-23, R-14 (API-06; CONFIRMED).

`rotationalSlip` is getter-only and hard-coded to 0.952 — the value
measured for the vevov chassis. It is absent from `setGeometry`, absent
from `kFields`, and has no block. The only palette knob that changes turn
geometry is `set track width` — exactly the knob the design docs forbid
using to compensate slip (the trackWidth/rotationalSlip doctrine in
`docs/design/design.md`). A chassis that differs from vevov cannot be
turn-calibrated without recompiling the extension.

Caution for the fix: the 0.952 constant's derivation comment (measured
164-166° → ratio 0.915 → effective track 120.0 mm → slip 114.2/120.0 =
0.952) is load-bearing — see `verify-comments.md`'s CHALLENGE on
motion_engine.h:335-346. Keep the derivation with the field wherever it
moves.

## What to do

Add `rotational slip` to the Setup group (or at minimum to `ConfigField`),
plumbed to a MotionEngine setter, with the same >0 validation style as
`setGeometry`. Update UC-013 (chassis calibration) to include it.
