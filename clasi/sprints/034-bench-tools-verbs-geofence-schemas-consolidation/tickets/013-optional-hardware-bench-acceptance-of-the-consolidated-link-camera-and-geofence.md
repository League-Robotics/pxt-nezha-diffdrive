---
id: '013'
title: 'OPTIONAL, HARDWARE: bench acceptance of the consolidated link, camera and
  geofence'
status: in-progress
use-cases:
- SUC-001
- SUC-002
- SUC-005
depends-on:
- '012'
github-issue: ''
issue:
- tools-v6-verbs-geofence-pose-csv-schema.md
- tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# OPTIONAL, HARDWARE: bench acceptance of the consolidated link, camera and geofence

## Description

**OPTIONAL. HARDWARE. LAST. Do not run this as part of the overnight
batch.** Every other ticket in this sprint is verifiable host-side with
no robot and no camera; this one is not, and it exists so that the
hardware dependency is named in one place instead of being buried inside
a software ticket.

**`completes_issue: false`** -- this ticket deliberately does not close
the issues it references. The software half is delivered and closed by
tickets 004-009; this is the on-field confirmation of that work, and the
issues should archive on those tickets' completion, not wait on a bench
session that may not happen.

Three things the host suite genuinely cannot prove:

1. **A `MOVE_X` sent through the consolidated `Link` actually moves the
   robot.** Ticket 005 proves the id is *attached*; only a robot proves
   it is *accepted and executed*. The whole failure mode being fixed is
   a command that looks sent and never runs -- and odometry cannot
   detect its own failure to move (`.claude/rules/playfield-testing.md`).
2. **The in-process `Cam` reads the same poses the subprocess did.**
   Ticket 008's tests use an injected fake client. A real daemon, a real
   tag and a real registered mount are a different thing.
3. **The geofence refuses a real out-of-bounds target** without breaking
   a legitimate run.

## Preconditions -- read before starting

- A board is assigned **by the stakeholder for this session**. There is
  no standing ownership table; do not infer a robot from an old note.
- Check the room lights **first** (Shelly at `192.168.1.122`,
  `Switch.GetStatus?id=0`, `output` must be `true`). They turn
  themselves off, and a dark field looks exactly like a broken camera.
- WiFi TCP is the default carrier (`rogo <name>`); the WiFi carrier is
  known to drop once the motors have been working, so prefer the radio
  or an on-robot Pi serial daemon for anything with sustained motion.
- Do **not** SSH to the robot Pis; use mDNS plus the advertised serial
  port.
- The aprilcam daemon needs a **Terminal** launch for camera TCC
  permission -- it will not start from an agent process tree.
- Compute the full projected path from a **measured** start pose before
  any commanded motion. That is the primary check; the geofence is the
  backstop.

## Acceptance Criteria

- [ ] Over the consolidated `Link`, a `MOVE_X` is acknowledged and the
      robot moves, confirmed by an **external instrument** (the overhead
      camera or a tape) -- never by odometry alone.
- [ ] `Cam` reports a pose consistent with ground truth for a robot
      parked on a known dot, using a registered mount.
