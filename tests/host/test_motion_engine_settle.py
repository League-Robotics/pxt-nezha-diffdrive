"""tests/host/test_motion_engine_settle.py -- sprint 008 ticket 004:
src/motion_engine.h/.cpp's `MotionEngine::settleToRest()`, extracted from
shims.cpp::tickDrive()'s former inline settle loop.

THE BUG THIS GUARDS (commit 3e919e5, 2026-08-20; see
test_regression_post_move_neutral.py for the full write-up): a move's
staged `kernel_.neutral()` only reaches the motors on the kernel's NEXT
`step()` -- and that one extra step's own encoder read can land
mid-spin-down, freezing `Output.velocityLeft/Right` at a nonzero value
forever unless the kernel keeps stepping until both wheels are MEASURED
at rest. `settleToRest()` is that bounded-iteration, break-on-rest
decision, byte-for-byte the same one shims.cpp's inline loop used to
make.

WHY THIS FILE EXISTS (closes settle-tick-loop-is-not-host-testable.md):
before this ticket, that decision lived ONLY in shims.cpp, which
includes pxt.h and cannot be compiled by this host harness -- so a
regression that deleted or shortened the loop passed the entire host
suite. test_regression_post_move_neutral.py could only pin the loop's
SHAPE by a Python-side mirror; it never executed shims.cpp's real loop
body (see that file's own module docstring, "WHAT THIS FILE CANNOT
PROVE"). This file calls the REAL, now-extracted
`MotionEngine::settleToRest()` C++ method directly -- deleting or
neutering it (e.g. changing the iteration cap, the rest threshold, or
short-circuiting the loop to a single step) fails the tests below.

ODOMETRY OWNERSHIP IS UNCHANGED by this extraction: settleToRest() never
touches Rig-local x/y/heading (motion_engine.cpp has no odomUpdate() of
its own, and never gains one here) -- shims.cpp's tickDrive() still
calls its own odomUpdate(r), once, immediately after settleToRest()
returns. This file has no way to observe that shims.cpp-side call (same
boundary test_regression_post_move_neutral.py's own module docstring
notes) -- it proves the DECISION, not the odometry fold.

VERIFICATION TECHNIQUE: `FakeSleeper::onSleep` (fake_ports.h, sprint 006
ticket 002) is armed (via the new `meArmSettleProfile` export) to play
back a step-indexed encoder position/sample-time SCRIPT while
settleToRest()'s own internal `kernel.step()` loop runs -- the only way
to feed a decaying (or held-high) coast-down profile across
settleToRest()'s OWN internal steps, which happen inside ONE C++ call
and are not otherwise individually steppable from Python (a
statically-armed FakeMotor position, left un-rearmed, reads back FROZEN
after its first `tick()` -- `DifferentialDrive::refreshSample()` only
accepts a sample whose `Motor::sampleTime()` actually changed).
Iteration counts are read back via `Output.cycleCount`'s own before/
after delta (`meSettleToRest`'s return value) -- cycleCount increments
unconditionally on every `kernel.step()` regardless of caller
(src/diffdrive.cpp), so no new production-code counter was needed.

Run with::

    uv run pytest tests/host/test_motion_engine_settle.py
"""

import ctypes
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
# the maxDuty=100% rail (mirrors test_motion_engine_reductions.py's own
# choice).
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# motion_engine.h's own settleToRest() constants (sprint 008 ticket 004
# -- moved here from shims.cpp by this ticket's extraction), restated
# so a reader can compare directly against src/motion_engine.h rather
# than trusting a hidden helper -- same convention
# test_regression_post_move_neutral.py's own SETTLE_CAP/
# SETTLE_REST_COUNTS_PER_S already established.
SETTLE_CAP = 12  # [steps]
SETTLE_REST_COUNTS_PER_S = 25.0  # [counts/s] ~2 mm/s

