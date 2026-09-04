# Sprint 029 ticket 007 -- bench acceptance session, 2026-09-03

Robot under test: **tovez** (stakeholder direction this session).

## 1. Build and flash -- PASS

`uv run tools/make_deploy.py --robot tovez --radio-link` failed on the
first attempt (real defect, not a benign packaging abort):

```
error: Extension this:
   nezha-diffdrive/src/shims.cpp(1481): declaration not understood: void setLimits(int accel, int decel, int vMax,
```

Root cause: `setLimits()` (added by sprint 029 ticket 004, the config
surface) is a `//%`-annotated PXT shim whose declaration was split
across two lines. Every other `//%` shim in `src/shims.cpp` keeps its
declaration on one line (`grep -n "^//%$" -A1 src/shims.cpp` confirms
all 37); the multi-line ones in the file (`setWheelsTimed`,
`driveTwistTimed`, `engineWheelsX`, `engineMoveX`) are explicitly *not*
`//%`-annotated, by design, per their own comments. `setLimits` was the
only `//%` shim broken this way. Fixed by joining the declaration onto
one line (`src/shims.cpp:1481`); no behavior change, comment/units
preserved.

Rebuilt clean:

```
hex: .tmp/deploy-head/built/binary.hex (1680281 bytes) [attempt 1]
radio: channel 55 group 108 for 'tovez'
make_deploy: v6 radio link ENABLED in test.ts (BOOT_RADIO_LINK = true)
```

`mbdeploy list --remote`: tovez on farm node **meili**, ENUM 6.

`mbdeploy deploy tovez --remote --hex .tmp/deploy-head/built/binary.hex`:
first attempt hit `flash erase sector failure (address 0x00000000;
result code 0x67)`; mbdeploy's own CTRL-AP mass-erase recovery kicked
in automatically and the retry programmed cleanly (418816 bytes, 103
pages, 0 identical -- a full reflash, not a partial/blank result).

Post-flash identity check over the farm remote connection
(`mbdeploy connect tovez --remote <verb>`, one verb per connection --
each open/close cycle resets the target program, matching
`.claude/rules/playfield-testing.md`'s serial-port-reset note, so the
first `HELLO` in a fresh connection got no reply and the second did):

```
HELLO  -> device NEZHA2 robot tovez 2314287040
VER    -> ver 1.20260903.1
ID     -> id diffdrive tovez 1.20260903.1 tovez
STATUS -> status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none
```

`ready=0`/`connL=0`/`connR=0` at this point is expected -- no motion
has been commanded yet (matches the `null-fleet-daemon` / cold-kernel
note that the kernel needs a small kick before `ready=1`); it is not
evidence of a fault this session, just a pre-motion baseline.

**Verdict: build and flash PASS.** Firmware `1.20260903.1` (today's
build) is running on tovez, radio link enabled, on farm node meili.

## 2. Camera and placement check -- STOP, no motion commanded

Per the ticket's mandatory order, before any commanded motion: read
the field through the aprilcam daemon and confirm (a) AprilTag 1 (the
fixed field-centre marker) reads world (0, 0), and (b) AprilTag 52
(tovez's mount) is visible and within ~30 cm of field centre.

`mcp__aprilcam__get_tags(camera="arducam-ov9782-usb-camera")`, two
consecutive polls (frame_index 97019 and 97077, ~8s apart): only the
ArUco border tags (1, 2, 3, 5, 6, 7) came back. **No AprilTag-family
tag was detected at all** -- neither AprilTag 1 (field-centre) nor
AprilTag 52 (tovez).

A raw frame and a deskewed frame from the same camera
(`raw-frame-placement-check.jpeg`, `deskewed-frame-placement-check.jpeg`,
this directory) explain why: **the playfield currently has the KIPR
line-following mat laid over it, with soda cans placed as obstacles at
several of the mat's numbered stations.** This is not the open
motion-gate playfield the design's G1-G6 gates need, and AprilTag 1
(field centre, painted straight onto the base playfield board under
the mat) is physically covered. tovez itself is not visible anywhere
in either frame -- it has not been placed on the field this session.

Room lights: `Switch.GetStatus` on the Shelly (`192.168.1.122`)
reported `output: true` immediately before this check, and the camera
frame itself confirms the field is well lit (not the
Shelly-says-on-but-frame-is-dark trap) -- lighting is not the cause
here.

**Stopped here per the ticket's instructions.** No `MOVE_X`,
`field_dance.py`, mount registration, or any other commanded motion
was run this session. Getting the field into a state where G1-G6 can
run needs a human:

1. Clear the KIPR line-following mat and the soda-can obstacles off
   the playfield.
2. Place tovez at (or very near) field centre, tag 52 facing a known
   direction, before the next session runs `field_dance.py`.

Everything downstream of this point in ticket 007
(`field_dance.py`, the mount registration/re-measurement, G1-G6, the
two §10.2 measurements, and the doc/config updates that depend on
their results) is **not started** and stays that way until the field
is cleared and tovez is placed.