- [ ] A registered sample's heading is used **unchanged** -- no `+90 deg`
      applied on top. A drive whose travel bearing comes out ~90 deg off
      while pivots look fine is that bug, not a mount problem
      (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`).
- [ ] `check_path()` refuses a deliberately out-of-bounds target, and
      does **not** refuse a legitimate in-bounds run.
- [ ] `uv run python tools/wire_acceptance.py --wifi-tcp <name>` passes
      (or its BLOCKED cases are accounted for) after ticket 006's
      changes to its link classes.
- [ ] Every result is captured to a file under `captures/` and cited by
      path, board name and date. **`captures/` is gitignored** -- use
      `git add -f`, or the MEASURED citation points at nothing.
- [ ] Any claim of measured behaviour names its artifact
      (`.claude/rules/measurement-citations.md`). If something was not
      run, write **UNVERIFIED** and say what would settle it. That is a
      perfectly respectable outcome for this ticket.

## Implementation Plan

### Approach

Per the project's hardware-ticket practice: on-robot acceptance is **one
scripted session run by the team-lead**, not a programmer dispatch
cycle. Write the script, dry-run its non-motion paths host-side, then
hand it over.

A pre-flight miss with a known tooling cause is not a stop signal -- but
a probe returning a heading offset more than a couple of degrees from
the expected +90 deg means the tag plate is physically rotated. That is
the finding; it is not a new offset to bake in.

### Files

A single scripted session program, most naturally under
`tests/calibration/` beside the other on-robot programs (read
`tests/calibration/DESIGN.md` first), plus a capture directory.

### Depends on

Ticket 012 -- everything else must be landed and documented first.

## Testing

- **Host-side**: the script's argument parsing, its pre-flight checks and
  its refusal paths are unit-testable with an injected fake link and fake
  camera, and **should be**, before it ever sees a robot.
- **On-robot**: the acceptance run itself, captured.
- **Verification command**: `uv run pytest tests/calibration -q` for the
  host-side half.

## Host-side implementation record

**Status: the HOST half is landed; the on-robot half is UNVERIFIED.**
No acceptance box above is ticked, because every one of them describes
a result that only a robot, a camera and a lit field can produce. This
section records what exists so a later session can run it, and what the
operator has to do to close them.

Per the ticket's Implementation Plan ("write the script, dry-run its
non-motion paths host-side, then hand it over") and the project's
hardware-ticket practice, the scripted session was written, its
argument parsing / pre-flight checks / refusal paths were unit-tested
against an injected fake link and fake camera, and nothing was driven.

### What landed

- `tests/calibration/consolidation_acceptance.py` -- the scripted
  session. Registered in `tests/calibration/calibrate.py`'s dispatcher
  as `acceptance` and documented in `tests/calibration/DESIGN.md`
  (its own section, since it is the one program in that directory that
  is not a calibration) and `tests/DESIGN.md`.
  - built on this sprint's consolidated surface only: `tools/link.py`
    (`Sequencer`/`LineBuffer` via `robotlink.Link`), `tools/robotlink.py`
    (`Link`, `open_link`, `WifiSerial`), `tools/wifilink.py`,
    `tools/camlink.py` (in-process `Cam`, `Cam.register()` from the
    calibration of record -- construction never registers),
    `tools/field.py` (`require_clear_path`/`PathRefused`,
    `usable_half_extent`, `DOTS`, `wrap`,
    `pose_from_registered_samples`, `registered_pose_distance`) and
    `tools/reposition.py` (`Repositioner`);
  - pre-flight, each PASS/FAIL/BLOCKED with a reason: Shelly lights
    (injectable HTTP getter; the real one is `urllib`), `PING` on the
    chosen carrier (never `HELLO` -- that is a session reset), the
    field-centre tag at world (0, 0), and this robot's tag visible and
    REGISTERED. A non-PASS stops the run before any move is armed and
    records the three checks `BLOCKED` rather than skipping them;
  - check (a) `check_move_x()`: measured start pose, full projected
    path checked from it, `MOVE_X` with the id attached by the shared
    `Sequencer`, ack matched by id, completion polled via `STATUS`,
    then displacement scored from the CAMERA against a minimum travel
    -- odometry alone never confirms it;
  - check (b) `check_pose_ground_truth()` against `field.DOTS`, with
    `registered_heading()` used unchanged and `double_add_signature()`
    naming the "+90 applied twice" pattern (a ~90 deg travel-bearing
    error while rotation looks fine) when it appears;
  - check (c) `check_geofence()`: an out-of-bounds `Repositioner.go()`
    must raise `PathRefused` with **nothing on the wire** (asserted
    against a `RecordingLink`), and a legitimate in-bounds target must
    not be refused;
  - capture: every result, the camera readings and every command line
    appended to `<capture-dir>/notes.md`, plus the `git add -f`
    reminder in the file and on the console;
  - `--dry-run` prints the whole plan and opens no carrier, no camera
    and no socket.
- `tests/calibration/test_consolidation_acceptance.py` -- **55 host
  tests**, no robot, no daemon, no network. Covers: lights BLOCKED when
  off / unreachable / malformed; field centre BLOCKED when tag 1 is not
  visible and when the stream is dead; the `MOVE_X` line carrying
  `#<id>` (through the REAL `robotlink.Link` over a `FakePort`, so the
  consolidated sequencer is what attaches it); the move FAILING when
  the camera shows no displacement, with the robot-is-off case named;
  the path check refusing with nothing sent; the geofence refusing
  out-of-bounds with nothing sent and accepting in-bounds; the
  registered heading NOT gaining a +90 (plus an `ast` guard that the
  program never calls `robot_heading_from_tag_yaw()`); `--dry-run`
  opening nothing; carrier selection and the capture file.

### What a future operator runs to close the boxes above

A board is assigned by the stakeholder for that session; `tovez` below
is a placeholder. Read the plan first, then run it:

```
uv run python tests/calibration/calibrate.py acceptance <robot> --dry-run
uv run python tests/calibration/calibrate.py acceptance <robot> --dot NE
uv run python tools/wire_acceptance.py --wifi-tcp <robot>
git add -f captures/consolidation-acceptance-<robot>-<date>/notes.md
```

Prefer `--radio` or `--serial <host:port>` over the default WiFi TCP
for the run with motion in it -- WiFi drops once the motors have been
working. Park the robot on the `--dot` dot **facing inward**: the
`MOVE_X` probe drives along its measured heading, so a robot facing out
from a corner has its probe refused (correctly) before anything is
sent. Exit code 0 = every check passed, 1 = something FAILED, 2 =
nothing failed but something was BLOCKED -- record those as
**UNVERIFIED** and say what would settle them, which is a perfectly
respectable outcome for this ticket.

### Deliberately not done here

No robot, relay, Shelly or aprilcam daemon was touched, and **no
MEASURED claim is written anywhere** in the program, its tests or this
record (`.claude/rules/measurement-citations.md`) -- the program
produces the artifact a future citation will point at. `status` stays
`in-progress`; how the on-robot half is recorded is the team-lead's
call.
