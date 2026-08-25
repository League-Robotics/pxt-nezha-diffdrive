"""tests/host/test_regression_post_move_neutral.py -- locks in
commit `3e919e5`'s fix ("Root-cause move-end coast:
deliver the stop on the completing tick") against `motion_engine`'s
ported completion path.

THE BUG (3e919e5, src/shims.cpp's `tickDrive()`): `MotionEngine::
serviceMove()` ends a move by calling `kernel_.neutral()` -- but that
only STAGES a zero command into the kernel (DifferentialDrive::neutral()
just writes `command_`). The stage only reaches the MOTORS (a real
`Motor::setDuty()` call) on the kernel's NEXT `step()`. A caller of the
shape `while (tickDrive())` exits the instant `tickDrive()` reports the
move done, so that next `step()` never ran, and the wheels coasted at
the last commanded (nonzero) duty until the starvation watchdog's
port-level stop intervened -- measured on-bench at ~100-150 ms per
occurrence, +9-13 degrees of extra rotation per turn, +15-22 mm of
extra travel per leg. This was THE dominant source of tour corruption
in the 2026-08-20 bench campaign (it was only ever intermittent because
the protocol fiber's now-removed co-ticking sometimes delivered the
missing step by accident).

THE FIX has two parts, both in `shims.cpp::tickDrive()`:
  1. Run one extra `kernel.step()` when `wasActive && !moveActive`, so
     the staged neutral actually lands before `tickDrive()` reports
     "done" -- this is the part that stops the wheels.
  2. Keep stepping (up to 12 more times, breaking early once BOTH
     wheels' MEASURED velocity reads at or under ~2 mm/s / 25 counts/s)
     before the final telemetry/odometry update -- because one step
     stops the DUTY but its encoder read can land mid-spin-down,
     freezing `Output.velocityLeft/Right` at a nonzero value forever
     (a second, distinct bench artifact: post-move telemetry charts
     showing the wheels "ending" at +4/-2.5 cm/s that never happened).

WHAT THIS FILE PROVES, against the host harness, per motion_engine_shim.
cpp's exposed entry points (meServiceMove/meStep/meMotorLastStagedDuty/
meOutVelocityLeft.../meEndMove -- no simulated physics; FakeMotor
positions are placed directly via `meMotorArmPosition`, same technique
test_motion_engine_reductions.py's own multi-tick moveX() tests use):

  1. Fix part 1, for real: driving a moveX() to natural completion
     records the FULL ordered sequence of setDuty() calls landed on the
     FakeMotor (one per side per `step()` -- see
     DifferentialDrive::controlStep()'s unconditional single
     `stageDuty()`/`stageStop()` call per mode branch) and asserts the
     LAST entry in that sequence is a neutral (zero) command -- not the
     last NONZERO commanded duty that was still staged the instant
     `serviceMove()` first reported the move done
     (test_move_x_natural_completion_delivers_neutral_to_motor).
  2. Fix part 2's own justification: a FakeMotor arranged to report a
     coasting (nonzero, MEASURED) velocity right at move completion
     still reads that same nonzero velocity after the ONE step fix part
     1 requires (frozen -- no new encoder sample arrived) -- proving a
     single extra step is not "assumed sufficient" for a settled
     reading. Continuing to step through a decaying velocity profile
     (mirroring `tickDrive()`'s own up-to-12-iteration, break-on-rest
     loop) brings the reading to rest within the same 12-step budget,
     without ever re-energizing the motors
     (same test, second half).
  3. Fix part 1 is not special-cased to the "happy path": an externally
     stopped move (`endMove()`, the STOP/ESTOP verbs' own code path)
     and a move aborted by its `timeout` backstop hit the exact same
     staged-vs-delivered gap and need the exact same extra step
     (test_end_move_delivers_neutral_to_motor,
     test_move_x_timeout_abort_delivers_neutral_to_motor).

WHAT THIS FILE CANNOT PROVE -- read before "simplifying" this file:
`tickDrive()`'s own up-to-12-iteration loop (the exact iteration cap,
the exact break condition, and the interleaved odometry fold-in) lives
ONLY in `shims.cpp`, which composes `Rig` over `CodalClock`/
`CodalSleeper`/`CodalFiberLauncher`/`NezhaMotorPort` and includes
`pxt.h` -- CODAL/PXT platform types this host build cannot compile (see
this test tree's own `_SHIM_SOURCES` lists, which include
`diffdrive.cpp`/`motion_engine.cpp` but never `shims.cpp`). Ticket 007's
handoff deliberately left the settle-loop in `tickDrive()` rather than
porting it into `MotionEngine`, on the grounds that it is TICK-ENGINE
PACING (how many more times to call `kernel.step()` before reporting
"done") rather than MOVE-ENGINE SHAPING (what `serviceMove()` itself
computes) -- a defensible line, but it means no host test, including
this one, can execute `tickDrive()`'s own loop body. Test 2 above proves
the loop's necessity and exercises the real velocity-settling machinery
(diffdrive.cpp's `refreshSample()`) it depends on, using a Python-side
loop that mirrors -- but does not invoke -- `tickDrive()`'s C++ one. A
regression that deleted or shortened the ACTUAL loop in shims.cpp would
not be caught by any host test today.

Run with::

    uv run pytest tests/host/test_regression_post_move_neutral.py
"""

