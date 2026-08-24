"""tests/host/test_cross_fiber_stop_settle_window.py -- sprint 006
ticket 002: closes R-08/BLK-01 (code review 2026-08-23, independently
re-derived in docs/code-review/2026-08-23/raw/verify-blocks.md).

THE BUG: `DifferentialDrive::neutral()` only STAGES a zero command
(diffdrive.cpp) -- delivery to the motors happens solely on a LATER
`step()`, and `step()`'s own duty write happens BEFORE its two
~4 ms-per-wheel encoder settle sleeps (`kSettle`). A stop or
move-completion issued from a fiber OTHER than the one currently inside
`step()`'s settle window therefore stages a neutral that is not
delivered until that `step()` returns AND another `step()` runs -- and
if the very call that staged it is what ended a `while (tickDrive())`
loop (the common case), no further `step()` ever runs until the
~100-150 ms starvation watchdog fires. That is the +9-13deg/turn,
+15-22 mm/leg overshoot class `tests/host/test_regression_post_move_
neutral.py` already pins for the IN-FIBER (move-completion-on-the-
ticking-fiber) case; this file is the CROSS-fiber sibling commit
3e919e5 did not cover.

THE FIX (`src/shims.cpp`'s `deliverStopNow()`, called from `stopAll()`,
the `endMove()` free function, and `updateMove()`'s own
wasActive-&&-!moveActive completion branch) pushes an immediate,
PORT-LEVEL zero write to both motors -- the exact primitive the
starvation watchdog already uses (`Motor::emergencyStop()`) -- alongside
the pre-existing staged `kernel.neutral()`/`engine.endMove()`. Because
`emergencyStop()` writes straight through, bypassing the kernel's
stage/tick split entirely, it does not matter WHEN inside a `step()`
the racing call lands: this file proves that even the two worst-case
timings BLK-01 identified -- squarely inside either of `step()`'s two
settle sleeps -- still deliver a zero duty by the time that SAME
`step()` returns, without any additional `step()` ever running.

WHAT THIS FILE CANNOT PROVE (read before "simplifying" this file):
`src/shims.cpp` includes `pxt.h` (CODAL/PXT platform types) and cannot
be host-compiled at all -- see `src/DESIGN.md` SS1/SS11 and this test
tree's own `_SHIM_SOURCES` lists, which never include `shims.cpp`. So
this file does NOT call `stopAll()`/`endMove()`/`updateMove()`
themselves; it exercises the KERNEL-LEVEL mechanism those functions'
`deliverStopNow()` helper is built on -- `Motor::emergencyStop()`
called directly on the same fake ports `DifferentialDrive::step()`
drives, at a scripted point inside the settle window -- which is the
only part of this fix that is host-portable. A green run here is
evidence the PRIMITIVE behaves as `deliverStopNow()` requires; it is
NOT evidence that `shims.cpp`'s three call sites compile or link for
either real embedded target (that is only ever proven by the sprint's
own flashable-hex checkpoint).

Run with::

    uv run pytest tests/host/test_cross_fiber_stop_settle_window.py
"""

import ctypes

import pytest

from test_kernel_harness import (  # noqa: F401 -- kernel_lib re-exported as a fixture
    LEFT,
    RIGHT,
    STATUS_OK,
    Kernel,
    kernel_lib,
)


def _bind_ticket_hooks(lib):
    """Attach ctypes argtypes/restype for the symbols this ticket added to
    kernel_shim.cpp -- test_kernel_harness.py's own `_bind()` (already
    run once by the `kernel_lib` fixture) does not know about these, but
    setting a ctypes function's argtypes/restype is a per-attribute,
    idempotent operation on the shared `CDLL` object, so doing it again
    here from a second test module is safe."""
    lib.kdArmCrossFiberStopOnSleepCall.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdArmCrossFiberStopOnSleepCall.restype = None
    lib.kdDisarmCrossFiberStop.argtypes = [ctypes.c_void_p]
    lib.kdDisarmCrossFiberStop.restype = None
    lib.kdOutI2cFaultCount.argtypes = [ctypes.c_void_p]
    lib.kdOutI2cFaultCount.restype = ctypes.c_uint32
    return lib


