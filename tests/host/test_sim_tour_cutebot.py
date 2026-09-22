"""test_sim_tour_cutebot.py -- sprint 040 ticket 006's own CI-runnable
proof: `sim_tour.py --board cutebot-pro` invoked as a Python function
(`run_cutebot_square()`), not only as a documented manual command, per
this sprint's "every acceptance criterion is host-verifiable" hard
constraint.

SCOPE. This exercises `sim_cutebot_robot_shim.cpp`'s whole-stack
composition: the real `CutebotDevice`/`CutebotMotorPort`/
`CutebotTapAdapter`/`CutebotActuationPolicy` over a simulated 0x10 slave
(`sim_cutebot_bus.h`), under the real kernel and `MotionEngine`. Like
`test_sim_profile_tracking.py`'s own scope note: the plant constants are
UNVERIFIED (no Cutebot Pro has been fitted yet -- `SimCutebotRobot`'s
own docstring says so), so this proves MECHANISM (does the hybrid
policy hand off, does the tour still close under all three modes),
never a value for a real board.

`CUTEBOT_SQUARE`'s two cruises (250 mm/s legs, 100 mm/s pivots) straddle
the default 200 mm/s `onboard_floor` on purpose -- see its own comment
in `sim_tour.py` -- so this file's tests can assert BOTH halves of the
both-wheels eligibility gate on one tour: an 0x80 frame ships on an
eligible (above-floor) leg and never on an ineligible (below-floor) one.
"""

import pytest

from sim_tour import (
    CUTEBOT_CLOSURE_PASS_MM,
    _bind_cutebot,
    build_cutebot,
    run_cutebot_square,
)


@pytest.fixture(scope="module")
def cutebot_lib(tmp_path_factory):
    return _bind_cutebot(build_cutebot(tmp_path_factory.mktemp("sim_cutebot")))


@pytest.fixture(scope="module", params=[0, 1, 2], ids=["pid0", "pid1", "pid2"])
def cutebot_tour(cutebot_lib, request):
    """One CUTEBOT_SQUARE tour per `onboard_pid` mode -- module-scoped
    and parametrized so a run failure names the mode without re-running
    the other two, and so the three modes' numbers can be compared
    directly in one pytest session."""
    return run_cutebot_square(cutebot_lib, onboard_pid=request.param)


def test_tour_runs_to_completion_at_every_onboard_pid(cutebot_tour):
    """AC1: no crash, no host-side exception, at onboard_pid 0, 1, 2 --
    simply reaching this assertion after the fixture built the tour
    proves it; the closure/heading fields must also be finite numbers,
    not NaN from a divide-by-zero in the pose integration."""
    import math
    assert math.isfinite(cutebot_tour["closure_mm"])
    assert math.isfinite(cutebot_tour["net_heading_deg"])


def test_tour_closes_at_every_onboard_pid(cutebot_tour):
    """AC2: the tour returns to within the existing host-sim pass bar
    (CUTEBOT_CLOSURE_PASS_MM -- see that constant's own comment for why
    it reuses test_sim_profile_tracking.py's 160 mm bound rather than a
    freshly invented one) of its start pose, at all three modes -- a
    failure specific to one mode points at the policy or the sim
    onboard loop, not the port ticket 002 already proved."""
    assert cutebot_tour["closure_mm"] < CUTEBOT_CLOSURE_PASS_MM, cutebot_tour


def test_mode0_ships_only_pwm(cutebot_lib):
    """Mode 0 is the control case (design doc: "pure A, proving ticket
    002's work end-to-end through a real move sequence"): zero 0x80
    frames across the whole tour, on every leg."""
    result = run_cutebot_square(cutebot_lib, onboard_pid=0)
    assert result["onboard_frames"] == 0
    assert result["handoffs"] == 0
    for move in result["per_move"]:
        assert move["onboard_frames"] == 0, move


@pytest.mark.parametrize("onboard_pid", [1, 2], ids=["pid1", "pid2"])
def test_hybrid_modes_ship_onboard_above_floor_and_never_below(
    cutebot_lib, onboard_pid
):
    """Both wheels' eligibility gate, proven per-leg rather than only in
    aggregate: CUTEBOT_SQUARE's straight legs cruise at 250 mm/s (above
    the 200 mm/s default onboard_floor) and its pivots at 100 mm/s
    (below it, on BOTH wheels -- a pivot's two wheels share one
    magnitude). Modes 1 and 2 must ship at least one 0x80 frame on
    every above-floor leg and exactly zero on every below-floor one --
    an arc with one wheel under the floor would need the same
    "never split the pair" guarantee ticket 004 already proved in
    isolation (test_cutebot_actuation_policy.py); this is that
    guarantee exercised through a real tour instead of a synthetic
    tick."""
    result = run_cutebot_square(cutebot_lib, onboard_pid=onboard_pid)
    assert result["onboard_frames"] > 0
    for move in result["per_move"]:
        if move["cruise"] >= 200.0:
            assert move["onboard_frames"] > 0, move
        else:
            assert move["onboard_frames"] == 0, move


def test_tour_ends_on_pwm_at_every_onboard_pid(cutebot_tour):
    """AC (this ticket's own scope item 2): the frame chosen on the
    final tick must be PWM/zero at rest, at every onboard_pid --
    CutebotActuationPolicy::decide() forces PWM on every neutral tick
    regardless of mode, so a tour (which always ends neutral) must never
    leave the simulated wheel servoing an onboard setpoint after the
    kernel itself has gone idle. "At rest" is checked directly too, not
    only inferred from the frame choice: the trace's own last sample
    (after the settle-tick coast `move_x()` always runs) must show both
    simulated wheels at zero velocity and zero applied duty."""
    assert cutebot_tour["final_onboard"] is False
    last = cutebot_tour["trace"][-1]
    _t, vl, vr, duty_l, duty_r, _x, _y, _h, active = last
    assert active == 0
    assert vl == pytest.approx(0.0, abs=1e-6)
    assert vr == pytest.approx(0.0, abs=1e-6)
    assert duty_l == pytest.approx(0.0, abs=1e-6)
    assert duty_r == pytest.approx(0.0, abs=1e-6)


def test_nezha_default_board_is_unchanged(tmp_path_factory):
    """AC3: sim_tour.py's existing --board-less invocation (Nezha)
    behaves identically to before --board existed. Proven two ways:
    parse_args() with no arguments defaults to board="nezha" with no
    Cutebot-only options forced on, and build()/run_square() (the
    functions the pre-existing test_sim_profile_tracking.py already
    imports and calls directly) still produce the same shape of result
    they always have -- this file does not re-run that suite; it only
    confirms this ticket's own refactor (build() -> _compile_lib())
    left build()'s public contract untouched."""
    from sim_tour import _bind, build, parse_args, run_square

    args = parse_args([])
    assert args.board == "nezha"

    lib = _bind(build(tmp_path_factory.mktemp("sim_robot_unchanged")))
    closure, net, moves, trace, bounds = run_square(lib)
    import math
    assert math.isfinite(closure)
    assert math.isfinite(net)
    assert len(moves) == 8
    assert len(bounds) == 8
    assert trace  # non-empty
