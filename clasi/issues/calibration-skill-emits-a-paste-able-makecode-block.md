---
status: pending
---

# A calibration skill that runs on the workbench and emits a paste-able MakeCode block

Priority: **High** — without it, every student's MakeCode robot runs on
fleet-default geometry. Measured on vevov, that is a **1.6% distance
error and a 2.4% rotation error** (`docs/vevov-regressions-20260828.md`),
and nothing in the student's workflow reveals it.

## The problem

Per-robot calibration lives in
`radio-robot-lib/config/robots/<robot>.json` and is injected at build
time by `tools/make_deploy.py`. **MakeCode cannot read that file**, so a
hex built and downloaded from MakeCode carries none of it: no
`travelCalib`, no `trackWidth`, no `rotationalSlip`, no OTOS lever arm,
no radio channel, no version.

Observed 2026-08-29 on vevov (`docs/BUG-makecode-calibration-deploy-20260829.md`):
a MakeCode-built board reported `ver unbaked`, `rotational_slip 0.952`
(the fleet default, not vevov's measured 0.987) and `otos=0`. Nothing in
the student's experience would surface any of that — the robot simply
drives slightly wrong, forever.

Calibration also cannot be a one-off: the values are **per chassis**, and
they change whenever a robot is rebuilt. vevov's OTOS lever arm moved
14.5 mm when its wheels were repositioned, and its track width went
114.2 -> 128 mm.

## The shape of the fix (stakeholder's design)

Calibration is a **workbench activity**, not a classroom one, because it
needs the overhead cameras as external truth:

1. A student brings their robot to the stakeholder's workbench — the one
   with the overhead camera rig.
2. They run a **calibration skill** through Claude, from their own
   machine (they may log into Claude there).
3. The skill drives the robot through the measurement sequence against
   the cameras.
4. It emits a **paste-able JavaScript block**.
5. The student pastes that block at the top of their MakeCode program.
   No blocks to reconstruct, nothing to retype.

Draft of the emitted block (values are vevov's, 2026-08-28):

```javascript
// ---- vevov calibration -- paste at the TOP of your program ----
diffDrive.setTrackWidth(12.8)                              // cm
diffDrive.setWheelCalibration(0.70066)                     // mm per shaft degree
diffDrive.setConfigValue(ConfigField.RotationalSlip, 0.987)
diffDrive.setWorldSensorOffset(-5.27, -0.12, 0.89)         // OTOS lever arm
diffDrive.startWorldTracking()
control.inBackground(function () {
    while (true) { diffDrive.readWorld(); basic.pause(100) }
})
```

Every call above already exists in `src/blocks/` — verified against
`motion.ts` and `world.ts` — including `rotational_slip`, reachable
through the generic `setConfigValue(ConfigField.RotationalSlip, ...)`
escape hatch. **UNVERIFIED**: this exact snippet has not been compiled
through a MakeCode build.

## What the skill has to do

The measurement procedures already exist and are proven; the work is
packaging them for someone who is not a robotics engineer.

| value | how it is measured | reference |
|---|---|---|
| `trackWidth` | stakeholder's calipers — geometric, never "corrected" | — |
| `travelCalib` | distance sweep, camera-truthed, fit `measured = a*cmd + c` | `captures/regressions-20260828/sweep_dist.py` |
| `rotationalSlip` | turn sweep both directions, minus the travel scale | `captures/regressions-20260828/sweep_turn.py` |
| OTOS lever arm | 8 pivots with the arm unapplied, least-squares circle fit | `captures/tour-20260828-otos/otos_arm.py` |
| camera tag mount | same fit shape, on the overhead tag | — |

Requirements the skill must carry, each of which was learned the hard
way and would otherwise be re-learned by every student:

- **Do not correct the same error twice.** Rotation is driven by wheel
  ARC, which scales with `travelCalib`, so the travel scale error is
  COMMON to both and only the residual belongs to `rotationalSlip`.
  `motion_engine.h` warns about this explicitly.
- **Sweep, do not spot-check.** The turn error crosses zero near 125 deg:
  a 30 deg check says "+3.5, turns run long", a 90 deg check says "fine",
  a 720 deg check says "-15, turns run short". All three are correct.
- **Never fold a fixed offset into a scale constant.** The measured
  per-turn overshoot (+2.0 deg below 90, +0.6 above 200) does not scale
  with angle; baking it into `rotationalSlip` fits one turn size and
  mis-turns every other.
- **`startWorldTracking()` must run on the MAIN fiber**, never from a RUN
  handler — I2C from a RUN handler hangs the board until reflashed
  (`captures/otos-run-handler-i2c-hang-20260828.md`).
- **Check the room lights.** They switched themselves off three times in
  one session; every tag vanishes and it looks exactly like a dead
  camera. Shelly at `192.168.1.122`.
- Emit **UNVERIFIED** honestly when a value could not be measured, rather
  than a plausible default.

## Open questions

- **Where does the truth live?** A pasted block is a COPY: the moment a
  robot is rebuilt, the student's program is stale and nothing detects
  it. Options: emit a `robot` + date comment in the block and have the
  firmware log a mismatch; or a `diffDrive.useRobot("vevov")` block with
  a compiled-in table (one block for students, but needs a codegen step
  and re-flashing to update).
- **How much field time per robot?** The full sweeps took ~45 min on
  vevov. A student-facing version probably wants a 10-minute subset with
  a documented accuracy cost.
- **Who runs it?** "Claude on the student's machine" implies the skill
  must be usable without access to this repo's history — it needs to be
  self-contained about the traps above.
- Should the skill ALSO write the values back to
  `radio-robot-lib/config/robots/<robot>.json`, keeping one source of
  truth for the `make_deploy.py` path? Probably yes.

## Related

- `docs/BUG-makecode-calibration-deploy-20260829.md` — the bug report to
  the MakeCode-environment agent, and the API-reachability check.
- `docs/vevov-regressions-20260828.md` — the sweeps and the error
  decomposition the skill would automate.
- `captures/regressions-20260828/` — the working harness
  (`sweeplib.py`, `sweep_dist.py`, `sweep_turn.py`, chart scripts).
