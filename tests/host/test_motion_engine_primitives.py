"""tests/host/test_motion_engine_primitives.py -- tests
src/motion/motion_engine.h/.cpp's geometry (effectiveTrackWidth/countsPerMm) and
its two wheel primitives, wheelsX and wheelsV.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/motion-api.md S2 ("Everything is
constant-ratio wheel segments"), S2.1 ("b is the effective track
width"), S3.1 (wheels_x), S3.2 (wheels_v).

Verification strategy: DiffDrive::DifferentialDrive's own
Output.velocity/twist are MEASURED quantities -- computed from encoder
deltas across two samples (core/diffdrive.cpp's refreshSample()) -- not the
COMMANDED values a hand-computed test here wants to check. Rather than
arming motor samples for every case, this file instead reads back the
FakeMotor's own LAST STAGED DUTY after exactly one step(), with the
kernel configured with only maxDuty/fullDutyVelocity set and every other
Config field left at its zero/off default -- the same "duty is pure
feedforward, no PID/bias/twist-hold contribution" configuration
test_kernel_harness.py's own smoke test already established. Under that
configuration, controlStep() (src/core/diffdrive.cpp) computes
rawLeft = velocity - twist, rawRight = velocity + twist and stages
duty = raw / fullDutyVelocity directly (clamped to the maxDuty rail),
so a hand-computed expected duty for each wheel needs only the
fixture's own countsPerMm() and the commanded (or ratio-derived) speeds
-- no encoder samples need to be armed. fullDutyVelocity is chosen large
enough (5000 counts/s) that every case below stays well under the
maxDuty=100% rail, so no test result is a clamped value in disguise.

wheels_x's own lease (the dead-reckoned distance-over-cruise duration,
capped by the required timeout backstop) is verified indirectly via the
kernel's own output().leaseExpired flag across a controlled FakeClock
advance: a step() one tick before the expected lease has elapsed reports
still-live; a step() one tick after reports expired and the duty reverts
to neutral. This primitive's bound is dead-reckoned, not a live
encoder-progress check (see motion_engine.h's own doc comment on
wheelsX) -- the closed-loop stop-on-arrival behavior is ticket 007's
shaping layer, built on top of this primitive's kinematics.

Run with::

    uv run pytest tests/host/test_motion_engine_primitives.py
"""

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

# DiffDrive::DifferentialDrive::Status's DECLARATION order (src/core/diffdrive.h).
STATUS_OK = 0

LEFT = 0
RIGHT = 1

# Chosen large enough that every commanded speed below (<= ~250 mm/s at
# this fixture's default countsPerMm) stays well under the maxDuty=100%
# rail -- so no assertion below is secretly checking a clamped value.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# Loose enough to absorb the float rounding difference between this
# file's direct `speed * cpm / fdv` computation and the engine's own
# mean/half-differential decomposition (velocity, twist) recombined by
# the kernel's controlStep() -- algebraically identical, not bit-for-bit
# identical.
_DUTY_REL = 1e-4


