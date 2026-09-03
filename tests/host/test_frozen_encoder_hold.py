"""tests/host/test_frozen_encoder_hold.py -- host coverage for the
platform-layer half of the frozen-encoder-read fix
(`src/platform/nezha_port.cpp::collect()`).

THE BUG: MEASURED gopiv 2026-09-01,
captures/gopiv-profile-sweep-20260901/tour_tight.json frames 185-191: a
SUCCESSFUL encoder read whose raw counts matched the previous tick's
exactly, while the wheel was under active drive, used to advance
`sampleTimeUs_` anyway (`i2cf` unmoved on that specific tick, since the
success branch stamped unconditionally). `DifferentialDrive::
refreshSample()` (src/core/diffdrive.cpp, unmodified by this fix) then
computed an honestly-derived-but-wrong velocity of 0 from the unchanged
position over the now-nonzero interval, and the velocity PID chased
that phantom error toward the duty rail (duty stepped 3300->4500 on
real hardware; the wheel overshot to 420 mm/s).

THE FIX (`NezhaMotorPort::collect()`) withholds the fresh
`sampleTimeUs_` stamp on that specific case -- raw counts unchanged
AND the wheel driven -- exactly mirroring the read-FAILURE branch's own
pre-existing contract ("sampleTimeUs_ HOLDS -- age grows honestly").

WHAT THIS FILE CANNOT PROVE: `nezha_port.{h,cpp}` include `pxt.h`
(CODAL/PXT platform types) and cannot be host-compiled at all (see
`tests/host/test_cxx11_syntax_gate.py`'s own exclusion list), so this
file never calls `NezhaMotorPort::collect()` itself. Instead it drives
the REAL kernel (`DiffDrive::DifferentialDrive`, via kernel_shim.cpp's
FakeMotor) through a scripted encoder stream that reports EXACTLY the
contract the fixed `collect()` now produces for this case --
`sampleTime()` withheld (unchanged) on a tick whose `position()` is
also unchanged -- and shows the kernel's existing, untouched
`refreshSample()` gate holds the prior velocity instead of manufacturing
a zero, so a proportional-gain PID does not react and step duty toward
the rail. A second test scripts the OLD, unfixed contract (`sampleTime`
advancing despite the unchanged position) as a methodology check: it
reproduces the duty spike this fix removes, proving the first test's
"holds" assertion is not vacuous. The platform-side half of the fix --
that `NezhaMotorPort::collect()` actually produces the withheld
contract on real hardware -- is reviewed in source and confirmed by the
ticket's own hardware-acceptance capture.

Run with::

    uv run pytest tests/host/test_frozen_encoder_hold.py
"""

import pytest

from test_kernel_harness import (  # noqa: F401 -- kernel_lib re-exported as a fixture
    LEFT,
    RIGHT,
    STATUS_OK,
    Kernel,
    kernel_lib,
)

_MAX_DUTY = 100.0              # [%] duty rail (rail fraction = 1.0)
_FULL_DUTY_VELOCITY = 1000.0   # [counts/s] wheel rate at 100% duty
_COMMANDED = 500.0             # [counts/s] commanded wheel speed
_KP = 0.2                      # proportional gain; iMax stays 0 (I disabled
                                # by default, matching motion_engine_shim's
                                # own "pure feedforward" baseline config)
_INTERVAL_S = 0.024            # [s] one kernel cycle (the firmware's own
                                # default Config::cyclePeriod cadence)
_STEP_US = int(_INTERVAL_S * 1e6)
_SETTLE_TICKS = 5              # ticks of exactly-matching samples (err == 0
                                # by construction) to let duty converge
_EXPECTED_SETTLED_DUTY = 0.5   # commanded / fullDutyVelocity, with err == 0
_TOL = 1e-3


class _EncoderKernel(Kernel):
    """Adds out_velocity_left readback -- kdOutVelocityLeft is already
    bound by the base class's own _bind() (test_kernel_harness.py), same
    pattern test_continuous_mode_odometry.py's CircleKernel uses for
    kdOutPositionLeft/Right."""

    def out_velocity_left(self):
        return self._lib.kdOutVelocityLeft(self._handle)


