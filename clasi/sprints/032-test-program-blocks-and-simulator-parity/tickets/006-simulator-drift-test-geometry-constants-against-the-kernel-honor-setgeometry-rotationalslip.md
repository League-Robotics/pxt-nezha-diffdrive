---
id: "006"
title: "Simulator: drift-test geometry constants against the kernel; honor _setGeometry/RotationalSlip"
status: open
use-cases: [SUC-005]
depends-on: ["005"]
github-issue: ""
issue: "simulator-split-parity-and-geometry-drift.md"
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Simulator: drift-test geometry constants against the kernel; honor _setGeometry/RotationalSlip

## Description

Confirmed in current `src/blocks/sim.ts`: `kSimTrackWidth = 114.2` and
`kSimRotationalSlip = 0.952` (line ~89-90) are FIXED constants used in
`_setWheels()`'s `simYawRate = (right - left) / (kSimTrackWidth /
kSimRotationalSlip)` computation. `_setGeometry(trackWidth, calib)`
and `_setKernelValue(field, value)` (line ~377-390) are confirmed
literal no-ops: they record their arguments into `simLastGeometry*`/
`simLastKernelField`/`simLastKernelValue` module variables that NOTHING
ELSE reads — their own comment says as much ("Recorded into
otherwise-unread module variables so each has a real body"). This means
a project that pastes a calibration block (`setGeometry`/a
`RotationalSlip` kernel-value write) gets ZERO change in simulated
turning behavior — the simulator silently keeps using the two hardcoded
constants regardless of what the student's own calibration data says,
which is exactly the classroom-facing gap
`calibration-skill-emits-a-paste-able-makecode-block.md` (referenced by
the issue as a related, open item) would otherwise walk students into.

This ticket is sequenced after ticket 005 since both touch `sim.ts`'s
geometry/kinematics section; doing the split-mirror first means this
ticket edits the POST-split `_startMove`/`simIntegrate` shape.

## Acceptance Criteria

- [ ] `_setGeometry(trackWidth, calib)` and/or `_setKernelValue(field,
      value)` (whichever actually corresponds to the wire's
      `RotationalSlip` kernel field — confirm the field-id mapping by
      reading `shims.cpp`'s real `setKernelValue()`/the
      config-descriptor table, don't guess) now actually update the
      values `_setWheels()`'s `simYawRate` computation divides by,
      replacing the fixed `kSimTrackWidth`/`kSimRotationalSlip`
      constants with mutable state that defaults to those same two
      values until a program calls one of these setters.
- [ ] `_driveTwist()`'s own analogous divisor (confirmed to already
      independently reproduce `effectiveTrackWidth()`'s formula per
      that function's own comment) is updated the SAME way — both
      call sites must read the same live geometry state, not just one
      of them, or the two would silently diverge from each other the
      same way the issue's own history describes them once doing
      (comment cites a prior 4.3% discrepancy between a bare-115
      literal and this exact formula).
- [ ] A drift test pins the simulator's DEFAULT (never-configured)
      geometry constants against `motion_engine.h`'s own compiled
      default `trackWidth_`/`rotationalSlip_` values — per Open
      Question 3 in `sprint.md`'s Architecture section, this compares
      two fixed SOURCE constants (buildable/comparable without a live
      robot), not a live per-robot fleet bake; state this scope
      explicitly in the new test's own docstring so a future reader
      doesn't mistake it for a live-hardware assertion.
- [ ] A behavioral test confirms that calling the simulator's
      `setGeometry`/kernel-value-write block CHANGES a subsequent
      move's simulated yaw rate (not just that the setter stores a
      value somewhere) — a before/after comparison of `simYawRate` (or
      an equivalent externally-observable quantity) for the same
      `_setWheels()` call, with and without a prior geometry-set call.
- [ ] `simLastGeometryTrackWidth`/`simLastGeometryCalib`/
      `simLastKernelField`/`simLastKernelValue` — if they become
      genuinely redundant once the real state they were standing in
      for exists — are either repurposed as the live state itself or
      removed; don't leave dead bookkeeping variables alongside new
      live ones for the same data.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full suite — geometry constants are exactly the kind of thing multiple existing tests might independently reference).
- **New tests to write**: the default-constants drift test and the setter-changes-behavior test described above.
- **TS type-check**: `npx tsc --noEmit`; prefer a real `pxt build` in `.tmp/` for the same reason as ticket 005 (this changes simulator runtime kinematics).
- **Verification command**: `uv run pytest tests/host/ -k "sim or geometry" -v`
