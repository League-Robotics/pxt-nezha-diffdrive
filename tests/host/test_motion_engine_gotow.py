"""tests/host/test_motion_engine_gotow.py -- sprint 003 ticket 010:
src/motion_engine.h/.cpp's world-frame reduction, goToW(), and the
PoseSource port it reads (a minimal x()/y()/heading() interface,
implemented for tests by FakePoseSource -- tests/host/fake_pose_source.h).

Sprint 006 ticket 007 extends this file with the production
EncoderPoseSource implementation (src/encoder_pose_source.h) and
selectPoseSource(), the host-testable stand-in for engineGoToW()'s own
OtosPort-vs-EncoderPoseSource selection rule (shims.cpp) -- see the
"sprint 006 ticket 007" section near the end of this file.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++): radio-robot-lib/docs/design/
motion-api.md S2 ("go_to_w(x, y) == read pose -> world-to-body ->
go_to_r"), S3.6 (go_to_w's pluggable pose source), S9.3 item 3.

Verification strategy: goToW() is a small, pure transform in front of an
ALREADY-tested reduction (goToR()/moveX(), sprint 003 ticket 007's own
test_motion_engine_reductions.py) -- so this file does not re-exercise
goToR()'s own branches (the pivot-vs-blend threshold, the timeout
backstop, wrong-way abort, ...) beyond what is needed to prove the
world-to-body transform feeds it correctly. Each test independently
recomputes, in Python, the same world-to-body rotation the C++ performs
(body_x = dx*cos(heading) + dy*sin(heading), body_y = -dx*sin(heading) +
dy*cos(heading) -- this project's CCW-positive convention, motion_engine.h
S2.1 header comment) and then goToR()'s own arc-solve formula
(motion-api.md S3.5), before reading back FakeMotor's LAST STAGED DUTY
after exactly one step() -- the same verification strategy
test_motion_engine_reductions.py uses for goToR() itself.

Per the ticket: cases below deliberately combine a NONZERO heading with a
NONZERO position (sign and rotation-direction errors hide exactly there),
and include headings near +-180 deg to exercise the transform across the
wrap boundary a naive angle-difference implementation could get wrong --
this implementation never subtracts two headings, it only takes cos/sin
of the ABSOLUTE current heading, so continuity across the wrap boundary
falls out for free; the test proves that rather than assuming it.

Run with::

    uv run pytest tests/host/test_motion_engine_gotow.py
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
# clamped value (mirrors test_motion_engine_reductions.py's own choice).
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

_DUTY_REL = 1e-4

# motion-api.md S3.3's measured pivot-first threshold -- used here only
# as a sanity guard so a test's chosen (pose, target) pair cannot
# accidentally land in moveX()'s pivot-first split, which would make it
# exercise a different code path than the plain arc solve this file
# means to test.
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

    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float

    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int

    lib.mePoseSourceSetPose.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ]
    lib.mePoseSourceSetPose.restype = None
    lib.meGoToW.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meGoToW.restype = None

    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    # ---- sprint 006 ticket 007: EncoderPoseSource / selectPoseSource ----
    lib.meEncoderPoseSourceSetPose.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ]
    lib.meEncoderPoseSourceSetPose.restype = None
    lib.meEncoderPoseSourceX.argtypes = [ctypes.c_void_p]
    lib.meEncoderPoseSourceX.restype = ctypes.c_float
    lib.meEncoderPoseSourceY.argtypes = [ctypes.c_void_p]
    lib.meEncoderPoseSourceY.restype = ctypes.c_float
    lib.meEncoderPoseSourceHeading.argtypes = [ctypes.c_void_p]
    lib.meEncoderPoseSourceHeading.restype = ctypes.c_float
    lib.meGoToWViaEncoder.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meGoToWViaEncoder.restype = None
    lib.meSelectPoseSourceX.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meSelectPoseSourceX.restype = ctypes.c_float

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_gotow_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    same shape as test_motion_engine_reductions.py's own Engine, extended
    with this ticket's goToW()/PoseSource entry points."""

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

    # ---- kernel ----
    def set_max_duty(self, v):
        self._lib.meSetMaxDuty(self._handle, v)

    def set_full_duty_velocity(self, v):
        self._lib.meSetFullDutyVelocity(self._handle, v)

    def begin(self):
        return self._lib.meBegin(self._handle)

    def step(self):
        self._lib.meStep(self._handle)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    # ---- geometry ----
    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    # ---- goToW / PoseSource ----
    def set_pose(self, x, y, heading):
        self._lib.mePoseSourceSetPose(self._handle, x, y, heading)

    def go_to_w(self, x, y, speed, arrive, timeout_ms):
        self._lib.meGoToW(self._handle, x, y, speed, arrive, timeout_ms)

    def arm_motor_position(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    # ---- EncoderPoseSource / selectPoseSource (sprint 006 ticket 007) ----
    def set_encoder_pose(self, x, y, heading):
        self._lib.meEncoderPoseSourceSetPose(self._handle, x, y, heading)

    def encoder_pose_x(self):
        return self._lib.meEncoderPoseSourceX(self._handle)

    def encoder_pose_y(self):
        return self._lib.meEncoderPoseSourceY(self._handle)

    def encoder_pose_heading(self):
        return self._lib.meEncoderPoseSourceHeading(self._handle)

    def go_to_w_via_encoder(self, x, y, speed, arrive, timeout_ms):
        self._lib.meGoToWViaEncoder(
            self._handle, x, y, speed, arrive, timeout_ms)

    def select_pose_source_x(self, primary_connected):
        return self._lib.meSelectPoseSourceX(
            self._handle, 1 if primary_connected else 0)


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == 0  # STATUS_OK
    return FULL_DUTY_VELOCITY


def _world_to_body(dx, dy, heading):
    """Independently-implemented mirror of MotionEngine::goToW()'s own
    rotation (motion_engine.cpp) -- NOT a call into the C++ under test."""
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    body_x = dx * cos_h + dy * sin_h
    body_y = -dx * sin_h + dy * cos_h
    return body_x, body_y


def _go_to_r_theta_s(x, y):
    """Mirrors MotionEngine::goToR()'s own arc solve (motion-api.md
    S3.5) exactly, including the near-zero-y straight-line special case."""
    theta = 2.0 * math.atan2(y, x)
    if abs(y) < 0.1:
        s = x
    else:
        radius = (x * x + y * y) / (2.0 * y)
        s = radius * theta
    return theta, s


def _segment(distance_mm, rotation_rad, cpm, b):
    """Mirrors MotionEngine::startSegment()'s own targets (mean +
    half-differential), all [counts]."""
    dist_target = distance_mm * cpm
    yaw_target = rotation_rad * 0.5 * b * cpm
    left = dist_target - yaw_target
    right = dist_target + yaw_target
    dominant = max(abs(left), abs(right))
    return left, right, dominant


def _expected_duty_pair(distance_mm, rotation_rad, cruise, cpm, b, fdv,
                        scale):
    """Hand-computed (duty_left, duty_right) for one moveX segment's
    FIRST tick at the given ramp `scale` -- same formula
    test_motion_engine_reductions.py uses for goToR()."""
    left, right, dominant = _segment(distance_mm, rotation_rad, cpm, b)
    cruise_counts = cruise * cpm
    raw_left = (left / dominant) * cruise_counts * scale
    raw_right = (right / dominant) * cruise_counts * scale
    return raw_left / fdv, raw_right / fdv


def _assert_go_to_w_matches(e, cpm, b, fdv, pose, target, speed):
    """Shared assertion body: arm `pose`, call go_to_w(*target, speed),
    step once, and check FakeMotor's staged duty against the
    independently-computed world-to-body + arc-solve expectation."""
    pose_x, pose_y, heading = pose
    target_x, target_y = target

    e.set_pose(pose_x, pose_y, heading)
    e.go_to_w(target_x, target_y, speed, 0.0, 5000)
    e.step()

    dx = target_x - pose_x
    dy = target_y - pose_y
    body_x, body_y = _world_to_body(dx, dy, heading)
    theta, s = _go_to_r_theta_s(body_x, body_y)
    # Sanity: stay on goToR's plain arc-solve branch, not moveX()'s
    # pivot-first split -- otherwise this test would silently exercise a
    # different code path than the one it means to check.
    assert abs(theta) < math.radians(_TURN_FIRST_DEG)

    expected_left, expected_right = _expected_duty_pair(
        s, theta, speed, cpm, b, fdv, scale=0.25)
    assert e.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=_DUTY_REL)
    assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=_DUTY_REL)


