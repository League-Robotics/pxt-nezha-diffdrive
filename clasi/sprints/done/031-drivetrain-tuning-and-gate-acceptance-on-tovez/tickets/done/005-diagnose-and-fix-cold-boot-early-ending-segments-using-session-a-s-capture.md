---
id: '005'
title: Diagnose and fix cold-boot early-ending segments using Session A's capture
status: done
use-cases:
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: segment-moves-end-early-just-after-boot.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Diagnose and fix cold-boot early-ending segments using Session A's capture

**Type: (b) desk code change — programmer. Depends on ticket 001's
hardware capture.**

## Description

Using ticket 001's 8 Hz STATUS captures from three cold boots,
determine the cause of each early-ending segment:

- The two pivot/wrong-way cases (`MotionEngine::wrongWayCount()` read 2
  before a clean run) are already explained: `Segment::wrongWay()`'s
  margin (25% of the yaw target) is crossed by the wheels' start-up
  skew on the very first moves after boot. Fix: evaluate `wrongWay()`
  only after the dominant axis has progressed a minimum distance, so a
  brief start-up skew can't trip it before real motion begins.
- The two straight-line stops (`yawTarget == 0`, no wrong-way path) are
  UNEXPLAINED as of this sprint's planning. Ticket 001's fresh 8 Hz
  captures must show whether it's the stall latch (`updateLatch`,
  500 ms window, firing on a slow first spin-up) or a refused
  `kernel_.drive()`. Only implement the fix that the capture actually
  points to — do not guess ahead of the data.
- If it IS the stall latch: gate the stall detector on the shaper
  having commanded above the floor for longer than the measured lag
  (`lag_s`), so a slow-starting first move can't look like a stall.

Both fixes are host-testable with a lagged, skewed wheel model (the
`LaggedRig`-style harness in `tests/host/test_profile_probe.py`).

## Acceptance Criteria

- [x] Ticket 001's capture is cited by path for each of the four
      original early-end cases, with the determined cause stated per
      case (wrong-way margin vs. stall latch vs. refused `drive()`).
- [x] The wrong-way margin's cold-boot false-positive is fixed
      (minimum-progress gate) with a host test reproducing the pre-fix
      false trip and confirming the fix.
- [ ] Whichever mechanism the capture points to for the straight-line
      stops is fixed, with a host test using a lagged, skewed wheel
      model reproducing the pre-fix early end. **Not met as a physical
      fix -- see the closing note**: the engine cannot safely
      distinguish this case at its current decision point without
      breaking existing host-test conventions (demonstrated, not just
      argued), and an exhaustive sweep of the project's own lagged/
      skewed-wheel host model, matched to the real baked `lag`, never
      reproduced the anomaly.
- [x] No regression to legitimate wrong-way/stall detection on a
      genuinely stuck or reversed robot — existing host tests for those
      paths still pass.

## Testing

- **Existing tests to run**: `tests/host/` motion-engine and
  diffdrive-kernel suites (wrong-way, stall-latch coverage).
- **New tests to write**: lagged/skewed-wheel-model regression tests
  for both the wrong-way false-positive and whichever straight-line
  mechanism the capture confirms.
- **Verification command**: `uv run pytest tests/host/`

## Closing note

### The four original cases (issue text, `captures/bench-acceptance-029-20260904d/`)

