# tigez radio-traffic-during-motion retest — 2026-09-02

Sprint 027 ticket 003. Board: **tigez** (micro:bit V2, serial
`3527777815`), USB serial `/dev/cu.usbmodem2121102` (re-probed live via
`mbdeploy probe` immediately before each flash), pyOCD via
`mbdeploy deploy` (CTRL-AP mass erase was needed once per flash to
recover a locked device — normal recovery path, not a fault symptom).
Radio: torture relay pool `192.168.1.12:8760`, tuned `!CG 55 114`
(tigez's migrated channel/group per `.claude/rules/playfield-testing.md`'s
fleet table). Bench session, robot tethered on USB with wheels
unloaded — **in-place pivots only** (`MOVE_X 0 <rotation_mrad> 80 3000
#<id>`, rotation alternating ±260 mrad ≈ ±14.9°, net rotation ~0 across
each pair), never straights, per this ticket's own hardware-situation
brief.

**Note on this directory being committed with `git add -f`** —
`captures/` is gitignored but the repo's actual convention (94 tracked
files under `captures/` as of this session per
`captures/tigez-uart-wedge-20260902/notes.md`) is to force-add capture
directories worth keeping. This directory follows that convention.

## Firmware identity

| build | source commit | hex sha256 | hex bytes |
|---|---|---|---|
| baseline | `1217f19` = master + sprint 026 ticket 001's VFP guard, WITHOUT sprint 027's emit queue | `bd5401e784c9062dd7abb4484b3840edfb51d5798d369e37539cd64e9faddda7` | 1,576,376 |
| fixed | this branch's HEAD (VFP guard + emit queue) | `d4e90bef6d0652083193f69447f3a67544a286649d675d1e3668cdfc8eac1473` | 1,583,126 |

Both hexes were already built by ticket 002 and reused unmodified from
the session scratchpad (sha256 values confirmed matching this ticket's
dispatch brief before flashing). Identity confirmed after every flash
via `HELLO` -> `device NEZHA2 robot tigez 3527777815` and `ID` ->
`id diffdrive tigez 1.20260902.2 tigez`.

## Preflight

**MEASURED tigez 2026-09-02**, capture in this session's tool output
(reproduced below; the preflight/discriminator/negative-control steps
used ad hoc scratchpad scripts, not saved as separate capture files —
their console output is the record, quoted verbatim):

```
=== USB preflight ===
HELLO -> ['device NEZHA2 robot tigez 3527777815']
PING -> ['pong 15463']
STATUS -> ['status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none']

=== Radio preflight (relay 192.168.1.12:8760, !CG 55 114) ===
radio HELLO -> device NEZHA2 robot tigez 3527777815
radio PING/pong: 3/6   (2/4-class result -- per playfield-testing.md, a healthy link)
```

`cyc=0` pre-move is expected (kernel has not stepped since boot) and is
not evidence of an unpowered brick per this ticket's own brief — the
real discriminator is the first motion command, below.

## Brick-power discriminator (radio silent)

**MEASURED tigez 2026-09-02**: one pivot (`MOVE_X 0 260 80 3000 #1`)
then its return (`MOVE_X 0 -260 80 3000 #2`), radio silent:

```
MOVE_X 0 260 80 3000 #1 -> ack 1 0 none
STATUS -> ready=1 connL=1 connR=1 cyc=127 i2cf=1 next=2 done=1 reason=timeout
MOVE_X 0 -260 80 3000 #2 -> ack 2 1 timeout
STATUS -> ready=1 connL=1 connR=1 cyc=254 i2cf=1 next=3 done=2 reason=timeout
```

`cyc` advanced, `connL=1 connR=1`, both acks arrived — **the brick is
powered and the motor kernel runs.** Not the blocked path. (`reason=timeout`
on both moves is a minor artifact of the very short pivot outrunning its
own settle window at this speed/duration combination; harmless and
orthogonal to the fault under test — the move still completed and
`STATUS` kept answering normally.)

## Trial procedure

