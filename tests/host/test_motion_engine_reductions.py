"""tests/host/test_motion_engine_reductions.py -- sprint 003 ticket 007:
src/motion_engine.h/.cpp's move engine -- moveX/moveV/goToR, and the
taper/ramp/wrong-way-abort shaping ported from shims.cpp's former
Rig::startMove()/serviceMove() (this ticket's own move-engine reduction,
built on top of ticket 006's wheelsX/wheelsV primitives).

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++): radio-robot-lib/docs/design/
motion-api.md S2 ("Everything is constant-ratio wheel segments"), S3.3
(move_x, including the pivot-vs-blend threshold), S3.4 (move_v), S3.5
(go_to_r's arc solve).

Verification strategy: same as test_motion_engine_primitives.py (ticket
006) -- read back FakeMotor's own LAST STAGED DUTY after exactly one
step(), with the kernel configured so duty is pure feedforward (only
maxDuty/fullDutyVelocity set). moveX()'s FIRST tick is additionally
scaled by the acceleration ramp's floor (0.25, motion_engine.cpp's own
`cmdScale = 0.25f` at segment start) -- every hand-computed expectation
below bakes that scale in explicitly rather than hiding it in a helper
default, so the ramp's existence stays visible at each call site.

Multi-tick behavior (the pivot-then-straight phase transition, the
`timeout` backstop, wrong-way abort) is driven by arming FakeMotor's
next-reported encoder position directly (`meMotorArmPosition`) -- no
simulated physics, the same "place the encoders wherever the test
wants" pattern fake_ports.h's own FakeMotor is built for.

Run with::

    uv run pytest tests/host/test_motion_engine_reductions.py
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

# Chosen large enough that every commanded speed below stays well under
# the maxDuty=100% rail -- no assertion here is secretly checking a
# clamped value (mirrors test_motion_engine_primitives.py's own choice).
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

_DUTY_REL = 1e-4

# motion-api.md S3.3's measured threshold, `navigator.cpp:237-240`'s
# `turn_first_angle` -- the same 50 deg the engine's own
# kTurnFirstAngleRad constant encodes (0.8726646 rad). Tests below use
# 49.5/50.5 deg -- comfortably on either side of the boundary -- rather
# than the exact 50.0 deg value, so a double-vs-float32 rounding
# difference between this file's math and the engine's own float
# literal can never flip which branch a test observes.
_TURN_FIRST_DEG = 50.0


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
    lib.meOutLeaseExpired.argtypes = [ctypes.c_void_p]
    lib.meOutLeaseExpired.restype = ctypes.c_int

    lib.meClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.meClockSetNow.restype = None

    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float
    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    # Ticket 009: the kernel's own MEASURED velocity (Output.
    # velocityLeft/Right) -- distinct from meMotorLastStagedDuty's
    # COMMANDED duty, see motion_engine_shim.cpp's own comment on these
    # two exports.
    lib.meOutVelocityLeft.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityLeft.restype = ctypes.c_float
    lib.meOutVelocityRight.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityRight.restype = ctypes.c_float

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float

    lib.meWheelsV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meWheelsV.restype = None
    lib.meWheelsX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meWheelsX.restype = None

    lib.meMoveX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meMoveX.restype = None
    lib.meMoveV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meMoveV.restype = None
    lib.meGoToR.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meGoToR.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meEndMove.argtypes = [ctypes.c_void_p]
    lib.meEndMove.restype = None
    lib.meProgress.argtypes = [ctypes.c_void_p]
    lib.meProgress.restype = ctypes.c_int
    lib.meWrongWayCount.argtypes = [ctypes.c_void_p]
    lib.meWrongWayCount.restype = ctypes.c_uint32

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_reductions_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    same shape as test_motion_engine_primitives.py's own Engine, extended
    with the move-engine entry points this ticket adds."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()
        # Monotonically-advancing arming clock, independent of the
        # kernel's own FakeClock -- see arm_motor_position()'s own
        # comment for why a fresh value is required on every call.
        self._next_sample_time_us = 1

    def _fresh_sample_time_us(self):
        value = self._next_sample_time_us
        self._next_sample_time_us += 1
        return value

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ---- kernel ----
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

    def arm_motor_position(self, side, position_counts):
        # A fresh, nonzero, ADVANCING sample time each call: see
        # meMotorArmPosition()'s own comment (motion_engine_shim.cpp) --
        # DifferentialDrive::refreshSample() ignores a position whose
        # sample time did not change, and never samples at all until it
        # is nonzero even once.
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts,
            self._fresh_sample_time_us())

    def arm_motor_position_at(self, side, position_counts, sample_time_us):
        # Same as arm_motor_position(), but the caller supplies the
        # sample time explicitly instead of the auto-incrementing
        # (~1 us/call) clock above -- needed whenever a test wants a
        # REALISTIC interval between two samples so the kernel's
        # computed Output.velocityLeft/Right (position delta / interval,
        # diffdrive.cpp refreshSample()) comes out to a chosen value
        # instead of an astronomically large one (ticket 009's own
        # settle-tick regression test uses this to stage a specific
        # "still coasting" velocity reading at move completion).
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    def motor_velocity(self, side):
        # Output.velocityLeft/Right: MEASURED (from encoder deltas), NOT
        # the commanded duty -- see motor_last_staged_duty()'s own
        # contrasting comment and motion_engine_shim.cpp's.
        if side == LEFT:
            return self._lib.meOutVelocityLeft(self._handle)
        return self._lib.meOutVelocityRight(self._handle)

    # ---- geometry ----
    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    # ---- move engine ----
    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def move_v(self, vx, omega, duration_ms):
        self._lib.meMoveV(self._handle, vx, omega, duration_ms)

    def go_to_r(self, x, y, speed, arrive, timeout_ms):
        self._lib.meGoToR(self._handle, x, y, speed, arrive, timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def end_move(self):
        self._lib.meEndMove(self._handle)

    def progress(self):
        return self._lib.meProgress(self._handle)

    def wrong_way_count(self):
        return self._lib.meWrongWayCount(self._handle)


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == 0  # STATUS_OK
    return FULL_DUTY_VELOCITY


def _segment(distance_mm, rotation_rad, cpm, b):
    """Mirrors MotionEngine::startSegment()'s own targets exactly
    (motion-api.md S2's wheels_x reduction, restated as mean +
    half-differential): returns (left, right, dominant), all [counts]."""
    dist_target = distance_mm * cpm
    yaw_target = rotation_rad * 0.5 * b * cpm
    left = dist_target - yaw_target
    right = dist_target + yaw_target
    dominant = max(abs(left), abs(right))
    return left, right, dominant


def _expected_duty_pair(distance_mm, rotation_rad, cruise, cpm, b, fdv,
                        scale):
    """Hand-computed (duty_left, duty_right) for one moveX segment's
    FIRST tick at the given ramp `scale` -- mirrors startSegment()'s
    velCmd/twistCmd followed by controlStep()'s pure-feedforward
    duty = raw / fullDutyVelocity (see this file's own header comment
    on the verification strategy, and test_motion_engine_primitives.py's
    matching comment for wheelsX/wheelsV)."""
    left, right, dominant = _segment(distance_mm, rotation_rad, cpm, b)
    cruise_counts = cruise * cpm
    raw_left = (left / dominant) * cruise_counts * scale
    raw_right = (right / dominant) * cruise_counts * scale
    return raw_left / fdv, raw_right / fdv


# ---- moveX degenerate cases (motion-api.md S2.1: move_x(d,0) straight, --
# ---- move_x(0,theta) pivot are the two most common motions) --------------


def test_move_x_straight_hand_computed(motion_lib):
    """move_x(d, 0) is a straight line -- both wheels at the same ratio
    (1:1), so both run at exactly `cruise`, scaled by the initial 0.25
    ramp floor on this, the move's first tick."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()

        e.move_x(200.0, 0.0, 150.0, 5000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            200.0, 0.0, 150.0, cpm, b, fdv, scale=0.25)
        assert expected_left == pytest.approx(expected_right, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


def test_move_x_pivot_hand_computed(motion_lib):
    """move_x(0, theta) is a pivot in place -- distance is zero, so this
    stays ONE segment (the pivot-vs-blend split only fires with a
    nonzero distance, motion-api.md S3.3) regardless of theta's size."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        theta = 90.0 * math.pi / 180.0  # [rad] CCW+, well past the threshold

        e.move_x(0.0, theta, 100.0, 5000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            0.0, theta, 100.0, cpm, b, fdv, scale=0.25)
        # Pure pivot: equal magnitude, opposite sign (CCW+ -> right wheel
        # forward, left wheel backward -- same convention
        # test_motion_engine_primitives.py's own sign tests establish).
        assert expected_left == pytest.approx(-expected_right, rel=_DUTY_REL)
        assert expected_right > 0.0
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


# ---- pivot-vs-blend threshold (motion-api.md S3.3) ------------------------


def test_move_x_blends_below_turn_first_threshold(motion_lib):
    """|rotation| < 50 deg WITH a nonzero distance is one blended
    segment -- the full (distance, rotation) pair reduces onto wheelsX
    together, in a single startSegment() call (not a pure pivot)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        rotation = (_TURN_FIRST_DEG - 0.5) * math.pi / 180.0  # 49.5 deg

        e.move_x(200.0, rotation, 150.0, 5000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            200.0, rotation, 150.0, cpm, b, fdv, scale=0.25)
        # Not a pure pivot: the distance contribution keeps the two
        # wheels' commanded speeds from being equal-and-opposite.
        assert expected_left != pytest.approx(-expected_right, rel=1e-2)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


def test_move_x_pivots_first_at_and_above_turn_first_threshold(motion_lib):
    """|rotation| >= 50 deg WITH a nonzero distance is NOT one blended
    segment (motion-api.md S3.3): the first tick must show a PURE PIVOT
    signature (equal magnitude, opposite sign) matching move_x(0,
    rotation) exactly -- independent of the commanded distance, which
    phase 1 does not touch at all. This is the test that would fail if
    moveX() blended instead of splitting."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        rotation = (_TURN_FIRST_DEG + 0.5) * math.pi / 180.0  # 50.5 deg
        distance = 200.0

        e.move_x(distance, rotation, 150.0, 5000)
        e.step()

        pivot_left, pivot_right = _expected_duty_pair(
            0.0, rotation, 150.0, cpm, b, fdv, scale=0.25)
        blend_left, blend_right = _expected_duty_pair(
            distance, rotation, 150.0, cpm, b, fdv, scale=0.25)
        # Sanity: for this (distance, rotation, cruise) the pivot and
        # blend predictions actually differ -- otherwise this test could
        # pass by accident.
        assert pivot_left != pytest.approx(blend_left, rel=1e-2)

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            pivot_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            pivot_right, rel=_DUTY_REL)


def test_move_x_pivot_then_straight_phase_transition(motion_lib):
    """The queued second phase actually runs: once the pivot (phase 1)
    completes cleanly, moveX() advances to a fresh straight segment
    (phase 2, rotation == 0) for the remaining distance -- a single
    caller-visible moveX() call, still active across the transition."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        rotation = 60.0 * math.pi / 180.0  # >= 50 deg -> pivot first
        distance = 300.0
        cruise = 100.0

        e.move_x(distance, rotation, cruise, 10_000)
        e.step()  # lands phase 1's own initial (floor-scaled) duty

        # Arm the encoders to report EXACT arrival at the pivot's target
        # (posLeft0/posRight0 are both 0 -- no move has run yet in this
        # fixture) -- meanProgress stays 0 (distTarget == 0 in phase 1),
        # so only yawDone needs satisfying.
        yaw_target_counts = rotation * 0.5 * b * cpm
        e.arm_motor_position(LEFT, -yaw_target_counts)
        e.arm_motor_position(RIGHT, yaw_target_counts)
        e.step()
        still_active = e.service_move()

        assert still_active  # phase 2 queued, not a full stop
        assert e.is_move_active()

        e.step()  # lands phase 2's own initial (floor-scaled) duty

        expected_left, expected_right = _expected_duty_pair(
            distance, 0.0, cruise, cpm, b, fdv, scale=0.25)
        assert expected_left == pytest.approx(expected_right, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


# ---- moveV (motion-api.md S3.4) -------------------------------------------


def test_move_v_hand_computed(motion_lib):
    """move_v(vx, omega) == wheels_v(vx - omega*b/2, vx + omega*b/2)
    (motion-api.md S2) -- no shaping, full rate immediately (a velocity
    hold has no "end" to taper toward)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        vx = 150.0       # [mm/s]
        omega = 1.0      # [rad/s] CCW+

        e.move_v(vx, omega, 800)
        e.step()

        twist_mm_s = omega * 0.5 * b
        expected_left = (vx - twist_mm_s) * cpm / fdv
        expected_right = (vx + twist_mm_s) * cpm / fdv
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)
        assert expected_right > expected_left  # CCW+ -> right wheel faster


def test_move_v_pure_forward_is_equal_wheels(motion_lib):
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.move_v(120.0, 0.0, 500)
        e.step()

        expected = 120.0 * cpm / fdv
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected, rel=_DUTY_REL)


def test_move_v_clears_an_in_flight_move_x(motion_lib):
    """motion-api.md S6: "wheels_* clears the planner" -- moveV()
    reduces onto wheelsV(), which must cancel an in-flight moveX()."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.move_x(500.0, 0.0, 100.0, 5000)
        assert e.is_move_active()

        e.move_v(50.0, 0.0, 500)

        assert not e.is_move_active()


# ---- goToR (motion-api.md S3.5) -------------------------------------------


def test_go_to_r_near_zero_y_is_straight(motion_lib):
    """|y| under the ~0.1 mm threshold is treated as a straight line
    (s == x), even though `theta` itself (2*atan2(y,x)) is computed
    unconditionally and is not exactly zero -- this test mirrors that
    exactly rather than assuming theta is zero."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = 300.0, 0.05, 120.0

        e.go_to_r(x, y, speed, 0.0, 5000)
        e.step()

        theta = 2.0 * math.atan2(y, x)
        expected_left, expected_right = _expected_duty_pair(
            x, theta, speed, cpm, b, fdv, scale=0.25)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


@pytest.mark.parametrize("y_sign", [1.0, -1.0])
def test_go_to_r_arc_hand_computed(motion_lib, y_sign):
    """A genuine arc (motion-api.md S3.5): turn angle phi = 2*atan2(y,x),
    arc length s = R*phi with R = (x^2+y^2)/(2y) -- exercised in both
    left (+y) and right (-y) directions."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = 200.0, 50.0 * y_sign, 100.0

        e.go_to_r(x, y, speed, 0.0, 5000)
        e.step()

        theta = 2.0 * math.atan2(y, x)
        radius = (x * x + y * y) / (2.0 * y)
        s = radius * theta
        # This (x, y) pair must stay under the pivot-first threshold, or
        # this test would be exercising goToR()'s own above-threshold
        # bearing-pivot-then-chord split (sprint 006, KERN-02) instead of
        # its plain arc reduction -- see
        # test_go_to_r_pivot_split_reaches_target_above_threshold and
        # test_go_to_r_behind_robot_splits_into_bounded_pivot, below, for
        # that above-threshold coverage.
        assert abs(theta) < math.radians(_TURN_FIRST_DEG)

        expected_left, expected_right = _expected_duty_pair(
            s, theta, speed, cpm, b, fdv, scale=0.25)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


def test_go_to_r_zero_target_is_a_no_op(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.go_to_r(0.0, 0.0, 100.0, 0.0, 5000)
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
        assert not e.is_move_active()


# ---- goToR: sprint 006 pivot-split fix, short-arc normalization, and -----
# ---- arrive gate (code review R-02/R-03/R-04, KERN-02/03/04) -------------
#
# See clasi/sprints/006-.../issues/goto-geometry-pivot-split-miss.md and
# docs/code-review/2026-08-23/raw/{correctness-kernel,verify-kernel}.md for
# the full arithmetic these tests mirror. goToR() now makes its own
# pivot-vs-blend split decision (bearing-pivot + chord above threshold,
# reached via the same pending-phase queuing moveX()'s own split uses --
# see test_move_x_pivot_then_straight_phase_transition, above, for that
# same two-phase pattern) instead of inheriting moveX()'s generic one,
# normalizes the arc angle to the short arc BEFORE deciding anything, and
# honors `arrive` as a radial no-op gate.


def _wrap_to_pi(angle_rad):
    """Python mirror of MotionEngine::wrapToPi() (motion_engine.cpp,
    anonymous namespace) -- the domain is always bounded to
    (-2*pi, 2*pi] (twice an atan2 result), so a single conditional wrap
    suffices, exactly as the C++ does."""
    pi = math.pi
    if angle_rad > pi:
        return angle_rad - 2.0 * pi
    if angle_rad <= -pi:
        return angle_rad + 2.0 * pi
    return angle_rad


def test_go_to_r_pivot_split_reaches_target_above_threshold(motion_lib):
    """KERN-02's own worked example: goToR(100, 100) is bearing 45 deg /
    theta 90 deg -- above the 50 deg threshold. Pre-fix, moveX()'s generic
    split reissued theta=90deg/arc-length s=157.1mm as pivot-then-
    straight, landing at (0, 157.1) -- a 115 mm miss on a 141 mm hop.
    goToR() now pivots to the line-of-sight BEARING (45 deg) then drives
    the straight-line CHORD (141.421 mm), which reaches (100, 100)
    exactly. Drives both phases to completion (mirroring
    test_move_x_pivot_then_straight_phase_transition's pattern) and
    kinematically integrates the issued (bearing, chord) pair to confirm
    the endpoint, per the ticket's own testing plan."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = 100.0, 100.0, 100.0

        bearing = math.atan2(y, x)
        chord = math.hypot(x, y)
        theta_raw = 2.0 * bearing
        assert abs(theta_raw) >= math.radians(_TURN_FIRST_DEG)  # sanity

        e.go_to_r(x, y, speed, 0.0, 10_000)
        e.step()  # phase 1's own initial (floor-scaled) duty

        pivot_left, pivot_right = _expected_duty_pair(
            0.0, bearing, speed, cpm, b, fdv, scale=0.25)
        # NOTE: a pure pivot's first-tick duty ratio is +-1 regardless of
        # the pivot's MAGNITUDE (only its sign) -- dominant == |yawTarget|
        # by construction, so this tick's duty alone cannot distinguish
        # "pivot to bearing (45 deg)" from "pivot to theta_raw (90 deg)",
        # the old buggy composition's own first phase. The real
        # discriminator is which ANGLE the pivot actually completes at --
        # see the arm_motor_position() call below, using bearing's own
        # yaw target: if the engine were still (wrongly) using theta_raw
        # internally, that target would be reached at half progress, the
        # pivot would NOT complete here, and the next tick's duty would
        # still show a pivot signature instead of phase 2's chord.
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            pivot_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            pivot_right, rel=_DUTY_REL)

        # Complete the pivot (mean progress stays 0 -- phase 1's distance
        # target is 0) and confirm phase 2 (the chord) is queued.
        yaw_target_counts = bearing * 0.5 * b * cpm
        e.arm_motor_position(LEFT, -yaw_target_counts)
        e.arm_motor_position(RIGHT, yaw_target_counts)
        e.step()
        assert e.service_move()  # still active: phase 2 queued
        assert e.is_move_active()

        e.step()  # phase 2's own initial (floor-scaled) duty
        chord_left, chord_right = _expected_duty_pair(
            chord, 0.0, speed, cpm, b, fdv, scale=0.25)
        assert chord_left == pytest.approx(chord_right, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            chord_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            chord_right, rel=_DUTY_REL)

        # Complete the chord leg and confirm the move ends outright (no
        # further pending phase).
        dist_target_counts = chord * cpm
        e.arm_motor_position(LEFT, dist_target_counts)
        e.arm_motor_position(RIGHT, dist_target_counts)
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()

        # Kinematically integrate the issued (bearing, chord) pair
        # (verify-kernel.md's KERN-02 arithmetic): pivot to `bearing`,
        # then drive `chord` forward along the new heading.
        endpoint = (chord * math.cos(bearing), chord * math.sin(bearing))
        assert endpoint == pytest.approx((x, y), abs=1e-2)


def test_go_to_r_behind_robot_splits_into_bounded_pivot(motion_lib):
    """SUC-001's own acceptance language: a target behind the robot
    issues a short-arc pivot (<= ~180 deg), not the long way around.
    (-50, 100) is comfortably above the split threshold both before and
    after short-arc normalization (bearing 116.57 deg, theta_raw 233.13
    deg wraps to -126.87 deg -- both sides of the wrap agree the split
    should fire, so this input is not near the wrap's own dead zone --
    see test_go_to_r_behind_robot_near_axis_avoids_long_way_around_runaway
    below for that case), and it is genuinely "behind" (x < 0) with a
    genuinely large commanded pivot -- a substantive instance of the
    bound, not just a technically-satisfied one."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = -50.0, 100.0, 100.0

        bearing = math.atan2(y, x)
        chord = math.hypot(x, y)
        # The bound this fix guarantees, and a check that this input
        # actually exercises a SUBSTANTIAL pivot, not a trivial one.
        assert abs(bearing) <= math.pi
        assert abs(bearing) > math.radians(90.0)

        e.go_to_r(x, y, speed, 0.0, 10_000)
        e.step()

        pivot_left, pivot_right = _expected_duty_pair(
            0.0, bearing, speed, cpm, b, fdv, scale=0.25)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            pivot_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            pivot_right, rel=_DUTY_REL)

        yaw_target_counts = bearing * 0.5 * b * cpm
        e.arm_motor_position(LEFT, -yaw_target_counts)
        e.arm_motor_position(RIGHT, yaw_target_counts)
        e.step()
        assert e.service_move()
        assert e.is_move_active()

        e.step()
        chord_left, chord_right = _expected_duty_pair(
            chord, 0.0, speed, cpm, b, fdv, scale=0.25)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            chord_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            chord_right, rel=_DUTY_REL)

        endpoint = (chord * math.cos(bearing), chord * math.sin(bearing))
        assert endpoint == pytest.approx((x, y), abs=1e-2)


def test_go_to_r_behind_robot_near_axis_avoids_long_way_around_runaway(
        motion_lib):
    """KERN-03's own worked example: goToR(-100, 1). Pre-fix: theta_raw =
    2*atan2(1,-100) = 358.85 deg, radius = 5000.5 mm, s = radius*theta_raw
    = ~31,319 mm -- combined with the old pivot-first split, a ~359 deg
    pivot plus a 31-METRE leg. Short-arc normalization wraps theta to
    ~-1.146 deg BEFORE the split decision, which (a) falls back below the
    50 deg split threshold -- so this is goToR's plain arc branch, not
    the pivot+chord split -- and (b) recomputes `s` from the SAME radius
    with the wrapped angle, landing at ~-100 mm: the robot backs straight
    up onto the target instead of driving 31 metres around a huge circle.
    Either way the resulting rotation is bounded well under the ~180 deg
    the fix guarantees."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = -100.0, 1.0, 100.0

        theta_raw = 2.0 * math.atan2(y, x)
        theta = _wrap_to_pi(theta_raw)
        radius = (x * x + y * y) / (2.0 * y)
        s = radius * theta
        s_raw = radius * theta_raw

        # The danger this fix removes: normalization must actually change
        # the value used, and drastically shrink the commanded distance.
        assert abs(theta) < math.radians(_TURN_FIRST_DEG)  # NOT split
        assert abs(theta_raw) > math.radians(170.0)  # the raw value: huge
        assert abs(s) < 500.0  # nowhere near the pre-fix ~31.3 m leg
        assert abs(s_raw) > 30_000.0  # sanity: the old leg really was ~31 m
        assert abs(theta) <= math.pi  # the "<= ~180 deg" bound, either way

        e.go_to_r(x, y, speed, 0.0, 10_000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            s, theta, speed, cpm, b, fdv, scale=0.25)
        # Sanity: this must NOT be a pure pivot (the old, buggy
        # composition's own first-tick signature, since |theta_raw| >= 50
        # deg would also have fired moveX()'s generic split on the RAW
        # value) -- the fix's single blended segment mixes a nonzero `s`
        # into both wheels' commanded speed.
        assert expected_left != pytest.approx(-expected_right, rel=1e-2)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)

        # Confirm this is genuinely ONE segment (no split at all): arming
        # both wheels to the single segment's own combined target ends
        # the move outright, not "still active, phase 2 queued."
        dist_target_counts = s * cpm
        yaw_target_counts = theta * 0.5 * b * cpm
        e.arm_motor_position(LEFT, dist_target_counts - yaw_target_counts)
        e.arm_motor_position(RIGHT, dist_target_counts + yaw_target_counts)
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()

        # Kinematically integrate the blended arc (verify-kernel.md's own
        # formula): endpoint = (R*sin(theta), R*(1 - cos(theta))).
        endpoint = (radius * math.sin(theta), radius * (1.0 - math.cos(theta)))
        assert endpoint == pytest.approx((x, y), abs=1e-2)


def test_go_to_r_theta_normalized_independent_of_split_decision(motion_lib):
    """Dedicated coverage for short-arc normalization ALONE, independent
    of the split branch: goToR(-100, 0.05) hits goToR's own |y| < 0.1
    straight-line special case, so `s == x == -100` regardless of
    normalization -- isolating theta as the ONLY value that changes.
    Pre-fix, theta_raw = 2*atan2(0.05,-100) = ~359.94 deg (the review's
    own "wasteful, not dangerous" example: a full pivot before backing
    up 100 mm); normalized, theta = ~-0.057 deg -- a below-threshold
    target behind the robot that still takes the short turn, not the raw
    2*atan2 value, exactly the case this ticket's own acceptance
    criteria calls out."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        x, y, speed = -100.0, 0.05, 100.0

        theta_raw = 2.0 * math.atan2(y, x)
        theta = _wrap_to_pi(theta_raw)
        s = x  # the |y| < 0.1 branch -- unaffected by normalization

        assert abs(theta_raw) > math.radians(170.0)  # the raw value: huge
        assert abs(theta) < math.radians(1.0)  # normalized: a tiny turn
        assert abs(theta) < math.radians(_TURN_FIRST_DEG)  # NOT split

        e.go_to_r(x, y, speed, 0.0, 5000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            s, theta, speed, cpm, b, fdv, scale=0.25)
        # Sanity: the raw (un-normalized) value would have been a PURE
        # PIVOT first-tick signature (moveX()'s own generic split firing
        # on |theta_raw| >= 50 deg: distance == 0, rotation == theta_raw)
        # -- equal-magnitude, OPPOSITE-sign wheel duties. This fix's
        # actual first tick is instead a blended segment dominated by the
        # (nonzero) distance, so both wheels read the SAME sign -- only
        # the RIGHT wheel actually distinguishes the two shapes here (the
        # LEFT wheel's ratio happens to be -1 either way: a pure pivot to
        # a positive angle and "mostly straight, backward" both drive the
        # left wheel in reverse).
        raw_pivot_right = _expected_duty_pair(
            0.0, theta_raw, speed, cpm, b, fdv, scale=0.25)[1]
        assert e.motor_last_staged_duty(RIGHT) != pytest.approx(
            raw_pivot_right, rel=1e-2)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


# ---- arrive: a radial no-op gate, not exact-float-equality (KERN-04) -----


@pytest.mark.parametrize("x,y,arrive", [
    (0.0, 0.0, 10.0),      # exact zero, well within a generous tolerance
    (0.02, 0.05, 10.0),    # measured-pose noise offset (~0.054 mm) < 10 mm
    (10.0, 0.0, 10.0),     # exactly AT the tolerance boundary (<=, inclusive)
])
def test_go_to_r_arrive_gate_is_a_no_op(motion_lib, x, y, arrive):
    """KERN-04: `arrive` is a radial no-op gate (`hypot(x, y) <= arrive`),
    not the old exact-float-equality guard a measured/noisy pose could
    essentially never satisfy. Being at (or within noise of) the target
    -- even off-axis noise like (0.02, 0.05) -- must issue no segment,
    not the up-to-180 deg correcting pivot the old guard allowed."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.go_to_r(x, y, 100.0, arrive, 5000)
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
        assert not e.is_move_active()


def test_go_to_r_arrive_gate_does_not_swallow_targets_beyond_tolerance(
        motion_lib):
    """The gate's other edge: a target just OUTSIDE `arrive` must still
    issue a real segment -- `arrive` is a tolerance, not a way to
    silently ignore every call."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.go_to_r(10.1, 0.0, 100.0, 10.0, 5000)
        e.step()
        assert e.is_move_active()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) != pytest.approx(0.0)