def _bind(lib):
    """Attach ctypes argtypes/restype for every motion_engine_shim.cpp
    export."""
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

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float
    lib.meTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meTrackWidth.restype = ctypes.c_float
    lib.meTravelCalib.argtypes = [ctypes.c_void_p]
    lib.meTravelCalib.restype = ctypes.c_float
    lib.meRotationalSlip.argtypes = [ctypes.c_void_p]
    lib.meRotationalSlip.restype = ctypes.c_float
    lib.meSetTrackWidth.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetTrackWidth.restype = None
    lib.meSetTravelCalib.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetTravelCalib.restype = None
    lib.meSetRotationalSlip.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetRotationalSlip.restype = None

    lib.meWheelsV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meWheelsV.restype = None
    lib.meWheelsX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meWheelsX.restype = None

    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    """Compile motion_engine.cpp (+ diffdrive.cpp + this file's own shim)
    exactly once for the whole pytest session, mirroring
    test_kernel_harness.py's own kernel_lib fixture."""
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle,
    mirroring test_kernel_harness.py's own Kernel wrapper."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()
        self._next_sample_us = 1000

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

    def lease_expired(self):
        return bool(self._lib.meOutLeaseExpired(self._handle))

    def set_clock(self, now_us):
        self._lib.meClockSetNow(self._handle, now_us)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    # ---- MotionEngine geometry ----
    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    def track_width(self):
        return self._lib.meTrackWidth(self._handle)

    def travel_calib(self):
        return self._lib.meTravelCalib(self._handle)

    def rotational_slip(self):
        return self._lib.meRotationalSlip(self._handle)

    def set_track_width(self, mm):
        self._lib.meSetTrackWidth(self._handle, mm)

    def set_travel_calib(self, mm_per_deg):
        self._lib.meSetTravelCalib(self._handle, mm_per_deg)

    def set_rotational_slip(self, slip):
        self._lib.meSetRotationalSlip(self._handle, slip)

    # ---- the two primitives ----
    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def wheels_x(self, left, right, cruise, timeout_ms):
        self._lib.meWheelsX(self._handle, left, right, cruise, timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def arm_motor_position(self, side, position_counts):
        # A fresh, nonzero, ADVANCING sample time each call -- see
        # meMotorArmPosition()'s own comment (motion_engine_shim.cpp).
        self._next_sample_us += 1000
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, self._next_sample_us)

    def land_first_command(self):
        """Sprint 029 ticket 003 (design S6.5's lazy start) -- see
        test_motion_engine_reductions.py's own Engine.land_first_command()
        for the full explanation this file mirrors: a fresh Segment
        (wheelsX()) no longer drives the kernel synchronously, so seeing
        its first command needs step(); service(); step(), not a single
        step()."""
        self.step()
        self.service_move()
        self.step()

    def land_steady_state_hold(self, start_us=0, advance_us=1_000_000):
        """For a continuous wheelsV() hold -- see
        test_motion_engine_reductions.py's own
        Engine.land_steady_state_hold() for the full explanation. Caller
        must have set_clock(start_us) BEFORE the wheels_v() call."""
        self.step()
        self.set_clock(start_us + advance_us)
        self.service_move()
        self.step()


def _ready(engine):
    """Configure the kernel with only maxDuty/fullDutyVelocity set (every
    other Config field stays at its zero/off default) and begin() it --
    see this file's own header comment for why that configuration makes
    duty pure feedforward."""
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == STATUS_OK
    return FULL_DUTY_VELOCITY


def _expected_duty(mm_per_s, cpm, fdv=FULL_DUTY_VELOCITY):
    return mm_per_s * cpm / fdv


# MotionLimits' own compiled-in defaults (motion_limits.h) -- see
# test_motion_engine_reductions.py's own _first_tick_duty_pair() for the
# full explanation these two constants exist for.
_V_FLOOR_MM_S = 70.0
_OMEGA_FLOOR_DEG_S = 20.0


# ---- geometry (motion-api.md S2.1) --------------------------------------


def test_effective_track_width_is_computed_not_stored(motion_lib):
    """b = trackWidth / rotationalSlip, recomputed on every call -- never
    a cached field. Also proves trackWidth's own
    read-back stays exactly the caliper-measured value even though the
    effective (rotation-corrected) value differs, and that setting
    trackWidth again never touches rotationalSlip -- the standing "never
    bend trackwidth to make a turn land" rule (motion-api.md S2.1)."""
    with Engine(motion_lib) as e:
        track_width = e.track_width()
        rotational_slip = e.rotational_slip()
        assert rotational_slip != pytest.approx(1.0)  # else this test proves nothing
        assert e.effective_track_width() == pytest.approx(
            track_width / rotational_slip)

        e.set_track_width(200.0)
        assert e.track_width() == pytest.approx(200.0)
        assert e.rotational_slip() == pytest.approx(rotational_slip)  # untouched
        assert e.effective_track_width() == pytest.approx(
            200.0 / rotational_slip)


def test_set_rotational_slip_updates_effective_track_width_and_rejects_non_positive(
        motion_lib):
    """Sprint 007 ticket 005 (closing R-14/API-06): rotationalSlip_ was
    getter-only ("no caller has ever needed to set it at runtime"); this
    is the setter that closes that gap (Acceptance Criterion 1/4). A
    valid set must move BOTH rotationalSlip() and effectiveTrackWidth()
    (== trackWidth_/rotationalSlip_, motion_engine.h) -- proving the new
    value actually reaches the turn kinematics every move/pivot primitive
    reads (test_motion_engine_reductions.py's own move_x/go_to_r tests
    all read effectiveTrackWidth() for exactly this reason), not just a
    field that round-trips in isolation. 0 and a negative value must both
    be silently ignored, matching setTrackWidth()/setTravelCalib()'s own
    tested ">0, else keep the prior value" behavior (verified above in
    test_effective_track_width_is_computed_not_stored for trackWidth)."""
    with Engine(motion_lib) as e:
        track_width = e.track_width()
        original_slip = e.rotational_slip()
        assert original_slip != pytest.approx(1.0)  # else this test proves nothing

        new_slip = original_slip * 0.5  # deliberately distinct from the default
        e.set_rotational_slip(new_slip)
        assert e.rotational_slip() == pytest.approx(new_slip)
        assert e.track_width() == pytest.approx(track_width)  # untouched
        assert e.effective_track_width() == pytest.approx(
            track_width / new_slip)

        # Invalid values (<= 0) are silently ignored -- the prior (new_slip)
        # value survives, and so does the effectiveTrackWidth it produced.
        e.set_rotational_slip(0.0)
        assert e.rotational_slip() == pytest.approx(new_slip)
        e.set_rotational_slip(-1.0)
        assert e.rotational_slip() == pytest.approx(new_slip)
        assert e.effective_track_width() == pytest.approx(
            track_width / new_slip)


