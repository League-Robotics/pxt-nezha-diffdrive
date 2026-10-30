---
id: '014'
title: Per-robot OTOS linear scale bake
status: done
use-cases:
- SUC-002
depends-on:
- '013'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Per-robot OTOS linear scale bake

## Description

Found on 2026-10-28 (overnight acceptance). In
`captures/sprint044-acceptance-20261028/vevov-straight1.jsonl`, six 25 cm
straights read OTOS/camera = 0.959-0.982 (mean ~0.968). vevov's OTOS
under-reads distance by ~3%. On 2026-10-28 the earlier run measured
~1.009 on the same robot, so the value is per robot and can change when
the mount is disturbed.

`OtosPort::begin()` always writes the chip's linear scalar register 0
(scale 1.000). The angular scalar is already baked per robot
(`otos_angular_scale` -> `angularScale_`). Add the same for linear:
- `float linearScale_ = 1.0f;` in otos_port.h, baked by make_deploy key
  `otos_linear_scale` (same regex/file mechanism as `otos_angular_scale`).
- In `begin()`, write `kRegLinearScalar` = round((linearScale_ - 1) /
  0.001), clamped to the chip's +-127. Check SparkFun's register meaning
  for the linear scalar (0.1% per LSB, signed). Confirm the sign
  convention against the angular code already there, and cite the
  reference.
- A robot with no key builds byte-identical to today.
- Document the key next to `otos_angular_scale` in the tools design doc,
  and list the measurement method: straights on camera, scale =
  camera / OTOS.

## Acceptance Criteria

- [x] make_deploy bakes `otos_linear_scale`; tests in
      tests/tools/test_make_deploy_geometry.py (present / absent / via
      `--bake` override)
- [x] begin() writes the scalar (source pin, or behaviourally through
      tests/host/sim_otos_bus.h if the shims rig can see the register
      write); clamp tested
- [x] `uv run pytest tests/host` and the make_deploy tool tests green
- [x] Hex builds
