"""tests/host/test_position_move_stop_paths.py -- every stop path hard-stops
a live position move (docs/knowledge/2026-10-27-nezha-brick-opcodes.md
section 3 rule 4, section 7a; stop table
docs/code-review/2026-10-27/data/mb_probe_stops1.csv).

`src/shims.cpp` cannot be compiled on the host (it includes pxt.h), so the
whole-stack simulator (`sim_robot_shim.cpp`) carries `srSoftStop` and
`srEstopAll`, which spell Rig::softStop() and estopAll() with the same
calls in the same order; source pins below tie shims.cpp to that shape.
The starvation watchdog is a fiber that calls Rig::softStop() once the
last tick is over 100 ms old, so "a live move plus 200 ms without a tick"
is: advance to a live move, let 200 ms pass with no tick, run that stop.
Nothing here is a hardware result.

Frame layout in the bus log: FF F9 <port> <dir> <op> <hi> <mode> <lo>.
"""

import ctypes
import pathlib
import re

import pytest

from sim_tour import _TICK_US, SimRobot, _bind, build

OP_HARD_STOP = 0x5F
OP_MOVE = 0x70
OP_DUTY = 0x60
PORTS = (1, 2)
ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    f = _bind(build(tmp_path_factory.mktemp("position_stop_paths")))
    P = ctypes.c_void_p
    f.srPositionMoveActive.argtypes = [P]
    f.srPositionMoveActive.restype = ctypes.c_int
    f.srSoftStop.argtypes = [P]
    f.srEstopAll.argtypes = [P]
    f.srSoftStopStaged.argtypes = [P]
    f.srDeliverStagedStop.argtypes = [P]
    f.srStop.argtypes = [P]
    f.srWheelPosition.argtypes = [P, ctypes.c_int]
    f.srWheelPosition.restype = ctypes.c_float
    return f


class Rig(SimRobot):
    def frames(self, start=0):
        buf = (ctypes.c_uint8 * 8)()
        out = []
        for i in range(start, self.f.srBusFrameCount(self.h)):
            assert self.f.srBusFrame(self.h, i, buf)
            out.append(tuple(buf))
        return out

    def tick(self, n=1):
        for _ in range(n):
            self.f.srTick(self.h, _TICK_US)

    def hard_stops(self, frames):
        return sorted(fr[2] for fr in frames if fr[4] == OP_HARD_STOP)


def _live(lib, mode=1, distance=1000.0):
    r = Rig(lib, position_mode=mode)
    r.tick(4)
    r.f.srMoveX(r.h, distance, 0.0, 150.0, 30000)
    assert r.f.srPositionMoveActive(r.h) == 1
    r.tick(6)
    return r


def _stop_via(name):
    return {"soft": "srSoftStop", "estop": "srEstopAll", "end": "srStop"}[name]


@pytest.mark.parametrize("path", ["soft", "estop", "end"])
def test_stop_path_hard_stops_both_ports_within_one_tick(lib, path):
    with _live(lib) as r:
        start = r.f.srBusFrameCount(r.h)
        getattr(r.f, _stop_via(path))(r.h)
        frames = r.frames(start)
        assert r.hard_stops(frames) == list(PORTS)
        assert r.f.srPositionMoveActive(r.h) == 0
        for port in PORTS:
            assert r.f.srBusMoveLive(r.h, port) == 0
        assert r.f.srBusViolations1D(r.h) == 0


def test_soft_stop_then_zero_after_hard_stop(lib):
    with _live(lib) as r:
        start = r.f.srBusFrameCount(r.h)
        r.f.srSoftStop(r.h)
        ops = [fr[4] for fr in r.frames(start)]
        # every 0x60 that follows lands after the hard stop on its port
        assert ops.count(OP_HARD_STOP) == 2
        first60 = [i for i, o in enumerate(ops) if o == OP_DUTY]
        last5f = max(i for i, o in enumerate(ops) if o == OP_HARD_STOP)
        assert all(i > last5f for i in first60) or not first60