def test_counts_per_mm(motion_lib):
    with Engine(motion_lib) as e:
        travel_calib = e.travel_calib()
        assert e.counts_per_mm() == pytest.approx(10.0 / travel_calib)

        e.set_travel_calib(0.5)
        assert e.counts_per_mm() == pytest.approx(20.0)


# ---- wheelsV (motion-api.md S3.2) ---------------------------------------


def test_wheels_v_straight_line_hand_computed(motion_lib):
    """motion-api.md S7's own example, wheels_v(150, 150, 800): both
    wheels commanded the same speed is a straight line. Sprint 029
    ticket 003: a continuous hold is now SHAPED too (design S4.4/S6.1,
    "jerk is bounded ... on continuous drive, not only mid-profile") --
    the old "full rate immediately" contract is gone;
    land_steady_state_hold() gives the shaper's own accel ramp a large
    `dt` so this test reads the steady-state kinematics instead of the
    (now retired) instantaneous first tick."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.set_clock(0)
        e.wheels_v(150.0, 150.0, 5000)
        e.land_steady_state_hold()

        expected = _expected_duty(150.0, cpm, fdv)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected, rel=_DUTY_REL)


def test_wheels_v_sign_convention_left_turn(motion_lib):
    """CCW-positive (motion-api.md S2.1): a right wheel commanded FASTER
    than the left is a LEFT turn -- the left wheel is the slower one.
    Written explicitly so a future cable-order "fix" fails this test
    instead of shipping (this project has shipped that exact bug and
    patched it four times downstream)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.set_clock(0)
        e.wheels_v(100.0, 150.0, 5000)  # right faster -> left/CCW turn
        e.land_steady_state_hold()

        duty_left = e.motor_last_staged_duty(LEFT)
        duty_right = e.motor_last_staged_duty(RIGHT)
        assert duty_left == pytest.approx(
            _expected_duty(100.0, cpm, fdv), rel=_DUTY_REL)
        assert duty_right == pytest.approx(
            _expected_duty(150.0, cpm, fdv), rel=_DUTY_REL)
        assert duty_right > duty_left  # right (faster) wheel: a left turn


def test_wheels_v_sign_convention_right_turn(motion_lib):
    """The mirror of the above, in the OTHER direction: left wheel
    faster is a right/CW turn -- both signs get their own test."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.set_clock(0)
        e.wheels_v(150.0, 100.0, 5000)  # left faster -> right/CW turn
        e.land_steady_state_hold()

        duty_left = e.motor_last_staged_duty(LEFT)
        duty_right = e.motor_last_staged_duty(RIGHT)
        assert duty_left == pytest.approx(
            _expected_duty(150.0, cpm, fdv), rel=_DUTY_REL)
        assert duty_right == pytest.approx(
            _expected_duty(100.0, cpm, fdv), rel=_DUTY_REL)
        assert duty_left > duty_right  # left (faster) wheel: a right turn


def test_wheels_v_pivot_in_place(motion_lib):
    """Left forward, right backward, equal magnitude: zero net velocity,
    a pure differential -- a pivot."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.set_clock(0)
        e.wheels_v(100.0, -100.0, 5000)
        e.land_steady_state_hold()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            _expected_duty(100.0, cpm, fdv), rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            _expected_duty(-100.0, cpm, fdv), rel=_DUTY_REL)


