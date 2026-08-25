"""tests/host/test_regression_yaw_taper_pure_turn.py -- locks in
commit `bd9f005`'s fix ("Arcs no longer taper on
yaw: a 0.57 deg bearing change was worth 4x speed") against
`motion_engine`'s ported copy of the same logic.

THE BUG (bd9f005, src/shims.cpp's serviceMove(), now
MotionEngine::serviceMove() in src/motion_engine.cpp): every move was
scaled by min(distanceAxisScale, yawAxisScale). The yaw axis divides
*remaining* yaw by a FIXED ~180-count (~15 deg) window regardless of
how large the move's total yaw target is. A gentle arc's entire yaw
target can be a degree or two -- far smaller than the window -- so
remain/window starts BELOW the taper floor and stays there: the move
begins inside its own taper and never leaves it, pinned at the floor
end to end.

That produced a cliff exactly at goToWorld's 0.01 rad straight-line
threshold. Measured on vevov, world tour: three legs ran at 5.0, 5.3
and 5.1 cm/s against a commanded 20 -- exactly the 25% distFloor --
while the one leg whose bearing fell under the straight-line threshold
(and so skipped the yaw branch entirely) ran the full 20.4 cm/s and
landed on its dot. A 0.57 deg difference in bearing was worth 4x in
speed.

THE FIX: the yaw axis's own axisScale is gated behind `pureTurn`
(`distTarget == 0 && yawTarget != 0`). The physics: in an ARC, twist
and velocity are LOCKED by curvature, so the distance taper already
scales yaw by the same factor and both axes finish together -- a
second, independent yaw taper double-counts. A PURE TURN has no
distance taper to lean on, so it keeps its own yaw taper -- that
shaping is what makes turns exact and is the whole reason the window
exists.

This file proves, against the host harness (no simulated physics --
FakeMotor positions are placed directly via `meMotorArmPosition`, the
same technique test_motion_engine_reductions.py uses for its own
multi-tick moveX() tests):

  1. An ARC's end-of-move scale is governed by the DISTANCE taper
     window ALONE (test_arc_scale_governed_by_distance_taper_only).
  2. A PURE TURN's end-of-move scale is still governed by the YAW
     taper window (test_pure_turn_scale_governed_by_yaw_taper) -- the
     shaping bd9f005 explicitly preserves.
  3. bd9f005's own measured signature: a GENTLE arc (small rotation,
     large distance -- the exact failing shape) reaches a scale
     approaching 1.0 long before its own end-of-move taper begins,
     rather than being pinned at the floor for its whole duration
     (test_gentle_arc_reaches_near_full_scale_before_its_own_taper).

Every assertion's failure message spells out what a `pureTurn`-gate
regression would look like and why the gate exists, so a future
"simplification" that deletes or bypasses it fails loudly instead of
quietly reintroducing bd9f005.

Run with::

    uv run pytest tests/host/test_regression_yaw_taper_pure_turn.py
"""

import math

import pytest

from test_motion_engine_reductions import (  # noqa: F401 -- motion_lib re-exported as a fixture
    LEFT,
    RIGHT,
    Engine,
    _expected_duty_pair,
    _ready,
    motion_lib,
)

# motion_engine.h's own end-of-move shaping DEFAULTS (no setter is
# exercised in this file -- every test below runs against these exact
# values, so they are restated here rather than hidden in a helper).
DIST_TAPER_COUNTS = 400.0  # [counts] ~32 mm window
YAW_TAPER_COUNTS = 180.0  # [counts] ~15 deg window
DIST_FLOOR = 0.25  # [1] arcs/straights crawl no slower than this
TURN_FLOOR = 0.12  # [1] pure turns crawl no slower than this
RAMP_MS = 400.0  # [ms] acceleration ramp -- tests wait this long out


def _dist_target_counts(distance_mm, cpm):
    """Mirrors MotionEngine::startSegment()'s own `move_.distTarget`."""
    return distance_mm * cpm


def _yaw_target_counts(rotation_rad, cpm, b):
    """Mirrors MotionEngine::startSegment()'s own `move_.yawTarget`."""
    return rotation_rad * 0.5 * b * cpm


