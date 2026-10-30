---
status: pending
---

# The OTOS lever arm comes only from the robot's config

Eric, 2026-10-29: no arm compiled in anywhere; measure it, put it in the
robot config, always use it from there.

Landed out of process at the sprint 044 close, 2026-10-29:

- `test/test.ts` no longer carries an arm. The hard-coded (-5.27, -0.12) cm
  and the unverified 0.89 deg yaw, `applyArm()`, the boot arming and
  `RUN arm` are gone. `RUN cal 0` still zeroes the arm for a lever
  calibration; the bake comes back on reboot.
- `OtosPort::setOffset()` applies what it is given. The arm starts at the
  bake (`offsetX_ = bakedArmX_`); the old "a baked arm wins" special case
  existed only to beat test.ts and is removed.
- radio-robot-lib `config/robots/tovez.json` and `vevov.json`
  `geometry.firmware_bake` carry `otos_arm_x/y`, `otos_angular_scale`,
  `otos_linear_scale` with provenance. vevov (-105.9, +2.9) mm from
  `RUN cal 0`. tovez (-52.7, -1.2) mm, the value its 100 m run validated:
  `RUN cal 0` fitted (-56.5, -7.6) (three runs, rms 5.3 mm, wandering
  pivot centre), and flown (`tovez-018-config-arm.hex`, `tovez-drift10-018`)
  it doubled the rightward arrival bias, 0.84 -> 2.1 cm.
- tovez now runs from config alone (`tovez-019-config-arm.hex`).

Still to do:

- `make_deploy.py` should warn loudly when a robot with an OTOS has no
  `otos_arm_x/y` in its config: the arm is now zero, silently.
- Measure and bake gopiv, zuvat, tigez (and any other OTOS robot).
- `RUN cal 0` cannot measure an arm on a robot whose pivot centre
  wanders (tovez). A camera-referenced fit is needed; the arrival-miss
  bias across the leg is a sensitive check on the lateral arm.