def test_wheels_v_duration_is_the_lease(motion_lib):
    """duration IS the hold's own deadline (design S4.4's Hold.until),
    tracked by the ENGINE and checked at the top of service()'s
    continuous-hold branch -- distinct from the kernel's own rolling
    500 ms lease, which service() now reissues on EVERY tick regardless
    (design S5) and so no longer tracks a caller's real duration at all
    (that old kernel-level signal, Output.leaseExpired, is what this
    test used to read; it is not the mechanism a hold's real duration
    bound uses any more). One tick before the duration elapses,
    service() is still driving; one tick after, it stages neutral and
    reports inactive -- the same OBSERVABLE contract as before, checked
    through the engine's own return value and the landed duty instead of
    the kernel's lease flag."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.wheels_v(100.0, 100.0, 500)  # [ms]
        e.step()

        e.set_clock(24_000)  # a realistic first tick
        assert e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)

        e.set_clock(499_000)  # 499 ms: still live
        assert e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)

        e.set_clock(501_000)  # 501 ms: expired
        assert not e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---- wheelsX (motion-api.md S3.1) ---------------------------------------


def test_wheels_x_straight_line_hand_computed(motion_lib):
    """motion-api.md S2.1's own degenerate case: wheels_x(d, d) is a
    straight line -- both wheels at ratio 1. Sprint 029 ticket 003:
    wheelsX() is now closed-loop, Segment-based, and lazily started like
    moveX() (design S12/S6.5) -- its first real command lands at the
    floor (v_floor), not `cruise`."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.wheels_x(200.0, 200.0, 150.0, 5000)
        e.land_first_command()

        expected = _expected_duty(_V_FLOOR_MM_S, cpm, fdv)
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            expected, rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            expected, rel=_DUTY_REL)


def test_wheels_x_pivot_hand_computed(motion_lib):
    """motion-api.md S2.1's other degenerate case: wheels_x(+d, -d) is a
    pivot in place -- opposite sign, equal magnitude. Sprint 029 ticket
    003: the first real command floors on omega_floor (converted to the
    dominant wheel's own mm/s, design S6.2), not `cruise` -- see
    test_wheels_x_straight_line_hand_computed's own comment."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()

        e.wheels_x(150.0, -150.0, 100.0, 5000)
        e.land_first_command()

        floor_mm_s = _OMEGA_FLOOR_DEG_S * math.pi / 180.0 * b * 0.5
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            _expected_duty(floor_mm_s, cpm, fdv), rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            _expected_duty(-floor_mm_s, cpm, fdv), rel=_DUTY_REL)


def test_wheels_x_ratio_locked_hand_computed(motion_lib):
    """A non-degenerate case: the DOMINANT wheel (larger magnitude, here
    left at 200mm vs right's 100mm) is the one that reaches the first
    tick's floor speed; the other follows the same ratio (motion-api.md
    S3.1: "both wheels finish together"). Not a pure turn (distTarget !=
    0), so the floor is v_floor -- see
    test_wheels_x_straight_line_hand_computed's own comment."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.wheels_x(200.0, 100.0, 150.0, 5000)  # left dominant -> right at half
        e.land_first_command()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(
            _expected_duty(_V_FLOOR_MM_S, cpm, fdv), rel=_DUTY_REL)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(
            _expected_duty(0.5 * _V_FLOOR_MM_S, cpm, fdv), rel=_DUTY_REL)


