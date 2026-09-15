"""tests/host/test_status_active_after_soft_stop.py -- sprint 039
ticket 002: closes status-active-stays-1-after-a-soft-stop.md.

THE BUG: `WireAdapter::status()`'s `active` bit (`src/comms/
wire_adapter.cpp`) is `ready && !estopped && !leaseExpired &&
!stallHalted && (velocityLeft != 0 || velocityRight != 0)`, reading
straight off the kernel's last-published `Output`. `Rig::softStop()`
(`src/shims.cpp`) -- the one soft stop every explicit stop path shares
(`stopAll()`/the wire `STOP` verb, `endMove()`, the starvation
watchdog) -- clears the move engine, stages `kernel.neutral()`, and
writes a port-level zero DIRECTLY to the motors (bypassing the kernel's
own stage/tick split, R-08/BLK-01's own fix), but never steps the
kernel again. If nothing else calls `tickDrive()` afterwards -- the
common case for a `stop()` issued once the caller is done -- the
kernel's `Output.velocityLeft/Right` keeps reading whatever it was
computed as during the LAST step() before the stop, which can be a
genuinely nonzero mid-drive value, and `STATUS active` reads stuck "1"
indefinitely. MEASURED vevov 2026-09-15,
`captures/calibratel-vevov-20260915/bench-log.md` run 9: a sequenced
`STOP now`, then three STATUS reads several seconds apart, all read
`active=1` with `cyc` frozen at 2901.

THE FIX (this ticket): `Rig::softStop()`'s not-`busGuard`-held branch
now calls `engine.settleToRest()` right after the port-level zero write
(bracketed in `busGuard.acquire()`/`release()`, the same protection
every other non-kernel I2C entry point in `shims.cpp` takes) -- the
SAME bounded, break-on-rest kernel-stepping loop `tickDrive()`'s own
`wasActive && !moveActive` branch already uses to close this exact gap
for a move's NATURAL deadline. `tickDrive()`'s staged/cross-fiber
delivery branch (`Rig::pendingStop_`) gets the identical addition. See
`src/shims.cpp`'s own comments on `Rig::softStop()` and that delivery
branch for the full reasoning.

WHAT THIS FILE CANNOT PROVE (read before "simplifying" this file):
`src/shims.cpp` includes `pxt.h` (CODAL/PXT platform types) and cannot
be host-compiled at all -- see `tests/host/README.md` and
`test_cross_fiber_stop_settle_window.py`'s own header comment for this
project's standing convention on that boundary. So this file does NOT
call `Rig::softStop()` itself; it exercises the mechanism through THREE
hand-mirrored call sequences in `motion_engine_shim.cpp`
(`meEndMoveOldStopSequence`/`meEndMoveFixedStopSequence`/
`meEndMoveSettledStopSequence`, the last one added by this ticket),
built from the same host-portable primitives `shims.cpp` composes (a
real `DiffDrive::DifferentialDrive` kernel + `diffDrive::MotionEngine`
over `FakeMotor`). `meEndMoveSettledStopSequence()` must be kept in sync
BY HAND with `Rig::softStop()`'s actual not-held call sequence -- there
is no compiler link between the two files. This file also cannot
exercise the CROSS-FIBER staged path (`Rig::pendingStop_`'s own
delivery in `tickDrive()`) at all -- there is no fiber concurrency on
this host harness for it to have (same limitation
`test_stop_move_zeros_continuous_drive.py`'s header comment notes for
its own pair of mirrors).

VERIFICATION TECHNIQUE for "genuinely nonzero, not just stale duty":
unlike `test_stop_move_zeros_continuous_drive.py` (which only needs
`motor_last_staged_duty()`, a STAGED, not measured, quantity), this
file needs the kernel's own MEASURED `Output.velocityLeft/Right` --
`STATUS active` reads exactly that, not applied duty. `FakeMotor`
position is FROZEN unless explicitly re-armed
(`test_motion_engine_settle.py`'s own header comment), so
`_drive_and_leave_coasting()` below arms two REAL, increasing
position/time pairs while a continuous `wheelsV()` hold is active, the
same "arm, then step" technique used throughout this test tree. Proving
the settled sequence actually clears that reading needs a scripted
coast-down PROFILE across `settleToRest()`'s own internal steps (same
`arm_settle_profile()`/`FakeSleeper::onSleep` technique
`test_motion_engine_settle.py` uses) -- without it, `FakeMotor` would
just keep re-committing the SAME frozen (position, sampleTime) pair on
every internal step, which `DifferentialDrive::refreshSample()`
(unchanged sampleTime) reads as "no new sample" and holds the stale
velocity forever regardless of what the fix does. A held-high profile
would therefore make even a CORRECT fix look broken; a decaying one is
what real coasting wheels look like and is what these tests use.

Run with::

    uv run pytest tests/host/test_status_active_after_soft_stop.py
"""

