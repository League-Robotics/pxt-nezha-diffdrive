"""Full motor-port regressions for the square-tour feedback transient."""

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
    closure, heading, moves, _, _ = square
    assert closure < 25.0
    assert abs(heading) < 2.0
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
    assert closure < 25.0
    assert abs(heading) < 2.0