def test_watchdog_equivalent_hard_stops_and_no_further_motion(lib):
    """200 ms without a tick (8+ ticks of 24 ms) then the watchdog's stop."""
    with _live(lib) as r:
        pos = [r.f.srWheelPosition(r.h, s) for s in (0, 1)]
        start = r.f.srBusFrameCount(r.h)
        r.f.srSoftStop(r.h)  # what the watchdog fiber runs
        assert r.hard_stops(r.frames(start)) == list(PORTS)
        after = r.f.srBusFrameCount(r.h)
        r.tick(12)  # 288 ms: the wheels coast to rest
        settled = [r.f.srWheelPosition(r.h, s) for s in (0, 1)]
        r.tick(12)
        assert [r.f.srWheelPosition(r.h, s) for s in (0, 1)] == settled
        # no motion command followed the stop
        assert [fr for fr in r.frames(after) if fr[4] in (OP_MOVE, OP_DUTY)] == []
        assert r.f.srBusViolations1D(r.h) == 0
        assert pos != settled  # the move had started


def test_held_bus_stage_writes_nothing_then_delivers_hard_stop(lib):
    with _live(lib) as r:
        start = r.f.srBusFrameCount(r.h)
        r.f.srSoftStopStaged(r.h)
        assert r.frames(start) == []  # another fiber owns the bus
        assert r.f.srPositionMoveActive(r.h) == 0
        r.f.srDeliverStagedStop(r.h)  # the bus holder's delivery
        assert r.hard_stops(r.frames(start)) == list(PORTS)
        assert r.f.srBusViolations1D(r.h) == 0


def test_stop_without_live_move_sends_no_hard_stop(lib):
    with Rig(lib, position_mode=0) as r:
        r.tick(4)
        start = r.f.srBusFrameCount(r.h)
        r.f.srSoftStop(r.h)
        r.f.srEstopAll(r.h)
        assert r.hard_stops(r.frames(start)) == []


def test_completed_move_then_stop_sends_no_second_hard_stop(lib):
    with _live(lib, distance=100.0) as r:
        n = 0
        while r.f.srPositionMoveActive(r.h) and n < 600:
            r.tick()
            n += 1
        r.tick(8)
        start = r.f.srBusFrameCount(r.h)
        r.f.srSoftStop(r.h)
        assert r.hard_stops(r.frames(start)) == []


# ---- source pins ---------------------------------------------------------

def _strip(text):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def test_fault_frame_covers_ports_one_to_four():
    src = _strip((ROOT / "src/platform/board_nezha.cpp").read_text())
    body = src.split("diffdrive_emergency_motor_stop() {", 1)[1]
    assert re.search(r"port\s*=\s*1\s*;\s*port\s*<=\s*4", body)
    assert not re.search(r"port\s*<=\s*2", body)


def test_soft_stop_stages_the_hard_stop_when_bus_is_held():
    src = _strip((ROOT / "src/shims.cpp").read_text())
    body = src.split("void Rig::softStop() {", 1)[1].split("\n}\n", 1)[0]
    assert "engine.endMoveStaged()" in body and "engine.endMove()" in body
    assert "pendingStop_ = true" in body
    assert "left.emergencyStop()" in body and "right.emergencyStop()" in body


def test_watchdog_stops_through_soft_stop_and_sees_position_moves():
    src = _strip((ROOT / "src/shims.cpp").read_text())
    dog = src.split("static void watchdogEntry(void* context) {", 1)[1].split("\n}\n", 1)[0]
    assert "r.softStop()" in dog
    assert "commandLooksActive" in dog
    hdr = _strip((ROOT / "src/motion/motion_engine.h").read_text())
    assert re.search(r"isDriving\(\)\s*const\s*\{[^}]*posMove_\.active", hdr)
