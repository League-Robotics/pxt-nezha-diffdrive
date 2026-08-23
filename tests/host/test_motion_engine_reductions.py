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
        # this test would be exercising moveX()'s pivot split instead of
        # goToR's own plain arc reduction.
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