def _begin_and_settle(k, base_us):
    """Configures the kernel, arms a baseline sample, issues drive(),
    then feeds _SETTLE_TICKS of exactly-matching encoder samples (a pure
    open-loop position script, independent of the kernel's own duty
    output) so the commanded duty converges to the steady-state
    feedforward value before a test starts scripting the frozen tick.
    Returns (now_us, position) at the end of settling."""
    k.set_max_duty(_MAX_DUTY)
    k.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
    k.set_kp(_KP)
    assert k.begin() == STATUS_OK

    k.set_clock(base_us)
    k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
    k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
    k.step()  # baseline sample -- velocity stays 0 until a second one

    assert k.drive(_COMMANDED, 0.0, 5000) == STATUS_OK

    now_us = base_us
    pos = 0.0
    for _ in range(_SETTLE_TICKS):
        now_us += _STEP_US
        pos += _COMMANDED * _INTERVAL_S
        k.set_clock(now_us)
        k.arm_motor_sample(LEFT, position=pos, sample_time_us=now_us)
        k.arm_motor_sample(RIGHT, position=pos, sample_time_us=now_us)
        k.step()

    duty = k.motor_last_staged_duty(LEFT)
    assert duty == pytest.approx(_EXPECTED_SETTLED_DUTY, abs=_TOL), (
        "settling did not converge to the expected feedforward duty -- "
        "fixture assumption broken, not the fix under test"
    )
    return now_us, pos


def test_frozen_but_acked_read_holds_prior_velocity_not_zero(kernel_lib):
    """The FIXED contract: sampleTime() withheld on a tick whose raw
    position is unchanged under active drive. Acceptance criterion:
    commanded duty must not step toward the rail on the frozen tick or
    the tick immediately after, and the held tick must still count
    toward i2cFaultCount_ -- core/diffdrive.cpp increments it whenever
    either wheel's sampleTime fails to advance across a step(); this
    fix's whole platform-layer value is that NezhaMotorPort now triggers
    that same, already-existing counter for this case too (previously it
    did not, since the success branch advanced the stamp unconditionally)."""
    with _EncoderKernel(kernel_lib) as k:
        now_us, pos = _begin_and_settle(k, base_us=1_000_000)
        assert k.out_i2c_fault_count == 0

        # Frozen-but-acked tick: LEFT's raw position AND sampleTime both
        # stay exactly where they were -- the withheld-stamp contract
        # the fixed collect() now produces. RIGHT keeps advancing
        # normally (an asymmetric, single-wheel wedge, the realistic
        # shape).
        frozen_us = now_us + _STEP_US
        k.set_clock(frozen_us)
        k.arm_motor_sample(LEFT, position=pos, sample_time_us=now_us)  # UNCHANGED
        k.arm_motor_sample(RIGHT, position=pos + _COMMANDED * _INTERVAL_S,
                            sample_time_us=frozen_us)
        k.step()
        duty_frozen = k.motor_last_staged_duty(LEFT)
        assert duty_frozen == pytest.approx(_EXPECTED_SETTLED_DUTY, abs=_TOL)
        assert k.out_i2c_fault_count == 1, (
            "the held tick must still count toward i2cFaultCount_ -- the "
            "failure stays visible in telemetry, not smoothed away"
        )

        # The tick immediately after: a fresh, good sample resumes,
        # reporting the true accumulated distance over the outage.
        after_us = frozen_us + _STEP_US
        after_pos = pos + _COMMANDED * (2 * _INTERVAL_S)
        k.set_clock(after_us)
        k.arm_motor_sample(LEFT, position=after_pos, sample_time_us=after_us)
        k.arm_motor_sample(RIGHT, position=after_pos, sample_time_us=after_us)
        k.step()
        duty_after = k.motor_last_staged_duty(LEFT)

        assert duty_frozen < _MAX_DUTY * 0.01 - 0.05, (
            "duty stepped toward the rail on the frozen tick"
        )
        assert duty_after == pytest.approx(_EXPECTED_SETTLED_DUTY, abs=_TOL), (
            "duty stepped toward the rail on the tick immediately after "
            "the frozen one"
        )


