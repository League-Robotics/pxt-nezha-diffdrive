# Sprint 029 ticket 007 -- bench acceptance session, 2026-09-04

Robot under test: **tovez** (stakeholder direction, continuing from
2026-09-03; firmware `1.20260903.1`, radio channel 55 / group 108,
farm node meili -- unchanged from the prior session, see
`captures/bench-acceptance-029-20260903/notes.md`).

**Verdict: BLOCKED on a suspected hardware/firmware kernel wedge on
tovez, discovered while running the mandatory pre-flight
`field_dance.py` check. No gate (G1-G6) or measurement (`stop_distance`,
`omega_floor`) was run.** All raw capture logs referenced below are
files in this same directory.

## 1. Lights and placement -- PASS

Shelly `Switch.GetStatus` on `192.168.1.122`: `output: true` (also
`temperature.tC: 59.3`, a plausible steady-state reading, not evidence
of anything). `mcp__aprilcam__get_tags` on `arducam-ov9782-usb-camera`
(one poll, frame_index 283468):

- AprilTag 1 (field centre): world (-0.04, -0.01) cm -- reads (0, 0)
  within noise.
- AprilTag 52 (tovez): world (8.50, 12.71) cm, well within the ~30 cm
  placement tolerance; yaw_rad 3.1809 (182.28 deg raw).

Both confirm the stakeholder's report that the field is now clear and
tovez is placed near centre. No motion commanded yet at this point.

## 2. Mount registration and kernel kick

