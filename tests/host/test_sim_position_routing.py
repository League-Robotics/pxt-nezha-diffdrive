"""tests/host/test_sim_position_routing.py -- which verbs reach the
brick's own position loop (frame op 0x70) and which stay on the kernel's
duty path (frame op 0x60), read off the simulated brick's frame log.

The engine (`MotionEngine`) does the routing from `position_mode`
(`setPositionMode()`): 0 never, 1 pure straights and pivots, 2 arcs too;
`wheelsV()` is a velocity command and never goes. The driver here is the
whole-stack simulator (`sim_robot_shim.cpp`), whose bus models the opcode
map in docs/knowledge/2026-10-27-nezha-brick-opcodes.md. Nothing here is
a hardware result.

Frame layout in the bus log: FF F9 <port> <dir> <op> <hi> <mode> <lo>.
"""

import ctypes
import math

import pytest

from sim_tour import _TICK_US, SQUARE, SimRobot, _bind, build

OP_MOVE = 0x70
OP_DUTY = 0x60
PORTS = (1, 2)


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    f = _bind(build(tmp_path_factory.mktemp("position_routing")))
    P, F, I = ctypes.c_void_p, ctypes.c_float, ctypes.c_int
    f.srPositionMoveActive.argtypes = [P]
    f.srPositionMoveActive.restype = I
    f.srIsDriving.argtypes = [P]
    f.srIsDriving.restype = I
    return f


class Rig(SimRobot):
    def op_count(self, op):
        buf = (ctypes.c_uint8 * 8)()
        n = 0
        for i in range(self.f.srBusFrameCount(self.h)):
            assert self.f.srBusFrame(self.h, i, buf)
            if buf[4] == op:
                n += 1
        return n

    def tick(self, n=1):
        for _ in range(n):
            self.f.srTick(self.h, _TICK_US)

    def run_out(self, limit=1500):
        n = 0
        while self.f.srIsDriving(self.h) and n < limit:
            self.tick()
            n += 1
        self.tick(16)
        return n


def _rig(lib, mode):
    r = Rig(lib, position_mode=mode)
    r.tick(4)
    return r


def _moves(r, name):
    cruise = 150.0
    if name == "move_x_straight":
        r.f.srMoveX(r.h, 300.0, 0.0, cruise, 20000)
    elif name == "move_x_pivot":
        r.f.srMoveX(r.h, 0.0, math.radians(90.0), cruise, 20000)
    elif name == "move_x_arc":
        r.f.srMoveX(r.h, 300.0, math.radians(45.0), cruise, 20000)
    elif name == "wheels_x_straight":
        r.f.srWheelsX(r.h, 300.0, 300.0, cruise, 20000)
    elif name == "wheels_x_pivot":
        r.f.srWheelsX(r.h, -60.0, 60.0, cruise, 20000)
    elif name == "go_to_r_straight":
        r.f.srGoToR(r.h, 300.0, 0.0, cruise, 5.0, 20000)
    elif name == "go_to_r_arc":
        r.f.srGoToR(r.h, 300.0, 40.0, cruise, 5.0, 20000)
    else:
        raise AssertionError(name)


STRAIGHTS_AND_PIVOTS = ["move_x_straight", "move_x_pivot",
                        "wheels_x_straight", "wheels_x_pivot",
                        "go_to_r_straight"]
ARCS = ["move_x_arc", "go_to_r_arc"]


@pytest.mark.parametrize("name", STRAIGHTS_AND_PIVOTS)
@pytest.mark.parametrize("mode", [1, 2])
def test_straights_and_pivots_take_the_brick_loop(lib, name, mode):
    with _rig(lib, mode) as r:
        _moves(r, name)
        assert r.f.srPositionMoveActive(r.h) == 1
        r.run_out()
        assert r.op_count(OP_MOVE) >= 1
        for port in PORTS:
            assert r.f.srBusFrames60WhileLive(r.h, port) == 0
        assert r.f.srBusViolations1D(r.h) == 0


@pytest.mark.parametrize("name", STRAIGHTS_AND_PIVOTS + ARCS)
def test_mode_zero_never_sends_a_move_frame(lib, name):
    with _rig(lib, 0) as r:
        _moves(r, name)
        assert r.f.srPositionMoveActive(r.h) == 0
        r.run_out()
        assert r.op_count(OP_MOVE) == 0
        assert r.op_count(OP_DUTY) >= 1