# ---- identity pose: goToW must reduce exactly onto goToR -------------------


def test_go_to_w_identity_pose_matches_go_to_r(motion_lib):
    """pose == (0, 0, 0): the world-frame delta IS the body-frame delta,
    so goToW(x, y, ...) must match goToR(x, y, ...) exactly."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()

        _assert_go_to_w_matches(
            e, cpm, b, fdv, pose=(0.0, 0.0, 0.0), target=(200.0, 50.0),
            speed=100.0)


# ---- the transform itself: nonzero position AND nonzero heading -----------


def test_go_to_w_world_to_body_transform_nonzero_pose_and_heading(
        motion_lib):
    """The case the ticket calls out explicitly: a nonzero heading
    combined with a nonzero position is where sign and rotation-direction
    errors hide. speed/target chosen so the resulting body-frame arc
    stays comfortably under the pivot-first threshold."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        heading = math.radians(30.0)

        _assert_go_to_w_matches(
            e, cpm, b, fdv, pose=(100.0, -50.0, heading),
            target=(500.0, 200.0), speed=120.0)


@pytest.mark.parametrize("heading_sign", [1.0, -1.0])
def test_go_to_w_world_to_body_transform_opposite_heading_sign(
        motion_lib, heading_sign):
    """Same nonzero-position-and-heading case, exercised with the
    heading's sign flipped (a right turn's transform vs. a left turn's)
    so a future cable/sign "fix" fails this test instead of shipping."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        heading = math.radians(30.0) * heading_sign

        _assert_go_to_w_matches(
            e, cpm, b, fdv, pose=(100.0, -50.0 * heading_sign, heading),
            target=(500.0, 200.0 * heading_sign), speed=120.0)


# ---- heading near +-180 deg: exercises the transform across the wrap ------
# ---- boundary (motion-api.md S3.6's "heading is unwrapped" concern) -------


def test_go_to_w_heading_near_positive_pi(motion_lib):
    """heading ~= +179 deg: the robot faces roughly the world -x
    direction. The target is placed roughly ahead of that heading, so
    this stays a small, well-conditioned arc -- the point is that a
    heading value this close to the +pi branch produces a sane,
    continuous result (this implementation takes cos/sin of the absolute
    heading directly, never a wrapped difference, so there is no
    discontinuity to trip on)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        heading = math.radians(179.0)

        _assert_go_to_w_matches(
            e, cpm, b, fdv, pose=(0.0, 0.0, heading),
            target=(-100.0, -5.0), speed=100.0)


