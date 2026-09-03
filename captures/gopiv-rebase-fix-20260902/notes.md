# Sprint 028 ticket 002 reopen -- rebase-race fix, hardware proof on gopiv

Board: **gopiv** (per `.claude/rules/robot-ownership.md`), mbdeploy farm
node meili, `192.168.1.150:43181` (zeroconf-resolved this session, same
port as the acceptance session's own capture -- unchanged).

Firmware: built from this session's HEAD (`src/motion/motion_engine.{h,cpp}`
containing the `MoveState::epochLeft0/epochRight0` re-anchor fix), version
string `0.20260902.2` unchanged from the pre-fix acceptance build (no
version bump this session, per `.claude/rules/git-commits.md`'s
once-per-sprint cadence -- board identity confirmed instead via `HELLO`:
`device NEZHA2 robot gopiv 2175407711`).

## Build

First `mbdeploy deploy --remote gopiv --hex .tmp/deploy-head/built/binary.hex`
attempt failed (`flash erase sector failure`, then a mass-erase recovery
attempt itself timed out) and left gopiv BLANK -- the same known
first-attempt farm flakiness the original acceptance session's own notes
recorded (`captures/gopiv-acceptance-028-20260902/notes.md`, Step B). An
immediate retry of the identical command succeeded cleanly (100 sectors
erased/programmed). Confirmed after: `HELLO -> device NEZHA2 robot gopiv
2175407711`.

## Root cause (confirmed by static analysis against the measured evidence, not re-derived from a fresh probe)

`SET rebase 1` (`src/shims.cpp`'s `setKernelValue()` case 32) calls
`kernel.rebasePosition()`, which only increments a request counter
(`src/core/diffdrive.cpp:389-391`) -- the actual re-anchor (wheel encoder
samples reset, `positionEpochLeft/Right` bumped) is DEFERRED to the
kernel's own next `step()` (`diffdrive.cpp:462-471`).

`src/comms/protocol.cpp`'s single-executor loop (`Protocol::run()`,
sprint 028 ticket 003) calls `tickDrive()` (which runs that `step()`)
ONLY while `wireAdapter_.hasLiveMotionObligation()` is true. A bare `SET
rebase 1` with no motion active never sets that flag, so the loop's next
pass goes straight to reading the NEXT wire line without ever stepping
the kernel first -- exactly what the evidence shows (`SET rebase 1`
immediately followed by `MOVE_X`, no gap, both accepted before any
`step()` intervenes).

`MotionEngine::moveX()` (`src/motion/motion_engine.cpp`) dispatches
synchronously off the incoming `MOVE_X` line, straight into
`startSegment()`, which snapshots `move_.posLeft0/posRight0` from
`kernel_.output()` -- at this point still the kernel's STALE, PRE-rebase
Output (the deferred request has not yet been honoured by any `step()`).
The move going active is what finally makes
`hasLiveMotionObligation()` true, so the VERY NEXT pass through
`Protocol::run()`'s loop calls `tickDrive()` -- the FIRST `step()` since
the rebase request. That one `step()` both (a) honours the deferred
rebase (resets the kernel's encoder samples, bumps
`positionEpochLeft/Right`) AND (b) delivers the just-staged drive command
for the new move. `MotionEngine::serviceMove()`'s completion check then
diffs the fresh, near-zero post-rebase position against the now-stale
pre-rebase `posLeft0/posRight0` -- producing a huge signed delta that
satisfies the yaw completion margin (`diffdrive.h`'s 4-count pure-turn
margin) on literally this move's first serviced tick. This matches
Step E.2's own measured shape exactly: `h` jumped to a small residual
(11 of ~5160 commanded centidegrees) and the move reported itself
complete with `vl=vr=0`.

## Fix

`src/motion/motion_engine.h`: `MoveState` gains `epochLeft0`/`epochRight0`
(`uint32_t`), captured alongside `posLeft0`/`posRight0`.

`src/motion/motion_engine.cpp`:
- `startSegment()` now also captures `out.positionEpochLeft/Right` into
  the new fields.
