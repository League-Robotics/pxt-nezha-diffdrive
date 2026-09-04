# The camera's tag yaw is the front EDGE, not the arrow. Robot = tag + 90°.

**Stop re-deriving this.** It is a fixed property of AprilCam, identical
on every board, every tag, every session. If you are about to run a
probe move to "find the heading offset," read this instead.

## The number

For a tag mounted with its **top / the green hat / the printed number's
"up"** pointing along robot-forward:

```
robot_heading_deg = tag_yaw_deg + 90        # mount_yaw_rad = -pi/2
```

Register it once and the daemon does it for you — with
`mount_yaw_rad = -math.pi/2` the reported `yaw_rad` IS the robot's
heading, no `+90` in your own code (`tools/camlink.py` docstring).

## Where the 90° comes from — it is not a fudge and not a mounting error

The overlay and the number describe **two different directions**, 90°
apart, and the overlay is the one that matches your intuition:

| what you see / read | direction it means |
|---|---|
| green peaked "hat", i.e. the up-arrow | **outward from** the front edge — robot forward |
| `yaw_rad` in the tag record | **along** the front edge, front-left → front-right |

The corner contract is `(front-left, front-right, back-right,
back-left)`, and yaw is literally `atan2` over the `0 → 1` edge vector
(`aprilcam/daemon/detection.py:_front_edge_yaw`, lines 560-574). The hat
apex is that same edge's midpoint pushed **away from the quad centroid**
(`aprilcam/client/renderer.py:_hat_apex`). Perpendicular directions,
same edge. That is the whole 90°.

So: the arrow points where you think forward is. The number points 90°
clockwise of it. Both are correct; they are answering different
questions.

MEASURED 2026-09-02 against the installed aprilcam
(`~/.local/pipx/venvs/aprilcam`, python 3.14):
`captures/tag-yaw-convention-20260902/yawconv.py`, output captured in
`captures/tag-yaw-convention-20260902/yawconv.out`:

```
hat points NORTH (+90 deg) -> reported yaw_rad = +0.0 deg
  mount_yaw=  +0.00 deg -> robot heading =   +0.00 deg
  mount_yaw= -90.00 deg -> robot heading =  +90.00 deg
```

A 4 cm square tag at the origin with corners FL(-2,2) FR(2,2) BR(2,-2)
BL(-2,-2) — hat pointing north — reports yaw 0° (east). Feeding that
through `correct_tag_pose` with `mount_yaw_rad = -pi/2` returns +90°,
i.e. north. The sign is `robot_yaw = tag_yaw - mount_yaw`
(`aprilcam/calibration/geometry.py:375`).

## Do not "measure" the 90° again

`mount_yaw_rad` conflates two things, and only one of them is worth a
probe:

- **−90.00° is the convention.** Fixed. Never measure it.
- **The remainder is the physical mount.** tigez's registered −89.65°
  is −90° plus 0.35° of crooked tape. That fraction of a degree is the
  only part a probe can tell you, and it is worth measuring only when
  the tag plate has actually been remounted.

A probe move that comes back "robot heading = tag yaw + 91.12°" has not
discovered anything: it has re-measured the convention and added 1.12°
of probe noise on top. If a probe returns anything not within a couple
of degrees of +90°, the tag is physically mounted wrong (or on its side)
— that is the finding, not a new offset to bake in.

## Why this kept happening