def test_go_to_w_heading_near_negative_pi(motion_lib):
    """Mirror of the +179 deg case at -179 deg -- physically ~2 deg apart
    from it (through +-180), but represented as a raw radians value on
    the opposite side of the branch cut. A correct, unwrapped transform
    gives a near-mirror-image result to the +179 deg case above; a
    wrap/modulo bug in a rewrite would instead show a discontinuity here."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        heading = math.radians(-179.0)

        _assert_go_to_w_matches(
            e, cpm, b, fdv, pose=(0.0, 0.0, heading),
            target=(-100.0, 5.0), speed=100.0)


# ---- target directly ahead of a rotated heading: hits goToR's straight- ---
# ---- line branch (|body_y| < 0.1 mm) through a nonzero heading -------------


def test_go_to_w_target_directly_ahead_of_rotated_heading_is_straight(
        motion_lib):
    """A target placed exactly along a 45 deg heading's forward ray must
    transform to body_y == 0 (the straight-line branch), proving the
    rotation -- not just the arc math -- is correct: an error in the
    rotation's sign or axis would show up here as a nonzero body_y."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        heading = math.radians(45.0)
        distance = 200.0

        pose = (0.0, 0.0, heading)
        target = (distance * math.cos(heading), distance * math.sin(heading))

        e.set_pose(*pose)
        e.go_to_w(*target, 90.0, 0.0, 5000)
        e.step()

        expected_left, expected_right = _expected_duty_pair(
            distance, 0.0, 90.0, cpm, b, fdv, scale=0.25)
        assert expected_left == pytest.approx(expected_right, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)