import ctypes

import pytest


STATUS_OK = 0

LEFT = 0
RIGHT = 1

# Large enough that every commanded speed below stays well under the
# maxDuty=100% rail -- mirrors test_motion_engine_settle.py's own
# choice, so no assertion here is secretly checking a clamped value.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# A long lease (well beyond this test's handful of ticks), mirroring
# test_stop_move_zeros_continuous_drive.py's own use of a long lease for
# the "continuous drive, never expires on its own" setup this bug
# requires.
_LONG_LEASE_MS = 60_000

_CYCLE_S = 0.024  # [s] one control cycle -- matches motion_engine.h's
                   # own DifferentialDrive::Config default cyclePeriod.

# motion_engine.h's own settleToRest() rest threshold (sprint 008
# ticket 004), restated here so a reader can compare directly against
# src/motion/motion_engine.h -- same convention
# test_motion_engine_settle.py's own SETTLE_REST_COUNTS_PER_S already
# established.
SETTLE_REST_COUNTS_PER_S = 25.0  # [counts/s] ~2 mm/s


class Engine:
    """Thin ctypes wrapper -- same shape as this test tree's other
    motion_engine test files' own Engine, trimmed to what this file's
    tests need plus the three stop-sequence mirrors."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()
        self._profile_positions = None
        self._profile_times = None

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

    def arm_motor_position(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    def motor_velocity(self, side):
        if side == LEFT:
            return self._lib.meOutVelocityLeft(self._handle)
        return self._lib.meOutVelocityRight(self._handle)

    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    # ---- the three hand-mirrored stop sequences (motion_engine_shim.cpp) --
    def end_move_old_stop_sequence(self):
        self._lib.meEndMoveOldStopSequence(self._handle)

    def end_move_fixed_stop_sequence(self):
        self._lib.meEndMoveFixedStopSequence(self._handle)

    def end_move_settled_stop_sequence(self):
        self._lib.meEndMoveSettledStopSequence(self._handle)

    # ---- settle-profile scripting (sprint 008 ticket 004's technique) ----
    def arm_settle_profile(self, velocities_counts_per_s, start_position,
                           start_time_us):
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


def _drive_and_leave_coasting(e):
    """Configure a continuous wheelsV() hold and step it to a point
    where the kernel's OWN measured velocity (Output.velocityLeft/
    Right) is honestly, genuinely nonzero -- the moment an EXTERNAL
    stop() interrupts a still-active drive. This is deliberately NOT a
    Segment/Hold reaching its own natural deadline (that gap is already
    closed by tickDrive()'s wasActive-&&-!moveActive branch, pinned by
    test_motion_engine_settle.py) -- it is the case THIS ticket's fix
    covers: a caller-issued stop while the drivetrain is still, as far
    as the kernel knows, actively commanded.

    Returns the clock timestamp [us] the last committed step() ran at.
    """
    e.set_max_duty(100.0)
    e.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert e.begin() == STATUS_OK

    t0 = 24_000
    e.arm_motor_position(LEFT, 0.0, t0)
    e.arm_motor_position(RIGHT, 0.0, t0)
    e.set_clock(t0)
    e.step()  # baseline sample -- velocity stays 0 after this one

    e.wheels_v(200.0, 200.0, _LONG_LEASE_MS)

    t1 = t0 + 24_000
    e.set_clock(t1)
    e.service_move()  # stages the hold's first command
    e.arm_motor_position(LEFT, 40.0, t1)
    e.arm_motor_position(RIGHT, 40.0, t1)
    e.step()  # lands it; velocity this tick: (40-0)/0.024 ~= 1667 counts/s

    t2 = t1 + 24_000
    e.set_clock(t2)
    e.service_move()
    e.arm_motor_position(LEFT, 90.0, t2)
    e.arm_motor_position(RIGHT, 90.0, t2)
    e.step()  # velocity this tick: (90-40)/0.024 ~= 2083 counts/s

    assert e.motor_last_staged_duty(LEFT) != pytest.approx(0.0), (
        "Sanity check failed: the motor must still be actively "
        "commanded before the stop sequence runs, or this test cannot "
        "distinguish 'the stop worked' from 'there was nothing to "
        "stop'."
    )
    assert e.motor_last_staged_duty(RIGHT) != pytest.approx(0.0)
    assert abs(e.motor_velocity(LEFT)) > SETTLE_REST_COUNTS_PER_S, (
        "Sanity check failed: the kernel's own measured velocity must "
        "be genuinely, honestly above the rest threshold before the "
        "stop sequence runs, or this test cannot prove the fix cleared "
        "a REAL stale reading rather than one that was already at "
        "rest."
    )
    assert abs(e.motor_velocity(RIGHT)) > SETTLE_REST_COUNTS_PER_S
    return t2


# ---- AC: STATUS active is accurate after a stop (SUC-003) --------------


def test_old_stop_sequence_leaves_measured_velocity_stale(motion_lib):
    """Regression pin, PRE-039-002 behavior: the port write alone zeros
    the MOTORS but the kernel is never stepped again, so Output.
    velocityLeft/Right -- what STATUS active actually reads -- keeps
    reporting the mid-drive value forever. This is the exact defect
    MEASURED in captures/calibratel-vevov-20260915/bench-log.md run 9
    (STATUS active=1, cyc frozen, across three reads several seconds
    apart)."""
    with Engine(motion_lib) as e:
        _drive_and_leave_coasting(e)
        stale_velocity = e.motor_velocity(LEFT)

        e.end_move_old_stop_sequence()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0), (
            "The port write itself must still land immediately -- this "
            "test is about the STALE VELOCITY reading, not the duty "
            "write, which R-08/BLK-01 already fixed."
        )
        assert e.motor_velocity(LEFT) == pytest.approx(stale_velocity), (
            "This is the bug: nothing stepped the kernel again after "
            "the stop, so its own measured velocity -- what STATUS "
            "active reads -- is unchanged from the last mid-drive "
            f"reading ({stale_velocity} counts/s), not zero."
        )
        assert e.motor_velocity(RIGHT) == pytest.approx(stale_velocity)


def test_fixed_stop_sequence_without_settle_also_leaves_velocity_stale(
        motion_lib):
    """Same regression, through the sequence that already fixed the
    DIFFERENT bug test_stop_move_zeros_continuous_drive.py pins (adding
    kernel.neutral() so the commanded MODE is disarmed, not just the
    port). That fix has nothing to do with the STATUS staleness bug
    this file is about -- kernel.neutral() only STAGES a change; no
    step() runs to publish it -- so the stale velocity reading survives
    here too, proving this file's fix (settleToRest()) is closing a
    genuinely separate gap, not re-proving the older one."""
    with Engine(motion_lib) as e:
        _drive_and_leave_coasting(e)
        stale_velocity = e.motor_velocity(LEFT)

        e.end_move_fixed_stop_sequence()

        assert e.motor_velocity(LEFT) == pytest.approx(stale_velocity)
        assert e.motor_velocity(RIGHT) == pytest.approx(stale_velocity)


def test_settled_stop_sequence_clears_measured_velocity_promptly(motion_lib):
    """THE FIX: the settled sequence (Rig::softStop() as of this
    ticket) must leave both the duty AND the kernel's own measured
    velocity at rest by the time it returns -- no second caller, no
    later tickDrive(), required. A genuinely decaying coast-down
    profile is scripted across settleToRest()'s own internal steps (see
    this file's header comment on why a profile is required at all)."""
    with Engine(motion_lib) as e:
        t2 = _drive_and_leave_coasting(e)

        # Coasts down to rest within 4 of settleToRest()'s 12-step cap
        # (test_motion_engine_settle.py's own SETTLE_CAP) -- comfortably
        # inside budget, so a correct fix clears the reading well before
        # the cap is ever a factor.
        decel_profile = [900.0, 400.0, 120.0, 10.0]
        assert decel_profile[0] > SETTLE_REST_COUNTS_PER_S
        assert decel_profile[-1] < SETTLE_REST_COUNTS_PER_S
        e.arm_settle_profile(decel_profile, start_position=90.0,
                             start_time_us=t2)

        e.end_move_settled_stop_sequence()
        e.disarm_settle_profile()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0), (
            "The port write must still land -- the settle addition "
            "must not weaken or bypass R-08/BLK-01's own port-level "
            "zero."
        )
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
        assert abs(e.motor_velocity(LEFT)) <= SETTLE_REST_COUNTS_PER_S, (
            "This is the fix under test: STATUS active reads out."
            "velocityLeft/Right != 0 (wire_adapter.cpp) -- after the "
            "settled stop sequence, that reading must be at rest, not "
            "the stale mid-drive value the two tests above pin as the "
            "bug."
        )
        assert abs(e.motor_velocity(RIGHT)) <= SETTLE_REST_COUNTS_PER_S


def test_settled_stop_sequence_never_reenergizes_the_motors(motion_lib):
    """Same guard test_motion_engine_settle.py's own settle test makes
    for the natural-deadline path: settleToRest()'s internal steps must
    never re-issue a nonzero duty on the way to a rest reading -- the
    commanded mode is neutral for the whole call (kernel.neutral() ran
    before it), so every internal step re-applies the same zero."""
    with Engine(motion_lib) as e:
        t2 = _drive_and_leave_coasting(e)
        decel_profile = [900.0, 400.0, 120.0, 10.0]
        e.arm_settle_profile(decel_profile, start_position=90.0,
                             start_time_us=t2)

        e.end_move_settled_stop_sequence()
        e.disarm_settle_profile()

        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
