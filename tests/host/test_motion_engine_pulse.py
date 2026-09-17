"""tests/host/test_motion_engine_pulse.py -- sprint 039 ticket 001
(SUC-001): `MotionEngine::pulseWheels()`, the raw-duty pulse primitive
the floor characterization gate (ticket 003) needs.

THE PRIMITIVE UNDER TEST: fires one bounded-amplitude, bounded-width
raw-duty pulse per wheel via the kernel's own `driveDuty()`
(`kModeRawDuty` -- already bypasses PID, the speed floor, the crawl
dither and twist-hold; E-stop and lease expiry still force neutral
through the kernel's own `controlStep()`), hard-zeros, then reports each
wheel's encoder-count delta once both wheels read at rest. Unlike every
other `MotionEngine` primitive tested elsewhere in this tree (`moveX()`/
`wheelsV()`/...), this one drives its OWN internal `kernel.step()` loop
synchronously and returns only once, at the end -- there is no per-tick
control point from Python during the call itself. Two techniques stand
in for that missing control point, both extending `fake_ports.h`'s
`FakeMotor`/`FakeSleeper` rather than re-deriving physics by hand:

  - `FakeMotor`'s new `dutyHistory` log (this ticket) -- every
    `setDuty()` call across the WHOLE `pulseWheels()` call, in order --
    proves the commanded SHAPE (N ticks of the requested duty, then a
    hard zero), which `lastStagedDuty` alone (only the MOST RECENT
    call) cannot.
  - `FakeSleeper.onSleep` (already existed, sprint 006 ticket 002) via
    the new `meArmEstopAfterSleepCall()` -- lets a test trigger a REAL
    `kernel.estop()` PARTWAY through the internal loop, proving E-stop
    forces neutral for the REMAINING ticks even though the loop keeps
    re-arming `driveDuty()` every iteration.

Run with::

    uv run pytest tests/host/test_motion_engine_pulse.py
"""

import pytest


LEFT = 0
RIGHT = 1

STATUS_OK = 0


