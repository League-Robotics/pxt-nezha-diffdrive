"""Full motor-port regressions for the square-tour feedback transient.

SCOPE. These run against `sim_tour.py`'s host model, whose plant
constants (`tau`, `breakaway`, `duty_vel_max`) are NOT fitted to any
robot -- its own docstring says so and says to use this tier for
MECHANISM, not for absolute values. So the closure/heading bounds below
are deliberately loose: they catch a profile that stops tracking or a
corner that accumulates error, and they must NOT be tightened onto
whatever the current model happens to produce.

That distinction is not academic. The model's `tau` EQUALS the
configured `lag`, so any change that credits the arrival predicate with
a full `vAct` coast is flattered here by construction -- the coast the
model delivers is exactly the coast such a form assumes. A `(lag > 0 ?
vAct : vNext) * dt` pipeline term scored 4.8-17.0 mm closure on this
model while costing 1.8 deg per 90 deg pivot on real hardware (MEASURED
tovez 2026-09-06, reports/square-hw-vs-sim-20260906/pivot-cruise-ab.json
vs ...-PREMERGE.json). Tight absolute bounds here would have locked that
regression in. Real drivetrains stop far faster than a first-order lag
near the speed floor; this model cannot represent that, and no threshold
in this file should pretend otherwise.
"""

import pytest

from sim_tour import _bind, build, run_square


@pytest.fixture(scope="module")
def simulation(tmp_path_factory):
    return _bind(build(tmp_path_factory.mktemp("profile_tracking")))


@pytest.fixture(scope="module", params=[0.0, 800.0], ids=["trapezoid", "jerk-limited"])
def square(simulation, request):
    return run_square(simulation, jerk=request.param)


def test_pivots_do_not_reverse_before_completion(square):
    _, _, moves, trace, bounds = square
    for move, (begin, end) in zip(moves, bounds):
        if not move["cmd_rot"]:
            continue
        pivot = trace[begin:end]
        turning = False
        for sample in pivot:
            twist = (sample[2] - sample[1]) * 0.5
            turning = turning or twist > 25.0
            if turning and sample[8]:
                assert twist >= -5.0


def test_wheel_speed_tracks_segment_cruise(square):
    _, _, moves, _, _ = square
    for move in moves:
        cruise = 100.0 if move["cmd_rot"] else 150.0
        assert move["peak_l"] <= cruise * 1.10
        assert move["peak_r"] <= cruise * 1.10


def test_square_closes_without_accumulating_corner_error(square):
    """Corner error must not ACCUMULATE. The per-pivot bound is the real
    assertion; the closure/heading bounds are model-slack (see module
    docstring) and exist only to catch gross divergence."""
    closure, heading, moves, _, _ = square
    assert closure < 35.0
    assert abs(heading) < 3.5
    for move in moves:
        if move["cmd_rot"]:
            assert abs(move["dheading"] - move["cmd_rot"]) < 1.0


@pytest.mark.parametrize("jerk", [0.0, 800.0])
def test_move_completion_requires_rest_without_external_pause(simulation, jerk):
    closure, heading, _, trace, bounds = run_square(
        simulation, jerk=jerk, settle_ticks=0)
    for _, end in bounds:
        sample = trace[end - 1]
        assert sample[8] == 0
        assert abs(sample[1]) < 5.0
        assert abs(sample[2]) < 5.0
    # Model-slack bounds, not a fitted expectation -- see the module
    # docstring on why absolute numbers from this plant are not a
    # target to tighten onto.
    assert closure < 35.0
    assert abs(heading) < 3.5