def test_unfixed_contract_would_have_spiked_duty_toward_rail(kernel_lib):
    """Methodology check, not a defect this ticket introduces: scripts
    the OLD, pre-fix contract (sampleTime ADVANCES even though the raw
    position is unchanged -- what collect()'s success branch did
    unconditionally before this fix) and confirms it reproduces the
    measured symptom -- a real duty step toward the rail on the tick
    after the frozen one, with i2cFaultCount_ NOT incremented for the
    frozen tick itself (matching the issue's own citation: "i2cf unmoved
    on that specific tick"). This proves the fixed-contract test above
    is not vacuously passing regardless of what gets scripted."""
    with _EncoderKernel(kernel_lib) as k:
        now_us, pos = _begin_and_settle(k, base_us=1_000_000)

        # Same frozen POSITION, but sampleTime ADVANCES anyway -- the
        # bug this ticket fixes.
        stale_us = now_us + _STEP_US
        k.set_clock(stale_us)
        k.arm_motor_sample(LEFT, position=pos, sample_time_us=stale_us)  # ADVANCED
        k.arm_motor_sample(RIGHT, position=pos + _COMMANDED * _INTERVAL_S,
                            sample_time_us=stale_us)
        k.step()
        assert k.out_i2c_fault_count == 0, (
            "pre-fix: sampleTime advanced, so this tick does not (yet) "
            "count as a fault -- this is exactly the gap the fix closes"
        )
        assert k.out_velocity_left() == pytest.approx(0.0, abs=_TOL), (
            "pre-fix: an unchanged position over a now-nonzero interval "
            "computes an honest-but-wrong velocity of 0"
        )

        after_us = stale_us + _STEP_US
        k.set_clock(after_us)
        k.arm_motor_sample(LEFT, position=pos + _COMMANDED * _INTERVAL_S,
                            sample_time_us=after_us)
        k.arm_motor_sample(RIGHT, position=pos + _COMMANDED * (2 * _INTERVAL_S),
                            sample_time_us=after_us)
        k.step()
        duty_after = k.motor_last_staged_duty(LEFT)
        assert duty_after > _EXPECTED_SETTLED_DUTY + 0.05, (
            "expected the phantom zero-velocity error to step duty "
            "toward the rail on the tick after the frozen one -- if this "
            "fails, the fixture no longer reproduces the bug and the "
            "'fixed' test above may be vacuous"
        )


def test_idle_undriven_wheel_at_rest_does_not_tick_i2c_fault(kernel_lib):
    """A wheel legitimately at rest (zero applied duty, unchanged
    position across many ticks) must keep reporting velocity 0 every
    tick, AND must not tick i2cFaultCount_ -- the fix must not defeat a
    genuine stop, and i2c-fault-count-climbs-on-idle-bus is a separate,
    out-of-scope issue this fix does not touch either direction. An
    undriven wheel's appliedDuty() is 0, so the fixed collect()'s new
    "driven and unchanged" condition never applies here -- sampleTime
    advances every tick exactly as it always has, and refreshSample()
    correctly computes a REAL zero from a position that is genuinely not
    moving, not a held stale one."""
    with _EncoderKernel(kernel_lib) as k:
        k.set_max_duty(_MAX_DUTY)
        k.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
        k.set_kp(_KP)
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()

        assert k.drive(0.0, 0.0, 5000) == STATUS_OK  # commanded rest

        now_us = base_us
        for _ in range(6):
            now_us += _STEP_US
            k.set_clock(now_us)
            # Position never changes -- a real stop -- but sampleTime
            # advances every tick, matching an undriven collect().
            k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
            k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
            k.step()
            assert k.out_velocity_left() == pytest.approx(0.0, abs=_TOL)
            assert k.motor_last_staged_duty(LEFT) == pytest.approx(0.0, abs=_TOL)
            assert k.out_i2c_fault_count == 0