def _positions_for_remaining(dist_target, yaw_target, remain_dist,
                             remain_yaw):
    """Solve the (dLeft, dRight) counts -- relative to the segment's own
    posLeft0/posRight0 baseline, which is 0 in a freshly-created Engine
    that has never armed a position -- that make
    MotionEngine::serviceMove()'s own remaining-distance/remaining-yaw
    read back exactly the requested values. Mirrors its math exactly
    (motion_engine.cpp serviceMove()):

        meanProgress = 0.5*(dLeft+dRight)
        diffProgress = 0.5*(dRight-dLeft)
        remain_dist  = |distTarget| - |meanProgress|
        toward       = distTarget-sign-of-yawTarget ? diffProgress
                                                     : -diffProgress
        remain_yaw   = |yawTarget| - toward
    """
    if dist_target != 0.0:
        mean_progress = math.copysign(
            abs(dist_target) - remain_dist, dist_target)
    else:
        mean_progress = 0.0
    if yaw_target != 0.0:
        toward = abs(yaw_target) - remain_yaw
        diff_progress = toward if yaw_target > 0.0 else -toward
    else:
        diff_progress = 0.0
    d_left = mean_progress - diff_progress
    d_right = mean_progress + diff_progress
    return d_left, d_right


def _observed_scale(e, distance_mm, rotation_rad, cruise, cpm, b, fdv):
    """Back out the taper/ramp `scale` MotionEngine::serviceMove()
    actually applied on the most recent step(), by comparing the
    observed staged duty against this segment's UNSCALED (scale=1.0)
    prediction on its dominant wheel (the larger-magnitude one, to
    avoid dividing by a near-zero reference on a near-pivot segment).
    velCmd/twistCmd are fixed at segment start from the ORIGINAL
    (distance, rotation) pair, so this recovers `scale` correctly at
    any point in the segment's life, independent of how much progress
    has been armed."""
    exp_left, exp_right = _expected_duty_pair(
        distance_mm, rotation_rad, cruise, cpm, b, fdv, scale=1.0)
    if abs(exp_left) >= abs(exp_right):
        return e.motor_last_staged_duty(LEFT) / exp_left
    return e.motor_last_staged_duty(RIGHT) / exp_right


# ---------------------------------------------------------------------
# AC1: an arc's end-of-move scale is governed by DISTANCE alone.
# ---------------------------------------------------------------------