# ---- timeout: a REAL backstop, distinct from any internal lease ----------


def test_move_x_timeout_is_a_real_backstop_on_a_blocked_robot(motion_lib):
    """A FakeMotor that never reports progress (encoders never armed --
    the robot is physically blocked) must still be stopped by `timeout`,
    not left running forever waiting for encoder confirmation that never
    comes. Distinct from wheelsX's own dead-reckoned lease
    (test_motion_engine_primitives.py) -- here the lease is
    CONTINUOUSLY re-issued (serviceMove()'s own rolling 500 ms reissue)
    and would never expire on its own; only the explicit deadline check
    ends the move."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.move_x(1000.0, 0.0, 50.0, 2000)  # [mm] [rad] [mm/s] [ms]

        e.set_clock(1_999_000)  # 1999 ms: still well inside the timeout
        e.step()
        assert e.service_move()
        assert e.is_move_active()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)

        e.set_clock(2_001_000)  # 2001 ms: past the timeout
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()
        # kernel_.neutral() only reaches the motors on the NEXT step() --
        # exactly the "settle tick" concern shims.cpp's tickDrive() owns
        # for real (ticket 009); one more step() here is this test's own
        # way of witnessing the stop actually land.
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---- preserved shaping behavior (ported, not re-derived) ------------------


def test_move_x_wrong_way_abort_increments_count(motion_lib):
    """SIGNED yaw progress: a pivot that physically turns the WRONG way
    aborts and is counted, rather than reporting success (preserved
    verbatim from the code this class is extracted from)."""
    with Engine(motion_lib) as e:
        _ready(e)
        before = e.wrong_way_count()
        rotation = 90.0 * math.pi / 180.0  # commanded CCW+

        e.move_x(0.0, rotation, 100.0, 5000)
        e.step()
        # Physically rotated CW (the wrong way): left forward, right
        # backward -- opposite of what a CCW+ commanded pivot means.
        e.arm_motor_position(LEFT, 1000.0)
        e.arm_motor_position(RIGHT, -1000.0)
        e.step()

        assert not e.service_move()
        assert not e.is_move_active()
        assert e.wrong_way_count() == before + 1


def test_move_x_progress_reports_zero_then_fraction(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        distance = 200.0

        e.move_x(distance, 0.0, 100.0, 5000)
        e.step()
        assert e.progress() == 0

        half_counts = 0.5 * distance * cpm
        e.arm_motor_position(LEFT, half_counts)
        e.arm_motor_position(RIGHT, half_counts)
        e.step()
        e.service_move()

        assert e.progress() == pytest.approx(500, abs=5)


def test_end_move_stops_and_clears_active_state(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.move_x(500.0, 0.0, 100.0, 5000)
        e.step()
        assert e.is_move_active()

        e.end_move()
        assert not e.is_move_active()

        e.step()  # let the staged neutral land
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
