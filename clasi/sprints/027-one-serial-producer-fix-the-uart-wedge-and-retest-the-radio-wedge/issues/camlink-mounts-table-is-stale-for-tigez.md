---
status: in-progress
sprint: '027'
tickets:
- 027-004
---

# camlink.py's mount table is stale and drives repeated tag-yaw re-derivation

`tools/camlink.py` is the single place this repo records what it knows
about robot-mounted camera tags. Two defects in it cause agents to
re-derive the camera→robot heading offset from a probe move at the start
of nearly every field session — a ritual that costs ten minutes and
rediscovers a fixed constant.

## Defect 1 — the "not persisted" docstring is stale

`tools/camlink.py:10-16` states:

> THE DAEMON DOES THE CORRECTING, AND ONLY IF YOU TELL IT TO.
> Tag mount parameters are NOT persisted across a daemon restart.
> ... Call `ensure_registered()` every session.

AprilCam changed. Mount registrations are now written to
`state_dir/mounts/registry.json` and reloaded automatically at daemon
startup; only an explicit `unregister_tag` removes one (AprilCam agent
guide §6). Annotations remain per-session — that half of the docstring
is still correct, and the distinction is exactly what the guide warns
about getting wrong.

`ensure_registered()` is still harmless (idempotent re-registration),
but the docstring's framing tells every reader that nothing is known
until they establish it, which is now false.

## Defect 2 — tag 57 (tigez) is missing from `MOUNTS`

`MOUNTS` covers 53 (vevov), 52 (tovez), 10 and 11 (fixed calibration
tags). **tigez has been the board on the playfield since 2026-08-30**
and its tag 57 is not there. A session working tigez finds no entry,
concludes the mount is unknown, and probes.

Its parameters are already measured — mount `(-0.67, -0.02)` cm at
−89.65°, from the tigez calibration of 2026-08-30 — they just never
landed in the table.

## Fix

1. Correct the module docstring: registrations persist and are reloaded
   at daemon start; annotations do not. Keep `ensure_registered()` as
   cheap idempotent insurance, but stop describing it as mandatory
   session setup.
2. Add tag 57 to `MOUNTS` with its measured offsets, `mount_z`, and
   `mount_yaw_rad = -math.pi/2`.
3. Add a comment splitting `mount_yaw_rad` into its two parts: −90.00°
   is the AprilCam **convention** (`yaw_rad` is `atan2` along the
   front-left→front-right edge, while the drawn hat points out of that
   edge — perpendicular, hence the 90°), fixed for every tag on every
   robot and never to be re-measured; only the sub-degree residual
   (tigez's 0.35°) is physical mounting and only changes when a plate is
   actually remounted.

## Background

- Rule: `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
- Verification: `captures/tag-yaw-convention-20260902/yawconv.py` and
  `yawconv.out`
- Source: `aprilcam/daemon/detection.py:_front_edge_yaw` (lines 560-574),
  `aprilcam/client/renderer.py:_hat_apex`,
  `aprilcam/calibration/geometry.py:375`