def test_arc_scale_governed_by_distance_taper_only(motion_lib):
    """An arc (distance AND rotation both nonzero) driven near the end
    of its move, then through to completion: the commanded scale must
    be governed by the DISTANCE taper window alone. bd9f005's fix gates
    MotionEngine::serviceMove()'s yaw-axis scale behind `pureTurn`
    precisely because an arc's twist and velocity are LOCKED by
    curvature -- the distance taper already scales yaw by the same
    factor, so a second, independent yaw taper would double-count."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        distance, rotation, cruise = 250.0, math.radians(15.0), 150.0
        assert rotation < math.radians(50.0)  # stays one blended segment

        e.set_clock(0)
        e.move_x(distance, rotation, cruise, 20_000)
        e.step()  # lands the segment's own initial (0.25 ramp) duty

        dist_target = _dist_target_counts(distance, cpm)
        yaw_target = _yaw_target_counts(rotation, cpm, b)

        # Near the end of the move: 150 of the 400-count distance-taper
        # window remain (axisScale = 150/400 = 0.375), while only 30 of
        # the much SMALLER 180-count yaw-taper window remain
        # (axisScale = 30/180 = 0.1667, well under the 0.25 distFloor).
        # Neither axis has finished yet (both remainders exceed their
        # 10-count margins), so this reads the taper mid-flight, not a
        # "just happens to be done" edge case.
        remain_dist, remain_yaw = 150.0, 30.0
        assert 10.0 < remain_dist < DIST_TAPER_COUNTS
        assert 10.0 < remain_yaw < YAW_TAPER_COUNTS
        d_left, d_right = _positions_for_remaining(
            dist_target, yaw_target, remain_dist, remain_yaw)
        e.arm_motor_position(LEFT, d_left)
        e.arm_motor_position(RIGHT, d_right)

        e.set_clock(int(RAMP_MS * 1000) + 100_000)  # well past the ramp
        e.step()  # commits the armed positions into kernel Output
        assert e.service_move()  # still active -- neither axis is done

        e.step()  # lands the newly-computed taper scale's duty

        expected_scale = remain_dist / DIST_TAPER_COUNTS  # 0.375
        observed_scale = _observed_scale(
            e, distance, rotation, cruise, cpm, b, fdv)

        assert observed_scale == pytest.approx(expected_scale, rel=2e-2), (
            "An arc's end-of-move scale must be governed by the "
            f"DISTANCE taper alone (bd9f005): expected {expected_scale:.4f} "
            f"(remaining distance {remain_dist:.0f} / distTaper "
            f"{DIST_TAPER_COUNTS:.0f}), observed {observed_scale:.4f}. "
            f"A reading near the {DIST_FLOOR:.2f} floor instead means "
            "the yaw axis's own (much smaller, 180-count) taper window "
            "is leaking back into an arc's scale -- check that "
            "MotionEngine::serviceMove()'s yaw axisScale is still "
            "gated behind `if (pureTurn)`. In an arc, twist and "
            "velocity are locked by curvature, so the distance taper "
            "already scales yaw by the same factor; a second, "
            "independent yaw taper double-counts. This is exactly the "
            "bug that pinned vevov's world-tour legs at a 25% floor "
            "(5.0/5.3/5.1 cm/s against a commanded 20) while only the "
            "leg under goToWorld's 0.01 rad straight-line threshold "
            "(which skips the yaw branch entirely) reached full speed "
            "(20.4 cm/s) -- a 0.57 deg bearing difference worth 4x in "
            "speed."
        )

        # "Through to completion": the same arc must still converge and
        # stop cleanly, not just produce one correct scale reading with
        # no consequence.
        d_left, d_right = _positions_for_remaining(
            dist_target, yaw_target, remain_dist=0.0, remain_yaw=0.0)
        e.arm_motor_position(LEFT, d_left)
        e.arm_motor_position(RIGHT, d_right)
        e.step()
        assert not e.service_move()
        assert not e.is_move_active()


# ---------------------------------------------------------------------
# AC2: a pure turn's end-of-move scale is still governed by YAW.
# ---------------------------------------------------------------------


def test_pure_turn_scale_governed_by_yaw_taper(motion_lib):
    """A PURE TURN (distance == 0, rotation != 0) must still taper
    according to the YAW window -- this shaping is preserved verbatim
    by bd9f005. Only ARCS lost their independent yaw taper; a pure
    turn's `pureTurn == True` keeps the exact-turn shaping that makes
    turns land within a degree instead of several."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        rotation, cruise = math.radians(40.0), 100.0

        e.set_clock(0)
        e.move_x(0.0, rotation, cruise, 20_000)
        e.step()  # lands the segment's own initial (0.25 ramp) duty

        yaw_target = _yaw_target_counts(rotation, cpm, b)

        # A pure turn's own yaw margin is tighter (4 counts, not the
        # arc/straight 10) -- 30 remaining counts is comfortably not
        # yet done, well inside the 180-count window.
        remain_yaw = 30.0
        assert 4.0 < remain_yaw < YAW_TAPER_COUNTS
        d_left, d_right = _positions_for_remaining(
            0.0, yaw_target, remain_dist=0.0, remain_yaw=remain_yaw)
        e.arm_motor_position(LEFT, d_left)
        e.arm_motor_position(RIGHT, d_right)

        e.set_clock(int(RAMP_MS * 1000) + 100_000)  # well past the ramp
        e.step()
        assert e.service_move()  # still active -- yaw is not done

        e.step()  # lands the newly-computed taper scale's duty

        expected_scale = remain_yaw / YAW_TAPER_COUNTS  # 0.1667
        observed_scale = _observed_scale(
            e, 0.0, rotation, cruise, cpm, b, fdv)

        assert observed_scale == pytest.approx(expected_scale, rel=2e-2), (
            "A pure turn's end-of-move scale must still be governed by "
            f"the YAW taper window: expected {expected_scale:.4f} "
            f"(remaining yaw {remain_yaw:.0f} / yawTaper "
            f"{YAW_TAPER_COUNTS:.0f}), observed {observed_scale:.4f}. A "
            "reading near 1.0 means the `if (pureTurn)` gate in "
            "MotionEngine::serviceMove() has been deleted or its "
            "branch made unreachable -- pure turns would then never "
            "taper at all, losing the exact-turn shaping bd9f005 "
            "explicitly preserved. Turns are the ONE case this taper "
            "is correct for: unlike an arc, nothing else (no distance "
            "taper) scales a pure turn's yaw down for it."
        )


# ---------------------------------------------------------------------
# AC3: bd9f005's own measured signature -- a gentle arc must not be
# pinned at the floor for its whole duration.
# ---------------------------------------------------------------------


