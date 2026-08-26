---
status: done
sprint: '017'
tickets:
- 017-002
---

# `travelCalib` 0.7878 never reached three docs or two bench tools, which now mis-scale by 2.8%

Priority: **High** -- the stale copies are in the two tools used to *measure*
accuracy, on a rig with three open accuracy issues.

`src/motion/motion_engine.h` now reads `travelCalib_ = 0.7878f` (commit
`fc84648`, 2026-08-25). The field comment behind it is exemplary -- twelve
`RUN:straight` legs at three distances in both directions, camera-bracketed at
rest, camera scale verified against three fixed tag pairs (+0.13% / -0.09% /
-0.11%), and a scale-vs-offset fit proving this constant is the right knob.

Still publishing the superseded **0.8102**:

| Site | Kind | Effect |
|---|---|---|
| `src/DESIGN.md:170` | doc | "Geometry defaults are the vevov bake: `travelCalib` 0.8102 mm/deg" |
| `docs/design/specification.md:694` | doc | the authoritative constants table |
| `docs/design/usecases.md:410` | doc | UC-013 calibration walkthrough |
| `tools/tour_watch.py:175` | **code** | `k = 0.8102/100` -- DIAG counts/s -> cm/s |
| `tools/tour_chart.py:61` | **code** | `--travel-calib` default |

Test *comments* also still cite 0.8102 at
`tests/host/test_wire_telemetry_projection.py:201` and
`tests/host/test_wire_motion_verbs.py:921` -- comments only, no assertion
depends on the value.

This is the mirrored-constant class the 2026-08-23 review called "the design's
weakest habit", now realized on the one constant that is specifically about
measurement accuracy.

## What to change

1. Update the three docs.
2. `tour_watch.py`'s conversion may simply be **unnecessary** now -- the v6
   `vl`/`vr` columns already carry mm/s (`wheelSpeed()`'s own unit;
   `tlm.py`'s `wheels_mms()` documents the 1:1). Check before re-scaling it.
3. Wherever a host genuinely needs the constant, it should come off the wire or
   be single-sourced with a drift test -- the way `kVersion` already is.

## The general lesson, worth acting on separately

Every mirrored constant in this repo that has a drift test (`kVersion`, the four
240s, `RUN_EVENT_SOURCE`, the `kDiag*` ordinals) has held across five sprints.
Every one without (this, `0x5F`, `defaultSpeed`/`defaultCruiseMmS_`, the sim's
115 vs hardware's 119.96) has drifted or is structurally able to. The rule that
falls out: **every mirrored constant gets a drift test, or gets merged.**
