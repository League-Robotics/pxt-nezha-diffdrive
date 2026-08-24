"""tests/host/test_continuous_drive_command_looks_active.py -- sprint 007
ticket 002: closes R-10/API-01 (code review 2026-08-23, the review's top
API finding) and clasi/issues/drivetick-contract-broken-idiom.md.

THE BUG: `tickDrive()` (`src/shims.cpp`) used to `return moveActive;` --
raw post-`serviceMove()` move-engine state. `setWheelSpeeds()`/
`driveTwist()` (backed by `MotionEngine::wheelsV()`, `motion_engine.cpp`)
call `cancelMove()` BEFORE ever touching the kernel, so after either of
those commands there is never a move-engine move in flight. The
documented continuous-drive idiom

    diffDrive.setWheelSpeeds(15, 15)
    while (diffDrive.driveTick()) { }

therefore exited on its very first iteration -- `moveActive` read
`false` immediately -- and the starvation watchdog stopped the robot
~150 ms later. Every documentation site (README x2, specification.md
§4.2, usecases.md UC-002 step 4) prescribed exactly this idiom;
`test/testrig.ts` quietly used a different, working pattern (a bare
`diffDrive.driveTick()` inside `basic.forever()`, ignoring the return
value) instead.

THE FIX changes `tickDrive()`'s final line to
`return commandLooksActive(r);` -- a helper sprint 006 already added
(and already proved correct in production) for the starvation watchdog:

    static bool commandLooksActive(const Rig& r) {
      if (r.engine.isMoveActive()) return true;
      const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
      return out.appliedDutyLeft != 0.0f || out.appliedDutyRight != 0.0f;
    }

"is anything still commanding the wheels" -- a move-engine move in
flight, OR nonzero applied duty -- is exactly what a continuous-mode
command needs, and it is the return value `tickDrive()` now reports.

WHAT THIS FILE CANNOT PROVE (read before "simplifying" this file):
`commandLooksActive()` and `tickDrive()` both live in `src/shims.cpp`,
which includes `pxt.h` (CODAL/PXT platform types) and cannot be
host-compiled at all -- see `src/DESIGN.md` §9's "not host-testable...
bolted to Rig-local odometry" note and this test tree's own
`_SHIM_SOURCES` lists, which never include `shims.cpp`. So this file
does NOT call either function; it constructs `DifferentialDrive` +
`FakeMotor` directly (the same `Kernel`/`kernel_lib` pattern
`test_kernel_harness.py` itself uses, with NO `MotionEngine` object at
all), issues a raw `drive()` velocity command -- the exact kernel-level
primitive `wheelsV()` calls, AFTER it has already cleared the move
planner (`motion_engine.cpp`'s `cancelMove()`) -- and asserts the
kernel's own `Output.appliedDutyLeft/Right` reads nonzero once stepped.

Because this test never constructs a `MotionEngine` at all, "is a
move-engine move active" is `false` here BY CONSTRUCTION, not because
some `isMoveActive()` call was made and returned `false` -- mirroring
the real call path exactly: `wheelsV()`/`wheelsX()` always call
`cancelMove()` before ever reaching the kernel, so by the time a
continuous-mode command's effect is observable on the kernel, no
move-engine move can be in flight. Combined with the nonzero-duty
assertion below, this reproduces both disjuncts of
`commandLooksActive()`'s condition for a continuous-mode command,
proving the CONCEPT `tickDrive()`'s new return expression depends on --
not the literal C++ text, which only a flashed hex and a bench read
prove (see this ticket's C++11 Gate Coverage and the sprint's own
bench-checkpoint ticket).

A companion test below proves the OTHER side of the same condition:
after a `neutral()` command lands (mirroring `stop()`/`emergencyStop()`),
applied duty returns to zero and the mirrored condition reads `false` --
so the documented `while (diffDrive.driveTick())` loop still ends when
a student actually stops the robot, not just when review changes go in.

Run with::

    uv run pytest tests/host/test_continuous_drive_command_looks_active.py
"""

import pytest

from test_kernel_harness import (  # noqa: F401 -- kernel_lib re-exported as a fixture
    LEFT,
    RIGHT,
    STATUS_OK,
    Kernel,
    kernel_lib,
)


class CommandLooksActiveKernel(Kernel):
    """test_kernel_harness.Kernel plus the one pre-existing kernel_shim.cpp
    export (`kdOutAppliedDutyLeft`/`Right`, already bound by the base
    class's own `_bind()`) this file needs and the base class does not
    itself wrap yet -- same minimal-subclass convention
    `test_cross_fiber_stop_settle_window.py`'s `StopWindowKernel` and
    `test_continuous_mode_odometry.py`'s `CircleKernel` already
    established for this test tree."""

    def out_applied_duty(self, side):
        if side == LEFT:
            return self._lib.kdOutAppliedDutyLeft(self._handle)
        return self._lib.kdOutAppliedDutyRight(self._handle)


