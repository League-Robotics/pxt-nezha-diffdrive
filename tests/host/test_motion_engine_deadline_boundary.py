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
    90 deg) -- this is the ONE shape that reaches
    `MotionEngine::moveX()`'s OWN internal pivot-then-straight split
    (motion_engine.cpp:166), where ONE `timeout` (set once, before the
    split) must cover TWO sequential ramp/taper overheads instead of
    one -- the shape most likely to exhaust the flat +1500 ms margin.
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

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "diffdrive.cpp",
    _SRC_DIR / "motion_engine.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

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


def _bind(lib):
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None

    lib.meSetMaxDuty.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetMaxDuty.restype = None
    lib.meSetFullDutyVelocity.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetFullDutyVelocity.restype = None
    lib.meBegin.argtypes = [ctypes.c_void_p]
    lib.meBegin.restype = ctypes.c_int
    lib.meStep.argtypes = [ctypes.c_void_p]
    lib.meStep.restype = None

    lib.meClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.meClockSetNow.restype = None

    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float
    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float

    lib.meMoveX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meMoveX.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meWrongWayCount.argtypes = [ctypes.c_void_p]
    lib.meWrongWayCount.restype = ctypes.c_uint32

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_deadline_boundary_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


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
    cruise/timeout derivation (lines 379-439) -- the ACTUAL formula
    `test.ts`'s tours drive through, not a simplified stand-in. Mirrors
    the C++ algebra term-for-term, including its `uint32_t` truncation
    of `duration*1000` before adding the flat backstop.

    Returns (cruise_mm_s, timeout_ms, duration_s, left_counts,
    right_counts) -- the last two are startSegment()'s own per-wheel
    targets (motion_engine.cpp:112-113), used by callers to compute the
    expected FINAL absolute encoder position regardless of whether
    moveX() ends up splitting this into two phases: `max(|d-y|,|d+y|)
    == |d|+|y|` is a general identity, so the pivot-then-straight
    split's two phases' own per-wheel targets always sum back to
    exactly these same (left_counts, right_counts) -- see this file's
    _expected_final_position() docstring.
    """
    rotation_rad = math.radians(rotation_deg)
    dist_target_counts = distance_mm * cpm
    yaw_target_counts = rotation_rad * 0.5 * b * cpm
    speed_counts = (speed_mm_s if speed_mm_s > 0 else 1.0) * cpm
    yaw_rad_per_s = math.radians(
        yaw_rate_deg_s if yaw_rate_deg_s > 0 else 1.0)
    twist_counts = yaw_rad_per_s * 0.5 * b * cpm

    duration = 0.0
    if dist_target_counts != 0.0:
        duration = abs(dist_target_counts) / speed_counts
    if yaw_target_counts != 0.0:
        yaw_duration = abs(yaw_target_counts) / twist_counts
        duration = max(duration, yaw_duration)
    assert duration > 0.0  # sanity: every leg below commands real motion

    left_counts = dist_target_counts - yaw_target_counts
    right_counts = dist_target_counts + yaw_target_counts
    dominant_counts = max(abs(left_counts), abs(right_counts))
    cruise_mm_s = (dominant_counts / duration) / cpm

    timeout_ms = int(duration * 1000.0) + _SHIMS_TIMEOUT_MARGIN_MS
    return cruise_mm_s, timeout_ms, duration, left_counts, right_counts


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
    cruise, timeout_ms, duration_s, left_counts, right_counts = (
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


# ---- blended split leg (legToward()'s arc branch, theta >= 50 deg: -------
# ---- the ONE shape that reaches moveX()'s OWN internal pivot-then- -------
# ---- straight split, motion_engine.cpp:166, sharing ONE deadline) --------


def _split_leg_params():
    """A blended (distance AND rotation) leg whose rotation is itself
    >=50 deg -- e.g. legToward()'s own arc branch with bearing 45 deg
    (theta = 2*bearing = 90 deg) reaching for a ~300 mm residual. Round
    numbers chosen directly as moveX()'s own (distance, rotation) args
    rather than re-deriving from a bearing/offset pair -- what matters
    for this file is the (distance, rotation, cruise, timeout) tuple
    moveX() actually receives, not which upstream TS geometry produced
    it. 70 deg comfortably clears kTurnFirstAngleRad (50 deg,
    motion_engine.cpp's own constant) so this is unambiguously the
    split path, not the blended-below-threshold one."""
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
    cruise, timeout_ms, duration_s, left_counts, right_counts = (
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
    cruise, timeout_ms, duration_s, _, _ = _shim_move_params(
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
    """Methodology check, not a defect: strips shims.cpp's own +1500 ms
    backstop (timeout = the bare naive duration, uint32_t-truncated the
    same way shims.cpp itself truncates it) from the SAME split leg
    used above, and confirms the deadline DOES cut the move short --
    stopping near the stripped timeout with the encoder well short of
    its commanded target. This is deliberately the negative control:
    it proves this file's drive loop and assertions can actually detect
    a truncated move (a boundary test that always reports "clean" no
    matter what would be worthless as a regression guard), and it
    demonstrates the +1500 ms margin the two tests above rely on is
    genuinely load-bearing, not incidental slack."""
    distance_mm, rotation_deg = _split_leg_params()
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
    cruise, timeout_ms, duration_s, left_counts, right_counts = (
        _shim_move_params(distance_mm, rotation_deg, PRODUCTION_SPEED_MM_S,
                          PRODUCTION_YAW_RATE_DEG_S, cpm, b))
    stripped_timeout_ms = timeout_ms - _SHIMS_TIMEOUT_MARGIN_MS
    assert stripped_timeout_ms == int(duration_s * 1000.0)

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
    cruise, timeout_ms, duration_s, left_counts, right_counts = (
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
