"""tests/host/test_continuous_mode_odometry.py -- sprint 006 ticket 003:
closes R-09/BLK-05 (code review 2026-08-23, independently re-derived and
scenario-corrected in docs/code-review/2026-08-23/raw/verify-blocks.md)
and clasi/sprints/006-.../issues/continuous-mode-odometry-chord-error.md.

THE BUG: `src/shims.cpp`'s `odomUpdate()` folds accumulated encoder
counts into pose as ONE straight chord at ONE midpoint heading, over
whatever has accumulated since the last call. Every existing call site
was move-path or pose-read; continuous-mode driving (`setWheels()`/
`driveTwist()` + a `while (tickDrive())` loop -- UC-002) never called it
at all, because `tickDrive()`'s own call was gated `if (wasActive)
odomUpdate(r);` (`wasActive` == a move-engine move in flight). A student
who drives a curve continuously and then reads pose gets a chord over
the WHOLE interval instead of the true path: heading comes out exactly
right (path-independent -- see below), x/y do not, and the error is the
entire path length for a closed loop.

THE FIX (`src/shims.cpp::tickDrive()`) makes that call unconditional --
`odomUpdate(r)` every tick, regardless of `wasActive` -- so the
accumulated delta each call folds in is only ONE TICK's worth, and the
per-tick midpoint-heading chord approximation tracks the true curved
path instead of replacing it with one giant straight line.

WHAT THIS FILE CANNOT PROVE (read before "simplifying" this file):
`src/shims.cpp` includes `pxt.h` (CODAL/PXT platform types) and cannot
be host-compiled at all -- see `src/DESIGN.md` SS1/SS11 and
`tests/host/DESIGN.md` SS6 ("shims.cpp's real Rig composition/
odometry/watchdog ... hardware sessions are their only test"). So this
file does NOT call `tickDrive()`/`odomUpdate()` themselves; it drives
the REAL kernel (`DiffDrive::DifferentialDrive`, via kernel_shim.cpp,
the same class `odomUpdate()` reads `Output.positionLeft/Right` from)
through a scripted circle, and applies `_ChordOdometry` below -- a
test-local mirror of `odomUpdate()`'s own formula (shims.cpp:213-233),
kept deliberately identical to it -- at two different call granularities
(every tick, vs. once at the end) to prove the MATHEMATICAL property
this ticket's fix depends on: per-tick chord integration closes a
circle back near the origin; a single lump chord over the whole
interval does not. That `src/shims.cpp::tickDrive()` itself now has
exactly one (unconditional) call site rather than a duplicated one is a
fact about the literal source text -- review-verified by reading the
diff, not something this host-only file can execute.

Counts-per-mm is fixed at 1.0 for this file (matching
tests/host/wire_motion_verb_shim.cpp's own convention) -- FakeMotor
positions are armed directly in mm, so `_ChordOdometry` needs no
separate counts-per-mm scaling step.

Run with::

    uv run pytest tests/host/test_continuous_mode_odometry.py
"""

import math

import pytest

from test_kernel_harness import (  # noqa: F401 -- kernel_lib re-exported as a fixture
    LEFT,
    RIGHT,
    STATUS_OK,
    Kernel,
    kernel_lib,
)


class CircleKernel(Kernel):
    """test_kernel_harness.Kernel plus Output.positionLeft/Right readback.
    kdOutPositionLeft/Right are already bound by the base class's own
    _bind() (test_kernel_harness.py) -- no additional ctypes wiring
    needed, unlike test_cross_fiber_stop_settle_window.py's
    StopWindowKernel, which binds ITS ticket's own new exports."""

    def out_position(self, side):
        if side == LEFT:
            return self._lib.kdOutPositionLeft(self._handle)
        return self._lib.kdOutPositionRight(self._handle)


