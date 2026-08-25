"""tests/tools/test_park.py -- the forward/reverse parking planner.

The claim under test is not "the planner produces a path" but the
specific one that motivated it: **reversing costs less rotation than
turning around, and on a robot whose rotation is biased that converts
directly into less final error.** Every test below is arithmetic, so
none of it needs a robot, a link, or a camera.

Run with::

    uv run pytest tests/tools/test_park.py
"""
import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))

import park
from park import DRIVE, PIVOT


def test_wrap_folds_to_half_open_interval():
    assert park.wrap(0) == 0
    assert park.wrap(180) == 180
    assert park.wrap(-180) == 180
    assert park.wrap(190) == pytest.approx(-170)
    assert park.wrap(-190) == pytest.approx(170)
    assert park.wrap(540) == 180


def test_already_parked_is_no_moves():
    assert park.plan((10, 10, 90), (10, 10, 90)) == []


def test_target_dead_ahead_drives_forward_without_pivoting():
    # Facing east at the origin, target 20 cm east, same heading.
    moves = park.plan((0, 0, 0), (20, 0, 0))
    assert moves == [(DRIVE, pytest.approx(20))]
    assert park.rotation_cost(moves) == 0


def test_target_directly_behind_reverses_instead_of_turning_around():
    """The headline case: 20 cm behind, same heading wanted.

    Turning around costs 180 out and 180 back. Backing up costs zero.
    """
    moves = park.plan((0, 0, 0), (-20, 0, 0))
    assert moves == [(DRIVE, pytest.approx(-20))]
    assert park.rotation_cost(moves) == 0


def test_reverse_branch_beats_forward_branch_on_rotation():
    # Target behind and to one side, final heading unchanged.
    start, target = (0, 0, 0), (-20, 5, 0)
    moves = park.plan(start, target)
    # Whatever it chose, it must be cheaper than the naive nose-first
    # plan through the same point.
    turn1, drive, face = park._leg(start, (-20, 5), reverse=False)
    forward_cost = abs(turn1) + abs(park.wrap(0 - face))
    assert park.rotation_cost(moves) < forward_cost
    # And it must actually be driving backwards.
    assert any(k == DRIVE and v < 0 for k, v in moves)


def test_plan_actually_reaches_the_target_on_a_perfect_robot():
    for start, target in [
        ((0, 0, 0), (30, 40, 90)),
        ((10, -5, 170), (-25, 12, -60)),
        ((50, 30, 180), (-50, -30, 0)),
        ((-12, 7, -90), (-12, 30, 45)),
    ]:
        end = park.apply(start, park.plan(start, target))
        assert end[0] == pytest.approx(target[0], abs=0.5)
        assert end[1] == pytest.approx(target[1], abs=0.5)
        assert park.wrap(end[2] - target[2]) == pytest.approx(0, abs=1.0)


def test_small_heading_residual_is_absorbed_not_pivoted_away():
    """A sub-tolerance aim error must NOT buy itself a pivot.

    This is the stakeholder's own framing: don't crawl back to kill 3
    degrees, carry it into the next move.
    """
    # 0.5 deg off, target straight ahead along the CURRENT heading.
    moves = park.plan((0, 0, 0.5), (20, 0, 0.5), head_tol=1.0)
    assert all(k != PIVOT for k, _ in moves)


def test_rotation_bias_hurts_the_forward_plan_more_than_the_reverse_one():
    """With a biased pivot, fewer degrees commanded == less error.

    vevov over-rotates ~0.9%; feed that to apply() and compare the two
    approaches to the same target. This is the whole argument for the
    reverse branch, reduced to a number.
    """
    SLIP = 1.009
    start, target = (0, 0, 0), (-25, 3, 0)

    chosen = park.plan(start, target)
    turn1, drive, face = park._leg(start, (-25, 3), reverse=False)
    naive = [(PIVOT, turn1), (DRIVE, drive), (PIVOT, park.wrap(0 - face))]

    end_chosen = park.apply(start, chosen, slip=SLIP)
    end_naive = park.apply(start, naive, slip=SLIP)

    err = lambda p: math.hypot(p[0] - target[0], p[1] - target[1])
    assert park.rotation_cost(chosen) < park.rotation_cost(naive)
    assert err(end_chosen) < err(end_naive)
    # NOT a strict heading win, and the reason is worth knowing: the
    # naive plan's two pivots are equal and opposite, so a SCALE error
    # (slip) multiplies both by the same factor and cancels exactly --
    # it lands on the right heading having driven in the wrong
    # direction. Position is where that plan pays. A constant
    # per-pivot OFFSET error would not cancel, and then fewer pivots
    # wins on heading too.
    assert abs(park.wrap(end_chosen[2] - target[2])) <= \
        abs(park.wrap(end_naive[2] - target[2])) + 1e-9


def test_pure_cross_track_offset_still_gets_corrected():
    """A sideways-only error cannot be closed by driving; it must plan."""
    moves = park.plan((0, 0, 0), (0, 10, 0))
    assert moves, 'a 10 cm sideways error must not be silently ignored'
    end = park.apply((0, 0, 0), moves)
    assert math.hypot(end[0], end[1] - 10) == pytest.approx(0, abs=0.5)


def test_cross_tol_never_swallows_more_than_pos_tol():
    """The no-pivot shortcut must not quietly accept a worse position."""
    moves = park.plan((0, 0, 0), (0, 5, 0), pos_tol=0.5, cross_tol=0.4)
    assert moves, 'a 5 cm cross-track error is not within tolerance'


def test_position_within_tolerance_is_a_pure_heading_job():
    """Standing on the target with a heading error costs ONE pivot.

    Regression for a hardware-observed defect: 0.24 cm from target with
    6 deg of heading error, the planner fell through to the approach
    logic, aimed at a target it was already standing on (a bearing that
    is pure noise at that range), and planned two pivots totalling
    106 deg. The correct plan is a single 6 deg pivot.
    """
    moves = park.plan((-44.85, -0.18, 6.02), (-45.0, 0.0, 0.0),
                      pos_tol=1.5, head_tol=2.0)
    assert len(moves) == 1
    kind, v = moves[0]
    assert kind == PIVOT
    assert v == pytest.approx(-6.02, abs=0.01)
    assert park.rotation_cost(moves) < 10


def test_no_move_is_ever_planned_toward_a_sub_tolerance_bearing():
    """Across a sweep of tiny offsets, rotation must stay bounded.

    Any plan that spends more than the heading error itself is aiming at
    bearing noise.
    """
    for dx in (-0.3, -0.05, 0.0, 0.05, 0.3):
        for dy in (-0.3, 0.0, 0.3):
            for herr in (-20.0, -5.0, 5.0, 20.0):
                moves = park.plan((dx, dy, herr), (0.0, 0.0, 0.0),
                                  pos_tol=1.5, head_tol=2.0)
                assert park.rotation_cost(moves) <= abs(herr) + 1e-6, (
                    f'offset ({dx},{dy}) herr {herr} planned '
                    f'{park.rotation_cost(moves):.1f} deg')
