"""tests/host/test_motion_engine_position_move.py -- sprint 042 ticket 006.

MotionEngine::beginPositionMove() (src/motion/motion_engine.cpp,
src/motion/position_move.h): a move run by the motors' own position
loops. Driven on the whole-stack simulator (`sim_robot_shim.cpp`): the
real NezhaMotorPort pair, kernel and engine over the simulated Nezha
brick (`sim_nezha_bus.h`), which models the opcodes of
docs/knowledge/2026-10-27-nezha-brick-opcodes.md. Nothing here is a
hardware result: the brick's dynamics are the simulator's fit to that
doc, not a new measurement.

Frame layout in the bus log: FF F9 <port> <dir> <op> <hi> <mode> <lo>;
op 0x5F is the hard stop, 0x60 the duty run, 0x1D must never appear.
"""

import ctypes
import math

import pytest

from sim_tour import _TICK_US, SimRobot, _bind, build

LEFT_PORT, RIGHT_PORT = 2, 1   # SimRobot default (tovez bake)
TICK_MS = _TICK_US / 1000.0


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    f = _bind(build(tmp_path_factory.mktemp("position_move")))
    P, F, I = ctypes.c_void_p, ctypes.c_float, ctypes.c_int
    f.srPositionMove.argtypes = [P, F, F, F, ctypes.c_uint32]
    f.srPositionMove.restype = I
    for n in ("srPositionMoveActive", "srPositionMoveArrived", "srIsDriving"):
        getattr(f, n).argtypes = [P]
        getattr(f, n).restype = I
    f.srSetPositionMotors.argtypes = [P, I]
    f.srEstop.argtypes = [P]
    f.srBlockWheel.argtypes = [P, I, I]
    f.srWheelPosition.argtypes = [P, I]
    f.srWheelPosition.restype = F
    return f


class Rig(SimRobot):
    def frames(self):
        out = []
        buf = (ctypes.c_uint8 * 8)()
        for i in range(self.f.srBusFrameCount(self.h)):
            assert self.f.srBusFrame(self.h, i, buf)
            out.append(bytes(buf))
        return out

    def count_op(self, op, port):
        return sum(1 for fr in self.frames() if fr[4] == op and fr[2] == port)

    def f60(self, port):
        return self.f.srBusFrames60(self.h, port)

    def pos(self, side):
        return self.f.srWheelPosition(self.h, side)

    def start(self, distance, rotation_deg, cruise=200.0, timeout=20000):
        return self.f.srPositionMove(self.h, distance, math.radians(rotation_deg),
                                     cruise, timeout)

    def tick(self):
        return self.f.srTick(self.h, _TICK_US)

    def run(self, limit=1200):
        n = 0
        while self.f.srPositionMoveActive(self.h) and n < limit:
            self.tick()
            n += 1
        return n

    def targets(self, distance, rotation_deg):
        """Ideal per-wheel counts from the segment maths (unrounded)."""
        cpm = self.f.srCountsPerMm(self.h)
        b = self.f.srEffectiveTrackWidth(self.h)
        d = distance * cpm
        y = math.radians(rotation_deg) * 0.5 * b * cpm
        return d - y, d + y


@pytest.fixture
def rig(lib):
    with Rig(lib) as r:
        for _ in range(4):
            r.tick()
        yield r


def _check_lands(rig, distance, rotation_deg):
    p0 = (rig.pos(0), rig.pos(1))
    f60 = (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT))
    assert rig.start(distance, rotation_deg) == 1
    assert rig.f.srIsDriving(rig.h) == 1
    ticks = rig.run()
    assert ticks < 1200, "move never completed"
    for _ in range(10):   # coast to rest
        rig.tick()
    wl, wr = rig.targets(distance, rotation_deg)
    assert abs((rig.pos(0) - p0[0]) - wl) <= 10.0
    assert abs((rig.pos(1) - p0[1]) - wr) <= 10.0
    assert rig.f.srPositionMoveArrived(rig.h) == 1
    assert rig.f.srIsDriving(rig.h) == 0
    # The kernel must not have staged a single 0x60 behind the latch.
    assert (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT)) == f60
    for port in (1, 2):
        assert rig.f.srBusFrames60WhileLive(rig.h, port) == 0
    assert rig.f.srBusViolations1D(rig.h) == 0
    return ticks


def test_straight_500mm_lands_within_a_quantum(rig):
    _check_lands(rig, 500.0, 0.0)


def test_pivot_90_degrees_lands_within_a_quantum(rig):
    _check_lands(rig, 0.0, 90.0)


