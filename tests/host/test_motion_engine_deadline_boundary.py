"""tests/host/test_motion_engine_deadline_boundary.py -- sprint 011
ticket 003: investigates whether MotionEngine::serviceMove()'s
`move_.deadline` backstop (motion_engine.cpp:156/221 set,
motion_engine.cpp:344 checked) can cut a move short before its
commanded distance/rotation is genuinely reached, under REALISTIC tick
cadence and a REALISTIC caller-supplied `timeout`.

Canonical finding this file pins (see this sprint's
`findings-003.md`): `src/shims.cpp::startMove()` (lines 379-439) --
the function `test.ts`'s tours actually drive through
(`tickedMove()`/`legToward()` -> `diffDrive.startMove()` -> this shim
-> `MotionEngine::moveX()`) -- computes the caller's `timeout` as the
OLD dual-rate dead-reckoned duration (`max(distance/speed,
yaw/yawRate)`) plus a flat "+1500 ms" backstop, with its own comment
naming exactly why: "allows for the end-of-move taper... the last
~15 deg / ~40 mm run at reduced rate, adding up to ~1 s." This file
does not trust that comment -- it drives the REAL C++ engine
(motion_engine.cpp, unmodified) through the ramp/taper/deadline
machinery at a realistic ~24 ms tick cadence (docs/design/design.md's
tick-model convention) and measures whether the backstop it computes
is actually sufficient, for the leg shapes `test.ts`'s tours actually
issue (see `test/test.ts::legToward()` and `::openLoopProfile()`):

  - a PURE PIVOT (`tickedMove(0, bearing)`, `legToward()`'s own
    >=50 deg branch) -- single segment, `turnFloor_`/`yawTaper_`.
  - a BLENDED leg whose rotation is itself >=50 deg
    (`legToward()`'s own arc branch can reach up to just under
    100 deg after its own <50 deg gate, e.g. bearing 45 deg -> theta
    90 deg). HISTORY: `MotionEngine::moveX()` used to split this shape
    into pivot-then-straight under ONE `timeout`, the shape most likely
    to exhaust the flat +1500 ms margin; moveX() no longer splits at any
    angle (reports/move-x-arc-space-20260906.md), so this is now one
    wide blended arc and the budget is the plain max() again.
  - a PURE STRAIGHT leg (`legToward()`'s <0.01 rad branch, and
    goToWorld()'s own straight-continuation leg) -- single segment,
    `distFloor_`/`distTaper_`.

Verification strategy (distinct from test_motion_engine_reductions.py's
single-tick hand-computed duty checks): this file needs the move to run
to completion across MANY ticks, so it drives a physically-consistent
closed loop instead -- each tick, it reads back the REAL last-staged
duty MotionEngine/DifferentialDrive just computed (motor_last_staged_duty,
the same readback test_motion_engine_reductions.py uses), converts it to
a velocity via the same pure-feedforward `duty = velocity/fullDutyVelocity`
relationship that config establishes, and integrates each wheel's
position forward by that velocity over one ~24 ms tick before arming it
as the NEXT tick's encoder reading (`meMotorArmPosition`, the same "place
the encoder wherever the test wants" seam every other multi-tick test in
this directory already uses). This is an idealization (instant velocity
tracking -- no motor inertia model), consistent with this project's own
kernel doctrine ("an encoder-servoed wheel-speed kernel", design.md) and
with how the rest of this file's sibling tests already treat commanded
duty as ground truth for encoder progress -- but it means the ENGINE's
own scale (ramp/taper) computation genuinely drives what "progress" looks
like each tick, not a hand-derived shadow formula. Two independent runs
per leg -- one with an effectively-infinite timeout (the TRUE, unforced
completion time) and one with the REAL caller-supplied timeout -- are
compared: if the real-timeout run's completion time and final encoder
position match the unforced baseline, the deadline never actually bound
anything for that leg.

Run with::

    uv run pytest tests/host/test_motion_engine_deadline_boundary.py
"""

import math

import pytest


LEFT = 0
RIGHT = 1