# ---- a target equal to the current pose is a no-op, at any heading -------


@pytest.mark.parametrize("heading_deg", [0.0, 30.0, 179.0, -179.0])
def test_go_to_w_target_equal_to_pose_is_a_no_op(motion_lib, heading_deg):
    """dx == dy == 0 must transform to a (0, 0) body-frame delta
    regardless of heading (cos/sin(heading) * 0 is always 0) -- goToR()
    already treats that as a no-op (ticket 007)."""
    with Engine(motion_lib) as e:
        _ready(e)
        heading = math.radians(heading_deg)

        e.set_pose(123.0, 45.0, heading)
        e.go_to_w(123.0, 45.0, 100.0, 0.0, 5000)
        e.step()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
        assert not e.is_move_active()


# ---------------------------------------------------------------------------
# sprint 006 ticket 007: EncoderPoseSource -- the encoder-odometry
# PoseSource fallback for GO_TO_W on robots with no OTOS fitted (most of
# the fleet -- motion-api.md S3.6: "OTOS when fitted, encoder odometry
# otherwise"). encoder_pose_source.h's own header comment carries the
# full design write-up; these tests exercise the REAL
# diffDrive::EncoderPoseSource class (bound to Handle's own encX_/encY_/
# encHeading_ fields, mirroring shims.cpp's Rig::x/y/heading +
# Rig::encoderPose wiring), and selectPoseSource() -- the host-testable
# stand-in for engineGoToW()'s own one-place selection rule (shims.cpp),
# since OtosPort::connected() has no host-testable seam of its own
# (otos_port.h includes pxt.h unconditionally).
# ---------------------------------------------------------------------------


def test_encoder_pose_source_reports_x_y_verbatim(motion_lib):
    """x()/y() are a bare passthrough of the bound fields -- no transform,
    no scaling, matching OtosPort's own x()/y() (only heading() differs in
    wrap convention -- see the parametrized test below)."""
    with Engine(motion_lib) as e:
        e.set_encoder_pose(123.5, -67.25, 0.0)
        assert e.encoder_pose_x() == pytest.approx(123.5)
        assert e.encoder_pose_y() == pytest.approx(-67.25)


@pytest.mark.parametrize("heading_rad", [
    0.0,
    math.radians(200.0),   # > +pi -- OtosPort's (-pi, pi] wrap would alter this
    math.radians(-250.0),  # < -pi -- same, on the negative side
    4.0 * math.pi,         # two full turns -- nowhere near +-pi either
])
def test_encoder_pose_source_heading_is_unwrapped_verbatim(
        motion_lib, heading_rad):
    """AC 2 (this ticket's own acceptance criteria): EncoderPoseSource::
    heading() returns the bound value EXACTLY, with no wrap applied --
    easy to accidentally "fix" to match OtosPort's (-pi, pi] convention,
    which would violate motion-api.md S3.6's explicit requirement for
    this specific implementation (encoder_pose_source.h's own header
    comment, and motion_engine.h's PoseSource comment on the two
    contractually-valid-but-different wrap conventions). Every case here
    is chosen to be a magnitude an OtosPort-style wrap would visibly
    change, so a regression to "wrap it like OtosPort" fails loudly."""
    with Engine(motion_lib) as e:
        e.set_encoder_pose(0.0, 0.0, heading_rad)
        assert e.encoder_pose_heading() == pytest.approx(
            heading_rad, rel=1e-6, abs=1e-6)


