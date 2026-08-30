# Bug report: a MakeCode-built hex ships with NO per-robot calibration

**To:** the agent building the MakeCode blocks / JavaScript environment
**From:** the calibration/field-test side
**Found:** 2026-08-29, vevov on the mbdeploy server at `192.168.4.50`

## What I observed

vevov was found running a build that never went through
`tools/make_deploy.py`. Read over `mbdeploy connect vevov --remote`:

| probe | on the MakeCode build | after a make_deploy flash |
|---|---|---|
| `VER` | **`ver unbaked`** | `ver 0.20260829.1` |
| `GET rotational_slip` | **`0.952`** (fleet default) | `0.987` (vevov's own) |
| `STATUS` `otos=` | **`0`** (sensor never started) | `1` |

`unbaked` is the literal placeholder in `src/comms/protocol.cpp`. Seeing
it is a reliable tell that a hex bypassed the deploy tool.

**This is not a complaint about your build breaking — it is a gap in the
pipeline.** MakeCode has no way, today, to know which robot it is being
flashed onto, so it cannot carry that robot's calibration.

## Why it matters

`make_deploy.py` injects FOUR per-robot things into a scratch copy
before building. A MakeCode-authored hex has none of them:

1. **`kChannel`** — the radio channel, from
   `radio-robot-lib/config/robots/<robot>.json`. Wrong channel means the
   robot answers on another robot's channel, or nobody's.
2. **`kProfile`** — which robot this hex is for, reported by `ID`.
3. **`kVersion`** — build provenance (`unbaked` when absent).
4. **`geometry.firmware_bake`** — `travelCalib` / `trackWidth` /
   `rotationalSlip`, opt-in per robot.

Running vevov on fleet-default geometry is a **~1.6% distance error and
a ~2.4% rotation error** — measured, not estimated: see
`docs/vevov-regressions-20260828.md` (39-trial distance sweep, 89-turn
sweep, camera-truthed).

## The fix I think you want: a paste-able JavaScript block

Everything needed IS already reachable from MakeCode — I checked each
signature in `src/blocks/`. So students need not rebuild this in blocks;
give them one JS block to paste at the top of `main`:

```javascript
// ---- vevov calibration -- paste at the TOP of your program ----
diffDrive.setTrackWidth(12.8)                              // cm
diffDrive.setWheelCalibration(0.70066)                     // mm per shaft degree
diffDrive.setConfigValue(ConfigField.RotationalSlip, 0.987)
diffDrive.setWorldSensorOffset(-5.27, -0.12, 0.89)         // OTOS lever arm: cm, cm, deg
diffDrive.startWorldTracking()                             // brings the OTOS up
control.inBackground(function () {                          // keeps its pose fresh
    while (true) { diffDrive.readWorld(); basic.pause(100) }
})
```

**UNVERIFIED**: these values and signatures are read from
`src/blocks/motion.ts`, `world.ts` and the measured config — this exact
snippet has NOT been run through a MakeCode build. Please compile it
once and tell me what breaks.

Signatures used, and their precision limits:

| call | units | quantisation |
|---|---|---|
| `setTrackWidth(cm)` | cm | `round(x*100)` -> 0.01 cm |
| `setWheelCalibration(mm/deg)` | mm/deg | `round(x*10000)` -> 0.70066 becomes 0.7007 |
| `setConfigValue(ConfigField.RotationalSlip, v)` | — | `round(v*1000)` -> 3 dp |
| `setWorldSensorOffset(x,y,yaw)` | cm, cm, deg | `round(x*100)` |

The `setWheelCalibration` rounding costs 0.006% — irrelevant next to the
1.6% it corrects.

## Three traps that will cost you a day each

1. **`startWorldTracking()` must run on the MAIN fiber at program
   start.** Any `uBit.i2c` transaction issued from a RUN handler HANGS
   THE BOARD permanently — silent to every verb on radio AND usb, only a
   reflash recovers it. Proven by probing `0x10`, the Nezha brick, which
   hung identically while the motion fiber drove that same address
   seconds later. Root cause is in vendored CODAL
   (`NRF52I2C::waitForStop()` resets its own timeout counter in the
   errata branch). Full write-up:
   `captures/otos-run-handler-i2c-hang-20260828.md`.
2. **Without the `readWorld()` loop the OTOS reports `(0,0,0)` forever.**
   `otosGet()` is cache-only; something must refill it. `otos=1` in
   STATUS only means the chip answered, NOT that it is tracking.
3. **The lever arm is per-chassis.** `-5.27, -0.12` is vevov's, measured
   2026-08-28 after its rebuild. tovez's differs. A wrong arm injects
   `2*|arm|*sin(theta/2)` of phantom translation into every pivot -- about
   53 mm per 90 deg corner.

## What I would like from you

1. **Confirm the snippet compiles** in the blocks/JS environment.
2. **Decide where per-robot values live for MakeCode.** They are in
   `radio-robot-lib/config/robots/<robot>.json` today, which MakeCode
   cannot read. Options, roughly in order of preference:
   - a generated snippet per robot, pasted by the student (works now);
   - a `diffDrive.useRobot("vevov")` block with the table compiled in
     (one block for students, but needs a codegen step);
   - MakeCode emits the hex and `make_deploy.py` still does the
     injection (keeps ONE source of truth, but breaks
     "download from MakeCode").
3. **Tell me how you want calibration handed over.** I can produce these
   values for any robot from the sweep harness in
   `captures/regressions-20260828/` — roughly 45 min of field time per
   robot. I would rather emit whatever format you can consume directly
   than have anyone retype numbers.

## Please don't reflash a field robot without saying so

vevov was mid-calibration-campaign when it was reflashed; the geometry,
the OTOS fix and the lever arm all went with it, and it took a
`GET rotational_slip` to notice. `mbdeploy list --remote` shows who is
plugged in where. Happy to coordinate — I mostly need vevov on the
playfield, and I can work on tovez or gopiv instead.