Not because nobody wrote it down. It **was** written down, correctly, on
2026-08-31 ("aprilcam tag yaw = the tag's x-axis (paper-right), 90° off
paper-top ... the whole fleet's −90s cancel the convention, not physical
rotation"). It still got re-derived. Three causes, all fixed:

1. **The safety probe and the convention lookup were fused into one
   ritual.** The 12 cm probe before driving is genuinely justified — the
   tag PLATE is removable and has come back on rotated, which put tigez
   into the rails. But its job is to *check* the known model, not to
   *learn* it. Report it pass/fail against +90°. A probe returning
   +91.12° found nothing but its own noise; one returning +1° or +181°
   means the plate is rotated, and that is the finding.
2. **`tools/camlink.py`'s docstring says mount registrations are "NOT
   persisted across a daemon restart."** Stale — AprilCam now writes
   them to `state_dir/mounts/registry.json` and reloads at startup
   (agent guide §6). Registrations survive; only annotations are still
   per-session. The stale claim tells every reader that nothing is known
   until they establish it.
3. **`tools/camlink.py`'s `MOUNTS` table knows tags 53 (vevov), 52
   (tovez), 10 and 11 — but not 57 (tigez)**, the board on the field
   since 2026-08-30. A tigez session finds no entry, concludes nothing
   is known, and probes.

(2) and (3) are tracked in
`clasi/issues/camlink-mounts-table-is-stale-for-tigez.md`.

## Registered vs raw: who adds the 90

The daemon and your own code must never BOTH add the convention.
Exactly one of them does, and which one depends on whether the tag has
been through `camlink.py --register <robot>` (or `Cam.register()`)
this daemon session:

| tag state | what `yaw_rad` reports | who adds the +90 |
|---|---|---|
| **unregistered / raw** | the raw front-edge yaw | your code, via `field.robot_heading_from_tag_yaw()` — the ONE place it happens for a raw reading |
| **registered** | the robot's heading, already corrected (`mount_yaw_rad = -pi/2 + residual` baked in at registration) | nobody — read `yaw_rad` straight, no further correction |

Running a REGISTERED reading through `robot_heading_from_tag_yaw()`
adds the convention a **second time**. The bug is easy to miss because
a pivot's PASS/FAIL survives it — a heading DELTA cancels a constant
offset — while every absolute-bearing check (a drive, a "face this
heading" command) comes out rotated by +90°. This is exactly what
happened: sprint 029 ticket 007's `tools/field_dance.py` registered
tovez's tag as a pre-flight step, then its own `pose()` called
`robot_heading_from_tag_yaw()` on the daemon's already-corrected
`yaw_rad` anyway. The 2026-09-04d dance session showed the signature
precisely — three pivots net +14.2° (close to clean, since deltas
mostly cancel the extra +90) while all three drives failed with a
consistent **+87°/+91°/+86°** bearing error. Fixed by
`field.pose_from_registered_samples()`, which reads a registered
sample's `yaw_rad` unchanged (`tools/field.py`, `tools/field_dance.py`,
sprint 029 ticket 007); pinned by
`tests/tools/test_field.py::test_pose_from_registered_samples_*`.

Before writing any code that reads a tag's absolute heading, know which
column you are in. If you are not sure whether a daemon connection has
the tag registered this session, check with
`mcp__aprilcam__list_annotations`/the mount registry, or just register
it explicitly first — registering twice is harmless (TL-02: `register()`
overwrites the daemon's stored entry, it does not compound).

## A residual near ±180° means the ROBOT is driving backwards, not that the plate is on backwards

A probe that comes back "travel bearing = daemon heading + 180°" has
two candidate explanations, and only one of them is the plate:

| candidate | how to tell | what to change |
|---|---|---|
| the plate's "up" points robot-rearward | **look at the camera frame**: the green arrow on the tag does not point at the robot's front | remount the plate; until then `mount_yaw_residual_deg: 180` |
| the firmware drives the robot backwards (wrong motor mapping for this wiring) | the arrow DOES point at the front; pivots still turn the commanded way (a swapped-and-inverted pair reverses travel and leaves rotation alone) | bake the robot's `firmware_bake.motors`; residual stays 0 |

**MEASURED tovez 2026-09-04**,
`captures/bench-acceptance-029-20260904d/heading-probe.log`: with the
tag registered at the fleet's −90° convention the daemon reported
`yaw_rad` = −165.8° while a 5 cm `MOVE_X 50 0 100 5000` displaced the
tag 4.87 cm at bearing +11.4° — the +177° gap. It was recorded as a
backward plate and `mount_yaw_residual_deg: 180` carried the rest of
that day's acceptance runs. It was the second row: the stakeholder
looked at the camera (the arrow pointed at the front, north, while the
daemon with the 180° residual said south), and the firmware's tracked
motor mapping is vevov's (`left{1,-1}/right{2,+1}` in `shims.cpp`)
while tovez is wired left = port 2 (−1), right = port 1 (+1) — a
fact `radio-robot-lib/config/robots/tovez.json`'s `motors` block had
recorded since August without anything baking it. Fixed by
`make_deploy.py::_inject_motors()` reading
`geometry.firmware_bake.motors`; the residual is back to 0.

So: before writing any residual larger than a few degrees, look at the
frame and check the arrow against the direction the robot moved. The
daemon's heading is the thing under test; the arrow is the truth.
`tests/tools/test_camlink.py::test_real_calibration_file_has_no_mounts_table_leftovers`
still accepts ±180° for the genuine backward-plate case and rejects
±90°.

Related: `playfield-testing.md` (camera section),
`measurement-citations.md`.
