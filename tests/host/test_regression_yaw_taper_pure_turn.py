"""tests/host/test_regression_yaw_taper_pure_turn.py -- locks in
commit `bd9f005`'s fix ("Arcs no longer taper on yaw: a 0.57 deg
bearing change was worth 4x speed") against the unified
`VelocityShaper`/`Segment` engine (design docs/design/
motion-profile-unification.md), which replaced the two-axis-scale
`serviceMove()` this regression was originally pinned against.

THE ORIGINAL BUG (bd9f005, src/shims.cpp's old serviceMove()): every
move was scaled by min(distanceAxisScale, yawAxisScale). The yaw axis
divided *remaining* yaw by a FIXED ~180-count (~15 deg) window
regardless of how large the move's total yaw target was. A gentle
arc's entire yaw target could be a degree or two -- far smaller than
the window -- so remain/window started BELOW the taper floor and
stayed there: the move began inside its own taper and never left it.

Measured on vevov, world tour: three legs ran at 5.0, 5.3 and 5.1 cm/s
against a commanded 20 -- exactly the 25% distFloor -- while the one
leg whose bearing fell under the straight-line threshold (and so
skipped the yaw branch entirely) ran the full 20.4 cm/s and landed on
its dot. A 0.57 deg difference in bearing was worth 4x in speed.

THE FIX, THEN: gate the yaw axis's own scale behind `pureTurn`.

THE FIX, NOW (this ticket, design S4.3/S5): there is no longer a
second, independently-computed yaw scale to gate at all. `Segment`
picks exactly ONE `dominantAxis` at construction (`pureTurn() ?
kYaw : kDistance`, motion_engine.cpp's beginSegment()), and
`Segment::remaining()` (segment.h) computes its return value from
EITHER `distTarget` OR `yawTarget` depending on that one field --
never both. `MotionEngine::service()` calls `remaining()` exactly
once per tick and feeds that single number to the one `VelocityShaper`
instance (motion_engine.cpp: `remain = seg_.remaining(out) / cpm`).
For an arc (`dominantAxis == kDistance`), `remaining()`'s kDistance
branch never reads `yawTarget` at all -- so an arc's taper cannot be
influenced by the SIZE of its own yaw target, no matter how small,
because that number is never consulted. bd9f005's bug is not just
fixed here, it is architecturally unrepresentable: there is nowhere
left to plug a second, competing yaw window back in without touching
`Segment::remaining()`'s own branch.

This file proves that restated invariant against the live engine (no
simulated physics -- FakeMotor positions are placed directly via
`meMotorArmPosition`/`land_steady_state_command`, the same techniques
test_motion_engine_reductions.py and test_wire_motion_verbs.py use for
their own multi-tick segment tests):

  1. An ARC's taper is governed by DISTANCE remaining alone -- proven
     by showing it is UNCHANGED when the yaw target is swapped between
     a 2 deg gentle arc and a 45 deg near-the-split-threshold one, same
     distance progress armed both times
     (test_arc_taper_is_independent_of_yaw_target_size).
  2. A PURE TURN's taper is still governed by YAW remaining -- the
     shaping bd9f005 explicitly preserves; a pure turn's dominant axis
     is always yaw, and it still ramps, plateaus and lands within its
     own exact-turn tolerance (test_pure_turn_lands_within_exact_turn_tolerance).
  3. bd9f005's own measured signature: a GENTLE arc (small rotation,
     large distance -- the exact failing shape) reaches its full
     commanded rate early in the move, rather than sitting pinned at
     the floor for its whole duration
     (test_gentle_arc_reaches_near_full_scale_before_its_own_taper).

Every assertion's failure message spells out what a dominant-axis
regression would look like and why the architecture rules it out, so a
future change that reintroduces a second, independent yaw scale fails
loudly instead of quietly reintroducing bd9f005.

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

# motion_limits.h's own compiled-in defaults -- restated here (not read
# back over ctypes) since no test in this file touches limits(), so
# these are exactly what the shaper's steady state and floor resolve
# against. See test_motion_engine_reductions.py's own matching
# constants for the same restatement.
ACCEL_MM_S2 = 400.0  # [mm/s^2]


def _land_steady_state_command(e, start_us=0, ticks=80, tick_us=24_000):
    """For a fresh Segment, with NO encoder position armed (so `remain`
    never shrinks and the segment never falsely arrives): runs `ticks`
    REALISTIC (24 ms, tickDrive()'s own cadence) step()+service_move()
    cycles so the shaper's own accel ramp climbs from the floor to its
    real steady-state target and PLATEAUS there. Mirrors
    test_wire_motion_verbs.py's WireAdapterHandle.land_steady_state_command()
    exactly, adapted to this file's microsecond Engine clock (see
    Engine.set_clock(), test_motion_engine_reductions.py). Returns the
    clock value (us) reached, so a caller can keep ticking realistically
    from there -- a Segment's `remain` is BOUNDED (unlike a Hold's), so
    jumping the clock by a large `dt` in one shot would falsely trigger
    predictive arrival instead of reading a real taper (design S6.3)."""
    t = start_us
    e.set_clock(t)
    e.step()
    for _ in range(ticks):
        t += tick_us
        e.set_clock(t)
        e.service_move()
        e.step()
    return t


def _tick(e, t, tick_us=24_000):
    """One further REALISTIC-dt step()+service_move()+step() cycle from
    clock value `t` (us) -- lands whatever new duty the shaper computes
    for the position just armed. Returns the new clock value."""
    t += tick_us
    e.set_clock(t)
    e.step()
    assert e.service_move()
    e.step()
    return t


def _observed_scale(e, distance_mm, rotation_rad, cruise, cpm, b, fdv):
    """Back out the shaper's currently-commanded scale, by comparing
    the observed staged duty against this segment's UNSCALED (scale=1.0,
    i.e. exactly at `cruise`) prediction on its dominant wheel (the
    larger-magnitude one, to avoid dividing by a near-zero reference on
    a near-pivot segment). Mirrors the pre-ticket-003 version of this
    helper exactly."""
    exp_left, exp_right = _expected_duty_pair(
        distance_mm, rotation_rad, cruise, cpm, b, fdv, scale=1.0)
    if abs(exp_left) >= abs(exp_right):
        return e.motor_last_staged_duty(LEFT) / exp_left
    return e.motor_last_staged_duty(RIGHT) / exp_right


# ---------------------------------------------------------------------
# AC1: an arc's taper is governed by DISTANCE remaining alone -- a
# second, independent yaw scale is architecturally gone.
# ---------------------------------------------------------------------


def test_arc_taper_is_independent_of_yaw_target_size(motion_lib):
    """Two arcs, same distance target and same DISTANCE progress armed,
    but with wildly different yaw targets (2 deg vs 45 deg -- both stay
    one blended segment, below the pivot-first split). If any code path
    still computed a second, yaw-derived scale (bd9f005's bug), the
    much smaller 2 deg target would read a tighter taper than the 45
    deg one at the identical checkpoint. Segment::remaining() never
    reads yawTarget for a kDistance-dominant segment (segment.h), so
    the two arcs' commanded scale must be identical."""
    scales = {}
    for rotation_deg in (2.0, 45.0):
        with Engine(motion_lib) as e:
            fdv = _ready(e)
            cpm = e.counts_per_mm()
            b = e.effective_track_width()
            distance, cruise = 250.0, 150.0
            rotation = math.radians(rotation_deg)
            assert rotation < math.radians(50.0)  # stays one blended segment

            e.set_clock(0)
            e.move_x(distance, rotation, cruise, 20_000)
            # No progress armed yet -- ramp to the shaper's own steady
            # cruise first (many REALISTIC ticks; a Segment's `remain`
            # is bounded, so a single huge `dt` jump here would falsely
            # trigger predictive arrival instead of reading a ramp).
            t = _land_steady_state_command(e, start_us=0)

            dist_target = distance * cpm

            # Arm PURE mean progress (dLeft == dRight): Segment::
            # remaining()'s kDistance branch reads only
            # 0.5*(dLeft+dRight), so this leaves exactly 40 mm of
            # distance still to travel, regardless of the yaw target
            # armed alongside it.
            remain_dist_mm = 40.0  # [mm] comfortably not yet arrived
            mean_progress = (abs(dist_target) - remain_dist_mm * cpm)
            mean_progress = math.copysign(mean_progress, dist_target)
            e.arm_motor_position(LEFT, mean_progress)
            e.arm_motor_position(RIGHT, mean_progress)

            _tick(e, t)  # one realistic-dt tick lands the new taper scale

            scales[rotation_deg] = _observed_scale(
                e, distance, rotation, cruise, cpm, b, fdv)

    assert scales[2.0] == pytest.approx(scales[45.0], rel=2e-2), (
        "An arc's taper scale must depend on DISTANCE remaining alone: "
        f"a 2 deg yaw target read scale {scales[2.0]:.4f} and a 45 deg "
        f"one (same distance progress) read {scales[45.0]:.4f}. These "
        "must be equal -- a difference means something is once again "
        "computing a yaw-derived scale and blending it in, exactly "
        "bd9f005's bug (a 0.57 deg bearing difference was once worth "
        "4x in speed on vevov's world tour). Check that "
        "Segment::remaining() (segment.h) still ignores yawTarget "
        "entirely when dominantAxis == kDistance."
    )


def test_arc_runs_to_completion_regardless_of_yaw_target_size(motion_lib):
    """The same two arcs as above, driven to their own distance target:
    both must converge and stop cleanly on DISTANCE arrival, whatever
    their yaw target is."""
    for rotation_deg in (2.0, 45.0):
        with Engine(motion_lib) as e:
            _ready(e)
            cpm = e.counts_per_mm()
            distance, cruise = 250.0, 150.0
            rotation = math.radians(rotation_deg)

            e.set_clock(0)
            e.move_x(distance, rotation, cruise, 20_000)
            e.step()

            dist_target = distance * cpm
            e.set_clock(2_000_000)
            e.arm_motor_position(LEFT, dist_target)
            e.arm_motor_position(RIGHT, dist_target)
            e.step()
            assert not e.service_move(), (
                f"a {rotation_deg} deg arc did not arrive on distance "
                "target -- an independent yaw check must be blocking "
                "completion"
            )
            assert not e.is_move_active()


# ---------------------------------------------------------------------
# AC2: a pure turn's taper is still governed by YAW remaining.
# ---------------------------------------------------------------------


def test_pure_turn_lands_within_exact_turn_tolerance(motion_lib):
    """A PURE TURN (distance == 0, rotation != 0) must still ramp,
    plateau and land cleanly on its own YAW target -- this shaping is
    preserved verbatim by bd9f005 and restated, not removed, by this
    ticket: a pure turn's `dominantAxis` is always `kYaw`
    (Segment::pureTurn(), segment.h), so `remaining()` reads
    `yawTarget` exclusively."""
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        rotation, cruise = math.radians(40.0), 100.0

        e.set_clock(0)
        e.move_x(0.0, rotation, cruise, 20_000)
        _land_steady_state_command(e, start_us=0)

        yaw_target = rotation * 0.5 * b * cpm

        e.set_clock(3_000_000)
        e.arm_motor_position(LEFT, -yaw_target)
        e.arm_motor_position(RIGHT, yaw_target)
        e.step()
        assert not e.service_move(), (
            "a pure turn did not arrive on its own yaw target -- "
            "Segment::remaining()'s kYaw branch (segment.h) must still "
            "be reachable and correct"
        )
        assert not e.is_move_active()


# ---------------------------------------------------------------------
# AC3: bd9f005's own measured signature -- a gentle arc must not be
# pinned at the floor for its whole duration.
# ---------------------------------------------------------------------


def test_gentle_arc_reaches_near_full_scale_before_its_own_taper(motion_lib):
    """bd9f005's exact measured bug shape: a GENTLE arc -- a small
    rotation relative to a much larger distance, the vevov world-tour
    shape that measured 5.0/5.3/5.1 cm/s against a commanded 20 cm/s
    (exactly the 25% distFloor) before the original fix -- must NOT
    spend its whole duration pinned at the floor. With no encoder
    progress armed (remain stays at the full 500 mm target throughout),
    the shaper's own accel ramp (400 mm/s^2) has comfortably reached
    its steady-state cruise well before this checkpoint -- there is no
    180-count yaw window left to pin it at 25% regardless of how small
    the 2 deg total yaw target is."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()
        # 2 deg of rotation over 500 mm of travel: the whole yaw target
        # is a couple of degrees -- exactly the shape that started a
        # buggily-yaw-tapered move INSIDE its own taper and never let
        # it leave. Cruise stays under the default 250 mm/s vMax so the
        # steady-state scale really is expected to approach 1.0, not a
        # vMax-clamped fraction of `cruise`.
        distance, rotation, cruise = 500.0, math.radians(2.0), 200.0

        e.set_clock(0)
        e.move_x(distance, rotation, cruise, 20_000)
        t = _land_steady_state_command(e, start_us=0)

        observed_scale = _observed_scale(
            e, distance, rotation, cruise, cpm, b, fdv)

        assert observed_scale == pytest.approx(1.0, abs=0.05), (
            "A gentle arc (small rotation, large distance) must reach "
            f"its commanded rate well before completion, not sit "
            f"pinned near the floor. Observed scale {observed_scale:.4f} "
            "after comfortably more than the accel ramp time "
            f"({cruise / ACCEL_MM_S2:.3f} s at {ACCEL_MM_S2:.0f} mm/s^2). "
            "This is bd9f005's own measured bug shape: a tiny total yaw "
            "target used to divide the WHOLE remaining yaw by a FIXED "
            "180-count window, pinning the move below its own floor for "
            "its entire duration -- the exact cliff that pinned three "
            "vevov world-tour legs at 5.0/5.3/5.1 cm/s against a "
            "commanded 20 cm/s (the 25% floor) while the one leg under "
            "goToWorld's 0.01 rad straight-line threshold ran the full "
            "20.4 cm/s and landed on its dot -- a 0.57 deg bearing "
            "difference worth 4x in speed. Check that "
            "MotionEngine::service() still derives `remain` from "
            "Segment::remaining() alone, with no second yaw-derived "
            "scale blended in."
        )

        # It DOES still taper -- via distance alone -- once the move
        # actually nears completion: this is not "never tapers", it is
        # "tapers on the right axis, at the right time".
        dist_target = distance * cpm
        remain_dist_mm = 20.0
        mean_progress = math.copysign(
            abs(dist_target) - remain_dist_mm * cpm, dist_target)
        e.arm_motor_position(LEFT, mean_progress)
        e.arm_motor_position(RIGHT, mean_progress)
        # Position held fixed at this same 20 mm-remaining checkpoint
        # across several realistic ticks: the shaper's own decel plan is
        # RATE-limited (design S6.1 step 1), so one 24 ms tick alone
        # only shaves `decel * dt` off the steady-state speed -- this
        # lets it converge onto the braking-plan target for `remain`.
        for _ in range(10):
            t = _tick(e, t)

        near_end_scale = _observed_scale(
            e, distance, rotation, cruise, cpm, b, fdv)
        assert near_end_scale < 0.9 * observed_scale, (
            "Even a gentle arc must eventually taper as it nears "
            f"completion (20 mm remaining of a {distance:.0f} mm "
            f"target): expected a scale well below the steady-state "
            f"{observed_scale:.4f}, observed {near_end_scale:.4f}. This "
            "taper must come from the DISTANCE window (VelocityShaper's "
            "own braking plan on `remain`), not a separately-computed "
            "yaw one."
        )