_CYCLE_S = 0.024  # [s] one control cycle, matching
                   # DifferentialDrive::Config's default cyclePeriod


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
    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    lib.meOutVelocityLeft.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityLeft.restype = ctypes.c_float
    lib.meOutVelocityRight.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityRight.restype = ctypes.c_float

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float

    lib.meMoveX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meMoveX.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int

    # ---- sprint 008 ticket 004: the extracted settle helper, plus its
    # own onSleep-driven test-script hook (motion_engine_shim.cpp). ----
    lib.meSettleToRest.argtypes = [ctypes.c_void_p]
    lib.meSettleToRest.restype = ctypes.c_uint32
    lib.meArmSettleProfile.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.c_int,
    ]
    lib.meArmSettleProfile.restype = None
    lib.meDisarmSettleProfile.argtypes = [ctypes.c_void_p]
    lib.meDisarmSettleProfile.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_settle_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin ctypes wrapper, same shape as the other motion_engine test
    files' own Engine (see test_motion_engine_reductions.py's for the
    canonical version) -- trimmed to what this file's tests need, plus
    the new settle-specific surface."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()
        # Monotonically-advancing arming clock, independent of the
        # kernel's own FakeClock -- see arm_motor_position_at()'s own
        # comment in test_motion_engine_reductions.py for why a fresh
        # value is required on every call.
        self._next_sample_time_us = 1
        # Keeps the ctypes arrays passed to meArmSettleProfile() alive
        # for as long as this Engine (and therefore the Handle holding
        # a raw pointer to them) is alive -- see arm_settle_profile()'s
        # own comment.
        self._profile_positions = None
        self._profile_times = None

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

    def arm_motor_position_at(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    def motor_velocity(self, side):
        if side == LEFT:
            return self._lib.meOutVelocityLeft(self._handle)
        return self._lib.meOutVelocityRight(self._handle)

    # ---- geometry ----
    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    # ---- move engine ----
    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    # ---- sprint 008 ticket 004: the settle helper under test ----
    def settle_to_rest(self):
        """Calls the REAL MotionEngine::settleToRest() once and returns
        how many kernel.step() calls it made internally (Output.
        cycleCount's own before/after delta -- see motion_engine_shim.
        cpp's own comment)."""
        return self._lib.meSettleToRest(self._handle)

    def arm_settle_profile(self, velocities_counts_per_s, start_position,
                           start_time_us):
        """Scripts the position/sample-time pair a following
        settle_to_rest() call's Nth internal step (0-based) will read --
        one velocity per step, realized as position += v * _CYCLE_S at
        a matching _CYCLE_S time advance each step, so the kernel's own
        computed Output.velocityLeft/Right comes out to exactly `v` on
        that step (see diffdrive.cpp's refreshSample():
        velocity = delta-position / delta-time). Arrays are kept alive
        on `self` for the lifetime of this Engine -- see
        meArmSettleProfile()'s own comment on pointer lifetime."""
        count = len(velocities_counts_per_s)
        positions = (ctypes.c_float * count)()
        times = (ctypes.c_uint64 * count)()
        position = start_position
        time_us = start_time_us
        for i, v in enumerate(velocities_counts_per_s):
            time_us += int(_CYCLE_S * 1_000_000)
            position += v * _CYCLE_S
            positions[i] = position
            times[i] = time_us
        self._profile_positions = positions  # keep alive
        self._profile_times = times
        self._lib.meArmSettleProfile(self._handle, positions, times, count)

    def disarm_settle_profile(self):
        self._lib.meDisarmSettleProfile(self._handle)
        self._profile_positions = None
        self._profile_times = None


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == 0  # STATUS_OK
    return FULL_DUTY_VELOCITY


def _drive_to_natural_completion(e, distance=200.0, cruise=150.0,
                                 timeout_ms=5000):
    """Reproduces test_regression_post_move_neutral.py's own natural-
    completion setup (same numbers, same technique) up through the
    moment `service_move()` first reports the move done -- the exact
    "neutral staged, not yet delivered, wheels still measured coasting"
    moment shims.cpp::tickDrive() hands off to the settle helper under
    test. See that file's test_move_x_natural_completion_delivers_
    neutral_to_motor for the full derivation of these numbers. Returns
    (dist_target, t_us) so a caller can continue arming realistic
    positions/timestamps from where this setup left off."""
    cpm = e.counts_per_mm()
    dist_target = distance * cpm

    e.move_x(distance, 0.0, cruise, timeout_ms)
    e.step()  # lands the segment's own initial (0.25 ramp) duty

    velocity_at_completion = 500.0  # [counts/s] ~40 mm/s, above rest
    approach_delta = velocity_at_completion * _CYCLE_S  # 12.0 counts
    t_us = 24_000
    e.arm_motor_position_at(LEFT, dist_target - approach_delta, t_us)
    e.arm_motor_position_at(RIGHT, dist_target - approach_delta, t_us)
    e.step()  # seeds the baseline sample
    assert e.service_move()  # still active

    t_us += 24_000
    e.arm_motor_position_at(LEFT, dist_target, t_us)
    e.arm_motor_position_at(RIGHT, dist_target, t_us)
    e.step()  # commits the completing sample: velocity = 500 counts/s
    assert not e.service_move()  # THIS is the moment "done" is first
                                   # reported -- neutral is now STAGED,
                                   # not yet delivered to the motors.
    assert not e.is_move_active()
    return dist_target, t_us


# ---- AC: steps repeatedly while above threshold, stops early without --
# ---- over-stepping, never re-energizes the motors ----------------------


def test_settle_to_rest_stops_early_once_at_rest_and_never_reenergizes(
        motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        dist_target, t_us = _drive_to_natural_completion(e)

        duty_at_completion = (
            e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))
        assert duty_at_completion != (pytest.approx(0.0), pytest.approx(0.0)), (
            "Sanity check failed: the motor must still be at the stale "
            "nonzero cruise duty the instant service_move() reports the "
            "move done -- kernel_.neutral() was only STAGED at that "
            "point. If this already reads zero, settle_to_rest()'s own "
            "first internal step would not be exercising the "
            "staged-vs-delivered gap it exists to close."
        )

        # A profile with genuine decay: still coasting well above rest
        # for the first three internal steps, then at rest on the
        # fourth -- comfortably inside the 12-step cap, so a correct
        # settle_to_rest() must stop EARLY (return 4), not run all 12.
        decel_profile = [500.0, 300.0, 120.0, 10.0]
        assert decel_profile[0] > SETTLE_REST_COUNTS_PER_S  # still coasting
        assert decel_profile[-2] > SETTLE_REST_COUNTS_PER_S  # still coasting
        assert decel_profile[-1] < SETTLE_REST_COUNTS_PER_S  # now at rest
        e.arm_settle_profile(decel_profile, start_position=dist_target,
                             start_time_us=t_us)

        steps_taken = e.settle_to_rest()
        e.disarm_settle_profile()

        assert steps_taken == len(decel_profile), (
            f"Expected settle_to_rest() to take exactly "
            f"{len(decel_profile)} internal steps (one per profile "
            f"entry, stopping the instant both wheels read at rest on "
            f"the {len(decel_profile)}th) -- got {steps_taken}. Fewer "
            "means it broke out too early (AC (b) violated: it must "
            "keep stepping while still above threshold, AC (a)); more "
            "means it kept going past the rest reading instead of "
            "breaking (AC (b) 'without over-stepping' violated)."
        )

        # Part 1 (delivered): the FakeMotor's last staged duty must now
        # be neutral -- settle_to_rest()'s first internal step is what
        # delivers the previously-staged kernel_.neutral().
        assert (e.motor_last_staged_duty(LEFT),
                e.motor_last_staged_duty(RIGHT)) == (
            pytest.approx(0.0), pytest.approx(0.0)), (
            "settle_to_rest() must still deliver the kernel's neutral to "
            "the motors (commit 3e919e5) -- the last setDuty() call "
            f"recorded was {(e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))}, "
            f"not (0.0, 0.0). The stale nonzero duty was "
            f"{duty_at_completion} the instant this call started."
        )

        # Part 2 (settled, not just stopped, and never re-energized):
        # the measured velocity must now read at rest, and it must have
        # gotten there without ANY nonzero duty being re-issued along
        # the way -- the assertion above already proves the FINAL duty
        # is zero, and because the commanded mode never changes away
        # from neutral during this call (settle_to_rest() issues no
        # kernel_.drive()/neutral() of its own), every one of its
        # internal steps re-applies the same zero duty; a nonzero
        # intermediate value could only appear here if that invariant
        # were broken.
        vl, vr = e.motor_velocity(LEFT), e.motor_velocity(RIGHT)
        assert abs(vl) <= SETTLE_REST_COUNTS_PER_S
        assert abs(vr) <= SETTLE_REST_COUNTS_PER_S


# ---- AC: the iteration cap is enforced, not merely "usually" hit early -


def test_settle_to_rest_enforces_the_iteration_cap(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)
        dist_target, t_us = _drive_to_natural_completion(e)

        # Held artificially above the rest threshold for well beyond the
        # 12-step cap -- a correct settle_to_rest() must return after
        # exactly SETTLE_CAP steps, not run indefinitely (or even one
        # step further).
        held_high_profile = [500.0] * (SETTLE_CAP + 5)
        e.arm_settle_profile(held_high_profile, start_position=dist_target,
                             start_time_us=t_us)

        steps_taken = e.settle_to_rest()
        e.disarm_settle_profile()

        assert steps_taken == SETTLE_CAP, (
            f"settle_to_rest() must stop after exactly {SETTLE_CAP} "
            f"steps when the wheels never read at rest -- got "
            f"{steps_taken}. This is the iteration CAP shims.cpp's "
            "former loop always enforced; a caller stuck coasting "
            "(a stall, a wedge, a sensor fault) must not hang tickDrive() "
            "forever waiting for a rest reading that may never come."
        )

        # Sanity: the profile fed in never actually settled on its own,
        # so the cap -- not an early break -- is what stopped this call.
        vl, vr = e.motor_velocity(LEFT), e.motor_velocity(RIGHT)
        assert abs(vl) > SETTLE_REST_COUNTS_PER_S or \
            abs(vr) > SETTLE_REST_COUNTS_PER_S, (
            "Sanity check failed: the held-high profile settled on its "
            "own within the cap, so this test is not actually proving "
            "cap enforcement -- widen held_high_profile or its values."
        )


# ---- The acceptance test that actually matters: a neutered/deleted -----
# ---- settle_to_rest() must fail a test, proven by inspection below -----
#
# This module does not itself delete settle_to_rest() (that would defeat
# the point of a standing regression test) -- see this ticket's own
# report for the red/green proof: shrinking kSettleMaxSteps to 1 (or
# short-circuiting the loop entirely) was manually verified to fail
# test_settle_to_rest_stops_early_once_at_rest_and_never_reenergizes
# above (steps_taken would read 1, not 4), and widening/removing
# kSettleMaxSteps was manually verified to fail
# test_settle_to_rest_enforces_the_iteration_cap (steps_taken would
# exceed SETTLE_CAP or the call would not return within the profile
# length). Restored afterward; both tests pass green again.
