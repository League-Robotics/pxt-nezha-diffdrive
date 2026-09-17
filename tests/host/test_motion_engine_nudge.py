"""tests/host/test_motion_engine_nudge.py -- sprint 039 ticket 004
(SUC-002): `MotionEngine::beginNudge()`/`serviceNudge()`, the
settle-gated raw-duty pulse stepper built on ticket 001's
`pulseWheels()` primitive.

This file covers the part of the nudge stepper a plain, manually-armed
`FakeMotor` (`fake_ports.h`, via `motion_engine_shim.cpp`/conftest.py's
shared `motion_lib` fixture) can exercise directly: mutual exclusion
with `seg_`/`hold_`, E-stop forcing neutral mid-nudge, immediate
arrival, and the encoder-VELOCITY half of "pulses fire only when
settled" (via `meMotorArmPosition()`'s "armed-then-committed" technique
to plant a genuinely nonzero measured velocity in `Output`).

The AUTONOMOUS duty->position stiction-plant behavior -- the ledger
converging over several REAL pulses, the pulse budget and deadline each
terminating the loop independently, a direction flip's step-count
parity, and "a target reachable in N pulses does not take N+1" -- needs
a Motor double that integrates position across `firePulseAndSettle()`'s
own internal, synchronous `kernel.step()` loop, which `FakeMotor`
deliberately does not provide. Those live in
`test_motion_engine_nudge_stiction.py`, over its own dedicated shim
(`motion_engine_nudge_stiction_shim.cpp`) -- see that file's own header
comment for why a second shim is the right call here, not the "extend,
don't invent" default.

Run with::

    uv run pytest tests/host/test_motion_engine_nudge.py
"""

import pytest


LEFT = 0
RIGHT = 1

STATUS_OK = 0


