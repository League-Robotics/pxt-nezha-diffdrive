"""tests/host/test_reply_backpressure.py -- a WiFi reply waits for room
in the transmit ring instead of losing its tail.

WifiLink's transmit ring holds 8 lines (kTxSlots) and drops the newest
when full. FUNCS writes one `funcs <name>` line per registered function
in one go, so over WiFi everything after the eighth line was dropped
before it left the robot: the function list on a calibration image built
with pxt-nezha-diffdrive v1.20260912.8 always ended at `calx`, though
`cala`, `spin` and `diag` are in the image. Protocol::writeWifi() now
makes a REPLY line wait, bounded, for room while it pumps the link.

src/comms/protocol.cpp includes pxt.h and cannot be built here, so this
pins the wait itself -- src/comms/reply_backpressure.h's waitForTxRoom()
-- against a fake link, pump and clock. WifiLink's own drop-newest
contract stays pinned by test_wifi_link.py::test_send_queue_is_bounded_drop_newest.

Run with::

    uv run pytest tests/host/test_reply_backpressure.py
"""
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SHIM_SOURCES = [_TEST_DIR / "reply_backpressure_shim.cpp"]

SLOTS = 8  # WifiLink::kTxSlots


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = compile_shared_lib(tmp_path_factory, sources=_SHIM_SOURCES,
                              out_name="libreply_backpressure_shim.so")
    lib = ctypes.CDLL(str(path))
    lib.rbWaitForTxRoom.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.rbWaitForTxRoom.restype = ctypes.c_int
    return lib


def wait(lib, queued, pumps_per_drain=0, unready_after_pumps=0,
         ms_per_yield=2, budget=2000):
    pumps, yields, depth = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    room = lib.rbWaitForTxRoom(queued, SLOTS, pumps_per_drain,
                               unready_after_pumps, ms_per_yield, budget,
                               ctypes.byref(pumps), ctypes.byref(yields),
                               ctypes.byref(depth))
    return bool(room), pumps.value, yields.value, depth.value


def test_room_available_returns_at_once_without_pumping(lib):
    room, pumps, yields, depth = wait(lib, queued=SLOTS - 1)
    assert room
    assert (pumps, yields, depth) == (0, 0, SLOTS - 1)


def test_full_ring_waits_until_a_send_completes(lib):
    """The FUNCS case: the ring is full, the link keeps draining."""
    room, pumps, yields, depth = wait(lib, queued=SLOTS, pumps_per_drain=10)
    assert room
    assert depth == SLOTS - 1
    assert pumps == 10, "waits exactly until the first send completes"


def test_a_long_reply_keeps_every_line(lib):
    """Twenty lines into an eight-slot ring: each waits in turn, none is
    lost, because every wait ends with room for the next line."""
    queued = 0
    delivered = 0
    for _ in range(20):
        room, _, _, queued = wait(lib, queued=queued, pumps_per_drain=5)
        assert room
        queued += 1  # the line goes into the ring
        delivered += 1
    assert delivered == 20


def test_a_ring_that_never_drains_gives_up_at_the_budget(lib):
    room, pumps, yields, depth = wait(lib, queued=SLOTS, pumps_per_drain=0,
                                      ms_per_yield=2, budget=2000)
    assert not room
    assert depth == SLOTS
    assert yields == 1000, "2 ms per yield against a 2000 ms budget"
    assert pumps == yields


def test_a_link_that_drops_stops_the_wait_at_once(lib):
    room, pumps, yields, depth = wait(lib, queued=SLOTS, pumps_per_drain=0,
                                      unready_after_pumps=3, budget=2000)
    assert not room
    assert pumps == 3
    assert yields == 3