# ---- selectPoseSource(): the one-place selection rule engineGoToW() -------
# ---- (shims.cpp) applies -- OtosPort when connected, EncoderPoseSource ----
# ---- otherwise (AC 3) ------------------------------------------------------


def test_select_pose_source_picks_primary_when_connected(motion_lib):
    """`pose` (FakePoseSource) stands in for OtosPort here, `encoderPose`
    for the fallback -- selectPoseSource() itself has no OtosPort
    dependency at all (encoder_pose_source.h), so this proves the RULE in
    isolation from OtosPort's own non-host-testability."""
    with Engine(motion_lib) as e:
        e.set_pose(111.0, 0.0, 0.0)           # "OTOS-like" arm
        e.set_encoder_pose(222.0, 0.0, 0.0)   # "encoder-like" arm

        assert e.select_pose_source_x(True) == pytest.approx(111.0)


def test_select_pose_source_picks_fallback_when_not_connected(motion_lib):
    with Engine(motion_lib) as e:
        e.set_pose(111.0, 0.0, 0.0)
        e.set_encoder_pose(222.0, 0.0, 0.0)

        assert e.select_pose_source_x(False) == pytest.approx(222.0)


# ---- goToW() dispatched THROUGH EncoderPoseSource, no OtosPort anywhere ---
# ---- in this test file's link (AC 1) ---------------------------------------


def test_go_to_w_through_encoder_pose_source_reaches_target(motion_lib):
    """The move dispatches and reaches its target when goToW() is called
    with a REAL diffDrive::EncoderPoseSource as its `pose` argument (not
    FakePoseSource) and no otos_port.h anywhere in this file's own include
    chain -- i.e. GO_TO_W works with no OTOS anywhere in the link. First
    checks the dispatched first-tick duty against the same independently-
    computed world-to-body + arc-solve expectation
    test_go_to_w_world_to_body_transform_nonzero_pose_and_heading uses,
    then drives the single below-threshold segment straight to its target
    (mirroring test_motion_engine_reductions.py's own
    test_go_to_r_pivot_split_reaches_target_above_threshold completion
    pattern) and confirms the move actually ends there."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        pose_x, pose_y, heading = 100.0, -50.0, math.radians(30.0)
        target_x, target_y = 500.0, 200.0
        speed = 120.0

        e.set_encoder_pose(pose_x, pose_y, heading)
        e.go_to_w_via_encoder(target_x, target_y, speed, 0.0, 5000)
        assert e.is_move_active()
        e.step()

        dx = target_x - pose_x
        dy = target_y - pose_y
        body_x, body_y = _world_to_body(dx, dy, heading)
        theta, s = _go_to_r_theta_s(body_x, body_y)
        # Sanity: stay on goToR's plain arc-solve branch (one segment, not
        # moveX()'s generic pivot-first split) -- same guard this file's
        # other goToW tests use.
        assert abs(theta) < math.radians(_TURN_FIRST_DEG)

        expected_left, expected_right = _expected_duty_pair(
            s, theta, speed, cpm, b, fdv, scale=0.25)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected_left, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected_right, rel=_DUTY_REL)

        # Drive the segment straight to its target and confirm the move
        # actually ends there (remain <= margin on both axes at exactly
        # the target is trivially true -- motion_engine.cpp's own
        # serviceMove()).
        dist_target_counts = s * cpm
        yaw_target_counts = theta * 0.5 * b * cpm
        e.arm_motor_position(LEFT, dist_target_counts - yaw_target_counts, 1)
        e.arm_motor_position(RIGHT, dist_target_counts + yaw_target_counts, 2)
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()
