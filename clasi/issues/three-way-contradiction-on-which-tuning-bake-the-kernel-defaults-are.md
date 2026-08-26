---
status: pending
sprint:
---

# Three-way contradiction on which tuning bake the kernel defaults actually are

## Summary

Three files in this repo make mutually contradictory claims about
which robot's measured calibration bake the kernel's tuning defaults
(`Rig::travelCalib`, `trackWidth`, etc.) actually come from:

- `src/shims.cpp:191` — "Kernel defaults: the **tovez** bake
  (boot_calibration.cpp) with NEUTRAL wheel gains -- a generic kit
  starts uncorrected."
- `src/DESIGN.md:182` — "Geometry defaults are the **vevov** bake:
  `travelCalib` 0.7878 mm/deg, `trackWidth` 114.2 mm, `rotationalSlip`
  0.952 -- each with the measurement history in the field comments."
- `src/motion/motion_engine.h:178` — "Geometry defaults below are the
  measured **tovez/vevov** bake -- see this class's own field comments
  for the measurement behind each."

These cannot all be true at once, or even pairwise agree: two name
different single robots for what should be one shared set of
constants, and the third hedges between both rather than naming either.
Since `travelCalib`/`trackWidth`/`rotationalSlip` are single fleet-wide
constants (not per-robot), exactly one of "tovez", "vevov", or neither
can be the actual source measurement -- not both, and not an
unresolved "either."

## How this surfaced

Found while fixing an unrelated defect: `src/comms/protocol.cpp`'s
`kProfile` wire-identity constant was hard-coded to `"tovez"`
fleet-wide, so every board (including vevov) reported `"tovez"` over
the wire `ID` verb. That fix (baking `kProfile` per-robot at deploy
time via `tools/make_deploy.py`) does **not** touch `shims.cpp`'s
tuning constants and does not resolve this contradiction -- it only
decouples `kProfile` (wire identity, now per-robot) from whatever bake
the `Rig` geometry defaults actually are (still fleet-wide, unchanged
by that fix). Reading `shims.cpp`'s own comment while doing that work
is what surfaced the mismatch against `DESIGN.md`'s and
`motion_engine.h`'s claims about the same constants.

## What needs to happen

Resolving this is a **measurement question**, not something to guess
or resolve by picking one file to trust over the others:

1. Determine which robot's actual measured session
   `travelCalib`/`trackWidth`/`rotationalSlip` values in
   `boot_calibration.cpp` / `shims.cpp`'s `Rig::ensure()` were fit
   against (an operator-supervised measurement/verification pass,
   the same kind `clasi/issues/travel-calib-is-2.8-percent-too-large.md`
   and `clasi/issues/finish-the-vevov-calibration-verification.md`
   describe for related calibration work).
2. Update whichever of the three sites are wrong so all three agree
   with the actual answer -- including `motion_engine.h`'s hedge,
   which should name one robot, not both.

Not fixed here on purpose: this is a documentation-consistency defect
requiring hardware measurement to resolve correctly, not a mechanical
edit.