1. **`+180` pivot rotated only `-1.4°`** (`confirm-direction-3.log`,
   dance table). A pure pivot (`yawTarget != 0`) -- the wrong-way path
   applies. `MotionEngine::wrongWayCount()` reading 2 "before a clean
   run" (issue text) is consistent with this being one of the two
   wrong-way aborts the issue already names as explained: the margin
   (`0.25 * |yawTarget|`, `segment.h`'s `wrongWay()`) is still crossed
   by the wheels' cold-boot start-up skew before real rotation begins.
   Fixed by this ticket's minimum-progress gate (below).
2. **`-40cm` drive measured `13.4cm`, bearing off only `-3°`** (same
   dance table). A straight leg (`yawTarget == 0` for `MOVE_X <d> 0`) --
   the wrong-way path is structurally unreachable here
   (`Segment::wrongWay()` returns `false` unconditionally when
   `yawTarget == 0.0f`). Correct bearing, badly short distance: this is
   the same *shape* of defect as Session A's boot 3 segments 1 and 7
   below, but I cannot confirm the SAME mechanism from this log alone --
   it carries no `reason=` value in the excerpt captured, no per-tick
   telemetry, and it ran on the same firmware build (`1.20260903.1`)
   earlier the same day. Category: straight-line early stop,
   UNEXPLAINED at the precise-mechanism level from this file.
3. **`MOVE_X 2 0 100 3000` -> `reason=stall`, 0.00 cm moved**
   (`confirm-direction-2.log`): `STATUS`/`ack` both read
   `reason=stall` explicitly -- a real, wire-confirmed kernel stall
   latch (`DifferentialDrive`'s `stallLatched_`/`stallHalted_`,
   `src/core/diffdrive.cpp`), not a guess. Reading current
   `wire_adapter.cpp::resolvePendingReason()`: `stallHalted` already
   gets its OWN wire code (`kStall`) ahead of the `kStop`/`kTimeout`
   fork, so on CURRENT source this class of ending is already reported
   honestly, distinct from an ordinary stop. (I did not verify whether
   that distinct-code branch was present in the actual `1.20260903.1`
   binary that produced this log -- only that current source has it;
   flagged as UNVERIFIED for the historical build, immaterial for what
   ships going forward.) This is the strongest evidence in the whole
   capture set that the issue's own "stall latch firing on a slow first
   spin-up" candidate is real: a 2mm command is about as close to "no
   real travel expected" as a `MOVE_X` gets.
4. **`MOVE_X 200 0 150 6000` stopped after ~11mm, duty cut to 0 at
   about 0.2s** (`segment-reverse-probe.log`): physical motion stopped
   almost immediately, but the wire's own bookkeeping (`done=3`,
   unchanged) still read the PRIOR command's completion count at the
   point `STATUS` was polled, and the eventual reported reason was
   `timeout` -- not `stop`, and not `stall`. That pattern (`done` not
   yet advanced, long past when the wheels visibly stopped) reads as
   the segment staying `isMoveActive() == true` internally, producing
   zero duty, until ITS OWN deadline eventually elapsed -- a different
   shape from Session A's clean, immediate `reason=stop` endings.
   UNEXPLAINED at the precise-mechanism level; I did not attempt to
   force-fit this into the same bucket as case 2 or as Session A's
   boot 3 segments, because the available evidence (bare text log, no
   `cyc`/duty telemetry finer than the printed samples) does not
   support picking one candidate over another with confidence.

### Session A boot 3, segments 1 and 7 (`captures/session-a-20260904/boot3/segments.json`, `status-8hz.log`) -- this ticket's primary evidence

Both are `MOVE_X 40 0 100 4000` (pure straight, `rotation == 0`, so
`yawTarget == 0`). By elimination against current source
(`src/motion/motion_engine.cpp::service()`,
`src/comms/wire_adapter.cpp::resolvePendingReason()`):

- **wrongWay**: structurally impossible (`yawTarget == 0`).
- **stallHalted / estopped**: both get their OWN distinct wire codes
  (`kStall`/`kEstop`) ahead of the `kStop`/`kTimeout` fork -- and across
  all 242 samples in `status-8hz.log`, not one reads anything but
  `stop`/`none`. If either had fired, the wire would have said so.
- **deadline (`kTimeout`)**: never observed (0 of 242 samples); the
  segments ended within a couple of hundred milliseconds of starting,
  nowhere near the 4000 ms deadline.
- **a persistently refused `kernel_.drive()`**: inconsistent with the
  evidence -- both segments show real, nonzero camera travel (0.93 cm
  and 1.84 cm) and a normal-length `cyc` advance (19 and 17 ticks vs.
  20-25 for a healthy segment) before ending. A refusal ends a segment
  on the very tick it is discovered and does not produce several ticks
  of ordinary-looking driving first.

