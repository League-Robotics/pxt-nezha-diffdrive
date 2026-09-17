"""tests/host/test_nudge_block_regression.py -- sprint 039 ticket 005
(SUC-002): `nudge()`/`nudgeTurn()` (blocks/motion.ts) and their C++
shim-layer reductions (`beginNudgeWheels()`/`beginNudgeTurn()`,
`nudgeMeasuredDistance()`/`nudgeMeasuredRotation()`, all
`src/shims.cpp`/`src/motion/motion_engine.h`).

blocks/motion.ts is TypeScript, out of reach of a host build (same
constraint `test_goto_block_regression.py`'s own module docstring
names) -- this file restates the two shim-layer reductions directly in
Python and drives them through the REAL `MotionEngine` (via
`motion_engine_shim.cpp`'s ctypes surface, ticket 004's own harness)
the same way `test_goto_block_regression.py` restates
`startGoTo()`/`legToward()`'s reductions.

Two things this file pins, matching ticket 005's acceptance criteria:

1. The (leftMm, rightMm) -> (distance, rotation) reduction
   `beginNudgeWheels()` applies (shims.cpp) round-trips exactly onto
   the SAME per-wheel encoder target `MotionEngine::wheelsX()` would
   reduce onto directly -- proven by arming the encoders at exactly
   that predicted target and confirming the nudge converges there, not
   somewhere else.
2. `nudgeMeasuredDistance()`/`nudgeMeasuredRotation()` report what the
   encoders ACTUALLY read, not the requested amount -- the one
   behavioral requirement ticket 005's own description calls out as
   new versus the issue's original proposal. Proven by requesting one
   displacement, then arming a DIFFERENT actual encoder delta (as a
   real pulse's own imperfect step would produce) and asserting the
   measured accessors track the ARMED delta, not the request.

Run with::

    uv run pytest tests/host/test_nudge_block_regression.py
"""

import math

import pytest

from test_motion_engine_nudge import Engine as _NudgeEngine


LEFT = 0
RIGHT = 1


def _approx(value, rel=1e-3, abs_=1e-3):
    return pytest.approx(value, rel=rel, abs=abs_)


class Engine(_NudgeEngine):
    """test_motion_engine_nudge.py's Engine, extended with the geometry
    accessors/setters and the ticket 005 measured-result accessors this
    file's own reductions need -- same "subclass and extend" shape
    test_goto_block_regression.py's ProbeEngine uses on
    test_motion_engine_reductions.py's Engine."""

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    def set_track_width(self, mm):
        self._lib.meSetTrackWidth(self._handle, mm)

    def set_rotational_slip(self, slip):
        self._lib.meSetRotationalSlip(self._handle, slip)

    def nudge_measured_distance(self):
        return self._lib.meNudgeMeasuredDistance(self._handle)

    def nudge_measured_rotation(self):
        return self._lib.meNudgeMeasuredRotation(self._handle)


def _ready(e, max_duty=100.0):
    e.set_max_duty(max_duty)
    assert e.begin() == 0  # STATUS_OK
    e.clear_duty_history(LEFT)
    e.clear_duty_history(RIGHT)


def _zero_origin(e, sample_time_us=1_000):
    """Explicitly arms both encoders at 0 and steps once, so the next
    beginNudge() call captures a KNOWN (0, 0) origin (Nudge::posLeft0/
    posRight0) instead of relying on FakeMotor's un-stepped default
    (fake_ports.h) -- self-documenting, matching this directory's own
    "place the encoders wherever the test wants" convention rather than
    an implicit assumption."""
    e.arm_motor_position(LEFT, 0.0, sample_time_us=sample_time_us)
    e.arm_motor_position(RIGHT, 0.0, sample_time_us=sample_time_us)
    e.step()


def _begin_nudge_wheels(e, left_mm, right_mm, timeout_ms=20_000):
    """Python restatement of shims.cpp's beginNudgeWheels(): distance is
    the mean of the two per-wheel requests, rotation is the inverse of
    beginNudge()'s own yawTarget formula (motion_engine.h) -- the exact
    formula this ticket's shim uses, so wheelsX()'s own half-difference
    reduction and beginNudge()'s (distance, rotation) pair agree on the
    SAME physical per-wheel target."""
    distance = 0.5 * (left_mm + right_mm)  # [mm]
    rotation = (right_mm - left_mm) / e.effective_track_width()  # [rad]
    e.begin_nudge(distance, rotation, timeout_ms)
    return distance, rotation


def _begin_nudge_turn(e, deg, timeout_ms=20_000):
    """Python restatement of shims.cpp's beginNudgeTurn(): a pure
    rotation, distance == 0."""
    rotation = deg * math.pi / 180.0  # [rad]
    e.begin_nudge(0.0, rotation, timeout_ms)
    return rotation