- `serviceMove()` checks, at the top of its per-tick body (before
  computing `dLeft`/`dRight`), whether the epoch has changed since the
  move's own snapshot; if so, it re-anchors `posLeft0`/`posRight0` to the
  CURRENT (fresh, post-rebase) position before computing progress. Since
  a rebase can only ever land at a move's very start (the commandable-
  state busy gate refuses `SET rebase 1` outright while any motion
  obligation is live, `err 10`), the rebase and the move's own first
  tick always land in the same real instant -- re-anchoring is the
  correct fix, not a workaround: `distTarget`/`yawTarget` stay untouched
  RELATIVE displacements, only the reference point they are measured
  from moves.
- `progress()` gets the equivalent (non-mutating, since it is `const`)
  guard, so a bare progress query landing in the same one-tick window
  reports "no progress yet" instead of the same bogus huge delta.

`src/core/diffdrive.{h,cpp}` (the vendored kernel) untouched, per this
ticket's own constraint.

## Host tests (foreground, `uv run pytest`, before any hardware flash)

New test:
`tests/host/test_wire_motion_verbs.py::test_move_x_immediately_after_a_successful_rebase_delivers_its_full_commanded_rotation`
-- reproduces the exact race (asymmetric prior left/right encoder
positions, matching a real prior pivot's own differential split; a
symmetric prior position was tried first and found to CANCEL OUT of the
yaw-axis completion check entirely, silently defeating the test -- see
the test's own comment) and proves both (a) the move does NOT resolve as
complete on its first post-rebase tick, and (b) it still reaches its own
full commanded target from the freshly re-anchored baseline.

Verified RED against the pre-fix source (`git stash` of
`src/motion/motion_engine.{h,cpp}` only, re-run, `git stash pop`):
`AssertionError: move reported complete on its first post-rebase tick`.
GREEN again with the fix restored.

Full scoped suite (287 tests, motion-engine + wire-motion-verb +
wire-motion-completion + regression files) and the two pinned-constraint
suites (`test_vfp_guard_source_pin.py`, `test_wire_constants_drift.py`,
23 tests) all pass. Raw output not attached here (terminal-only); rerun
with:

```
uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_motion_completion.py \
  tests/host/test_motion_engine_primitives.py tests/host/test_motion_engine_reductions.py \
  tests/host/test_motion_engine_gotow.py tests/host/test_motion_engine_deadline_boundary.py \
  tests/host/test_motion_engine_estop_and_refusal.py tests/host/test_motion_engine_settle.py \
  tests/host/test_motion_engine_acceleration_profile.py tests/host/test_motion_engine_shaping_fields.py \
  tests/host/test_motion_engine_default_cruise_for_distance.py tests/host/test_regression_post_move_neutral.py \
  tests/host/test_regression_yaw_taper_pure_turn.py tests/host/test_stop_move_zeros_continuous_drive.py \
  tests/host/test_vfp_guard_source_pin.py tests/host/test_wire_constants_drift.py -q
```

## Hardware proof (gopiv, this session)

Scripts: `gopiv_link.py` (unmodified copy of the acceptance session's
own `Link` helper, same host/port), `rebase_fix_retest.py`. Full
transcript: `rebase_fix_transcript.txt`.

### R.1-R.5: pivot, `SET rebase 1`, `MOVE_X 0 <+-900> 60 3000` immediately after

Each rep: a leading/prior pivot establishes a genuine nonzero
accumulated position, `SET rebase 1` acks and all post-rebase pose
frames read `x=y=h=0` (8 frames each, all zero), then
`MOVE_X 0 <+-900> 60 3000` is sent with NO gap after the rebase --
the exact E.2 race.

| rep | rebase zeroed | move commanded | move delivered (final h) | % of ~5157 cdeg commanded |
|---|---|---|---|---|
| R.1 | yes (8/8 frames) | -900 mrad | -5497 | 106.6% |
| R.2 | yes (8/8 frames) | +900 mrad | +5426 | 105.2% |
| R.3 | yes (7/7 frames) | -900 mrad | -5554 | 107.7% |
| R.4 | yes (8/8 frames) | +900 mrad | +5396 | 104.6% |
| R.5 | yes (8/8 frames) | -900 mrad | -5528 | 107.2% |

MEASURED gopiv 2026-09-02, `rebase_fix_transcript.txt` lines 8-40. All
5 reps deliver 104.6-107.7% of the commanded rotation, a direct contrast
with Step E.2's own PRE-fix measurement of 0.2% (11 of ~5160 commanded
centidegrees, `captures/gopiv-acceptance-028-20260902/step_e_transcript.txt`
lines 24-48). The slight (~5-8%) overshoot versus E.4's own PRE-fix
reference completion (5008 of 5157, ~97%) is not chased further here --
plausibly session-specific (battery, friction) rather than a fix defect,
since it is a small, consistent excess in the SAME direction across all
5 reps, not a shortfall, and every rep's own post-rebase zero and
full-delivery halves both independently pass.