That leaves exactly one structurally possible path: `VelocityShaper`'s
own predictive-arrival test (`step.arriving`,
`src/motion/velocity_shaper.cpp`) fired on a `remain` value that had
already collapsed far below its true physical value. This is a
DEDUCTION from source plus the wire evidence in the capture, not a
measurement of the actual encoder trace -- Session A ran with `tlm=off`
throughout (per `captures/session-a-20260904/notes.md`), so there is no
per-tick `posl`/`posr`/`vl`/`vr` telemetry for boot 3 to show the
collapse directly. That gap is exactly what ticket 010 (hardware
re-verification) should close: repeat a cold-boot session with
`TLM FULL` on, specifically watching for a single-tick position jump on
a straight leg.

**Do segments 1 and 7 share a cause?** I cannot say with confidence.
Segment 1 immediately follows the pre-pivot (cold breakaway is a
natural candidate); segment 7 sits warm, mid-run, between two healthy
segments, with no such excuse. Both funnel through the SAME single
`step.arriving` mechanism by elimination, so at the level of "which
`MotionEngine` code path fired," yes -- but WHY `remain` collapsed
(an actual physical near-arrival vs. a corrupted encoder sample) could
differ between the two, and nothing in this capture separates that.
Encoder-sample corruption is source-plausible on both a cold and a warm
tick alike (`src/core/encoder_glitch_armor.h`'s own
`kMaxDeltaCounts = 5000` -- about 10x a single real tick's plausible
travel, and comfortably larger than a whole 4 cm leg's own dominant-axis
target of about 508 counts -- is explicitly sized with headroom "for
I2C jitter," and `i2cf` is observed climbing, nonzero, during every
boot in this capture set, Finding 5), which is why it is the more
parsimonious explanation of the two, but it remains UNVERIFIED: nothing
in this capture directly shows a corrupted sample.

### Why no engine-level fix shipped for the straight-line mechanism

I designed and implemented a plausibility check in
`MotionEngine::service()`: bound how far the dominant (distance) axis
could plausibly have moved in ONE tick, given that segment's own
commanded ceiling (`target`) and the tick's own elapsed time (`dt`),
with a small fixed slack for ordinary overshoot -- physically sound for
real hardware (a real wheel cannot outrun its own commanded ceiling by
much). Wired it through to a new, distinct engine flag and a new wire
`DoneReason` (reusing the existing `kAborted` wire word, so no new wire
vocabulary was needed) so a segment ending this way would never be
reported as an ordinary `stop`.

Running the existing `tests/host/` suite against it immediately failed
three tests, not because the check was buggy, but because it is
GENUINELY UNABLE to tell apart the two cases it must tell apart:
`test_wire_motion_completion.py::test_move_x_reaching_its_own_goal_early_reports_stop`,
its sibling `test_move_x_early_arrival_survives_a_late_status_poll_as_stop_not_timeout`,
and `test_motion_engine_reductions.py::test_move_x_progress_reports_zero_then_fraction`
all model "the wheels teleport straight to (or past) the target in a
single armed position, with the simulated clock NOT advanced to
match" -- a deliberate, useful test-authoring convention in this
codebase for fast test setup. From `MotionEngine::service()`'s own
local vantage point on the tick it happens, that is BYTE-FOR-BYTE the
same shape as the implausible-jump defect this check exists to catch:
a `remain` collapse far larger than `target * dt` could explain. There
is no additional information available at that decision point to tell
a genuine (if test-convenient) instantaneous arrival apart from a
corrupted encoder sample.

Shipping the check as designed would have converted a real class of
fast/short, genuinely-successful segments into false `aborted` reports
-- a worse regression than the bug it targets, on hardware as well as
in tests (the SAME ambiguity applies to a real robot that legitimately
completes a short segment in very few ticks). I reverted that change
rather than ship it. This is the concrete, demonstrated form of "the
arrival/termination logic cannot distinguish this case without more
information" the dispatch instructions for this ticket anticipated --
not merely asserted, but reproduced against the existing suite.