class StopWindowKernel(Kernel):
    """test_kernel_harness.Kernel plus this ticket's settle-window
    stop-delivery hook, i2cFaultCount readback, and the handful of
    existing kernel_shim.cpp exports the base class does not itself
    wrap (it wraps only what earlier tickets needed)."""

    def __init__(self, lib):
        super().__init__(_bind_ticket_hooks(lib))

    # ---- this ticket's settle-window hook ----
    def sleeper_sleep_calls(self):
        return self._lib.kdSleeperSleepCalls(self._handle)

    def arm_cross_fiber_stop(self, sleep_call_number):
        self._lib.kdArmCrossFiberStopOnSleepCall(self._handle, sleep_call_number)

    def disarm_cross_fiber_stop(self):
        self._lib.kdDisarmCrossFiberStop(self._handle)

    @property
    def out_i2c_fault_count(self):
        return self._lib.kdOutI2cFaultCount(self._handle)

    # ---- pre-existing exports the base class does not wrap yet ----
    def motor_applied_duty(self, side):
        return self._lib.kdMotorAppliedDuty(self._handle, side)

    def motor_set_collect_succeeds(self, side, succeeds):
        self._lib.kdMotorSetCollectSucceeds(self._handle, side, 1 if succeeds else 0)

    def out_applied_duty(self, side):
        if side == LEFT:
            return self._lib.kdOutAppliedDutyLeft(self._handle)
        return self._lib.kdOutAppliedDutyRight(self._handle)

    def out_position(self, side):
        if side == LEFT:
            return self._lib.kdOutPositionLeft(self._handle)
        return self._lib.kdOutPositionRight(self._handle)

    @property
    def out_estopped(self):
        return self._lib.kdOutEstopped(self._handle)


def _drive_to_nonzero_duty(k):
    """Get both FakeMotors' appliedDuty() to a known nonzero value via one
    committed drive() + step(), mirroring test_kernel_harness.py's own
    test_smoke_drive_and_step_reports_expected_duty_and_velocity setup.
    Returns the clock timestamp [us] the committing step() ran at, so a
    caller can advance the clock cleanly for its own next step()."""
    k.set_max_duty(100.0)
    k.set_full_duty_velocity(1000.0)
    assert k.begin() == STATUS_OK

    base_us = 1_000_000
    k.set_clock(base_us)
    k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
    k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
    k.step()  # baseline sample -- velocity stays 0 after this one

    assert k.drive(500.0, 0.0, 5000) == STATUS_OK

    next_us = base_us + 100_000
    k.set_clock(next_us)
    k.arm_motor_sample(LEFT, position=50.0, sample_time_us=next_us)
    k.arm_motor_sample(RIGHT, position=50.0, sample_time_us=next_us)
    k.step()  # lands the nonzero cruise duty

    assert k.motor_applied_duty(LEFT) != pytest.approx(0.0), (
        "Sanity check failed: the motor was already at zero before the "
        "interrupted step(), so this test cannot distinguish 'the stop "
        "was delivered' from 'there was never anything to stop'."
    )
    assert k.motor_applied_duty(RIGHT) != pytest.approx(0.0)
    return next_us


@pytest.mark.parametrize(
    "sleep_offset",
    [1, 2],
    ids=["lands-in-lefts-settle-sleep", "lands-in-rights-settle-sleep"],
)
def test_cross_fiber_stop_during_settle_window_zeros_duty_within_the_same_tick(
    kernel_lib, sleep_offset,
):
    """BLK-01's own worst case, scripted directly: a cross-fiber
    `Motor::emergencyStop()` call (what `shims.cpp`'s `deliverStopNow()`
    does) lands squarely inside `DifferentialDrive::step()`'s encoder
    settle window -- between `left_.requestSample()`/`left_.tick()`
    (sleep_offset=1) or between `right_.requestSample()`/`right_.tick()`
    (sleep_offset=2), FakeSleeper's own two documented positions. Unlike
    `kernel.neutral()` (which needs a LATER step() to reach the motor --
    see test_regression_post_move_neutral.py), `emergencyStop()` writes
    straight through: both FakeMotors' applied duty, and the kernel's
    own published `Output.appliedDutyLeft/Right`, must already read zero
    by the time THIS SAME step() call returns -- no second step(), no
    watchdog-scale wait.
    """
    with StopWindowKernel(kernel_lib) as k:
        next_us = _drive_to_nonzero_duty(k)

        target_sleep_call = k.sleeper_sleep_calls() + sleep_offset
        k.arm_cross_fiber_stop(target_sleep_call)

        third_us = next_us + 100_000
        k.set_clock(third_us)
        k.arm_motor_sample(LEFT, position=100.0, sample_time_us=third_us)
        k.arm_motor_sample(RIGHT, position=100.0, sample_time_us=third_us)
        k.step()  # THE interrupted tick -- no further step() follows

        assert k.motor_applied_duty(LEFT) == pytest.approx(0.0), (
            "A cross-fiber stop landing inside step()'s own settle "
            "window must still zero the motor's applied duty by the "
            "end of THIS tick -- this is exactly the race BLK-01 "
            "identified: the old kernel.neutral()-only path staged a "
            "zero that was not delivered until a step() that, in the "
            "abandoned-loop case, never ran again."
        )
        assert k.motor_applied_duty(RIGHT) == pytest.approx(0.0)
        assert k.out_applied_duty(LEFT) == pytest.approx(0.0)
        assert k.out_applied_duty(RIGHT) == pytest.approx(0.0)

        k.disarm_cross_fiber_stop()

        # The fix must stay in the same resumable "soft stop" family the
        # starvation watchdog already established -- never the kernel's
        # own estopLatch_ (that would require clearEmergencyStop() to
        # resume, a materially different UX for a plain stop/move
        # completion). Assert this directly: not latched, and a fresh
        # drive() is accepted with no refusal.
        assert k.out_estopped == 0
        assert k.drive(500.0, 0.0, 5000) == STATUS_OK


