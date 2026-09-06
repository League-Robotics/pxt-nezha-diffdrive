# tovez pre-flight — 2026-09-04, sprint 031 session

Board assigned by the stakeholder this session: **tovez**.

## Environment

- Room lights: `Switch.GetStatus?id=0` -> `"output": true`. ON.
- Camera: `arducam-ov9782-usb-camera` (the OV9782 — the OV9281 cannot see
  the field). `present/usable/calibrated: true`, `calibration_stale:
  false`, `flatfield_present: true`, `frame_dark: false`.
- Camera sanity: **AprilTag 1** (fixed field-centre marker) reads world
  (0.049, 0.002) cm — must be (0,0), and is. Full ArUco border set
  (1-10) detected.
- Carrier: tovez is on farm node **zilch**. Zilch is a Pi Zero mounted ON
  the robot, so tovez is already on the field and drives over zilch's
  serial daemon with no cable drag. `tovez.local` does NOT resolve —
  the WiFi link is not up on this firmware.

## Firmware

`ID` -> `id diffdrive tovez 1.20260903.1 tovez`

**This is PRE-sprint-030.** Sprint 030 merged 2026-09-04 (BusGuard,
fiber-identity gate, self-resolving motion obligation, real one-shot
`TLM NOW`, raw-zero glitch rejection, staged stop). Anything depending
on post-030 behaviour needs a reflash first.

## The Nezha brick IS powered

Pre-tick `STATUS` read:

```
status ready=0 active=0 connL=0 connR=0 otos=1 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none
```

`connL=0 connR=0` looks like the documented brick-off signature, but it
is not — it is just the pre-tick state. The kernel had never ticked
(`cyc=0`). After one `MOVE_X`:

```
status ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=2 cyc=127 tlm=off next=2 done=1 reason=timeout
```

The discriminator was not `STATUS` — it was the **camera**, which saw
real displacement. Odometry alone could not have told us.

## Probe: `MOVE_X 20 0 100 3000 #1` (2 cm commanded)

Tag 52 world position, camera-truthed:

| | x [cm] | y [cm] | yaw_rad [deg] |
|---|---|---|---|
| before | -15.639 | +0.040 | -0.68 |
| after  | -14.107 | -0.026 | +1.55 |
| delta  | +1.532  | -0.066 | — |

- Displacement **1.53 cm** for 2.0 cm commanded (77%). A 2 cm move is
  dominated by breakaway/stiction and a cold first move; not a
  calibration finding on its own.
- Travel bearing = `atan2(-0.066, +1.532)` = **-2.5 deg**.

### Tag 52 IS registered — corrected finding

`yaw_rad` before the probe was -0.68 deg. Travel bearing came out -2.5
deg. Those agree within 2.5 deg, which means **`yaw_rad` is already the
robot's corrected heading** — i.e. the daemon has tag 52 registered with
the fleet's `mount_yaw_rad = -pi/2` baked in.

An earlier pre-flight note in this session claimed tag 52 was
UNREGISTERED (because no `mounts/registry.json` turned up under
`~/.config/aprilcam-v1/`) and therefore that robot heading was
`yaw + 90 = +89.3 deg`. **That was wrong.** Had it been acted on, every
absolute-bearing leg this session would have been planned 90 deg
rotated — exactly the failure
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` documents for
sprint 029 ticket 007's `field_dance.py`.

Read tag 52's `yaw_rad` straight. Do NOT pass it through
`robot_heading_from_tag_yaw()`.

Robot heading at rest after the probe: **+1.55 deg** (facing east).

## Noted for the sprint

- `i2cf=2` after a single 2 cm move. Small, but not zero. Watch whether
  it climbs across a real run.
- `done=1 reason=timeout` on a move that arrived early. This is almost
  certainly the known lazy-resolution bug, which is one of sprint 031's
  own linked issues (`wire-done-reason-is-resolved-lazily.md`) — i.e.
  the sprint's first observation is a live reproduction of one of the
  issues it exists to fix.
