# Sprint 028 ticket 001 -- root-cause fix + hardware re-acceptance on gopiv, 2026-09-02

Board: **gopiv** (per `.claude/rules/robot-ownership.md`), mbdeploy farm,
node meili, `192.168.1.150:43181`. Bare-motor bench rig: motors +
encoders, no wheels on the ground, no OTOS.

This session follows up
`captures/gopiv-acceptance-028-20260902/notes.md` Step D, which found
that the ORIGINAL ticket-001 fix (`NezhaMotorPort::collect()`'s
raw-unchanged guard) did **not** eliminate the hardware symptom: 5/6
tour reps still showed a genuinely-cruising encoder tick where the
wire-reported velocity read exactly 0 and duty stepped 14-25 points
toward the rail, overshoot to 446 mm/s.

## Phase 1-2: evidence gathering + pattern analysis (no code changes)

Re-read `src/platform/nezha_port.cpp::collect()` and
`src/core/diffdrive.cpp::refreshSample()`/`step()` end to end. Three
possible outcomes exist for a *successful* I2C read, gated by
`EncoderGlitchArmor::evaluate()` (`src/core/encoder_glitch_armor.h`):

| decision | `collect()` action (BEFORE this session's fix) | `sampleTimeUs_` |
|---|---|---|
| `kAccept`, raw unchanged, driven | ticket 001's existing guard: `return` early | **HELD** (correct) |
| `kRejectPending` (1st implausible jump) | `return` early | **HELD** (correct) |
| `kAcceptAsRebaseline` (2nd, self-consistent implausible jump -- the "counter restarted" outcome) | re-anchors `encOffset_` so `pos == lastPosition_`, then **falls through** to the shared accept-path code | **ADVANCES** |

The third row is the bug. `DifferentialDrive::refreshSample()` (the
vendored kernel, unmodified) computes
`sample.velocity = (position - sample.position) / interval` whenever
`sampleTime` changes. On a `kAcceptAsRebaseline` tick, `position()`
(`pos`) is *forced* equal to the position already held from before the
event (that is the whole point of the offset re-anchor: prevent a
multi-metre reintegration spike). So `refreshSample()` computes a
confidently-fresh, honestly-derived velocity of **exactly 0** -- the
same "honestly-derived-but-wrong zero" shape this ticket's Description
names for the raw-unchanged case, just reached through a second,
previously unaddressed trigger. `i2cFaultCount_` does NOT increment for
this tick (sampleTime DID advance), which does not match Step D's
observation of `i2cf` incrementing -- but Step D's own TLM cadence
caveat (~3 kernel ticks per telemetry frame) means the i2cf increment
attributed to "the frozen frame" is very plausibly from an EARLIER tick
in the same 3-tick gap (a `kRejectPending` hold, or an outright read
failure) that precedes the `kAcceptAsRebaseline` tick landing in the
same frame -- consistent with the measured pattern, not contradicting
it.

`clasi/sprints/028-.../design/DESIGN.md` S10 independently flags this
exact channel as unverified: *"the hardware premise -- whether a Nezha
brick MCU reset actually restarts the 0x46 counter near zero --
remains unconfirmed absent a bench run."* Given `kAcceptAsRebaseline`
fired repeatedly within single short tours (not a rare brick-reset
event), the far more likely real-world trigger on gopiv is an
encoder-wedge/I2C hiccup whose read resumes with a large, self-consistent
jump because the wheel kept physically moving during the outage -- the
armor cannot distinguish that from a genuine counter restart (by
design, see `encoder_glitch_armor.h`'s own doc comment), but the
CALLER's velocity-reporting choice for that outcome is a `nezha_port.cpp`
decision, in scope for this ticket.

## Phase 3: hypothesis + minimal test

**Hypothesis.** Withholding `sampleTimeUs_` on the `kAcceptAsRebaseline`
tick too (same treatment as the other two rows) will make
`refreshSample()` hold the prior, real velocity instead of computing a
fabricated 0, without reopening the multi-metre spike
`kAcceptAsRebaseline` exists to prevent (the position re-anchor itself
is untouched).

## Phase 4: root-cause fix

`src/platform/nezha_port.cpp::collect()`'s `kAcceptAsRebaseline` branch:
keeps the existing `encOffset_` re-anchor and `rebaselineCount_`
increment, but no longer falls through to the shared
sampleTimeUs_-advancing code -- it now sets `connected_`/`lastPosition_`/
`hasLastTick_` directly and returns, exactly mirroring the ticket's
existing raw-unchanged guard and the outright-read-failure branch.
`src/core/diffdrive.{h,cpp}` untouched (`git diff` empty on both, per
the ticket's binding scope decision).

Host tests unaffected/still green (this path cannot be host-compiled --
`nezha_port.h` includes `pxt.h` unconditionally -- so hardware
acceptance is the only test of the platform-layer change, as the
ticket's own `test_frozen_encoder_hold.py` docstring already states for
the sibling guard):

```
uv run pytest tests/host/test_frozen_encoder_hold.py \
  tests/host/test_encoder_glitch_armor.py \
  tests/host/test_archaeology_marker_budget.py \
  tests/host/test_vfp_guard_source_pin.py \
  tests/host/test_cxx11_syntax_gate.py \
  tests/host/test_include_paths_match_target.py
# 67 passed
```

## Build + flash

`uv run python tools/make_deploy.py --robot gopiv` -- clean build after
wiping the stale `.tmp/deploy-head` scratch copy (first attempt hit the
"not all translation units compiled" checkpoint from a prior session's
partial cache).

`mbdeploy deploy --remote gopiv --hex .tmp/deploy-head/built/binary.hex`
-- first attempt: `flash erase sector failure`, automatic CTRL-AP mass
erase recovery, immediate retry succeeded (100 sectors erased/
programmed). Confirmed: `HELLO -> device NEZHA2 robot gopiv 2175407711`,
`VER -> ver 0.20260902.2`.

## Hardware re-acceptance -- Step D methodology, gopiv, 2026-09-02

Same orange-dot 100x60 cm tour, same shaping SETs, `TLM FULL`, same
`analyze_frozen.py` filter (frozen position + duty driven + a
significant measured velocity 2 frames earlier, i.e. genuinely
cruising, not breakaway) used in the prior FAILED acceptance. Two runs:

| capture | reps | frames | script |
|---|---|---|---|
| `step_d_fixed_frames.json` | 6 | 1800 | `step_d_frozen_encoder.py 6 step_d_fixed` |
| `step_d_fixed12_frames.json` | 12 | 3589 | `step_d_frozen_encoder.py 12 step_d_fixed12` |

Analysis: `step_d_fixed_analysis.txt` (6 events), `step_d_fixed12_analysis.txt`
(14 events) -- both produced by `analyze_frozen.py <file>`, the same
filtered analyzer the prior FAILED acceptance used.

**The named defect (wire-reported velocity reading exactly 0 at a
genuinely-cruising frozen-encoder tick) is GONE.** 0 of 20
genuinely-cruising frozen-encoder events across both runs (18 reps,
5389 frames total) show `vel_at == 0` -- every one holds close to its
`vel_prev2` value instead (e.g. frame 346: `vel_prev2=272 vel_at=276`;
frame 1447: `vel_prev2=312 vel_at=312`). Direct comparison against the
PRE-fix/still-failing citations:

| | pre-fix (`tour_tight.json` 185-191) | Step D FAILED (`step_d_frames.json` #30) | this session (20 events, both runs) |
|---|---|---|---|
| `vr` at the frozen tick | 0 | 0 | **never 0** (holds prior value) |
| duty jump (points) | ~11 (3300->4400) | ~17 (3600->5299) | **4-14** (mostly 6-12) |

**Honest residual, NOT the named defect, reported per this session's
own "stop and report a failure rather than paper over it" instruction:**
a smaller, real (not fabricated) velocity/duty transient still
correlates with encoder-fault-recovery events. Across the 12-rep run,
overall peak `vr` was 447 mm/s (once, at frame 849, following an
unusually long fault run -- `i2cf` +8 within 5 telemetry frames)
against a no-recent-fault ceiling of 328-354 mm/s (p99/max over 1216
frames with no `i2cf` change in the preceding 10 frames). Every single
`vr` reading above 400 mm/s in both runs (18 of 18) occurs within 5
telemetry frames of an `i2cf` increment -- this is fault-correlated,
not general profile noise (checked directly, not assumed).

**Root cause of the residual, and why it is out of this ticket's
scope.** `DifferentialDrive::controlStep()` (`src/core/diffdrive.cpp`,
vendored kernel) computes `errLeft = speedLeft - sampleLeft_.velocity`
and feeds it to the PID **unconditionally** -- it does NOT gate on the
`freshLeft`/`freshRight` staleness flags the same function already
computes a few lines earlier (those two flags gate bias ADAPTATION
only, `diffdrive.cpp:671,673`, not the immediate PID error). So while
`sampleTimeUs_` is withheld (this fix, and the two pre-existing hold
paths), the PID keeps computing error against the stale-but-honest held
velocity and keeps commanding duty accordingly; when a fresh sample
finally lands, `refreshSample()` reports the true AVERAGE velocity over
the whole held span, which can legitimately be higher than the
immediately-prior cruise speed if duty climbed during the outage.
Eliminating this would require gating `errLeft`/`errRight` (or the
whole PID call) on sample freshness inside `controlStep()` --
`src/core/diffdrive.{h,cpp}`, which this ticket's own binding scope
decision keeps byte-identical to upstream. This is a materially
different, much smaller-magnitude mechanism than the bug this ticket
names (verified: it never produces a fabricated 0), present to some
degree in the pre-existing, already-accepted outright-read-failure
hold path too (not something this session's fix introduces).

## Verdict

**Root cause found, fixed, and hardware-confirmed for the defect this
ticket names.** The hardware-acceptance criterion as literally written
("confirm no speed excursion... and no overshoot") is **not fully
met** -- a smaller, mechanistically distinct, kernel-bound residual
remains. Recommend: file a follow-up issue for
`DifferentialDrive::controlStep()`'s PID gating on sample freshness
(requires touching the vendored kernel -- its own architecture
decision, out of this ticket's scope) rather than blocking this
ticket's fix on it, but leaving the final call (accept as sufficient
and close vs. keep open pending the follow-up) to the team-lead per
this session's explicit instruction not to mark `status: done` unless
the hardware proof passed outright.