# ---- AC: nudge()'s (leftMm, rightMm) reduction lands on wheelsX()'s own
# per-wheel target --------------------------------------------------------


def test_nudge_wheels_reduction_converges_at_the_wheels_x_target(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        _zero_origin(e)

        left_mm, right_mm = 6.0, 2.0  # an UNEVEN pair -- exercises both
                                       # the distance and rotation axes
                                       # at once, not just a pure
                                       # straight or a pure turn
        _begin_nudge_wheels(e, left_mm, right_mm)
        assert e.is_nudge_active()

        cpm = e.counts_per_mm()
        # The exact per-wheel encoder target wheelsX(left_mm, right_mm,
        # ...) would drive to directly (motion_engine.cpp's own
        # wheelsX(): distTarget = 0.5*(left+right)*cpm, yawTarget =
        # 0.5*(right-left)*cpm; the target LEFT/RIGHT counts are
        # distTarget -+ yawTarget, matching beginSegment()'s own
        # left = distTarget - yawTarget, right = distTarget + yawTarget
        # convention -- which reduces to just left_mm*cpm/right_mm*cpm
        # for the ORIGINAL per-wheel request, by construction).
        left_target_counts = left_mm * cpm
        right_target_counts = right_mm * cpm

        e.arm_motor_position(LEFT, left_target_counts, sample_time_us=2_000)
        e.arm_motor_position(
            RIGHT, right_target_counts, sample_time_us=2_000)
        e.step()
        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active(), (
            "beginNudgeWheels()'s (distance, rotation) reduction did not "
            "converge at wheelsX()'s own per-wheel target -- the two "
            "reductions disagree")


# ---- AC: nudgeTurn() is a pure rotation, distance stays at 0 -----------


def test_nudge_turn_reduction_is_a_pure_rotation(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        _zero_origin(e)

        rotation = _begin_nudge_turn(e, 3.0)  # [rad]
        assert e.is_nudge_active()

        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        # yawTarget = rotation * 0.5 * b * cpm (motion_engine.h); a pure
        # turn's per-wheel counts are -+yawTarget with distTarget == 0.
        yaw_target_counts = rotation * 0.5 * b * cpm

        e.arm_motor_position(
            LEFT, -yaw_target_counts, sample_time_us=2_000)
        e.arm_motor_position(RIGHT, yaw_target_counts, sample_time_us=2_000)
        e.step()
        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active()


# ---- AC: the measured accessors report what the encoders ACTUALLY read,
# not what was requested (ticket 005's own headline requirement) --------


def test_nudge_measured_distance_reports_the_armed_delta_not_the_request(
        motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        # A nonzero origin -- proves the measured accessors difference
        # against the ORIGIN captured at beginNudge() time, not against
        # a coincidental zero.
        e.arm_motor_position(LEFT, 1000.0, sample_time_us=1_000)
        e.arm_motor_position(RIGHT, 1000.0, sample_time_us=1_000)
        e.step()

        requested_distance_mm = 20.0
        e.begin_nudge(requested_distance_mm, 0.0, 20_000)

        # A single real pulse never lands exactly on the request --
        # arm an ACTUAL delta smaller than what was asked for, the way
        # ticket 003's own ~1.79 mm-per-pulse measurement means a
        # multi-mm request is never fully satisfied in one step.
        cpm = e.counts_per_mm()
        actual_delta_mm = 1.79
        e.arm_motor_position(
            LEFT, 1000.0 + actual_delta_mm * cpm, sample_time_us=2_000)
        e.arm_motor_position(
            RIGHT, 1000.0 + actual_delta_mm * cpm, sample_time_us=2_000)
        e.step()

        measured = e.nudge_measured_distance()
        assert measured == _approx(actual_delta_mm)
        assert measured != _approx(requested_distance_mm), (
            "nudgeMeasuredDistance() reported the REQUESTED amount, not "
            "the encoder-measured one -- this is exactly the bug ticket "
            "005 exists to prevent")


def test_nudge_measured_rotation_reports_the_armed_delta_not_the_request(
        motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        _zero_origin(e)

        requested_deg = 5.0
        e.begin_nudge(0.0, requested_deg * math.pi / 180.0, 20_000)

        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        actual_deg = 0.9  # ticket 003's own ~0.9 deg/pulse figure
        actual_yaw_counts = (actual_deg * math.pi / 180.0) * 0.5 * b * cpm
        e.arm_motor_position(
            LEFT, -actual_yaw_counts, sample_time_us=2_000)
        e.arm_motor_position(RIGHT, actual_yaw_counts, sample_time_us=2_000)
        e.step()

        measured = e.nudge_measured_rotation()
        assert measured == _approx(actual_deg)
        assert measured != _approx(requested_deg), (
            "nudgeMeasuredRotation() reported the REQUESTED angle, not "
            "the encoder-measured one")