def test_arc_300mm_45deg_lands_and_wheels_finish_together(rig):
    left_done = right_done = None
    p0 = (rig.pos(0), rig.pos(1))
    assert rig.start(300.0, 45.0) == 1
    n = 0
    while rig.f.srPositionMoveActive(rig.h) and n < 1200:
        rig.tick()
        n += 1
        if left_done is None and not rig.f.srBusMoveLive(rig.h, LEFT_PORT):
            left_done = n
        if right_done is None and not rig.f.srBusMoveLive(rig.h, RIGHT_PORT):
            right_done = n
    assert left_done is not None and right_done is not None
    # Both moves finish within one tick of each other (acceptance).
    assert abs(left_done - right_done) <= 1
    for _ in range(10):
        rig.tick()
    wl, wr = rig.targets(300.0, 45.0)
    assert abs((rig.pos(0) - p0[0]) - wl) <= 10.0
    assert abs((rig.pos(1) - p0[1]) - wr) <= 10.0
    assert rig.f.srPositionMoveArrived(rig.h) == 1


def _tick_until_inactive(rig, limit=200):
    for n in range(1, limit):
        rig.tick()
        if not rig.f.srPositionMoveActive(rig.h):
            return n
    raise AssertionError("position move never ended")


def _runs(rig):
    assert rig.start(500.0, 0.0) == 1
    for _ in range(6):
        rig.tick()
    assert rig.f.srPositionMoveActive(rig.h) == 1
    assert rig.count_op(0x5F, LEFT_PORT) == 0
    assert rig.count_op(0x5F, RIGHT_PORT) == 0


def test_cancel_hard_stops_both_ports_at_once(rig):
    _runs(rig)
    rig.f.srStop(rig.h)
    assert rig.f.srPositionMoveActive(rig.h) == 0
    assert rig.count_op(0x5F, LEFT_PORT) >= 1
    assert rig.count_op(0x5F, RIGHT_PORT) >= 1
    assert rig.f.srIsDriving(rig.h) == 0


def test_estop_hard_stops_both_ports_within_one_tick(rig):
    _runs(rig)
    rig.f.srEstop(rig.h)
    rig.tick()
    assert rig.f.srPositionMoveActive(rig.h) == 0
    assert rig.count_op(0x5F, LEFT_PORT) >= 1
    assert rig.count_op(0x5F, RIGHT_PORT) >= 1
    assert rig.f.srBusViolations1D(rig.h) == 0


def test_deadline_hard_stops_both_ports(rig):
    assert rig.start(500.0, 0.0, timeout=300) == 1
    n = _tick_until_inactive(rig)
    assert n * TICK_MS <= 300 + TICK_MS + 1
    assert rig.count_op(0x5F, LEFT_PORT) == 1
    assert rig.count_op(0x5F, RIGHT_PORT) == 1
    assert rig.f.srPositionMoveArrived(rig.h) == 0


def test_stall_ends_with_hard_stop_after_the_window(rig):
    rig.f.srBlockWheel(rig.h, 1, 1)
    rig.f.srBlockWheel(rig.h, 2, 1)
    assert rig.start(500.0, 0.0) == 1
    n = _tick_until_inactive(rig)
    # kernel stallWindow is unset in the sim: the engine's 500 ms default.
    assert 500 <= n * TICK_MS <= 500 + 2 * TICK_MS
    assert rig.count_op(0x5F, LEFT_PORT) == 1
    assert rig.count_op(0x5F, RIGHT_PORT) == 1
    assert rig.f.srPositionMoveArrived(rig.h) == 0


def test_starting_another_command_cancels_the_position_move(rig):
    _runs(rig)
    rig.f.srMoveX(rig.h, 100.0, 0.0, 100.0, 5000)
    assert rig.f.srPositionMoveActive(rig.h) == 0
    assert rig.count_op(0x5F, LEFT_PORT) >= 1
    assert rig.count_op(0x5F, RIGHT_PORT) >= 1
    assert rig.tick() == 1   # the segment is the live command now


def test_position_move_cancels_a_live_segment(rig):
    rig.f.srMoveX(rig.h, 200.0, 0.0, 100.0, 5000)
    for _ in range(3):
        rig.tick()
    assert rig.start(100.0, 0.0) == 1
    f60 = (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT))
    rig.run()
    for _ in range(10):
        rig.tick()
    # Had the segment survived it would keep writing 0x60 after the
    # position move; and the move must land its own 100 mm.
    assert (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT)) == f60
    assert rig.f.srIsDriving(rig.h) == 0


def test_unsupported_port_falls_back_to_the_kernel_segment(rig):
    rig.f.srSetPositionMotors(rig.h, 0)
    before = (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT))
    rig.start(100.0, 0.0, cruise=100.0)
    assert rig.f.srPositionMoveActive(rig.h) == 0
    assert rig.f.srIsDriving(rig.h) == 1   # the segment is live
    for _ in range(30):
        rig.tick()
    assert (rig.f60(LEFT_PORT), rig.f60(RIGHT_PORT)) != before
    assert rig.count_op(0x70, LEFT_PORT) == 0
