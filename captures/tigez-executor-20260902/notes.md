# Executor inversion hardware acceptance -- tigez, 2026-09-02

Sprint 028 ticket 003 (`clasi/sprints/028-single-executor-honest-encoder-velocity-and-a-frame-zeroing-verb/tickets/003-...md`).
Board: tigez, USB (`/dev/cu.usbmodem2121102`), pyserial via `uv run --with pyserial`.
Motion: **in-place pivots only** (bench-tethered, off the playfield, per the
dispatcher's explicit bench-safety instruction) -- `RUN:pivot:<deg>` and one
wire `MOVE_X 0 <rotation_mrad> <cruise> <timeout> #<id>` pivot, alternating
sign so net rotation stays near zero.

## Builds

- Baseline (tickets 001+002 merged, no ticket-003 changes; commit
  `c21c2b0`, `git stash`-restored working tree): `binary.hex`
  sha256 `009c256787c5f9909d94bd972958066d97832257c8faa128a190d10f5f0515fb`.
- Fixed (this ticket's full diff): `binary.hex`
  sha256 `f91ad687884a07a3dd9c7cbccc75e51ae6b30e9362d2edc6dd13b2aaebdac23d`.

Both built via `uv run python tools/make_deploy.py --robot tigez` after
`rm -rf .tmp/deploy-head`; both verified against
`.tmp/deploy-head/built/dockercodal/pxtapp/nezha-diffdrive/src/...` before
flashing (`invokeRunDispatch`/`registerRunDispatch` present only in the
fixed build's copy).

## A real build-system trap, found and fixed as part of this ticket

Adding `enum class MotionOwner { kNone, kWire, kJob };` inside
`Protocol` (no `//%`, private, C++-only) broke the PXT build with
`error: please add 'enums.d.ts' to "files" in pxt.json`, then (once
that file existed) with TS1005/TS1132 syntax errors inside a garbled,
auto-generated `enums.d.ts`. Root cause, read directly out of
`node_modules/pxt-core/built/pxtlib.js`: PXT's C++ header scanner
matches ANY line of ANY file listed in `pxt.json`'s `files` against
`/^\s*enum\s+(|class\s+|struct\s+)(\w+)\s*({|$)/` -- unconditionally,
with no regard for access specifiers or `//%` annotations -- and tries
to expose whatever it finds as a TS enum. Every *existing* `enum class`
in this codebase (`Wire::Result`, `Wire::TlmMode`,
`DiffDrive::DifferentialDrive::Status`, `EncoderGlitchArmor::Decision`,
...) already dodges this by declaring an explicit underlying type
(`enum class Result : uint8_t { ... }`), which puts a `:` right after
the name where the regex needs `{` or end-of-line, so the match fails.
`MotionOwner` was the one new enum in this ticket's diff written
without one. Fixed by adding `: uint8_t` -- `enum class MotionOwner :
uint8_t { kNone, kWire, kJob };` -- which is also a harmless size
optimization on its own. No `enums.d.ts` entry needed once that was
fixed; the placeholder file and pxt.json line added while chasing this
were reverted.

## A test-harness bug, found and fixed before the baseline results below
can be trusted

The first several baseline runs (`baseline-pre-inversion-20260902-144834.txt`
through `...-v3-...txt`) show heavily garbled serial text (dropped
characters throughout STATUS/HELLO replies) and, once, a hard
`OSError: [Errno 6] Device not configured` mid-session. Traced to the
test script itself: an exception mid-run skipped `link.close()`,
leaving the CDC-ACM port open in a dead process; `lsof
/dev/cu.usbmodem2121102` confirmed a **stale PID still holding the
device** after the script that opened it had already exited, and
reopening the same port from a fresh process while that stale handle
was still registered produced exactly this corruption/disconnect
pattern. Fixed by wrapping the whole link session in `try/finally:
link.close()` (`bench_check.py`) and waiting for `lsof` to show the
port free before reconnecting. `baseline-pre-inversion-final-...txt`,
`baseline-stepB-isolated-...txt`, and every `fixed-*` transcript were
captured after this fix and show zero corruption. **This was a bench
Python bug, not a firmware or hardware defect** -- nothing in the
`SerialTransport`/`EmitQueue` write path changed between the corrupted
and clean runs (same firmware, same physical board, same cable).

One number from the pre-fix runs is still worth flagging rather than
discarding: `baseline-pre-inversion-final-...txt` shows the robot's own
`pong` uptime dropping from `40592`ms (step B's own "after" read) to
`4520`/`6248`ms (step C's "before" reads) across only ~1-2 real
seconds -- consistent with an actual reset, not merely corrupted text,
timed suspiciously close to the harness's own `link.hello()` resync
call between steps. **UNVERIFIED which of the two (a real
baseline-firmware reset vs. the harness's own port-reopen instability)
caused it** -- the harness bug above is a sufficient, simpler
explanation (the same session had a hard disconnect two steps later),
so this is reported as an open question, not a confirmed baseline
defect, and is not needed to establish this ticket's own result: the
FIXED-firmware runs below are unambiguous on their own.

## Baseline (tickets 001+002 only) -- clean run

`baseline-pre-inversion-final-20260902-145821.txt`:
- Step A (`RUN:pivot:90` alone): no reset (`pong_ms` 26928->32648,
  monotonic; no unsolicited `device NEZHA2` banner).
- Step B (`RUN:pivot:90` then wire `MOVE_X` mid-job): no reset observed;
  the `MOVE_X`'s ack (`ack 1 0 none`) is the only reply captured in the
  drain window -- no `err` line, consistent with the pre-fix
  architecture accepting/racing the wire move rather than refusing it
  (the defect this ticket exists to close), though the drain window in
  this specific run was too short to also catch a stomped-move
  confirmation with certainty.
- Step C (`RUN:pivot:90` then `RUN:abort`): no reset observed.

## Fixed (this ticket) -- clean run, zero corruption

`fixed-executor-inversion-20260902-150608.txt`:
- **Step A**: `RUN:pivot:90` alone completes normally
  (`DBG:pivot:profile=open` / `GAP:27` / `PIVOT:end`), `pong_ms`
  13759->19507 monotonic, no reset.
- **Step B**: `RUN:pivot:-90` then, ~0.35 s later, wire
  `MOVE_X 0 1571 100 3000 #1` -- reply is `ack 1 0 none` **followed by
  `err 10 #1`** (`err 10` = `ERR_BUSY`, `Wire::Result::kBusy`, wired
  through `WireAdapter::onMoveX()`'s new `jobOwnsMotion_` check). The
  job's own tick loop is undisturbed: `GAP:27` / `PIVOT:end` still
  follow, at the pivot's own natural pace. This is the acceptance
  criterion's own "a wire MOVE_X sent mid-tour is observably refused
  (error code), not silently overwritten" -- hardware-confirmed.
- **Step C**: `RUN:pivot:90` then `RUN:abort` -- no reset; see the
  precisely-timed follow-up below for confirmation abort actually cuts
  the job short rather than merely completing normally afterward.
- **Step D**: 12 back-to-back `RUN:pivot:<±30>` jobs (alternating sign)
  -- `faults_at=[]`, zero resets, zero missing pongs. `i2cf` 0->1->2
  across the whole soak (not climbing abnormally), `cyc` 0->132
  advancing steadily, `next=` (the wire sequence counter) advancing
  1->2 correctly across the one sequenced verb sent mid-soak. This
  exercises the deeper call depth `dispatchJob() -> runAction0() ->
  test.ts's onRun handler -> tickToCompletion() -> driveTick() (C++) ->
  tickDrive() -> the service hook -> serviceOnce()` twelve times with
  no fault -- `device_stack_size = 4096` (this ticket's own `pxt.json`
  addition; it was not actually present in `pxt.json` before this
  ticket despite sprint 026 planning to add it -- see this ticket's
  final report) is sufficient for this depth on this build.
- **Step E**: a wire `MOVE_X #2` sent while a third job runs raced past
  that job's own (short, 30 deg) completion before landing --
  inconclusive on its own (only an `ack`, no `err`, because by the time
  it was processed `motionOwner_` had likely already dropped back to
  `kNone`); superseded by Step B's own clean result on a longer (90
  deg) job, which leaves no such race window.

### Abort timing, precisely measured (`fixed-abort-timing-*.txt`)

`RUN:pivot:90` alone: `PIVOT:end` at **1.287 s**.
`RUN:pivot:90` then `RUN:abort` sent at **0.3 s**: `PIVOT:end` at
**0.343 s** -- the job is cut short within ~40 ms of the abort landing,
not merely completing on its own. Confirms "no queue delay" is real,
not just "no crash."

### Telemetry stays live through a dispatched job (`fixed-tlm-during-job-*.txt`)

`TLM POSE` subscribed, then `RUN:pivot:90` sent: **49 telemetry frames**
observed during the ~1.27 s the job ran, with `h` (heading) advancing
live (0 -> 267 -> 651 centidegrees at the three frames sampled) and
`flags=31` showing the motors actually driving. The link never hung --
this is the serial-side re-check of the
`cleartext-run-hangs-the-link-under-active-telemetry.md` class of
defect under the executor inversion specifically (sprint 027 already
fixed the underlying single-serial-producer defect; this confirms the
inversion does not reopen it). **Not repeated over radio** -- this
session tested USB/serial only; a full radio-traffic-during-motion
retest (the acceptance criterion's own "confirm still true here" for
the radio wedge) needs the relay and untethered driving, which this
in-place, bench-tethered session cannot exercise -- reported UNVERIFIED
here, not assumed.

## What was NOT run, and why (explicit substitutions, not omissions)

- **`RUN:square:20`**: UNVERIFIED. tigez is bench-tethered, wheels not
  confirmed clear of a translating tour's real footprint -- substituted
  with the pivot-only battery above (Steps A-E), per the dispatcher's
  own explicit bench-safety instruction. Needs a bench stand (wheels
  truly off the ground) or the playfield.
- **`tests/system/run_tour.py`**: UNVERIFIED, same reason -- it drives a
  real `.tour` figure over the wire, which is exactly the translating
  motion this session was told not to run in-place-only. The host-side
  test-suite pins (`test_run_abort_source_pin.py`,
  `test_wire_constants_drift.py`) are the host-testable substitute for
  the parts of this ticket that host tests CAN reach; this file's own
  acceptance criterion is hardware-only and stays open until a
  bench-stand or playfield session runs it.
- **Radio-traffic-during-motion retest**: UNVERIFIED over radio
  specifically (see the telemetry section above) -- serial-side
  equivalent confirmed clean.