`uv run tools/camlink.py --register tovez` registered tag 52 from the
(UNVERIFIED) `field_calibration.json` entry -- unchanged mount_x/y/z,
residual 0.0. `field_calibration.json`'s `default_robot` was switched
from `vevov` to `tovez` for this session (required for
`field_dance.py`, which drives whichever robot `default_robot` names --
see `tools/field_dance.py:43-49`). tovez's entry was missing
`lever_cm`/`parallax_k`, which `field_dance.py` requires unconditionally;
added PLACEHOLDER values (`lever_cm: [0,0]`, `parallax_k` borrowed from
vevov's 1.1167, tag heights are close: 11.3 cm tovez vs 11.8 cm vevov)
with an explicit `_lever_parallax_note` -- reasoned in the same note
that `lever_cm=[0,0]` cannot affect `field_dance.py`'s PASS/FAIL
(`turn()` only reads the heading delta, which is lever-independent;
`drive()` differences two poses at the same heading, so a constant
lever error cancels).

First `field_dance.py` run refused outright: `STATUS` showed
`ready=0` (`field-dance-01.log`) -- the known cold-kernel state (see
`.claude/rules` history / MEMORY.md "kernel needs a small kick before
ready=1"). Cleared with `RUN:clearestop` + a single 2 mm `MOVE_X 2 0 50
3000` kick, matching the documented recipe: `ack 1 1 stop`, and
`STATUS` flipped to `ready=1 connL=1 connR=1 cyc=88`. This IS the
session's "cold first move" (MEMORY.md "Cold first move yaws") --
subsequent moves are past that warm-up.

## 3. `field_dance.py` -- FAIL (`field-dance-02.log`)

```
home (   8.7,  12.7) h= -89.5

step                     expected   measured      err  result
turn +90 deg               +90.0d    +146.2d   +56.2d  **FAIL**
turn +180 deg             +180.0d    -122.4d   +57.6d  **FAIL**
turn +90 deg               +90.0d    +137.6d   +47.6d  **FAIL**
drive +20 cm                20.0c     -13.9c   -33.9c  **FAIL**  (bearing off +125 deg)
drive -40 cm                40.0c       5.1c   -34.9c  **FAIL**  (bearing off -39 deg)
drive +20 cm                20.0c      -5.9c   -25.9c  **FAIL**  (bearing off +135 deg)

returned home                0.0c       5.0c    +5.0c  PASS
DANCE FAILED
```

Per `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`: this is
**not** a clean convention flip. A wrong-sign or wrong-90 convention
produces errors clustered near 0/90/180/270; here every pivot
over-rotates by 47-58 deg on 90/180 deg commands and every drive is off
by 26-35 cm with wildly inconsistent bearings (+125, -39, +135 deg) --
not a fixed geometric offset. Read per the rule's own guidance ("a
probe returning anything not within a couple degrees of the model has
found nothing but its own noise, OR the model does not apply") --
this pattern does not fit "convention wrong," it fits "the robot is not
stopping where commanded."

## 4. Evidence gathering (four-phase debugging protocol, Phase 1)

Two further ISOLATED single-pivot probes were run to characterize the
failure before writing it up -- each bracketed by a fresh camera fix
immediately before and after, same discipline as `field_dance.py`'s own
`turn()`. This is a deliberate, logged deviation from
"`field_dance.py` passes before any other commanded motion" --
justified as evidence-gathering after a FAILED dance, not as driving
the field; both probes stayed within the same ~25 cm circle the dance
itself uses, per its own safety argument.

**Probe 1** (`evidence-pivot90-01.log`), `TLM POSE`, commanded
`MOVE_X 0 1571 100 5000` (+90 deg):
camera BEFORE world=(5.25, 8.51) yaw=150.53 deg; AFTER
world=(3.64, 7.78) yaw=260.61 deg -- raw yaw delta **+110.08 deg** on a
commanded +90. Both camera reads are self-consistent with real
physical rotation (small translation matching a short lever arm).

**Probe 2** (`evidence-pivot90-full-telemetry.log`,
`evidence-pivot90-full-frames.json`), `TLM FULL`, same command:
camera BEFORE world=(3.71, 7.71) yaw=261.65 deg; AFTER
world=(5.58, 6.80) yaw=24.97 deg -- raw yaw delta **+123.32 deg**.

**The critical finding is in the telemetry, not the camera.** Every one
of the 76 `t` frames captured during this probe's 6.4 s window shows
`h` (odometry heading, cumulative centidegrees) frozen at exactly
`85807`, `vl`/`vr` = 0, `dutl`/`dutr` = 0, throughout -- the firmware's
own telemetry reports **zero motion for the entire window**, while the
camera (independently confirmed stable and jitter-free at rest
immediately afterward, see below) shows a large, real rotation. `cyc`
(kernel cycle counter) climbed normally to 2336 by the end of the
capture and then **never advanced again** in any later `STATUS` read
this session (`evidence-atrest-camera-stability.log`: `cyc=2336`,
twice, several `STATUS`/`HELLO` round trips apart).

**Camera cross-check (no motion commanded)**: 8 samples over ~4 s at
rest, `evidence-atrest-camera-stability.log` -- x/y/yaw stable to
<0.02 cm / <0.3 deg, corner geometry consistent frame to frame. The
camera instrument is not the fault; per
`.claude/rules/playfield-testing.md`'s "prove the instrument was
watching" discipline, it was watching, and it was stable.

`RUN:clearestop` (unsequenced in the cleartext plane) got **no reply**
in the probe-2 script (3 retries), and a subsequent bare `ESTOP` (one
of the firmware's seven always-unsequenced exemptions, per
`.claude/rules/playfield-testing.md`'s wire-command table) **also got
no reply** (4 retries) -- while `HELLO` and `STATUS` continued
answering normally throughout every one of these scripts.

**Working hypothesis, not confirmed**: the robot's motion-control fiber
wedged partway through or shortly after probe 1 (or before it -- exact
onset not pinned down), most likely an I2C/OTOS wedge given this
fleet's well-documented history (`STATUS`'s own `otos=1` flag, and the
`RUN:probe bricks the board` / `I2C wedge is stale state, not firmware`
project lore) -- the wire/radio handling layer stayed alive and kept
answering `HELLO`/`STATUS` (and generating the unconditional
`ack <id> <lastDone> <lastReason>` header per `src/comms/wire_handler.cpp:733`),
while the fiber that owns motion state, telemetry sampling, and (it
appears) `ESTOP`/`RUN:clearestop` handling stopped ticking (`cyc` frozen).
Under this hypothesis the large, real camera-measured rotations reflect
motion that genuinely happened on the wheels before/during the wedge,
never cleanly braked or reported, continuing until each command's
outer deadline (5000 ms) force-stopped it -- which is also consistent
with every observed `ack`/status line this session reporting
`reason=timeout`, and NEVER `reason=stop`, on any of the six dance
moves or either evidence pivot (only the very first 2 mm kick, before
any of this, reported `reason=stop`).

This is a hypothesis, not a MEASURED conclusion -- `STATUS`'s own
`wedge` flag reads `wedge=0` throughout, which does not fit cleanly,
and no independent instrument (e.g. a serial console on tovez, if one
exists) was available this session to confirm the fiber is actually
stalled versus something else entirely (a firmware defect in the new
K1-K4 kernel patches or the predictive-arrival logic that merely LOOKS
like a wedge from the wire side). Distinguishing these needs hands-on
access this session does not have.

## 5. Safety action and stop

An `ESTOP` was sent as a safety measure once the anomaly was
recognized (no reply, consistent with the fiber-wedge hypothesis --
see above). No further commanded motion was sent after this. The
robot's last confirmed position (camera, at rest): world (5.58, 6.80)
cm, well inside the field and the safety margin -- no geofence risk.

**Everything downstream of this point -- the lever-arm/residual fit,
`field_dance.py` passing, all of G1-G6, and the two design S10.2
measurements (`stop_distance`, `omega_floor`) -- is NOT started.**

## What a human needs to do before this ticket can resume

1. **Physically recover tovez's kernel** -- most likely a power cycle
   (this fleet's I2C wedges have historically needed a hard reset or a
   `gauti`-style serial BREAK; MEMORY.md "gauti BREAK reset unbricks
   vevov" describes the technique for a robot with an onboard
   companion Pi -- unclear whether tovez has an equivalent; a plain
   power cycle is the fallback). A reflash is a second-line option if
   a power cycle does not clear it (MEMORY.md "I2C wedge is stale
   state, not firmware -- a reflash cures it, which silently
   invalidates firmware bisects").
2. **Re-run `field_dance.py` from a clean boot** before anything else.
   If it passes cleanly (errors within the dance's own 8 deg / 3 cm
   tolerance), the wedge hypothesis above is supported and ticket 007
   can resume at the mount-fit step. If it fails again with the SAME
   kind of large, inconsistent errors, this is a firmware defect in
   the new engine, not a wedge, and needs `radio-robot-elite`/firmware
   engineering attention before any bench acceptance number here can
   be trusted.
3. Session robot-of-record: `tools/field_calibration.json`'s
   `default_robot` was left as `tovez` (was `vevov`) -- a future
   session on a different robot must switch it back, per
   MEMORY.md "robot assignment is per session."