class Engine:
    """Thin ctypes wrapper, same shape as this directory's other
    motion_engine_shim.cpp test files (test_motion_engine_pulse.py's is
    the closest sibling) -- trimmed to what this file's tests need."""

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

    def step(self):
        self._lib.meStep(self._handle)

    def kernel_estop(self):
        self._lib.meKernelEstop(self._handle)

    def out_estopped(self):
        return bool(self._lib.meOutEstopped(self._handle))

    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def arm_motor_position(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    # ---- move engine / hold (for the mutual-exclusion tests) ----
    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def is_driving(self):
        return bool(self._lib.meIsDriving(self._handle))

    # ---- the nudge stepper under test ----
    def begin_nudge(self, distance_mm, rotation_rad, timeout_ms):
        self._lib.meBeginNudge(self._handle, distance_mm, rotation_rad,
                               timeout_ms)

    def is_nudge_active(self):
        return bool(self._lib.meIsNudgeActive(self._handle))

    def nudge_pulse_count(self):
        return self._lib.meNudgePulseCount(self._handle)

    def service(self):
        return bool(self._lib.meServiceMove(self._handle))

    def nudge_max_pulses(self):
        return self._lib.meNudgeMaxPulses(self._handle)

    def nudge_amplitude(self):
        return self._lib.meNudgeAmplitude(self._handle)

    def set_nudge_amplitude(self, v):
        self._lib.meSetNudgeAmplitude(self._handle, v)

    def nudge_width_ticks(self):
        return self._lib.meNudgeWidthTicks(self._handle)

    def set_nudge_width_ticks(self, v):
        self._lib.meSetNudgeWidthTicks(self._handle, v)

    def nudge_settle_ms(self):
        return self._lib.meNudgeSettle(self._handle)

    def set_nudge_settle_ms(self, v):
        self._lib.meSetNudgeSettle(self._handle, v)

    # ---- FakeMotor duty-history readback ----
    def motor_duty_history(self, side):
        count = self._lib.meMotorDutyHistoryCount(self._handle, side)
        return [self._lib.meMotorDutyHistoryAt(self._handle, side, i)
                for i in range(count)]

    def clear_duty_history(self, side):
        self._lib.meMotorClearDutyHistory(self._handle, side)


def _ready(e, max_duty=100.0):
    e.set_max_duty(max_duty)
    assert e.begin() == STATUS_OK
    e.clear_duty_history(LEFT)
    e.clear_duty_history(RIGHT)


def _any_nonzero(history):
    return any(v != 0.0 for v in history)


# ---- AC: exactly one of seg_/hold_/nudge_ is ever live ---------------------


def test_begin_nudge_supersedes_an_in_flight_move_and_reports_active(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        e.move_x(200.0, 0.0, 150.0, 5000)
        assert e.is_move_active()
        assert not e.is_nudge_active()

        e.begin_nudge(5.0, 0.0, 5000)

        assert not e.is_move_active()
        assert e.is_nudge_active()


def test_begin_nudge_supersedes_an_in_flight_continuous_hold(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        e.wheels_v(100.0, 100.0, 5000)
        assert e.is_driving()

        e.begin_nudge(5.0, 0.0, 5000)

        # hold_ is cleared -- isDriving() (seg_/hold_ only, this ticket's
        # own header comment on why it is NOT extended to nudge_) reads
        # false even though a nudge is now in flight.
        assert not e.is_driving()
        assert e.is_nudge_active()


def test_move_x_after_a_nudge_clears_the_nudge(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        e.begin_nudge(5.0, 0.0, 5000)
        assert e.is_nudge_active()

        e.move_x(200.0, 0.0, 150.0, 5000)

        assert not e.is_nudge_active()
        assert e.is_move_active()


# ---- AC: E-stop still forces neutral mid-nudge ------------------------


def test_estop_before_begin_nudge_ends_it_on_the_first_service_call_with_no_duty(
        motion_lib):
    """kernel.estop() called directly -- never through anything
    resembling shims.cpp's own estopAll() ordering (see
    test_motion_engine_estop_and_refusal.py's identical precedent for
    why that matters: this class must not depend on an ordering it does
    not control)."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.kernel_estop()
        e.step()  # Output is a published snapshot -- estop() alone does
                  # not update it; one step() lands the latch (matches
                  # test_motion_engine_estop_and_refusal.py's own "step()
                  # is always the caller's, once per tick" contract).
        assert e.out_estopped()
        # Discard the diagnostic step() above's own neutral duty write --
        # this test is about what begin_nudge()+service() themselves
        # stage, not the setup.
        e.clear_duty_history(LEFT)
        e.clear_duty_history(RIGHT)

        e.begin_nudge(5.0, 0.0, 5000)
        assert e.is_nudge_active()

        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active()
        # serviceNudge()'s own e-stop branch returns before ever calling
        # firePulseAndSettle() -- no duty is staged AT ALL (not even a
        # hard-zero write, since that needs a further step() this test
        # never makes).
        assert e.motor_duty_history(LEFT) == []
        assert e.motor_duty_history(RIGHT) == []


def test_estop_mid_nudge_ends_it_promptly_without_a_further_pulse(motion_lib):
    """A target well outside the default arrive margin, so the ONLY way
    this nudge ends within a couple of ticks is the e-stop -- proves
    E-stop wins over "still work to do", not just over "already
    arrived"."""
    with Engine(motion_lib) as e:
        _ready(e)

        e.begin_nudge(50.0, 0.0, 30_000)
        assert e.is_nudge_active()

        e.kernel_estop()
        e.step()  # publish the latch into Output -- see the previous
                  # test's own comment on why this is needed.
        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active()


# ---- AC: pulses fire only when settled (encoder-velocity half) --------


def test_nudge_does_not_fire_while_the_wheels_still_read_moving(motion_lib):
    """Plants a genuinely nonzero MEASURED velocity via meMotorArmPosition
    ()'s "armed-then-committed" technique (two different (position,
    sampleTime) pairs across two step()s), then proves serviceNudge()
    refuses to fire while that reads back nonzero -- only firing once a
    THIRD step (unchanged position, a fresh sample stamp) brings the
    measured velocity back to 0."""
    with Engine(motion_lib) as e:
        _ready(e)

        # Establish a first sample (no velocity yet -- refreshSample()'s
        # own "everSampled" branch never computes one from a single
        # sample).
        e.arm_motor_position(LEFT, 100.0, sample_time_us=1_000)
        e.step()
        # A second, DIFFERENT sample: the kernel now computes a large,
        # genuinely nonzero velocity from the position delta across the
        # two samples.
        e.arm_motor_position(LEFT, 500.0, sample_time_us=2_000)
        e.step()

        e.begin_nudge(20.0, 0.0, 30_000)
        e.clear_duty_history(LEFT)
        e.clear_duty_history(RIGHT)

        still_active = e.service()
        assert still_active
        assert not _any_nonzero(e.motor_duty_history(LEFT)), (
            "the nudge fired while the left wheel still read a nonzero "
            "measured velocity")
        assert not _any_nonzero(e.motor_duty_history(RIGHT))

        # A third sample at the SAME position: the measured velocity
        # over this interval is 0 -- now at rest.
        e.arm_motor_position(LEFT, 500.0, sample_time_us=3_000)
        e.step()

        still_active = e.service()
        assert still_active
        assert _any_nonzero(e.motor_duty_history(LEFT)), (
            "the nudge never fired once the wheels genuinely read at rest")


# ---- AC: immediate arrival fires no pulse at all -----------------------


def test_a_target_already_inside_the_default_margin_ends_with_no_pulse(
        motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        # Default arriveDist is 1.0 mm (motion_limits.h) -- 0.05 mm is
        # comfortably inside it.
        e.begin_nudge(0.05, 0.0, 5000)
        assert e.is_nudge_active()

        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active()
        assert e.nudge_pulse_count() == 0
        assert not _any_nonzero(e.motor_duty_history(LEFT))
        assert not _any_nonzero(e.motor_duty_history(RIGHT))


def test_zero_magnitude_nudge_is_a_defensive_noop_like_beginsegment(motion_lib):
    with Engine(motion_lib) as e:
        _ready(e)

        e.begin_nudge(0.0, 0.0, 5000)

        assert not e.is_nudge_active()


# ---- config surface: amplitude/width/settle defaults and validation ---


def test_nudge_config_defaults_match_the_measured_operating_point(motion_lib):
    """MEASURED vevov 2026-09-16,
    captures/039-003-pulse-gate-20260916/notes.md -- the accepted
    (amplitude, width) operating point."""
    with Engine(motion_lib) as e:
        assert e.nudge_amplitude() == pytest.approx(15.0)
        assert e.nudge_width_ticks() == 2
        assert e.nudge_settle_ms() == pytest.approx(0.0)


def test_nudge_config_setters_validate_like_rotational_slip(motion_lib):
    with Engine(motion_lib) as e:
        e.set_nudge_amplitude(22.0)
        assert e.nudge_amplitude() == pytest.approx(22.0)
        e.set_nudge_amplitude(-5.0)  # invalid -- silently ignored
        assert e.nudge_amplitude() == pytest.approx(22.0)

        e.set_nudge_width_ticks(3)
        assert e.nudge_width_ticks() == 3
        e.set_nudge_width_ticks(0)  # invalid -- silently ignored
        assert e.nudge_width_ticks() == 3

        e.set_nudge_settle_ms(75.0)
        assert e.nudge_settle_ms() == pytest.approx(75.0)
        e.set_nudge_settle_ms(0.0)  # 0 IS legal (off)
        assert e.nudge_settle_ms() == pytest.approx(0.0)
        e.set_nudge_settle_ms(-1.0)  # invalid -- silently ignored
        assert e.nudge_settle_ms() == pytest.approx(0.0)


def test_nudge_max_pulses_is_the_conservative_forty_pulse_backstop(motion_lib):
    """Design Rationale (sprint.md): "keep it conservative, ~40 pulses
    per the issue's own suggestion"."""
    with Engine(motion_lib) as e:
        assert e.nudge_max_pulses() == 40