# Same rationale as test_motion_engine_reductions.py's own
# FULL_DUTY_VELOCITY: large enough that every commanded speed below
# stays well under the maxDuty=100% rail, so no assertion here is
# secretly checking a clamped value.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# docs/design/design.md "Execution model (tick model, sprint 002)":
# the kernel's control cycle self-paces to an absolute 24 ms deadline --
# this is the realistic cadence this ticket's own acceptance criteria
# names explicitly.
TICK_MS = 24.0

# openLoopProfile() (test/test.ts) reasserts MotionEngine's own taper/
# floor/ramp defaults verbatim (400/180 counts, 25%/12%, 400 ms) -- a
# freshly-constructed engine below already matches production tuning on
# those knobs with no explicit setter calls needed. Only speed/yawRate
# live outside the engine (shims.cpp/motion.ts globals), so those two are
# set explicitly, matching openLoopProfile()'s own values.
PRODUCTION_SPEED_MM_S = 200.0    # [mm/s] diffDrive.setDefaultSpeed(20)
PRODUCTION_YAW_RATE_DEG_S = 90.0  # [deg/s] diffDrive.setDefaultYawRate(90)

# shims.cpp::startMove()'s own flat backstop (src/shims.cpp:432-437's
# own comment: "allows for the end-of-move taper... adding up to ~1 s").
_SHIMS_TIMEOUT_MARGIN_MS = 1500

