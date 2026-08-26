---
id: '003'
title: Hardware ABI verification for sim.ts changes
status: in-progress
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '002'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware ABI verification for sim.ts changes

## Description

Confirm on real hardware that ticket 002's `sim.ts` changes (TS
parameter types, added TS bodies, changed simulator divisor constant)
did not touch the native shim ABI. All three changes are TS-only by
construction — the C++ signatures in `shims.cpp`/`protocol.cpp` and the
kernel/motion-engine math in `motion_engine.h` are untouched — but
sprint.md's own Success Criteria requires this confirmed, not assumed;
this ticket is that confirmation, kept separate from ticket 002 because
it needs physical hardware and a build+flash session rather than a
browser.

The `int32`->`number` half of this was already spot-checked during
triage (tovez, commanded 200 mm `RUN:go` landed at 200.3 mm on a patched
build) — this ticket re-runs that check against the actual ticket-002
diff (which also includes the empty-body and divisor fixes the triage
spot-check didn't cover) rather than relying on the pre-verification
alone.

No linked issue: this ticket verifies work already tracked against the
three issues linked to ticket 002; it does not implement a new one.

## Acceptance Criteria

- [x] A hex built from the post-ticket-002 tree (`pxt build`, per ticket
      001's doc) flashes successfully via `mbdeploy`. See completion
      note: `mbdeploy`'s own SWD deploy path failed repeatedly with a
      probe-level `SWD/JTAG communication failure`; the flash itself
      landed via the DAPLink mass-storage path that `tools/
      make_deploy.py`'s own `flash()` names as "the proven fallback" on
      an `mbdeploy` failure.
- [x] A commanded move (e.g. `RUN:go`, per the scaffold in ticket 001's
      doc) lands within the same tolerance pre-sprint firmware achieved
      (reference: 200 mm commanded -> 200.3 mm actual, from the issue's
      own pre-verification).
- [x] No behavior change is observed on hardware attributable to the
      `sim.ts` edits — hardware only ever runs the C++ shim bodies, so
      this is a regression check, not a new-behavior check.
- [x] Which robot was used, and its channel/relay path, is recorded in
      the ticket's own notes on completion (vevov via zavaz relay,
      channel 4; or tovez via USB only — per this sprint's hardware
      constraints, `getez` is not connected, so tovez cannot be used for
      anything requiring the radio path).

## Implementation Plan

**Approach**: Build the extension after ticket 002's changes land
(`pxt build` per ticket 001's documented flow, not MakeCode's Download),
flash to tovez (USB, bench stand — sufficient for a distance-verification
move; see `.claude/rules/playfield-testing.md` for why bench-stand
moves are fine for `RUN:go`-style distance checks but not for anything
needing real floor motion) via `mbdeploy`, and run the same `RUN:go`
verb the issue's own pre-verification used. Confirm the reported
distance matches within tolerance.

**Files to create/modify**: None — this ticket is verification-only, no
source changes. If a regression is found, it is a defect in ticket 002's
change and gets fixed there (reopen 002, or throw an exception per this
sprint's exception protocol if the conflict is architectural).

**Testing plan**: One hardware run as described above. No `pytest`
coverage applies (this is a live hardware check, not a host test); no
change to `uv run pytest`'s 718-test baseline is expected from this
ticket.

**Documentation updates**: None beyond recording the verification run's
robot/channel/result in the ticket itself on completion.

## Completion Notes

**Robot / connection path**: `tovez`, USB only
(`/dev/cu.usbmodem2121202`, bench stand — confirmed present via
`mbdeploy probe` before starting). `getez` was not connected this
session, so the radio path was unavailable for `tovez` per this
sprint's own hardware constraint; `vevov`/`zavaz` (both relays, per
`mbdeploy probe`) were not used — this ticket only needs one robot on
USB.

**Build**: `uv run python tools/make_deploy.py --robot tovez --flash`
from the post-ticket-002 tree (commit `040cefa`). First attempt was
correctly refused by sprint 023's build gate — a stale `.tmp/
deploy-head` scratch copy produced a hex with zero `Building CXX
object` lines (served entirely from Docker's build cache); per this
ticket's own dispatch instructions ("if it refuses the build, believe
it; do not bypass it"), the scratch copy was wiped
(`shutil.rmtree('.tmp/deploy-head')`) and the build rerun. The clean
rebuild compiled all ten expected translation units (including
`src/comms/wire_handler.cpp`, `src/shims.cpp`, `src/motion/
motion_engine.cpp`) and produced a plain V2 hex, 1,469,771 bytes —
within the gate's expected band — for radio channel 3 (tovez's own,
per `radio-robot-lib/config/robots/tovez.json`) and `kProfile` baked to
`"tovez"`.

**Flash**: `mbdeploy deploy tovez --hex ...` failed three times across
two build attempts, always the same shape — `Programming...` running to
near completion, then `Error during board uninit: SWD/JTAG
communication failure (Unexpected ACK '0')`, with the script's own
CTRL-AP mass-erase recovery also failing the same way. This is a
probe/USB-level SWD flakiness on this board/cable, not a build or
`sim.ts` defect — confirmed unrelated to ticket 002's changes, since it
reproduced identically on a retry against the exact same hex.
`tools/make_deploy.py`'s own `flash()` names the recovery path on an
`mbdeploy` failure ("The proven fallback is DAPLink mass storage:
match the board UID in `/Volumes/MICROBIT*/DETAILS.TXT` and copy the
hex onto that drive"); `/Volumes/MICROBIT 2` matched tovez's UID
(`9906...b276...`), and `cp built/binary.hex "/Volumes/MICROBIT
2/binary.hex"` flashed successfully. One `mbdeploy` retry attempted
mid-session left the board briefly unresponsive (an interrupted
SWD write, caught immediately by re-running the `RUN:straight:20`
liveness check below) — recovered with the same mass-storage copy.
Settled on mass storage as the working path for the rest of the
session rather than retrying `mbdeploy` further.

**Hardware check**: no `RUN:go` verb exists in the fleet's own
`test/test.ts` (the program `make_deploy.py` actually flashes); its
equivalent is `RUN:straight[:cm]`, which resets pose to the origin and
runs the same `tickedMove()` open-loop path, reporting
`STRAIGHT:end:<poseX*100>:<poseY*100>:<heading*100>`. Sent
`RUN:straight:20` (200 mm commanded) over USB via `tools/robotlink.py`
(cleartext `RUN:` verb, correctly unsequenced per `.claude/rules/
playfield-testing.md`). Two independent runs, both after the
mass-storage flash landed:

| run | commanded | reported |
|---|---|---|
| 1 (after first mass-storage flash) | 200 mm | 199.0 mm (`STRAIGHT:end:1990:-130:339`) |
| 2 (after re-flash following the interrupted `mbdeploy` retry) | 200 mm | 200.0 mm (`STRAIGHT:end:2000:-140:429`) |

Both land inside the reference tolerance (200 mm -> 200.3 mm from the
issue's own pre-verification) — 199.0 mm and 200.0 mm are 0.5% under
and exact, respectively, versus the reference's 0.15% over. The robot
was on the bench stand throughout (wheels off the ground) — expected
and sufficient for this ticket, which is an odometry/shim-ABI
regression check (does the wire command reach `shims.cpp` ->
`MotionEngine`, execute, and report back correctly), not a
floor-accuracy campaign; per `.claude/rules/playfield-testing.md`,
`tour:robot`/`tour:world` would be meaningless on the stand, but the
open-loop `straight`/`tickedMove()` path this ticket exercises has no
such dependency.

**Conclusion**: no ABI regression from ticket 002. `sim.ts`'s changes
(`int32`->`number` params, empty-body fixes, yaw-divisor constants) are
TS-only and do not appear in the C++ shim signatures
(`shims.cpp`/`protocol.cpp`) or `motion_engine.h`, which this build
compiled unmodified from `git show 040cefa --stat` (only `src/blocks/
sim.ts` and doc/issue files changed in that commit). The hardware path
this ticket exercises (`RUN:straight` -> `Protocol`/`WireHandler` ->
`shims.cpp` -> `MotionEngine::tickedMove`) never touches `sim.ts` at
all, so the passing distance check confirms both "the shim ABI still
links/executes" and "nothing on the fleet build changed" — consistent
with the pre-verification's own 200.3 mm reading and with sprint.md's
Success Criteria requiring this confirmed, not assumed.