def test_wheels_x_sign_convention_both_directions(motion_lib):
    """Same CCW-positive convention as wheelsV, exercised through
    wheelsX's own ratio math in both directions."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.wheels_x(100.0, 150.0, 150.0, 5000)  # right dominant -> left/CCW turn
        e.land_first_command()
        duty_left = e.motor_last_staged_duty(LEFT)
        duty_right = e.motor_last_staged_duty(RIGHT)
        assert duty_right == pytest.approx(
            _expected_duty(_V_FLOOR_MM_S, cpm, fdv), rel=_DUTY_REL)
        assert duty_left == pytest.approx(
            _expected_duty((100.0 / 150.0) * _V_FLOOR_MM_S, cpm, fdv),
            rel=_DUTY_REL)
        assert duty_right > duty_left

    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()

        e.wheels_x(150.0, 100.0, 150.0, 5000)  # left dominant -> right/CW turn
        e.land_first_command()
        duty_left = e.motor_last_staged_duty(LEFT)
        duty_right = e.motor_last_staged_duty(RIGHT)
        assert duty_left == pytest.approx(
            _expected_duty(_V_FLOOR_MM_S, cpm, fdv), rel=_DUTY_REL)
        assert duty_right == pytest.approx(
            _expected_duty((100.0 / 150.0) * _V_FLOOR_MM_S, cpm, fdv),
            rel=_DUTY_REL)
        assert duty_left > duty_right


# DELETED (sprint 029 ticket 003): test_wheels_x_dead_reckoned_lease and
# test_wheels_x_timeout_caps_the_lease both pinned wheelsX()'s OLD
# dead-reckoned duration (dominant/cruise, capped by timeout) -- design
# S12's own recorded decision retires that mechanism outright: "wheelsX
# becomes closed-loop on encoders like moveX() ... the dead-reckoned
# lease was the only reason the two primitives differed in how they
# end." There is no computed lease left to pin; `timeoutMs` is now the
# Segment's own REAL deadline (identical mechanism to moveX()'s own
# timeout), and real closed-loop arrival ends the move the same way a
# moveX() segment does. Replaced by the two tests below.


def test_wheels_x_timeout_is_the_real_backstop_on_a_blocked_robot(
        motion_lib):
    """Sprint 029 ticket 003 (design S12): wheelsX() is now closed-loop,
    Segment-based -- `timeoutMs` is its own real deadline backstop, the
    same mechanism moveX() uses (mirrors
    test_motion_engine_reductions.py's own
    test_move_x_timeout_is_a_real_backstop_on_a_blocked_robot). A
    FakeMotor that never reports progress (the robot is physically
    blocked) is stopped by `timeout`, not by any distance/cruise-derived
    lease -- there is no such lease left to compute."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.wheels_x(200.0, 200.0, 100.0, 2000)  # [mm] [mm] [mm/s] [ms]
        e.land_first_command()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)

        # service() reissues its rolling 500 ms kernel lease on EVERY
        # tick now (design S5) -- a clock jump must call service_move()
        # BEFORE step() to refresh it at the new time (see
        # test_move_x_timeout_is_a_real_backstop_on_a_blocked_robot's
        # own comment on this ordering).
        e.set_clock(1_999_000)  # 1999 ms: still well inside the timeout
        assert e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)

        e.set_clock(2_001_000)  # 2001 ms: past the timeout
        assert not e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_x_closed_loop_completion_ends_on_arrival(motion_lib):
    """The other half of "wheelsX() is a Segment like moveX()" (design
    S12): a REAL encoder arrival ends the move on its own, well before
    `timeout` -- the old wheelsX() had no such check at all (it drove
    dead-reckoned for its whole computed lease no matter what the
    encoders reported)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        e.wheels_x(200.0, 200.0, 100.0, 20_000)  # generous timeout
        e.land_first_command()
        assert e.is_move_active()

        dist_target_counts = 200.0 * cpm
        e.arm_motor_position(LEFT, dist_target_counts)
        e.arm_motor_position(RIGHT, dist_target_counts)
        e.set_clock(24_000)
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()


def test_wheels_x_zero_magnitude_is_a_no_op(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.wheels_x(0.0, 0.0, 100.0, 5000)
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_x_non_positive_cruise_is_a_no_op(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.wheels_x(200.0, 200.0, 0.0, 5000)
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---- degenerate wheels_x() must stop motion already in progress ---------
#
# The two tests above start from an idle kernel, where "nothing to
# command" and "the motor reads zero duty" are indistinguishable -- they
# would pass identically whether or not the degenerate branch touches
# the kernel at all. These two instead establish a LIVE wheels_v() hold
# first: cancelMove() (wheelsX()'s own first call) only clears the move
# engine's own bookkeeping, never the kernel, so a degenerate wheels_x()
# that doesn't also neutral the kernel would leave that hold running
# under its own lease. kernel_.neutral() only STAGES the stop -- it
# lands on the NEXT step(), same staged-vs-delivered contract
# test_regression_post_move_neutral.py pins for the move engine.


def test_wheels_x_zero_magnitude_stops_a_live_wheels_v_hold(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.wheels_v(150.0, 150.0, 5000)
        e.land_steady_state_hold()  # lands wheels_v()'s own nonzero duty
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) != pytest.approx(0.0)

        e.wheels_x(0.0, 0.0, 100.0, 5000)  # degenerate: zero magnitude
        e.step()  # the staged neutral lands
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0), (
            "A degenerate wheels_x() must stop a wheels_v() hold still "
            "in progress -- WHEELS_X 0 0 100 1000 issued during a "
            "WHEELS_V hold used to ack `ok` and leave the robot driving."
        )
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_x_non_positive_cruise_stops_a_live_wheels_v_hold(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.wheels_v(150.0, -150.0, 5000)
        e.land_steady_state_hold()
        assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) != pytest.approx(0.0)

        e.wheels_x(200.0, 200.0, 0.0, 5000)  # degenerate: cruise <= 0
        e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
