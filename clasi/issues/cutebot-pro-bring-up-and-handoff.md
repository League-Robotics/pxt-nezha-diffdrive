---
status: pending
---

# Cutebot Pro: bring-up, calibration, and the PWM/onboard handoff on the robot

## Description

Second half of the Cutebot Pro arc, after
`cutebot-pro-board-seam-and-hybrid-port.md` has landed a hex that
builds. Design: `docs/design/cutebot-pro-support.md` §3.D (handoff
hazards), §5 (WiFi pins), §8 (bench order).

Nothing about the Cutebot Pro has been measured. The ELECFREAKS wiki
does not give wheel diameter, track width, gear ratio or v2 encoder
resolution; whether a v2 board answers the v1 raw-pulse read; whether
the MCU itself clamps the onboard loop at 200 mm/s or only the
extension does; whether a `0x10` PWM write cancels a running `0x80`
loop; which zero stops a wheel under onboard control. Each of those
is a MEASURED line before any bake.

The assigned board: the stakeholder said zeguz on mangi; the farm
advertised zetuv on magni and no zeguz (2026-09-21 22:29), and zetuv
refused a connect as `busy`. Resolve by `HELLO` first.

## Proposed resolution

In the doc's §8 order, every step a capture under
`captures/cutebot-bringup-<date>/` and a MEASURED citation:

1. Identity (`HELLO`), revision probe, firmware version, raw-pulse
   probe, encoder sign and resolution by hand-spinning a wheel.
2. Caliper geometry; pulses per revolution against the 1428 figure.
3. First Cutebot build over USB: `PING`, `STATUS`, `WHEELS_V` sign
   bake, `fullDutyVelocity`, the kernel bake for 3.3 V / 0.2 A
   motors; `MOVE_X` vs tape for `travelCalib`; pivots for
   `rotationalSlip`.
4. The handoff probes: onboard floor at 100/150 mm/s; setpoint
   accuracy vs our encoder at 200/300/400; up-handoff trace from a
   running PWM; does `0x10` cancel `0x80`; which zero stops the wheel.
5. Three-way square tour A/B at `onboard_pid 0 / 1 / 2`, scored on
   closure and per-leg heading like every tour in `reports/`; the
   winner becomes the fleet-JSON default for this board.
6. Encoder-resolution decision (§3.A: raw pulses, longer velocity
   window, or accept); WiFi pin answer (§5); the servo verb for the
   gripper (`0x40`).