@pytest.mark.parametrize("name", ARCS)
def test_arcs_take_the_brick_loop_only_in_mode_two(lib, name):
    with _rig(lib, 1) as r:
        _moves(r, name)
        assert r.f.srPositionMoveActive(r.h) == 0
        r.run_out()
        assert r.op_count(OP_MOVE) == 0
    with _rig(lib, 2) as r:
        _moves(r, name)
        assert r.f.srPositionMoveActive(r.h) == 1
        r.run_out()
        assert r.op_count(OP_MOVE) >= 1


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_wheels_v_never_takes_the_brick_loop(lib, mode):
    with _rig(lib, mode) as r:
        r.f.srWheelsV(r.h, 100.0, 100.0, 600)
        assert r.f.srPositionMoveActive(r.h) == 0
        r.tick(40)
        assert r.op_count(OP_MOVE) == 0
        assert r.op_count(OP_DUTY) >= 1


def test_ports_without_position_support_stay_on_the_kernel(lib):
    with _rig(lib, 2) as r:
        lib.srSetPositionMotors.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.srSetPositionMotors(r.h, 0)
        r.f.srMoveX(r.h, 300.0, 0.0, 150.0, 20000)
        assert r.f.srPositionMoveActive(r.h) == 0
        r.run_out()
        assert r.op_count(OP_MOVE) == 0
        assert r.op_count(OP_DUTY) >= 1


def test_tour_leg_in_mode_one_ends_within_a_quantum_or_two(lib):
    """The tour's first leg and a corner, run in position_mode 1."""
    with Rig(lib, position_mode=1) as r:
        r.move_x(1000.0, 0.0, 150.0)
        quantum_mm = 10.0 / r.cpm
        assert abs(r.x - 1000.0) <= 2.0 * quantum_mm + 1.0
        assert abs(r.y) <= 2.0 * quantum_mm + 1.0
        r.move_x(0.0, 90.0, 100.0)
        yaw_quantum_deg = math.degrees(
            quantum_mm / (0.5 * r.f.srEffectiveTrackWidth(r.h)))
        assert abs(r.heading_deg - 90.0) <= 2.0 * yaw_quantum_deg + 1.0
        assert r.op_count(OP_MOVE) >= 2
        for port in PORTS:
            assert r.f.srBusFrames60WhileLive(r.h, port) == 0


def test_square_tour_closes_in_mode_one(lib):
    """The eight-move square tour (sim_tour.SQUARE), every move on the
    brick loop: it comes home within a few quanta per move."""
    with Rig(lib, position_mode=1) as r:
        x0, y0, h0 = r.x, r.y, r.heading_deg
        for dist, rot, cruise in SQUARE:
            r.move_x(dist, rot, cruise)
        closure = math.hypot(r.x - x0, r.y - y0)
        net = (r.heading_deg - h0 + 540) % 360 - 180
        assert closure <= 8 * 2.0 * (10.0 / r.cpm) + 1.0
        assert abs(net) <= 8 * 2.0 * 1.5
        assert r.op_count(OP_MOVE) >= 2 * len(SQUARE)
        assert r.f.srBusViolations1D(r.h) == 0


# ---- shims.cpp is not host-compilable: pin the pieces that carry the
# routing to the block layer and the wire's done channel ----------------

import pathlib
import re

_SHIMS = (pathlib.Path(__file__).resolve().parents[2] / "src" /
          "shims.cpp").read_text()


def _body(signature):
    m = re.search(re.escape(signature) + r" \{(.*?)\n\}", _SHIMS, re.DOTALL)
    assert m, signature
    return m.group(1)


def test_position_mode_setter_reaches_the_engine():
    assert "r.engine.setPositionMode(r.positionMode);" in _body(
        "void cfgSetPositionMode(Rig& r, float v)")


def test_blocks_and_wire_keep_calling_the_routed_engine_verbs():
    # startMove (move/pivots/whileMoving), the wire's MOVE_X/WHEELS_X and
    # goTo's GO_TO_R all go through the engine calls that route.
    assert "r.engine.moveX(requestedDistance" in _body(
        "void startMove(int distance, int yaw, int speed, int yawRate)")
    assert "r.engine.wheelsX(" in _SHIMS
    assert "r.engine.goToR(" in _SHIMS


def test_done_and_moving_reads_include_a_live_position_move():
    assert "isPositionMoveActive()" in _body("bool engineMoveActive()")
    assert "isPositionMoveActive()" in _body("bool moving()")


def test_update_move_does_not_soft_stop_after_a_position_move():
    body = _body("bool updateMove()")
    assert "wasActive || r.engine.isPositionMoveActive()" in body
    assert "if (wasActive && !moveActive) r.softStop();" in body


def test_status_flag_reads_the_live_position_move():
    assert "case 41: return ensure().engine.isPositionMoveActive()" in _SHIMS