import pytest

from test_motion_engine_reductions import (  # noqa: F401 -- motion_lib re-exported as a fixture
    LEFT,
    RIGHT,
    Engine,
    _ready,
    motion_lib,
)

# shims.cpp tickDrive()'s own settle-loop constants, restated here (not
# hidden in a helper) so a reader can compare them against
# src/shims.cpp directly.
SETTLE_CAP = 12  # [steps] the loop's own iteration bound
SETTLE_REST_COUNTS_PER_S = 25.0  # shims.cpp's own kRest, "~2 mm/s"

_CYCLE_S = 0.024  # [s] one control cycle -- DifferentialDrive::Config's
                   # own default cyclePeriod (24 ms), used here only to
                   # convert a chosen counts/s velocity into a per-tick
                   # position delta; it does not need to match any
                   # FakeClock setting since sample time and the
                   # kernel's own clock are independent axes in this
                   # harness (see arm_motor_position_at()'s own
                   # comment).


def test_move_x_natural_completion_delivers_neutral_to_motor(motion_lib):
    """3e919e5's own two-part fix, proved against a straight moveX()
    driven to natural completion (distDone && yawDone in
    MotionEngine::serviceMove()).

    Part 1 (deliver the stop): the ordered sequence of every setDuty()
    call landed on the FakeMotor must end in a neutral (zero) command --
    not the last NONZERO cruise duty that was still staged the instant
    serviceMove() first reports the move done. kernel_.neutral() only
    STAGES a zero (DifferentialDrive::neutral() just writes command_);
    that stage reaches the motor only on the kernel's NEXT step(). A
    caller that stops after seeing serviceMove() return false -- without
    running that one more step -- ships the wheels coasting at full
    duty for ~100-150 ms (+9-13 deg/turn, +15-22 mm/leg) until the
    starvation watchdog's port-level stop, the dominant class of tour
    corruption 3e919e5 fixed.

    Part 2 (settle, not just stop): a FakeMotor arranged so the LAST
    real encoder sample lands exactly at move completion, showing the
    wheel still coasting at 500 counts/s (~40 mm/s, comfortably above
    shims.cpp's own ~25 counts/s "at rest" threshold) -- after the ONE
    step part 1 requires, the MEASURED velocity is unchanged (frozen:
    no new encoder sample arrived on that step), still well above the
    settle threshold. This is the exact bench artifact 3e919e5's
    settle-loop comment describes: "One extra step delivers the stop
    but its encoder read lands mid-spin-down, freezing Output ... at a
    nonzero velocity forever." Only by continuing to step -- mirroring
    shims.cpp::tickDrive()'s own up-to-12-iteration, break-on-rest loop,
    fed a decaying velocity profile here -- does the reading settle,
    and it must do so within the same 12-step budget, with the duty
    staying at neutral throughout (the settle loop only WATCHES the
    coast down; it never re-energizes the motors).
    """
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        distance, cruise, timeout_ms = 200.0, 150.0, 5000
        dist_target = distance * cpm

        duty_history = []  # every (left, right) setDuty() pair, in order

        def record():
            duty_history.append(
                (e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))
            )

        e.move_x(distance, 0.0, cruise, timeout_ms)
        e.step()  # lands the segment's own initial (0.25 ramp) duty
        record()

        # A chosen "still coasting at 500 counts/s" velocity at the
        # completing sample: the last 12 counts (~1 mm) of the move
        # arrive in one 24 ms tick, 500 counts/s = 12 counts / 0.024 s.
        velocity_at_completion = 500.0  # [counts/s] ~40 mm/s
        assert velocity_at_completion > SETTLE_REST_COUNTS_PER_S  # sanity

        approach_delta = velocity_at_completion * _CYCLE_S  # 12.0 counts
        t_us = 24_000
        e.arm_motor_position_at(LEFT, dist_target - approach_delta, t_us)
        e.arm_motor_position_at(RIGHT, dist_target - approach_delta, t_us)
        e.step()  # seeds the baseline sample -- no velocity yet (first
        record()  # -ever sample), remain = 12 counts > the 10-count
                  # margin, so the move is not done yet.
        assert e.service_move()  # still active

        t_us += 24_000
        e.arm_motor_position_at(LEFT, dist_target, t_us)
        e.arm_motor_position_at(RIGHT, dist_target, t_us)
        e.step()  # commits the completing sample: velocity = 12/0.024
        record()  # = 500 counts/s exactly; meanProgress == distTarget.

        assert not e.service_move()  # THIS is the moment "done" is
                                      # first reported.
        assert not e.is_move_active()

        # The instant completion is reported, the motor's last staged
        # duty is still the CRUISE value from the tick that just
        # committed -- kernel_.neutral() (called inside serviceMove()
        # above) has only STAGED the stop, not delivered it.
        duty_at_completion = duty_history[-1]
        assert duty_at_completion != (pytest.approx(0.0), pytest.approx(0.0)), (
            "Sanity check failed: the motor was already at zero the "
            "instant serviceMove() reported the move done, so this "
            "test cannot distinguish 'staged' from 'delivered'. "
            "Re-check the approach_delta/velocity_at_completion setup."
        )
        velocity_left = e.motor_velocity(LEFT)
        velocity_right = e.motor_velocity(RIGHT)
        assert velocity_left == pytest.approx(velocity_at_completion, abs=1.0)
        assert velocity_right == pytest.approx(velocity_at_completion, abs=1.0)

        # ---- Part 1: the ONE required extra step ----
        e.step()
        record()

        assert duty_history[-1] == (pytest.approx(0.0), pytest.approx(0.0)), (
            "A move that ends must still deliver the kernel's neutral "
            "to the motors (commit 3e919e5): the LAST setDuty() call "
            f"recorded was {duty_history[-1]}, not (0.0, 0.0). "
            f"serviceMove() staged kernel_.neutral() but nothing ran "
            "the one more kernel.step() needed to write that zero to "
            "the FakeMotor -- exactly the gap that let the wheels "
            "coast at full duty (the last nonzero commanded duty was "
            f"{duty_at_completion}) for ~100-150 ms in production "
            "(+9-13 deg per turn, +15-22 mm per leg) until the "
            "starvation watchdog's port-level stop finally intervened."
        )

        # ---- Part 2: one step stops the duty but not (necessarily)
        # the reported velocity -- the settle loop's own justification.
        frozen_velocity_left = e.motor_velocity(LEFT)
        frozen_velocity_right = e.motor_velocity(RIGHT)
        assert frozen_velocity_left > SETTLE_REST_COUNTS_PER_S, (
            "Expected the MEASURED velocity to still read above "
            f"shims.cpp's own ~{SETTLE_REST_COUNTS_PER_S:.0f} counts/s "
            "settle threshold immediately after the single required "
            "extra step -- no new encoder sample arrived on that step, "
            "so Output.velocityLeft is frozen at its last real reading "
            f"({frozen_velocity_left:.1f}). If this reads at or below "
            "the threshold, the test's own setup is no longer "
            "reproducing the 'encoder read lands mid-spin-down' "
            "scenario the settle loop exists for."
        )
        assert frozen_velocity_right > SETTLE_REST_COUNTS_PER_S

        # Now mirror tickDrive()'s own settle loop: keep stepping
        # through a DECAYING coast profile, breaking once both sides
        # read at or under the rest threshold. (This exercises the real
        # velocity-settling machinery in diffdrive.cpp; it does not
        # execute shims.cpp's own loop body -- see this file's module
        # docstring.)
        decel_profile = [300.0, 120.0, 40.0, 10.0]  # [counts/s]
        assert decel_profile[-1] < SETTLE_REST_COUNTS_PER_S  # must settle
        position = dist_target
        settled_after = None
        for i, v in enumerate(decel_profile, start=1):
            t_us += 24_000
            position += v * _CYCLE_S
            e.arm_motor_position_at(LEFT, position, t_us)
            e.arm_motor_position_at(RIGHT, position, t_us)
            e.step()
            record()

            # The settle loop only WATCHES the coast down -- it must
            # never re-energize the motors while doing so.
            assert duty_history[-1] == (pytest.approx(0.0), pytest.approx(0.0)), (
                "The settle loop must not re-issue a nonzero duty while "
                f"waiting for the wheels to read at rest (iteration {i}: "
                f"{duty_history[-1]})."
            )

            vl, vr = e.motor_velocity(LEFT), e.motor_velocity(RIGHT)
            if abs(vl) <= SETTLE_REST_COUNTS_PER_S and abs(vr) <= SETTLE_REST_COUNTS_PER_S:
                settled_after = i
                break

        # 1 (the required step) + however many settle-loop iterations
        # this took, must stay within tickDrive()'s own 12-step budget.
        assert settled_after is not None, (
            "The coast-down velocity never settled at or under "
            f"{SETTLE_REST_COUNTS_PER_S:.0f} counts/s within "
            f"{len(decel_profile)} further steps -- shims.cpp's own "
            f"loop caps at {SETTLE_CAP} total iterations; a settle "
            "loop that cannot converge on a realistic decay profile "
            "this short would time out against the real cap too."
        )
        assert 1 + settled_after <= SETTLE_CAP
        # The whole point of part 2: a single extra step was NOT
        # sufficient (settled_after == 1 would mean the very first
        # post-stop reading was already at rest -- not what this test
        # arranged, and not what the bench campaign observed).
        assert settled_after > 1, (
            "This test arranged a velocity that takes multiple ticks "
            "to decay below the settle threshold specifically to prove "
            "that a single extra step is not 'assumed sufficient' "
            "(motion_engine_shim.cpp/shims.cpp's own settle-loop "
            "rationale). Settling in exactly one more step here means "
            "the decel_profile above no longer exercises that case."
        )

        assert duty_history[-1] == (pytest.approx(0.0), pytest.approx(0.0))