class Engine:
    """Thin ctypes wrapper, same shape as the other motion_engine test
    files' own Engine (test_motion_engine_reductions.py's is the
    canonical version) -- trimmed to what this file's tests need, plus
    this ticket's own pulse/duty-history/mid-call-estop surface."""

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

    def begin(self):
        return self._lib.meBegin(self._handle)

    def kernel_estop(self):
        self._lib.meKernelEstop(self._handle)

    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def arm_motor_position(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    # ---- move engine (only used by the "clears any in-flight move"
    # test) ----
    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def is_driving(self):
        return bool(self._lib.meIsDriving(self._handle))

    # ---- the pulse primitive under test ----
    def pulse_wheels(self, amp_left, amp_right, width_ticks):
        self._lib.mePulseWheels(self._handle, amp_left, amp_right,
                                width_ticks)

    def pulse_left_counts(self):
        return self._lib.mePulseLeftCounts(self._handle)

    def pulse_right_counts(self):
        return self._lib.mePulseRightCounts(self._handle)

    # ---- FakeMotor duty-history readback ----
    def motor_duty_history(self, side):
        count = self._lib.meMotorDutyHistoryCount(self._handle, side)
        return [self._lib.meMotorDutyHistoryAt(self._handle, side, i)
                for i in range(count)]

    def clear_duty_history(self, side):
        self._lib.meMotorClearDutyHistory(self._handle, side)

    # ---- mid-call E-stop injection ----
    def arm_estop_after_sleep_call(self, call_number):
        self._lib.meArmEstopAfterSleepCall(self._handle, call_number)

    def disarm_estop_after_sleep_call(self):
        self._lib.meDisarmEstopAfterSleepCall(self._handle)


def _ready(e, max_duty=100.0):
    e.set_max_duty(max_duty)
    assert e.begin() == STATUS_OK
    e.clear_duty_history(LEFT)
    e.clear_duty_history(RIGHT)


# ---- AC: fires the exact commanded shape, then hard-zeros -----------------


def test_pulse_wheels_drives_exact_duty_shape_then_hard_zeros(motion_lib):
    """widthTicks=2 at amp_left=25%/amp_right=-40% (maxDuty=100, so the
    rail never clips): duty history must show EXACTLY two ticks of the
    requested (clamped-to-rail) duty per wheel, then a hard zero --
    delivered by settleToRest()'s own first internal step, which this
    unarmed-motor setup settles in exactly one iteration (velocity reads
    0 from the very first check, since nothing ever arms a nonzero
    encoder movement)."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.pulse_wheels(25.0, -40.0, 2)

        left = e.motor_duty_history(LEFT)
        right = e.motor_duty_history(RIGHT)

        assert left == pytest.approx([0.25, 0.25, 0.0])
        assert right == pytest.approx([-0.40, -0.40, 0.0])


def test_pulse_wheels_amplitude_scales_linearly_with_percent(motion_lib):
    """A different amplitude produces a proportionally different staged
    duty -- pins driveDuty()'s own `duty * 0.01f` percent-to-fraction
    scale is what this primitive relies on, not a hidden rescale of its
    own."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.pulse_wheels(15.0, 15.0, 1)

        assert e.motor_duty_history(LEFT) == pytest.approx([0.15, 0.0])
        assert e.motor_duty_history(RIGHT) == pytest.approx([0.15, 0.0])


def test_pulse_wheels_nonpositive_width_ticks_is_a_defensive_noop(motion_lib):
    """widthTicks <= 0 fires no pulse at all -- still hard-zeros and
    settles (this method's own header comment, motion_engine.h): the
    ONLY duty ever staged is the single settle-delivered zero."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.pulse_wheels(25.0, 25.0, 0)
        assert e.motor_duty_history(LEFT) == pytest.approx([0.0])
        assert e.motor_duty_history(RIGHT) == pytest.approx([0.0])

        e.clear_duty_history(LEFT)
        e.clear_duty_history(RIGHT)
        e.pulse_wheels(25.0, 25.0, -3)
        assert e.motor_duty_history(LEFT) == pytest.approx([0.0])
        assert e.motor_duty_history(RIGHT) == pytest.approx([0.0])


# ---- AC: reports each wheel's encoder-count delta, matching the fake ------
# ---- motor's simulated encoder movement -----------------------------------


def test_pulse_wheels_reports_delta_matching_simulated_encoder_movement(
        motion_lib):
    """The LEFT motor's encoder is armed to a single fixed
    (position, sample_time) pair BEFORE firing -- fake_ports.h's own
    "armed-then-committed, frozen once left un-rearmed" contract (see
    motion_engine_shim.cpp's meArmSettleProfile() comment for the same
    technique): pulseWheels()'s own internal kernel.step() loop lands on
    it on its very FIRST step, then reads it back unchanged (velocity 0)
    for every step after, including every settleToRest() iteration -- a
    fully deterministic final delta with no duty-to-position physics
    model needed. The RIGHT motor is left entirely unarmed (frozen at
    the kernel's own start-of-day 0), so its own delta comes back 0,
    proving the two wheels are measured independently."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.arm_motor_position(LEFT, 500.0, sample_time_us=1000)

        e.pulse_wheels(25.0, 25.0, 3)

        assert e.pulse_left_counts() == pytest.approx(500.0)
        assert e.pulse_right_counts() == pytest.approx(0.0)


def test_pulse_wheels_delta_is_measured_across_the_whole_call_not_from_a_stale_origin(
        motion_lib):
    """A SECOND pulse's reported delta is relative to where THIS call
    started, not to the kernel's absolute zero -- i.e. the primitive
    reads its own before/after Output rather than assuming positionLeft/
    Right start at 0 every time."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.arm_motor_position(LEFT, 300.0, sample_time_us=1000)
        e.pulse_wheels(25.0, 25.0, 1)
        assert e.pulse_left_counts() == pytest.approx(300.0)

        e.clear_duty_history(LEFT)
        e.arm_motor_position(LEFT, 550.0, sample_time_us=2000)
        e.pulse_wheels(25.0, 25.0, 1)
        assert e.pulse_left_counts() == pytest.approx(250.0)  # 550 - 300


# ---- AC: clears any in-flight move-engine command first -------------------


def test_pulse_wheels_clears_any_in_flight_move_engine_command(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        e.move_x(200.0, 0.0, 150.0, 5000)
        assert e.is_move_active()

        e.pulse_wheels(25.0, 25.0, 1)

        assert not e.is_move_active()
        assert not e.is_driving()


# ---- AC: E-stop still forces neutral during a pulse ------------------------


def test_pulse_wheels_estop_before_prevents_any_nonzero_duty(motion_lib):
    """An E-stop already latched BEFORE the call: driveDuty()'s own
    checkCommandable() gate (src/core/diffdrive.cpp) refuses every
    single re-armed command this loop issues, so the kernel's commanded
    mode never leaves neutral -- every tick's own controlStep() stages
    zero. Nothing physically moves (no position ever armed), so the
    reported delta is (0, 0) too."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.kernel_estop()

        e.pulse_wheels(25.0, 25.0, 3)

        assert e.motor_duty_history(LEFT) == pytest.approx([0.0, 0.0, 0.0, 0.0])
        assert e.motor_duty_history(RIGHT) == pytest.approx([0.0, 0.0, 0.0, 0.0])
        assert e.pulse_left_counts() == pytest.approx(0.0)
        assert e.pulse_right_counts() == pytest.approx(0.0)


def test_pulse_wheels_estop_mid_pulse_forces_neutral_for_remaining_ticks(
        motion_lib):
    """An E-stop that lands PARTWAY through the internal loop: the first
    tick, already committed before the estop lands, keeps its commanded
    duty; every tick from the estop onward -- including ticks this
    primitive's own loop keeps re-arming driveDuty() for -- reads
    kernel.output().estopped and is forced neutral by the KERNEL's own
    controlStep(), not by any special-casing in pulseWheels() itself.
    callNumber=2 lands the estop right after tick 1's own two settle
    sleeps (step() calls sleepMillis() exactly twice per step,
    fake_ports.h), so tick 1 is unaffected and ticks 2/3 are not."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.arm_estop_after_sleep_call(2)
        e.pulse_wheels(25.0, 25.0, 3)
        e.disarm_estop_after_sleep_call()

        left = e.motor_duty_history(LEFT)
        assert left[0] == pytest.approx(0.25), (
            "tick 1 lands BEFORE the estop takes effect (mid-tick-1 "
            f"sleep) -- expected the commanded 0.25, got {left[0]}")
        assert left[1:] == pytest.approx([0.0] * (len(left) - 1)), (
            "every tick from the estop onward (including the settle "
            f"tail) must be forced neutral -- got {left}")
        assert e.pulse_left_counts() == pytest.approx(0.0)
        assert e.pulse_right_counts() == pytest.approx(0.0)