# Effectively unbounded -- used for the "how long does this leg actually
# take, left alone" baseline measurement. Real legs finish in low
# single-digit seconds; this is nowhere near tight.
_UNBOUNDED_TIMEOUT_MS = 3_600_000  # 1 hour


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    same shape as test_motion_engine_reductions.py's own Engine, pared
    down to only what this file's realistic multi-tick drive loop
    needs (no pending-phase/wrong-way/taper-setter surface -- this file
    never overrides taper/floor/ramp, see PRODUCTION_* constants'
    comment above)."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def set_max_duty(self, v):
        self._lib.meSetMaxDuty(self._handle, v)

    def set_full_duty_velocity(self, v):
        self._lib.meSetFullDutyVelocity(self._handle, v)

    def begin(self):
        return self._lib.meBegin(self._handle)

    def step(self):
        self._lib.meStep(self._handle)

    def set_clock(self, now_us):
        self._lib.meClockSetNow(self._handle, now_us)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    def arm_motor_position_at(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def wrong_way_count(self):
        return self._lib.meWrongWayCount(self._handle)


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == 0  # STATUS_OK
    return FULL_DUTY_VELOCITY


def _shim_move_params(distance_mm, rotation_deg, speed_mm_s, yaw_rate_deg_s,
                      cpm, b):
    """Python mirror of `src/shims.cpp::startMove()`'s own duration/
    cruise/timeout derivation -- the ACTUAL formula `test.ts`'s tours
    and the `move()` block drive through, not a simplified stand-in.
    Mirrors the C++ algebra term-for-term, including its `uint32_t`
    truncation of `duration*1000` before adding the flat backstop.

    The TIMEOUT budget is max(dist_duration, yaw_duration): moveX() is
    one blended segment whose two axes finish together. (Sprint 015
    ticket 004 once made this dist_duration + yaw_duration for the
    |rotation| >= 50 deg case, when moveX() split those into two
    sequential phases under one deadline; that split is gone.)
    `duration` is also what derives `cruise_mm_s` -- that dual-rate
    reconciliation is the same reconciliation.

    Returns (cruise_mm_s, timeout_ms, duration_s, left_counts,
    right_counts, budget_duration_s). `left_counts`/`right_counts` are
    startSegment()'s own per-wheel targets (motion_engine.cpp), used by
    callers to compute the expected FINAL absolute encoder position.
    `budget_duration_s` == duration_s, kept as a separate return so the
    callers' shape did not change.
    """
    rotation_rad = math.radians(rotation_deg)
    dist_target_counts = distance_mm * cpm
    yaw_target_counts = rotation_rad * 0.5 * b * cpm
    speed_counts = (speed_mm_s if speed_mm_s > 0 else 1.0) * cpm
    yaw_rad_per_s = math.radians(
        yaw_rate_deg_s if yaw_rate_deg_s > 0 else 1.0)
    twist_counts = yaw_rad_per_s * 0.5 * b * cpm

    dist_duration = 0.0
    if dist_target_counts != 0.0:
        dist_duration = abs(dist_target_counts) / speed_counts
    yaw_duration = 0.0
    if yaw_target_counts != 0.0:
        yaw_duration = abs(yaw_target_counts) / twist_counts
    duration = max(dist_duration, yaw_duration)
    assert duration > 0.0  # sanity: every leg below commands real motion

    left_counts = dist_target_counts - yaw_target_counts
    right_counts = dist_target_counts + yaw_target_counts
    dominant_counts = max(abs(left_counts), abs(right_counts))
    cruise_mm_s = (dominant_counts / duration) / cpm

    budget_duration = duration

    timeout_ms = int(budget_duration * 1000.0) + _SHIMS_TIMEOUT_MARGIN_MS
    return (cruise_mm_s, timeout_ms, duration, left_counts, right_counts,
            budget_duration)


def _drive_to_completion(e, fdv, max_ticks=2000):
    """Ticks the REAL serviceMove() at TICK_MS cadence, integrating each
    wheel's encoder position between ticks from the ACTUAL last-staged
    duty (readback, not a shadow reimplementation of the taper/ramp
    math) -- see this file's own header comment for the full
    verification-strategy rationale. Returns (elapsed_ms, final_pos)
    where final_pos is a {LEFT: counts, RIGHT: counts} dict of the
    absolute integrated encoder position at the tick serviceMove()
    first reports the move over (for any reason: completion, deadline,
    stall, or wrong-way -- this helper doesn't distinguish; callers do,
    from elapsed_ms and final_pos against their own expectations)."""
    pos = {LEFT: 0.0, RIGHT: 0.0}
    duty = {
        LEFT: e.motor_last_staged_duty(LEFT),
        RIGHT: e.motor_last_staged_duty(RIGHT),
    }
    t_ms = 0.0
    for _ in range(max_ticks):
        for side in (LEFT, RIGHT):
            pos[side] += duty[side] * fdv * (TICK_MS / 1000.0)
        t_ms += TICK_MS
        sample_time_us = int(t_ms * 1000.0)
        e.arm_motor_position_at(LEFT, pos[LEFT], sample_time_us)
        e.arm_motor_position_at(RIGHT, pos[RIGHT], sample_time_us)
        e.set_clock(sample_time_us)
        e.step()
        still_active = e.service_move()
        duty[LEFT] = e.motor_last_staged_duty(LEFT)
        duty[RIGHT] = e.motor_last_staged_duty(RIGHT)
        if not still_active:
            return t_ms, pos
    raise AssertionError(
        f"move never completed within {max_ticks} ticks "
        f"({max_ticks * TICK_MS:.0f} ms)")


def _run_leg(motion_lib, distance_mm, rotation_deg, cruise_mm_s,
            timeout_ms):
    """Fresh engine, one moveX() call, driven to completion. Returns
    (elapsed_ms, final_pos, wrong_way_count)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        e.set_clock(0)  # move_.deadline = nowMs() + timeoutMs is anchored here
        e.move_x(distance_mm, math.radians(rotation_deg), cruise_mm_s,
                 timeout_ms)
        elapsed_ms, final_pos = _drive_to_completion(e, fdv)
        return elapsed_ms, final_pos, e.wrong_way_count()


def _assert_reached_target(final_pos, left_counts, right_counts, tol=40.0):
    """The engine's own completion margins are 10 counts (distance) and
    4-10 counts (yaw, pure-turn vs blended) -- see motion_engine.cpp's
    distMargin/yawMargin. This check is deliberately looser: this isn't
    re-testing those margins (test_motion_engine_reductions.py already
    does that on a single hand-computed tick), it's confirming the leg
    actually reached the VICINITY of its commanded target rather than
    stopping for some other reason entirely. 40 counts accounts for
    this file's own TICK_MS (24 ms) discretization: _drive_to_completion
    only checks distDone/yawDone once per tick, so the last tick before
    completion can overshoot the engine's own margin by up to one
    tick's worth of floor-rate travel (measured up to ~25 counts for
    the two-phase split leg below, whose pivot phase crawls at
    turnFloor_ (0.12) and whose straight phase crawls at distFloor_
    (0.25) -- each its own separate overshoot opportunity)."""
    assert final_pos[LEFT] == pytest.approx(left_counts, abs=tol)
    assert final_pos[RIGHT] == pytest.approx(right_counts, abs=tol)


# ---- pure pivot (legToward()'s own >=50 deg branch: tickedMove(0, bearing)) --


def test_deadline_boundary_pure_pivot_production_timeout_matches_unbounded(
        motion_lib):
    """A 90 deg in-place pivot (turnFloor_ 0.12, yawTaper_ 180 counts) at
    production tuning (PRODUCTION_YAW_RATE_DEG_S). Compares the REAL
    shims.cpp-computed timeout (naive duration + 1500 ms) against an
    effectively-unbounded baseline: if the deadline never actually
    bound anything, both runs finish at the same tick with the same
    final encoder position."""
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts, _ = (
        _shim_move_params(0.0, 90.0, PRODUCTION_SPEED_MM_S,
                          PRODUCTION_YAW_RATE_DEG_S, cpm, b))

    baseline_ms, baseline_pos, baseline_wrong_way = _run_leg(
        motion_lib, 0.0, 90.0, cruise, _UNBOUNDED_TIMEOUT_MS)
    _assert_reached_target(baseline_pos, left_counts, right_counts)
    assert baseline_wrong_way == 0

    real_ms, real_pos, real_wrong_way = _run_leg(
        motion_lib, 0.0, 90.0, cruise, timeout_ms)

    # The load-bearing assertion: the production timeout must not have
    # fired before the unforced completion time -- if it had, real_ms
    # would be pinned at (approximately) timeout_ms while baseline_ms
    # is genuinely larger.
    assert real_ms == pytest.approx(baseline_ms, abs=TICK_MS)
    assert real_ms < timeout_ms
    _assert_reached_target(real_pos, left_counts, right_counts)
    assert real_wrong_way == 0


# ---- wide blended leg (legToward()'s arc branch, theta >= 50 deg) -------
# ---- HISTORY: this used to be the ONE shape that reached moveX()'s -------
# ---- internal pivot-then-straight split; it is one arc now.       -------


def _split_leg_params():
    """A blended (distance AND rotation) leg whose rotation is itself
    >=50 deg -- e.g. legToward()'s own arc branch with bearing 45 deg
    (theta = 2*bearing = 90 deg) reaching for a ~300 mm residual. Round
    numbers chosen directly as moveX()'s own (distance, rotation) args
    rather than re-deriving from a bearing/offset pair. 70 deg is well
    past goToR()'s 50 deg kTurnFirstAngle, which moveX() used to borrow
    as its own split; the name is kept so the three tests below still
    read against their history."""
    return 350.0, 70.0  # [mm] [deg]


def test_deadline_boundary_split_leg_production_timeout_matches_unbounded(
        motion_lib):
    """The split leg (two sequential ramp+taper overheads sharing ONE
    caller-supplied deadline, motion_engine.cpp's own header comment:
    "deadline... is NOT reset across a pivot-to-straight phase
    transition") is the shape most likely to exhaust the flat
    +1500 ms backstop -- this is the ticket's own central question.
    Same unbounded-vs-production comparison as the pure-pivot test
    above."""
    distance_mm, rotation_deg = _split_leg_params()
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts, _ = (
        _shim_move_params(distance_mm, rotation_deg, PRODUCTION_SPEED_MM_S,
                          PRODUCTION_YAW_RATE_DEG_S, cpm, b))
    assert abs(rotation_deg) >= 50.0  # sanity: this must be the split path

    baseline_ms, baseline_pos, baseline_wrong_way = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, _UNBOUNDED_TIMEOUT_MS)
    _assert_reached_target(baseline_pos, left_counts, right_counts)
    assert baseline_wrong_way == 0

    real_ms, real_pos, real_wrong_way = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, timeout_ms)

    assert real_ms == pytest.approx(baseline_ms, abs=TICK_MS)
    assert real_ms < timeout_ms
    _assert_reached_target(real_pos, left_counts, right_counts)
    assert real_wrong_way == 0


def test_deadline_boundary_split_leg_margin_consumed_is_bounded(motion_lib):
    """Quantifies the finding for the writeup: how much of the flat
    +1500 ms backstop does the split leg's own doubled ramp+taper
    overhead actually consume? Asserts the consumed margin is a small,
    bounded fraction of the 1500 ms budget -- not just "less than
    1500 ms" (the previous test already proves that indirectly via
    real_ms < timeout_ms), but comfortably bounded, so a future change
    to taper/ramp defaults that erodes this margin has room to be
    caught here before it reaches zero."""
    distance_mm, rotation_deg = _split_leg_params()
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, _, _, _ = _shim_move_params(
        distance_mm, rotation_deg, PRODUCTION_SPEED_MM_S,
        PRODUCTION_YAW_RATE_DEG_S, cpm, b)

    actual_ms, _, _ = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, _UNBOUNDED_TIMEOUT_MS)

    naive_ms = duration_s * 1000.0
    overhead_ms = actual_ms - naive_ms
    margin_remaining_ms = timeout_ms - actual_ms

    # The two-phase ramp+taper overhead is real (this leg's split does
    # cost meaningfully more than the naive dead-reckoned duration)...
    assert overhead_ms > 0.0
    # ...but stays well under the flat backstop, leaving genuine slack
    # rather than exhausting it. 1000 ms is a generous ceiling relative
    # to the ~700-900 ms two-phase overhead this leg's own ramp (400 ms
    # rise, twice) and taper windows (32 mm / 15 deg, twice) predict --
    # see this ticket's findings-003.md for the worked arithmetic.
    assert overhead_ms < 1000.0
    assert margin_remaining_ms > 0.0


def test_deadline_boundary_split_leg_truncates_without_the_margin(
        motion_lib):
    """Methodology check, not a defect: strips this leg down to a
    deliberately insufficient timeout and confirms the deadline DOES
    cut the move short -- stopping near that timeout with the encoder
    well short of its commanded target. This is deliberately the
    negative control: it proves this file's drive loop and assertions
    can actually detect a truncated move (a boundary test that always
    reports "clean" no matter what would be worthless as a regression
    guard).

    HISTORY: this used to strip only the +1500 ms margin, and later
    (sprint 015 ticket 004, when moveX() split this leg into two phases
    and the budget became a sum) probe with the max()-based bare
    duration instead. moveX() no longer splits and the budget is the
    max()-based duration again, which on ideal wheels covers this leg
    on its own -- so the deliberately insufficient timeout is now HALF
    the bare duration, unambiguously short of any completion."""
    distance_mm, rotation_deg = _split_leg_params()
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts, _ = (
        _shim_move_params(distance_mm, rotation_deg, PRODUCTION_SPEED_MM_S,
                          PRODUCTION_YAW_RATE_DEG_S, cpm, b))
    stripped_timeout_ms = int(0.5 * duration_s * 1000.0)
    assert stripped_timeout_ms < timeout_ms - _SHIMS_TIMEOUT_MARGIN_MS

    truncated_ms, truncated_pos, _ = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, stripped_timeout_ms)

    # Stopped at (approximately) the stripped deadline, not later --
    # the move was still actively progressing when it was cut off.
    assert truncated_ms == pytest.approx(
        float(stripped_timeout_ms), abs=TICK_MS)
    assert truncated_ms < timeout_ms  # i.e. strictly before the real deadline

    # And genuinely short of the target -- not a coincidental near-miss.
    remaining_left = abs(left_counts - truncated_pos[LEFT])
    remaining_right = abs(right_counts - truncated_pos[RIGHT])
    assert remaining_left > 50.0 or remaining_right > 50.0


# ---- move(30 cm, 180 deg): sprint 015 ticket 004's own repro shape -------
# ---- (arc-moves-abort-distance-never-driven.md). HISTORY: max()'s -------
# ---- budget truncated the old two-phase split; it is one arc now. -------


def _split_leg_30cm_180deg_params():
    """move(30 cm, 180 deg) -- the issue's own named repro shape
    (arc-moves-abort-distance-never-driven.md's "smallest nominal-rate
    case unambiguously over budget"). Unlike `_split_leg_params()`
    above, this needs a caller-set yaw RATE well under this file's own
    PRODUCTION_YAW_RATE_DEG_S (90 deg/s) to reproduce under this file's
    ideal-wheels drive loop: sweeping distance 0-500 mm and rotation
    50-350 deg at (PRODUCTION_SPEED_MM_S, PRODUCTION_YAW_RATE_DEG_S)
    finds a smallest margin of +540 ms -- never negative -- because at
    90 deg/s the two-phase ramp+taper overhead this file's ideal-wheels
    model can show (no PID lag; see this file's own header comment on
    the idealization) stays well under the flat 1500 ms backstop
    regardless of shape. The issue's own rule (`margin = 1500 ms -
    min(dist_duration, yaw_duration)`) says the shorter axis needs to
    exceed 1.5 s before the flat margin is even in play -- at 15 deg/s,
    yaw_duration is 12.0 s (dist_duration is 2.0 s at this leg's own
    150 mm/s, the block-default speed magnitude PRODUCTION_SPEED_MM_S's
    own comment names), comfortably past that line. 15 deg/s is a rate
    a caller can genuinely set via the block's own "set turn rate" --
    not an extreme/synthetic value, just slower than the block default.
    """
    return 300.0, 180.0, 150.0, 15.0  # [mm] [deg] [mm/s] [deg/s]


def test_deadline_boundary_wide_arc_30cm_180deg_completes_within_max_budget(
        motion_lib):
    """HISTORY: this leg (30 cm with a 180 deg rotation at a slow 15
    deg/s yaw rate) was the reproduction for arc-moves-abort-distance-
    never-driven.md -- moveX()'s old pivot-then-straight split ran two
    SEQUENTIAL phases under a deadline sized for one, and shims.cpp
    widened its budget to dist_duration + yaw_duration for the split
    case. moveX() no longer splits: this is one blended arc (R = 300 /
    pi = 95 mm), both axes finish together, and the plain max()-based
    budget shims.cpp now computes must cover it with the same unforced
    completion an unbounded run reaches."""
    distance_mm, rotation_deg, speed_mm_s, yaw_rate_deg_s = (
        _split_leg_30cm_180deg_params())
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts, budget_s = (
        _shim_move_params(distance_mm, rotation_deg, speed_mm_s,
                          yaw_rate_deg_s, cpm, b))
    assert budget_s == duration_s  # one segment, one max()-based budget

    baseline_ms, baseline_pos, baseline_wrong_way = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, _UNBOUNDED_TIMEOUT_MS)
    _assert_reached_target(baseline_pos, left_counts, right_counts)
    assert baseline_wrong_way == 0

    real_ms, real_pos, real_wrong_way = _run_leg(
        motion_lib, distance_mm, rotation_deg, cruise, timeout_ms)
    assert real_ms < timeout_ms - TICK_MS
    assert real_ms == pytest.approx(baseline_ms, abs=TICK_MS)
    _assert_reached_target(real_pos, left_counts, right_counts)
    assert real_wrong_way == 0


# ---- pure straight leg (legToward()'s <0.01 rad branch, and -------------
# ---- goToWorld()'s own straight-continuation leg) ------------------------


def test_deadline_boundary_pure_straight_production_timeout_matches_unbounded(
        motion_lib):
    """A 600 mm straight run (one of test.ts's own LEG_CM magnitudes) --
    single segment, distFloor_/distTaper_ only, no split. Same
    unbounded-vs-production comparison as the other two leg shapes,
    included for full regression coverage of all three leg shapes
    test.ts's tours actually issue."""
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts, _ = (
        _shim_move_params(600.0, 0.0, PRODUCTION_SPEED_MM_S,
                          PRODUCTION_YAW_RATE_DEG_S, cpm, b))

    baseline_ms, baseline_pos, baseline_wrong_way = _run_leg(
        motion_lib, 600.0, 0.0, cruise, _UNBOUNDED_TIMEOUT_MS)
    _assert_reached_target(baseline_pos, left_counts, right_counts)
    assert baseline_wrong_way == 0

    real_ms, real_pos, real_wrong_way = _run_leg(
        motion_lib, 600.0, 0.0, cruise, timeout_ms)

    assert real_ms == pytest.approx(baseline_ms, abs=TICK_MS)
    assert real_ms < timeout_ms
    _assert_reached_target(real_pos, left_counts, right_counts)
    assert real_wrong_way == 0