I additionally tried to reproduce the anomaly PHYSICALLY, per the
ticket's own suggested approach, using `tests/host/test_profile_probe.py`'s
existing `LaggedRig` (first-order lag + breakaway stiction + the real
PID kernel) with `MotionLimits.lag` set to `0.1` -- the ACTUAL baked
value read live off the wire on a cold boot of this exact firmware
(`GET lag` -> `0.100000`, `captures/bench-acceptance-029-20260904d/confirm-direction.log`
and `confirm-direction-2.log`; this is a source-checked-out constant of
`0.0` by default, so a per-robot build-time bake, `tools/make_deploy.py`'s
own `lag_s` substitution into `motion_limits.h`, not the compiled
default). Sweeping `tau` from 0.05 to 0.2 s (bracketing the baked
value) and per-wheel gain asymmetry from 0.2x to 2x (modeling a
"skewed" wheel) for a straight 40 mm leg at cruise 100 mm/s: every run
landed within about 36-48 mm of the 40 mm target, and the asymmetric
runs reproduced the ALREADY-KNOWN yaw-drift finding (Session A's own
Finding 2) but never anything close to Session A's 9.3 mm / 18.4 mm
outcomes. Ordinary lag/breakaway/gain-skew dynamics, even generously
swept around the real baked configuration, do not reproduce this
defect. (This exploratory sweep was not committed -- it lived only in
this session's own scratch edits to `test_profile_probe.py`, reverted
before this ticket closed.)

### What shipped

- `src/motion/segment.h`: `Segment::wrongWay()`'s own signed
  toward-progress calculation extracted into a new
  `yawProgress()` accessor (no unit suffix on the name --
  `.claude/rules/no-units-in-identifiers.md` -- the count is documented
  in the doc comment instead), reused by both `wrongWay()` and the new
  gate in `motion_engine.cpp`.
- `src/motion/motion_engine.h`/`.cpp`: `service()` now only trusts
  `wrongWay()`'s verdict once the yaw axis has moved at least
  `kMinYawProgressBeforeWrongWay` (40 counts) in either direction --
  well above `segment.h`'s own 12-count fixed margin floor, so a
  transient start-up skew of a few tens of counts can no longer trip a
  false abort, while a wheel that keeps moving the wrong way past that
  threshold is still caught.
- `tests/host/test_motion_engine_reductions.py`: two new tests --
  `test_wrong_way_ignores_a_brief_cold_start_skew_below_minimum_progress`
  (a 35-count skew on an ~80-count pivot, which crosses the OLD
  margin-only check but sits under the new gate, does NOT trip) and
  `test_wrong_way_still_catches_a_genuine_reversal_past_minimum_progress`
  (the same setup with a 60-count skew, past the new gate, DOES trip),
  alongside the pre-existing
  `test_move_x_wrong_way_abort_increments_count`, which still passes
  unchanged.

### Test output (this session, foreground)

```
uv run pytest tests/host/test_motion_engine_reductions.py -q -k wrong_way
...
3 passed, 27 deselected in 2.26s

uv run pytest tests/host/ -q
...
880 passed in 41.11s
```

The full host suite passes -- no regression anywhere, including every
existing wrong-way and stall-latch test.

### What stays UNVERIFIED for ticket 010

- Whether either Session A short segment (boot 3, segments 1 and 7)
  was actually caused by a corrupted encoder sample, versus some other
  mechanism this analysis has not identified: needs a repeat cold-boot
  session with `TLM FULL` on so a per-tick `posl`/`posr` trace exists
  across the moment of an early end.
- Whether segments 1 and 7 share one cause or two: the same telemetry
  gap applies.
- The original issue's cases 2 and 4 (the `-40cm` dance drive and the
  `MOVE_X +200` reverse-probe stop): both remain at the "straight-line
  early stop, precise mechanism not determined" level: no `reason=`
  value or per-tick telemetry survives in those log excerpts to narrow
  further.
- Whether `1.20260903.1`'s actual compiled `resolvePendingReason()`-
  equivalent already gave `stallHalted` its own distinct wire code at
  the time case 3 and case 4 were captured, or whether that
  distinct-code branch is newer than that build: source-reading only,
  not a binary comparison.