def test_end_move_delivers_neutral_to_motor(motion_lib):
    """3e919e5's fix is not special-cased to natural completion: an
    EXTERNALLY stopped move (MotionEngine::endMove(), the code path
    behind the wire's STOP/ESTOP verbs) posts the same
    `if (move_.active) kernel_.neutral();` and hits the exact same
    staged-vs-delivered gap -- `is_move_active()` clearing immediately
    is not evidence the motor has actually been zeroed."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.move_x(500.0, 0.0, 100.0, 5000)
        e.step()  # lands a nonzero cruise duty
        assert e.is_move_active()
        duty_before_stop = (
            e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))
        assert duty_before_stop != (pytest.approx(0.0), pytest.approx(0.0))

        e.end_move()
        assert not e.is_move_active()
        # endMove() only STAGED kernel_.neutral() -- the motor has not
        # been written to since the last active step yet.
        assert (e.motor_last_staged_duty(LEFT),
                e.motor_last_staged_duty(RIGHT)) == duty_before_stop

        e.step()  # the required extra step
        assert (e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT)) == (
            pytest.approx(0.0), pytest.approx(0.0)), (
            "An externally stopped move (endMove(), commit 3e919e5's "
            "same fix) must still deliver the kernel's neutral to the "
            "motors on the very next step -- without it, an external "
            "STOP/ESTOP would leave the wheels coasting at "
            f"{duty_before_stop} for ~100-150 ms exactly like the "
            "natural-completion case, just triggered by a different "
            "caller."
        )


def test_move_x_timeout_abort_delivers_neutral_to_motor(motion_lib):
    """3e919e5's fix applies to serviceMove()'s TIMEOUT abort branch
    too, not only the distDone && yawDone happy path: a robot that
    never reports encoder progress (physically blocked) is stopped by
    its `timeout` backstop, which reaches the exact same
    `kernel_.neutral(); move_.active = false;` completion code -- and so
    needs the exact same one more step to actually reach the motor."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_clock(0)
        e.move_x(1000.0, 0.0, 50.0, 2000)  # [mm] [rad] [mm/s] [ms]

        e.set_clock(1_999_000)  # still inside the timeout
        e.step()
        assert e.service_move()
        assert e.is_move_active()
        duty_before_timeout = (
            e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))
        assert duty_before_timeout != (pytest.approx(0.0), pytest.approx(0.0))

        e.set_clock(2_001_000)  # past the timeout
        e.step()  # lands whatever scale the PRIOR service_move() call
                   # reissued (the ramp has long since reached full
                   # scale by 1999 ms, so this is not duty_before_timeout
                   # itself -- only that it is still nonzero matters
                   # here).
        duty_at_expiry = (
            e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT))
        assert duty_at_expiry != (pytest.approx(0.0), pytest.approx(0.0))

        assert not e.service_move()  # detects `expired`, STAGES
                                       # kernel_.neutral() -- not yet
                                       # delivered.
        assert not e.is_move_active()
        # Same staged-not-delivered gap as the natural-completion path:
        # the timeout abort's kernel_.neutral() (just staged above) has
        # not reached the motor yet -- the duty is unchanged from the
        # instant before this call.
        assert (e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT)) == (
            duty_at_expiry)

        e.step()  # the required extra step
        assert (e.motor_last_staged_duty(LEFT), e.motor_last_staged_duty(RIGHT)) == (
            pytest.approx(0.0), pytest.approx(0.0)), (
            "A move aborted by its `timeout` backstop (commit 3e919e5's "
            "same fix) must still deliver the kernel's neutral on the "
            "very next step -- a physically blocked robot that timed "
            "out would otherwise keep driving into whatever it is "
            "blocked against for another ~100-150 ms."
        )