def test_cross_fiber_stop_with_corrupted_collect_holds_last_good_sample(kernel_lib):
    """Architecture-review-flagged residual risk (sprint 006's
    design/DESIGN.diff.md Migration Concerns / Risk section, and the
    ticket's own issue write-up): the new immediate port-level stop
    write shares the Nezha I2C bus with the encoder settle window --
    landing there is exactly the kind of "other I2C traffic during the
    settle window" `diffdrive.h`'s own kernel invariant warns can
    corrupt a sample. This is pre-existing exposure (the starvation
    watchdog's own port writes already do this) that this ticket makes
    MORE FREQUENT, not a new failure mode -- and it is already absorbed
    by `DifferentialDrive::refreshSample()`'s existing fault path
    (unmodified by this ticket): a failed collect holds the last-good
    sample and increments `i2cFaultCount_`, rather than being silently
    accepted as a valid new (and here, deliberately implausible)
    reading. This test proves that path still runs when a stop write
    coincides with a corrupted collect on the exact tick it fires.
    """
    with StopWindowKernel(kernel_lib) as k:
        next_us = _drive_to_nonzero_duty(k)
        position_before = k.out_position(LEFT)
        fault_count_before = k.out_i2c_fault_count

        target_sleep_call = k.sleeper_sleep_calls() + 1  # LEFT's own settle sleep
        k.arm_cross_fiber_stop(target_sleep_call)
        # Simulate the port write colliding with LEFT's select->settle->
        # read in flight (nezha_port.cpp's own "a sample destroyed by
        # interposed bus traffic" scenario), modeled at the fake-port
        # level per FakeMotor's own collectSucceeds contract (fake_ports.
        # h: "a failed collect leaves position()/sampleTime() exactly
        # where they were").
        k.motor_set_collect_succeeds(LEFT, False)

        third_us = next_us + 100_000
        k.set_clock(third_us)
        # A wildly implausible reading if it WERE accepted -- proves this
        # test is not vacuously passing because nothing changed anyway.
        k.arm_motor_sample(LEFT, position=999999.0, sample_time_us=third_us)
        k.arm_motor_sample(RIGHT, position=100.0, sample_time_us=third_us)
        k.step()

        assert k.out_i2c_fault_count == fault_count_before + 1, (
            "A corrupted collect landing in this exact window must be "
            "COUNTED (i2cFaultCount_), not silently accepted."
        )
        assert k.out_position(LEFT) == pytest.approx(position_before), (
            "A failed collect must HOLD the last-good sample -- the "
            "newly-armed (implausible) reading must never be accepted "
            "as real position just because a stop write happened to "
            "land on the bus at the same moment."
        )
        # The stop still lands in the same tick regardless of the
        # corrupted collect -- the design doc's own framing: "the robot
        # is stopping in that same tick regardless," so a stale encoder
        # reading for one cycle is low-consequence.
        assert k.motor_applied_duty(LEFT) == pytest.approx(0.0)
        assert k.motor_applied_duty(RIGHT) == pytest.approx(0.0)

        k.disarm_cross_fiber_stop()