class _ChordOdometry:
    """Test-local mirror of src/shims.cpp's odomUpdate() (lines 213-233),
    kept deliberately identical to that function's math -- see this
    module's docstring for why the real function cannot be linked here.

    Matches odomUpdate()'s own two behaviors exactly:
      - First call: primes (records the current positions, no pose
        change) -- odomUpdate()'s own `if (!r.odomPrimed) { ...; return;
        }` branch.
      - Every call after: diffs against the LAST positions this object
        consumed, immediately re-stamps them, and folds the delta in as
        one straight chord at the CURRENT midpoint heading -- odomUpdate()'s
        `dCenter`/`dHeading`/`midHeading` math, verbatim.

    This "diff against last consumed, then re-stamp" shape is also what
    makes a repeated call with unchanged positions a provable no-op --
    see test_repeated_odometry_update_with_no_intervening_step_is_a_no_op
    below.
    """

    def __init__(self, track_width_mm):
        self.track_width_mm = track_width_mm
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self._last_left = 0.0
        self._last_right = 0.0
        self._primed = False

    def update(self, position_left_mm, position_right_mm):
        if not self._primed:
            self._last_left = position_left_mm
            self._last_right = position_right_mm
            self._primed = True
            return
        d_left = position_left_mm - self._last_left
        d_right = position_right_mm - self._last_right
        self._last_left = position_left_mm
        self._last_right = position_right_mm
        d_center = 0.5 * (d_left + d_right)
        d_heading = (d_right - d_left) / self.track_width_mm
        mid_heading = self.heading + 0.5 * d_heading
        self.x += d_center * math.cos(mid_heading)
        self.y += d_center * math.sin(mid_heading)
        self.heading += d_heading


# Test geometry/kinematics -- deliberately round numbers chosen for exact
# closure, not this robot's real calibration (see class docstring: this
# is a general property of the odomUpdate() formula, not a
# vevov-specific fact). trackWidth=100mm, forward speed=100mm/s, yaw
# rate=90 deg/s (pi/2 rad/s) -> radius = v/w = 63.66mm, full-circle
# period T = 2*pi/w = 4.0s exactly. At a 100ms test tick (this file's own
# choice, NOT this project's real 24ms cyclePeriod -- see the module
# docstring), that is exactly 40 ticks per circle, so every tick turns
# exactly 9 degrees and the circle closes with no leftover fraction.
_TRACK_WIDTH_MM = 100.0
_FORWARD_SPEED_MM_S = 100.0
_YAW_RATE_RAD_S = math.pi / 2.0
_TICK_S = 0.1
_TICKS_PER_CIRCLE = 40
_LEFT_SPEED_MM_S = _FORWARD_SPEED_MM_S - _YAW_RATE_RAD_S * 0.5 * _TRACK_WIDTH_MM
_RIGHT_SPEED_MM_S = _FORWARD_SPEED_MM_S + _YAW_RATE_RAD_S * 0.5 * _TRACK_WIDTH_MM


def _prime_kernel(k):
    """Establish the kernel's own first-ever encoder sample (both wheels
    at position 0) -- refreshSample()'s `everSampled` priming step,
    mirroring test_kernel_harness.py's own smoke-test setup."""
    k.set_clock(0)
    k.arm_motor_sample(LEFT, position=0.0, sample_time_us=1)
    k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=1)
    k.step()