def test_gentle_arc_reaches_near_full_scale_before_its_own_taper(motion_lib):
    """bd9f005's exact measured bug shape: a GENTLE arc -- a small
    rotation relative to a much larger distance, the vevov world-tour
    shape that measured 5.0/5.3/5.1 cm/s against a commanded 20 cm/s
    (exactly the 25% distFloor) before this fix -- must NOT spend its
    whole duration pinned at the floor. Early in the move (well outside
    the 400-count distance-taper window), the scale must approach 1.0
    -- not the floor-clamped ~0.25 a double-counted 180-count yaw
    taper against a 2-degree total yaw target would produce. The move
    must still taper -- via DISTANCE, not yaw -- once it actually
    nears completion."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        # 2 deg of rotation over 500 mm of travel: the whole yaw target
        # is a couple of degrees, far smaller than the 180-count
        # (~15 deg) yaw-taper window -- exactly the shape that starts a
        # buggily-yaw-tapered move INSIDE its own taper and never lets
        # it leave.
        distance, rotation, cruise = 500.0, math.radians(2.0), 400.0

        e.set_clock(0)
        e.move_x(distance, rotation, cruise, 20_000)
        e.step()  # lands the segment's own initial (0.25 ramp) duty

        dist_target = _dist_target_counts(distance, cpm)
        yaw_target = _yaw_target_counts(rotation, cpm, b)
        # Sanity: this really is the failing shape -- the ENTIRE yaw
        # target is smaller than the yaw-taper window, and the whole
        # distance target is much larger than the distance-taper
        # window, so nothing legitimately tapers this early.
        assert abs(yaw_target) < YAW_TAPER_COUNTS
        assert abs(dist_target) > 10.0 * DIST_TAPER_COUNTS

        # Early in the move: no progress armed on either axis (the
        # freshly-created Engine's FakeMotor positions default to 0,
        # matching posLeft0/posRight0 captured at segment start) --
        # comfortably outside the distance taper window.
        e.set_clock(int(RAMP_MS * 1000) + 50_000)  # well past the ramp
        e.step()
        assert e.service_move()  # still active -- nowhere near done

        e.step()  # lands the newly-computed taper scale's duty

        observed_scale = _observed_scale(
            e, distance, rotation, cruise, cpm, b, fdv)

        assert observed_scale == pytest.approx(1.0, abs=0.05), (
            "A gentle arc (small rotation, large distance) must reach "
            "its commanded rate early in the move, not sit pinned at "
            f"the {DIST_FLOOR:.2f} floor for its whole duration. "
            f"Observed scale {observed_scale:.4f}. This is bd9f005's "
            "own measured bug: serviceMove() divided the WHOLE "
            "remaining yaw by a FIXED 180-count window regardless of "
            f"how small the total yaw target was, so a target of only "
            f"{abs(yaw_target):.1f} counts (~2 deg) started the move "
            "BELOW the taper floor and never left it -- the exact "
            "cliff that pinned three vevov world-tour legs at "
            "5.0/5.3/5.1 cm/s against a commanded 20 cm/s (the 25% "
            "floor) while the one leg under goToWorld's 0.01 rad "
            "straight-line threshold ran the full 20.4 cm/s and landed "
            "on its dot -- a 0.57 deg bearing difference worth 4x in "
            "speed. Check that MotionEngine::serviceMove()'s yaw "
            "axisScale is still gated behind `if (pureTurn)`."
        )

        # It DOES still taper -- via distance alone -- once the move
        # actually nears completion (same shape as
        # test_arc_scale_governed_by_distance_taper_only, for this
        # specific gentle-arc case): this is not "never tapers", it is
        # "tapers on the right axis, at the right time".
        remain_dist, remain_yaw = 150.0, 5.0
        d_left, d_right = _positions_for_remaining(
            dist_target, yaw_target, remain_dist, remain_yaw)
        e.arm_motor_position(LEFT, d_left)
        e.arm_motor_position(RIGHT, d_right)
        e.step()
        assert e.service_move()
        e.step()

        near_end_scale = _observed_scale(
            e, distance, rotation, cruise, cpm, b, fdv)
        expected_near_end_scale = remain_dist / DIST_TAPER_COUNTS  # 0.375
        assert near_end_scale == pytest.approx(
            expected_near_end_scale, rel=2e-2), (
            "Even a gentle arc must eventually taper as it nears "
            f"completion: expected {expected_near_end_scale:.4f} "
            f"(remaining distance {remain_dist:.0f} / distTaper "
            f"{DIST_TAPER_COUNTS:.0f}), observed {near_end_scale:.4f}. "
            "This taper must come from the DISTANCE window, not a "
            "separately-computed yaw one."
        )