def _command_looks_active(k):
    """Mirrors shims.cpp's `commandLooksActive(const Rig&)` exactly,
    minus the move-engine disjunct -- which this test proves `false` by
    construction (see module docstring) rather than by calling anything,
    since no `MotionEngine` object exists anywhere in this file."""
    move_engine_move_active = False  # by construction -- see docstring
    return (
        move_engine_move_active
        or k.out_applied_duty(LEFT) != 0.0
        or k.out_applied_duty(RIGHT) != 0.0
    )


def test_continuous_mode_drive_leaves_command_looks_active_true(kernel_lib):
    """The positive case (SUC-002's main flow): a raw, continuous-mode
    `drive()` velocity command -- what `wheelsV()` calls after clearing
    the move planner -- leaves the kernel's `Output.appliedDutyLeft/
    Right` nonzero once stepped, with no move-engine move ever having
    existed. This is exactly the state that makes `commandLooksActive()`
    -- and so `tickDrive()`'s new return value -- read `true`, which is
    what keeps the documented `while (diffDrive.driveTick())` loop
    running instead of exiting on its first iteration.
    """
    with CommandLooksActiveKernel(kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(1000.0)
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()  # baseline sample -- velocity stays 0 after this one

        # The kernel-level primitive wheelsV() calls after cancelMove()
        # -- no MotionEngine object exists in this file, so there is
        # nothing here that could set a move-engine move active.
        assert k.drive(500.0, 0.0, 5000) == STATUS_OK

        next_us = base_us + 100_000
        k.set_clock(next_us)
        k.arm_motor_sample(LEFT, position=50.0, sample_time_us=next_us)
        k.arm_motor_sample(RIGHT, position=50.0, sample_time_us=next_us)
        k.step()  # lands the nonzero commanded duty

        assert k.out_applied_duty(LEFT) != 0.0 or k.out_applied_duty(RIGHT) != 0.0, (
            "Sanity check failed: the kernel's own applied duty is zero "
            "right after a nonzero continuous-mode drive() + step() -- "
            "this test cannot prove commandLooksActive()'s condition "
            "without a genuinely nonzero applied duty to observe."
        )
        assert _command_looks_active(k), (
            "commandLooksActive()'s condition must read true for a "
            "continuous-mode command with no move-engine move active -- "
            "this is the exact condition tickDrive()'s new "
            "`return commandLooksActive(r);` depends on to keep the "
            "documented `while (diffDrive.driveTick())` idiom from "
            "exiting on its first iteration (R-10/API-01)."
        )


def test_neutral_after_continuous_drive_leaves_command_looks_active_false(kernel_lib):
    """The negative case: once a stop actually lands (neutral() + a
    step() to deliver it, mirroring stop()/emergencyStop()'s own
    deliverStopNow() path), applied duty returns to zero and the
    mirrored condition reads false again -- so the fix does not turn the
    documented tick loop into one that never exits. Pins the OTHER half
    of the contract this ticket changes, not just the half the bug
    report focused on.
    """
    with CommandLooksActiveKernel(kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(1000.0)
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()

        assert k.drive(500.0, 0.0, 5000) == STATUS_OK
        next_us = base_us + 100_000
        k.set_clock(next_us)
        k.arm_motor_sample(LEFT, position=50.0, sample_time_us=next_us)
        k.arm_motor_sample(RIGHT, position=50.0, sample_time_us=next_us)
        k.step()
        assert _command_looks_active(k), (
            "Setup sanity check: the command must look active before "
            "the stop, or this test cannot distinguish 'the stop "
            "cleared it' from 'it was never active'."
        )

        k.neutral()
        third_us = next_us + 100_000
        k.set_clock(third_us)
        k.arm_motor_sample(LEFT, position=100.0, sample_time_us=third_us)
        k.arm_motor_sample(RIGHT, position=100.0, sample_time_us=third_us)
        k.step()  # delivers the staged neutral to the motor

        assert k.out_applied_duty(LEFT) == pytest.approx(0.0)
        assert k.out_applied_duty(RIGHT) == pytest.approx(0.0)
        assert not _command_looks_active(k), (
            "Once a stop actually lands, commandLooksActive()'s "
            "condition must read false again -- the fix must not turn "
            "the documented `while (diffDrive.driveTick())` loop into "
            "one that never exits."
        )