def test_continuous_mode_per_tick_integration_closes_a_circle_the_single_chord_reading_does_not(
    kernel_lib,
):
    """The ticket's own acceptance criterion #1: drive a full circle
    under a constant-twist continuous command (wheelsV/driveTwist-
    equivalent: constant, DIFFERENT per-wheel speeds -- exactly what
    continuous-mode driving commands, never varied mid-drive) in an
    unconditional tick loop (mirroring testrig.ts:118-120's pattern, per
    verify-blocks.md's scenario correction to BLK-05 -- NOT the
    documented-but-broken `while (driveTick())` idiom, which exits after
    one tick in continuous mode; see this ticket's own Description).

    Per-tick chord integration should close back near the origin;
    reading the SAME total encoder movement as one lump chord (today's
    bug -- nothing calls odomUpdate() until a pose read) should report
    approximately the whole path length instead, in the direction of
    the midpoint (half-circle) heading.
    """
    with CircleKernel(kernel_lib) as k:
        k.set_max_duty(100.0)  # begin() refuses kRefusedUnconfigured otherwise
        assert k.begin() == STATUS_OK
        _prime_kernel(k)

        per_tick = _ChordOdometry(_TRACK_WIDTH_MM)
        per_tick.update(k.out_position(LEFT), k.out_position(RIGHT))  # prime

        start_left = k.out_position(LEFT)
        start_right = k.out_position(RIGHT)

        for tick in range(1, _TICKS_PER_CIRCLE + 1):
            t_s = tick * _TICK_S
            t_us = int(round(t_s * 1_000_000.0)) + 1  # stay clear of 0
            k.set_clock(t_us)
            k.arm_motor_sample(
                LEFT, position=_LEFT_SPEED_MM_S * t_s, sample_time_us=t_us
            )
            k.arm_motor_sample(
                RIGHT, position=_RIGHT_SPEED_MM_S * t_s, sample_time_us=t_us
            )
            k.step()
            # THE FIX: fold odometry in on EVERY tick, unconditionally --
            # exactly what tickDrive() now does.
            per_tick.update(k.out_position(LEFT), k.out_position(RIGHT))

        end_left = k.out_position(LEFT)
        end_right = k.out_position(RIGHT)

        per_tick_distance = math.hypot(per_tick.x, per_tick.y)
        assert per_tick_distance == pytest.approx(0.0, abs=0.5), (
            f"per-tick odometry should close the circle back near the "
            f"origin; got ({per_tick.x:.3f}, {per_tick.y:.3f}) mm, "
            f"{per_tick_distance:.3f} mm from origin"
        )
        # Heading is path-independent (verify-blocks.md's own finding):
        # both integrations should agree it turned exactly one full
        # circle regardless of granularity.
        assert per_tick.heading == pytest.approx(2.0 * math.pi, abs=1e-3)

        # THE BUG: today's shims.cpp never calls odomUpdate() during
        # continuous driving -- the next pose read integrates the WHOLE
        # interval as one chord, computed here directly from the start/
        # end encoder counts with no intervening per-tick calls.
        single_chord = _ChordOdometry(_TRACK_WIDTH_MM)
        single_chord.update(start_left, start_right)  # prime
        single_chord.update(end_left, end_right)  # one lump chord
        single_chord_distance = math.hypot(single_chord.x, single_chord.y)

        expected_path_length = _FORWARD_SPEED_MM_S * (
            _TICKS_PER_CIRCLE * _TICK_S
        )
        assert single_chord_distance == pytest.approx(
            expected_path_length, rel=0.02
        ), (
            "sanity check: the single-chord (bug) reading should read "
            "back approximately the whole path length, not near the "
            "origin -- otherwise this test cannot tell the fix apart "
            "from the bug it fixes"
        )
        assert single_chord.heading == pytest.approx(2.0 * math.pi, abs=1e-3)
        # The bug reading must be grossly displaced compared to the fix.
        assert single_chord_distance > 50.0 * max(per_tick_distance, 1e-6)


def test_repeated_odometry_update_with_no_intervening_step_is_a_no_op(kernel_lib):
    """The ticket's own acceptance criterion #3 (no double-integration).

    tickDrive()'s existing `if (wasActive) odomUpdate(r);` call ahead of
    serviceMove() becomes an unconditional `odomUpdate(r);` in this
    ticket's fix -- a REPLACEMENT of the one call site, not an addition
    of a second one (see src/shims.cpp's own diff for that literal
    fact -- untestable here, since shims.cpp cannot be host-linked; see
    this module's docstring). What IS host-testable, and what this
    ticket's safety actually rests on, is that the underlying primitive
    is re-entrant: odomUpdate() (mirrored as _ChordOdometry) diffs
    against the last Output it consumed and immediately re-stamps that
    value, so a second call with no intervening kernel.step() sees a
    zero delta and changes nothing. Even in the worst case where this
    fix had accidentally left two call sites firing in the same tick,
    pose would not double-count.
    """
    with CircleKernel(kernel_lib) as k:
        k.set_max_duty(100.0)  # begin() refuses kRefusedUnconfigured otherwise
        assert k.begin() == STATUS_OK
        _prime_kernel(k)

        odom = _ChordOdometry(_TRACK_WIDTH_MM)
        odom.update(k.out_position(LEFT), k.out_position(RIGHT))  # prime

        # One real tick of curved motion.
        k.set_clock(100_000)
        k.arm_motor_sample(LEFT, position=10.0, sample_time_us=100_000)
        k.arm_motor_sample(RIGHT, position=40.0, sample_time_us=100_000)
        k.step()
        odom.update(k.out_position(LEFT), k.out_position(RIGHT))
        x1, y1, heading1 = odom.x, odom.y, odom.heading
        assert (x1, y1, heading1) != (0.0, 0.0, 0.0), (
            "sanity check: the first call must actually move pose, or "
            "this test cannot distinguish 'correctly a no-op' from "
            "'nothing happened anyway'"
        )

        # A second call landing in the SAME tick, no kernel.step() in
        # between -- the exact shape a duplicated call site would
        # produce.
        odom.update(k.out_position(LEFT), k.out_position(RIGHT))

        assert odom.x == pytest.approx(x1)
        assert odom.y == pytest.approx(y1)
        assert odom.heading == pytest.approx(heading1)