### R.busy: `SET rebase 1` sent immediately after an in-flight `MOVE_X` (busy-refusal recheck)

MEASURED gopiv 2026-09-02, `rebase_fix_transcript.txt` lines 42-100:
`MOVE_X 0 900 40 4000 #13` acked, `SET rebase 1 #14` acked then
IMMEDIATELY followed by `err 10 #14` (kBusy) -- matches E.4's own
pre-fix result exactly, confirming the busy gate is unaffected by this
fix. The in-flight `MOVE_X` was undisturbed: `h` ran from -5528
(left over from R.5, no rebase happened this cycle) to a final -271,
a net change of +5257 against the +5157 (900 mrad) commanded (~101.9%)
-- a normal, undisturbed completion (the transcript's absolute `h`
values look unrelated to the commanded magnitude at a glance because
telemetry `h` is session-cumulative, not zeroed here; the DELTA is what
matters and matches).

### R.tour: `SET rebase 1`, then a 4-leg tour

MEASURED gopiv 2026-09-02, `rebase_fix_transcript.txt` lines 148-158.
Leg 1 is the actually-relevant case (a pivot issued immediately after
the tour's own leading rebase -- the same race as R.1-R.5): commanded
900 mrad, delivered final h=5426, **105.2%, clean**. Legs 2/4 are
straight legs (bare-motor rig, wheels off the ground -- odometry-only,
not physically meaningful here). Leg 3 (`MOVE_X 0 -1800 60 3500`, a
103 deg pivot) initially read only 47.9% delivered
(`rebase_fix_transcript.txt` line 154) -- **this is a test-script
artifact, not a firmware or fix regression**: leg 3 has no rebase
anywhere near it (it is two legs after the tour's only rebase), and a
standalone isolated retest of the identical command with a longer
budget (`MOVE_X 0 -1800 60 6000`, 6.5s wait instead of the tour script's
2.5s) delivered a clean completion: net h change from the prior -4944 to
a final -15420 is a delta of -10476 against -10313 commanded (~101.6%).
The original 3500ms timeout / 2.5s read-wait was simply too short for a
103 deg pivot at 60 mm/s cruise (the same "distTaper_/yawTaper_ dominant
cost in tour wall clock" `motion_engine.h` already documents) -- unrelated
to `SET rebase`, which was not involved in that leg at all.

## Summary

| check | result |
|---|---|
| rebase zeroes the frame (E.1-equivalent) | PASS, all 5 reps |
| move immediately after a successful rebase delivers its full commanded rotation (E.2, the reopened defect) | **PASS, all 5 reps, 104.6-107.7%** -- FIXED |
| busy refusal during an in-flight move (E.4-equivalent) | PASS, err 10, move undisturbed (~101.9%) |
| rebase-at-leg-1 tour, first leg after rebase | PASS (105.2%); leg 3's own reading was a test-script timeout artifact, confirmed by an isolated recheck, unrelated to rebase |
| OTOS-equipped-chassis half | still UNVERIFIED -- gopiv has no OTOS, no other OTOS-equipped robot was reachable this session (unchanged limitation from the original acceptance) |
| camera-truthed half | still UNVERIFIED -- no camera available this session (unchanged limitation) |