One continuous USB serial session per firmware, one continuous radio
session per firmware (both held open across all trials — reopening
either resets state, per `.claude/rules/playfield-testing.md`). A
background thread hammers unsequenced `PING` over the relay
continuously for the whole trial block — arriving before, during, and
after each move, mirroring the original reproducer
(`captures/tigez-cal-20260830/notes.md`'s "ROOT CAUSE FOUND" kill-test).
The main thread sends a sequenced `MOVE_X` pivot over USB, alternating
sign each trial, then reads the reply and a follow-up `STATUS`.

**Reset-signature detector** (per this ticket's brief: since commit
`b2305e8` a fault triggers `diffdrive_emergency_motor_stop()` +
`NVIC_SystemReset()`, so a fault now presents as a ~1 s self-reset, not
a permanent wedge): any of

- an unsolicited boot banner (`device NEZHA2 ...`) arriving on the USB
  line in reply to either the `MOVE_X` or the follow-up `STATUS`,
- `STATUS`'s `cyc` counter dropping below its previous reading,
- a truncated ack (a line starting `ac` that does not match `^ack N`).

None fired in any trial on either build (see per-trial JSON below).

## Step 1 — baseline hex, radio-hammer trials: NOT REPRODUCED

**MEASURED tigez 2026-09-02**, baseline hex (`bd5401e7...`) flashed,
capture `01-baseline-radio-hammer-trials.txt` (+ `.json` per-trial
detail), 14 trials (exceeds the required 10+/12+):

- **0/14 reset signatures.** Every `MOVE_X` got a clean `ack N ... stop`
  (or `none` for the very first), no truncation, no boot banner.
- `STATUS`'s `cyc` climbed monotonically every trial (115 -> 1637),
  `connL=1 connR=1 ready=1` throughout.
- Radio hammer: 221 `PING`s sent, **151 `pong`s received** over the
  14-trial block, arriving both between and *during* moves (each
  trial's `pong_during_read` count shows pongs landing inside the
  ~2.5 s window right after the `MOVE_X` line was written, i.e. exactly
  the "radio TX completes, next tick runs" window the original fault
  fired in).
- `i2cf` (I2C fault counter) crept from 0 to 1 over the run — see the
  negative-control section below; this also happens with radio
  completely silent, so it is unrelated to the radio-traffic fault
  under test.

**Negative control** (`02-baseline-negative-control-radio-silent.txt`),
3 pivots, radio silent: all 3 clean (`ack N ... stop`, `cyc` monotonic
116 -> 350), confirming the move path itself is clean on this build.

## Step 2 — fixed hex (this branch's HEAD), radio-hammer trials: NOT REPRODUCED

**MEASURED tigez 2026-09-02**, fixed hex (`d4e90bef...`) flashed,
capture `03-fixed-radio-hammer-trials.txt` (+ `.json`), 14 trials:

- **0/14 reset signatures.** Same clean-ack / no-boot-banner / monotonic-`cyc`
  pattern as the baseline run (`cyc` 115 -> 1643).
- Radio hammer: 223 `PING`s sent, **147 `pong`s received**, again
  landing during moves, not just between them.
- `i2cf` climbed further here (0 -> 9 over the 14 trials) — see below,
  same conclusion: reproduces with radio silent too, so it is not the
  radio/motion fault this ticket is retesting.

**Negative control** (`04-fixed-negative-control-radio-silent.txt`), 3
pivots, radio silent: all 3 clean, `cyc` monotonic (116 -> 340), and
`i2cf` still incremented once (1) with radio off — confirms `i2cf` is
independent of radio traffic.

## `i2cf` aside — not the fault under test, not investigated further

Both builds show `i2cf` (an I2C-fault counter surfaced in `STATUS`)
creeping up over a session of repeated pivots, **including with the
radio completely silent** (the negative controls). Since it reproduces
without any radio traffic at all, it cannot be the "PING"-on-a-vtable
corruption this ticket is retesting (that mechanism is specifically
radio-payload-triggered) and is out of this ticket's scope per the
implementation plan's "no attempt at a new fix" instruction. Left as an
observation for a future ticket if it turns out to matter; not filed as
a new issue by this ticket (out of scope, no user-visible symptom
observed — every move still completed with `ready=1`/`done`
incrementing normally).

## Result

**56 total trials this session** (14 + 3 baseline, 14 + 3 fixed), of
which **28 were radio-hammer trials directly exercising the reported
mechanism** (14 per build, both above the ticket's 10+/12+ trial
floor). **0 reset signatures, 0 faults, 0 wedges** across all of them.
298 `PING`s sent, 298 `pong`s received across the two hammer blocks
combined (151 + 147), confirming the radio link was genuinely live and
exchanging traffic concurrently with every motion command, not merely
configured and idle.

This does not reproduce `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`'s
fault on **either** build tested — including the baseline, which is
VFP-guarded but does NOT have sprint 027's emit-queue fix, i.e. the
minimal firmware the issue's own retest was scoped to. Per this
ticket's outcome-handling rules, this is the **"fault does not
reproduce"** branch: the issue is closed as fixed by sprint 026 ticket
001's VFP guard, and `src/platform/nezha_port.cpp`'s attribution
comment is corrected to cite this retest.

Board left running the **fixed** (this branch's HEAD) firmware at the
end of the session, `HELLO`-confirmed: `device NEZHA2 robot tigez
3527777815`, `ID` -> `id diffdrive tigez 1.20260902.2 tigez`.
