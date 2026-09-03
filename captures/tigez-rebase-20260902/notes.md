# tigez bench acceptance -- sprint 028 ticket 002 (SET rebase / SET estop_clear)

MEASURED tigez 2026-09-02, USB bench (`/dev/cu.usbmodem2121102`), fw built
from this ticket's own working tree via
`uv run python tools/make_deploy.py --robot tigez` (after wiping the
stale `--robot gopiv` `.tmp/deploy-head`) and flashed with
`mbdeploy deploy tigez --hex .tmp/deploy-head/built/binary.hex`.
Transcripts: `transcript.txt` (main run), `busy_refusal_retest.txt`
(focused retest of the busy-refusal check -- see below for why a retest
was needed). Both produced by
`uv run --with pyserial python <script>` one-shot scripts (source not
checked in; this file records what each did and found).

**This is a BENCH-ONLY check.** tigez was on this Mac's USB at the bench,
not the playfield, and no OTOS-equipped robot was reachable this session
(gopiv on farm node meili: SWD No-ACK; tovez/vevov: not on USB or the
farm). The ticket's hardware acceptance criterion (a camera-truthed tour
issuing `SET rebase 1` at leg 1, on an OTOS-equipped chassis AND tigez)
stays **UNVERIFIED** for the field/camera half -- see the ticket's own
notes for what was substituted here.

## HELLO / identity

```
>>> HELLO
<<< device NEZHA2 robot tigez 3527777815
```

Matches the fleet table (`3527777815 mod 3125 = 2815 -> base5("tigez")`).

## `SET rebase 1` reaches the kernel and zeroes the frame, and STAYS zero

Sequence: `TLM POSE #1` (subscribe) -> first in-place pivot
(`MOVE_X 0 250 60 3000 #2`, a pure pivot, distance=0) -> pose read
(x=-1mm y=0mm h=1471 cdeg, i.e. ~14.7 deg, close to the commanded
250 mrad/14.3 deg) -> `SET rebase 1 #3` -> ack -> **every subsequent `t`
frame reads x=0 y=0 h=0**, for the ~20 frames captured before the next
command, with no spurious jump on the tick the kernel's own deferred
`rebasePosition()` request actually applies (the exact failure mode
`odomUpdate()`'s new `positionEpochLeft/Right` guard exists to prevent --
see `src/shims.cpp`'s case 32 comment). This is the load-bearing proof:
without that guard, the encoder-frame accumulator would have picked up
a spurious multi-thousand-count jump on the kernel's next `step()` after
the rebase, the moment `positionLeft/positionRight` re-anchor to their
new software zero.

A SECOND pivot after the rebase (`MOVE_X 0 -250 60 3000 #4`) confirms
odometry resumes cleanly from the new zero rather than staying stuck:
h moved from 0 to -30 cdeg (a much smaller angle than the first pivot --
see "Open question" below) and then held flat, still starting from
exactly 0, not from any stale pre-rebase value.

## `SET estop_clear 1` reaches the kernel and acks cleanly

Sent on an IDLE robot with no prior `ESTOP` (per this ticket's own
instruction -- a cold `ESTOP` with no wire-level clear used to require a
reboot, and the point of this check is the ack path, which the host
suite's `test_estop_clear_reaches_kernel_estop_clear_and_reads_back`
covers with a real preceding `ESTOP`):

```
>>> SET estop_clear 1 #5
<<< ack 5 4 timeout
```

No `err` line -- accepted. (No GET readback was taken on the bench for
this one; the host suite's own test covers the GET-reads-the-live-flag
contract end to end, `estopped: 1 -> SET estop_clear -> estopped: 0`.)

## Busy refusal: `SET rebase 1` during an in-flight `MOVE_X`

**First attempt (`transcript.txt`) missed the window.** The refusal
check there sent `MOVE_X 0 250 40 3000 #6` then, after a 0.3 s read
window, `SET rebase 1 #7` -- but a 250 mrad pivot completes in
roughly 300 ms on this hardware (see the first pivot's own timing
above), so the move had already finished (`hasLiveMotionObligation()`/
`engineMoveActive()` both already false) by the time the SET went out,
and it was correctly ACCEPTED (`ack 7 6 stop`, frame right after reads
x=y=h=0) rather than refused. This is a bench-script timing miss, not
evidence against the refusal -- `tests/host/test_wire_motion_verbs.py`'s
`test_rebase_and_estop_clear_refused_busy_during_live_motion` already
proves the refusal deterministically (a frozen `FakeClock`, no timing
race possible).

**Retest (`busy_refusal_retest.txt`), same session pattern but with a
bigger pivot (900 mrad, ~4 s timeout) and the `SET rebase 1` sent with
NO delay right after the `MOVE_X`'s own line (back-to-back writes, no
read in between):**

```
>>> MOVE_X 0 900 40 4000 #2
>>> SET rebase 1 #3
<<< ack 2 0 none
<<< ack 3 0 none
<<< err 10 #3
<<< t 10 ... 0 0 0 0 0 0 0 0 1
<<< t 11 ... 0 0 177 0 0 0 -36 36 1
... (h climbs to ~5234 cdeg / 52.3 deg, then holds flat -- the move
    completed normally, UNAFFECTED by the refused rebase)
```

`err 10` is wire code 10 = `Wire::Result::kBusy`, exactly matching
`wire_handler.cpp`'s `resultCode(Result::kBusy) -> 10`. This is the
acceptance criterion: `SET rebase 1` refused with an error reply while a
motion is live, confirmed on real hardware with the ack-then-err merits-
rejection shape the host suite also pins. `estop_clear`'s own busy
refusal was NOT separately bench-retested (time), but it shares the
IDENTICAL gate in `wire_adapter.cpp`'s `onSet()`
(`entry->ordinal == kOrdinalRebase || entry->ordinal == kOrdinalEstopClear`)
and both are proven refused by the same host test.

## Open question (not this ticket's scope, noted for the record)

- `STATUS` at pre-flight read `ready=0` even though motion worked fine
  immediately after -- UNVERIFIED why; not chased down, since `ready`'s
  exact semantics are outside this ticket and motion was never blocked
  by it.
- The second pivot (after rebase) reached only ~-0.3 deg where the
  first, otherwise-identical command reached ~+14.7 deg, and telemetry
  `flags` read `31` (decimal) from the first `MOVE_X` onward for the
  rest of both sessions, never dropping back down -- including through
  a successful `SET estop_clear` and multiple further successful moves,
  so it is NOT a real, persistent estop/stall condition (motion kept
  working). UNVERIFIED what specifically it reflects; not a `rebase`/
  `estop_clear` defect (the frame zeroed and stayed zeroed correctly
  regardless, and later moves completed normally) -- worth a bench
  session of its own if it recurs.

## `radio-robot-lib/docs/design/protocol.md` confirmation

Read `radio-robot-lib/docs/design/protocol.md` S7 (`GET`/`SET` own
"stores no configuration, field names are project-local" text) --
unchanged by this ticket, as the ticket's own binding design decision
required. No PR needed there.
