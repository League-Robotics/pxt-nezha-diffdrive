"""tests/host/test_radio_transport_rx_capacity.py -- host test for
src/comms/radio_transport.h's radioRxLineFits() (sprint 010 ticket 001,
radio-rx-capacity-fragmentation.md): the pure accept/reject predicate
that replaces RadioTransport::onDatagram()'s old silent
truncate-and-accept of an over-length inbound line.

**Why this is the only host-testable proxy for the fix.**
radio_transport.cpp includes pxt.h (uBit.radio, PacketBuffer), so
RadioTransport::onDatagram() itself -- the actual RX call site -- cannot
be compiled into any host test at all (src/DESIGN.md §1's layering
table). radio_transport.h, unlike its .cpp, has no CODAL dependency
(only <cstddef>/<cstdint>), so radioRxLineFits() -- the one piece of
this fix that IS pure logic -- can be. This suite exercises it directly
at the boundary values the ticket calls for: 0, 1, the buffer's own
240-byte capacity, 241 (one byte past it), and ~247 (the physical
single-fragment MTU ceiling -- MICROBIT_RADIO_MAX_PACKET_SIZE (250,
pxt.json's yotta config) minus the 3-byte [SEQ][FLAGS][LEN] fragment
header, radio_transport.cpp's own kMtu). Wiring the predicate into
onDatagram() itself, and RadioTransport's rxLine_ bookkeeping around
it, are review-verified only -- see radio_transport.cpp's onDatagram()
for that wiring.

**Also here: `radioRxClassify()` and `RadioRxCounters`.** The same
argument applies twice. onDatagram()'s remaining decision -- accept
this line, drop it as over-length, or drop it because the single RX
slot is still full -- and the four counters recording it are equally
free of CODAL, so they live beside radioRxLineFits() in the header and
are driven here directly. What stays review-verified is the call from
onDatagram() and Protocol's accessors surfacing the counters at diag
ordinals 31-34.

Run with::

    uv run pytest tests/host/test_radio_transport_rx_capacity.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

_SHIM_SOURCES = [_TEST_DIR / "radio_transport_rx_capacity_shim.cpp"]

# RadioTransport::rxLine_'s buffer capacity (radio_transport.h's private
# kMaxLineBytes) -- pinned here as a literal the same way
# test_wire_constants_drift.py pins RadioTransport::kMaxPayloadBytes at
# 200: radioRxLineFits() itself takes bufferCapacity as an explicit
# parameter (it knows nothing about any particular buffer), so this
# value is this test's own stand-in for "the real rxLine_ size", not
# something the predicate could look up on its own.
_RX_LINE_CAPACITY = 240

# Physical single-fragment payload ceiling: MICROBIT_RADIO_MAX_PACKET_SIZE
# (250, pxt.json's yotta.config) - kFrameHeaderBytes (3) = 247. Comfortably
# above _RX_LINE_CAPACITY, which is exactly why sprint 010's planning
# concluded no multi-fragment reassembly is needed -- a v6 line always
# arrives as one physical fragment.
_PHYSICAL_MTU = 247


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libradio_transport_rx_capacity_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.radioTransportRxLineFits.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    loaded.radioTransportRxLineFits.restype = ctypes.c_int
    loaded.radioRxCountersNew.argtypes = []
    loaded.radioRxCountersNew.restype = ctypes.c_void_p
    loaded.radioRxCountersFree.argtypes = [ctypes.c_void_p]
    loaded.radioRxCountersFree.restype = None
    loaded.radioRxClassify.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int]
    loaded.radioRxClassify.restype = ctypes.c_int
    for name in ("radioRxFrames", "radioRxAccepted",
                 "radioRxOversizeDropped", "radioRxOverrunDropped"):
        getattr(loaded, name).argtypes = [ctypes.c_void_p]
        getattr(loaded, name).restype = ctypes.c_uint
    for name in ("radioRxDispositionCodeAccept",
                 "radioRxDispositionCodeOversize",
                 "radioRxDispositionCodeOverrun"):
        getattr(loaded, name).argtypes = []
        getattr(loaded, name).restype = ctypes.c_int
    return loaded


class Counters:
    """One accumulating RadioRxCounters, driven line by line."""

    def __init__(self, lib):
        self._l = lib
        self.h = lib.radioRxCountersNew()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._l.radioRxCountersFree(self.h)
        return False

    def arrive(self, declared_len, slot_busy=False,
               capacity=None):
        capacity = _RX_LINE_CAPACITY if capacity is None else capacity
        return self._l.radioRxClassify(
            self.h, declared_len, capacity, 1 if slot_busy else 0)

    def totals(self):
        return {
            "frames": self._l.radioRxFrames(self.h),
            "accepted": self._l.radioRxAccepted(self.h),
            "oversize": self._l.radioRxOversizeDropped(self.h),
            "overrun": self._l.radioRxOverrunDropped(self.h),
        }


@pytest.fixture
def dispositions(lib):
    return {
        "accept": lib.radioRxDispositionCodeAccept(),
        "oversize": lib.radioRxDispositionCodeOversize(),
        "overrun": lib.radioRxDispositionCodeOverrun(),
    }


def _fits(lib, declared_len, capacity):
    return bool(lib.radioTransportRxLineFits(declared_len, capacity))


@pytest.mark.parametrize(
    "declared_len,expected",
    [
        (0, True),
        (1, True),
        (_RX_LINE_CAPACITY, True),  # exactly at capacity: accepted whole
        (_RX_LINE_CAPACITY + 1, False),  # one byte over: REJECTED, not truncated
        (_PHYSICAL_MTU, False),  # the physical single-fragment MTU ceiling
    ],
    ids=["0B", "1B", "240B-at-capacity", "241B-one-over", "247B-physical-mtu"],
)
def test_radio_rx_line_fits_boundary_values(lib, declared_len, expected):
    """radioRxLineFits() must accept any declared length up to and
    including the 240-byte rxLine_ capacity, and reject anything past
    it -- including the ~247-byte physical single-fragment MTU ceiling,
    the exact residual overflow band (radio-rx-capacity-fragmentation.md)
    this ticket closes by enlarging rxLine_ from 64 to 240 and rejecting
    (not truncating) what's still too big to fit."""
    assert _fits(lib, declared_len, _RX_LINE_CAPACITY) is expected


def test_radio_rx_line_fits_matches_le_comparison_across_a_sweep(lib):
    """Same property as above, exercised properly via the shared `lib`
    fixture: for a range of capacities and declared lengths straddling
    each one, radioRxLineFits() must agree exactly with
    declaredLen <= bufferCapacity."""
    for capacity in (0, 1, 64, 200, _RX_LINE_CAPACITY):
        for declared_len in range(0, capacity + 3):
            expected = declared_len <= capacity
            got = _fits(lib, declared_len, capacity)
            assert got == expected, (
                f"radioRxLineFits({declared_len}, {capacity}) returned "
                f"{got}, expected {expected}"
            )


# ---------------------------------------------------------------------------
# radioRxClassify(): the disposition, and the counters behind it
# ---------------------------------------------------------------------------
#
# Two of these counters (`frames`, `accepted`) sat in RadioTransport for
# a long time as members nothing ever incremented and nothing ever read,
# so "did the radio drop anything" had a permanent, confident answer of
# zero. The single-slot drop -- the one that actually happens, whenever
# two datagrams land inside one 24 ms tick -- was not counted at all.
#
# radioRxClassify() is the whole of that decision, and it has no CODAL
# in it. Wiring it into onDatagram(), and Protocol's accessors onto
# diag ordinals 31-34, are review-verified only, for the same reason
# this file's docstring already gives for radioRxLineFits().


def test_a_line_that_fits_an_idle_slot_is_accepted_and_counted(
        lib, dispositions):
    with Counters(lib) as c:
        assert c.arrive(100) == dispositions["accept"]
        assert c.totals() == {
            "frames": 1, "accepted": 1, "oversize": 0, "overrun": 0}


def test_a_line_arriving_on_a_busy_slot_is_an_overrun_drop(lib, dispositions):
    """The drop that was silent: radio holds ONE inbound line, so a
    second datagram inside the same servicing window is refused. Nothing
    counted it, so a host whose commands vanished had no way to tell
    this from air loss."""
    with Counters(lib) as c:
        assert c.arrive(100, slot_busy=True) == dispositions["overrun"]
        assert c.totals() == {
            "frames": 1, "accepted": 0, "oversize": 0, "overrun": 1}


def test_an_over_length_line_is_an_oversize_drop(lib, dispositions):
    with Counters(lib) as c:
        assert c.arrive(_RX_LINE_CAPACITY + 1) == dispositions["oversize"]
        assert c.totals() == {
            "frames": 1, "accepted": 0, "oversize": 1, "overrun": 0}


def test_over_length_wins_over_busy(lib, dispositions):
    """Capacity is judged before occupancy, deliberately: a line too long
    to fit is too long whatever the slot was doing, and the two are not
    equally fixable (one is the sender's line, the other is the drain's
    pace). Pinned so the ordering is a decision, not an accident."""
    with Counters(lib) as c:
        assert c.arrive(_PHYSICAL_MTU, slot_busy=True) == dispositions["oversize"]
        assert c.totals()["oversize"] == 1
        assert c.totals()["overrun"] == 0


def test_every_arrival_is_counted_exactly_once_somewhere(lib, dispositions):
    """The invariant a bench operator reads these four numbers by:
    frames is everything that arrived, and accepted + the two drop
    counts account for all of it. A path out of the classifier that
    counted nothing would break this."""
    with Counters(lib) as c:
        arrivals = [
            (10, False), (10, True), (_RX_LINE_CAPACITY, False),
            (_RX_LINE_CAPACITY + 1, False), (0, False), (241, True),
            (240, True), (1, False),
        ]
        for declared_len, busy in arrivals:
            c.arrive(declared_len, slot_busy=busy)
        t = c.totals()
        assert t["frames"] == len(arrivals)
        assert t["accepted"] + t["oversize"] + t["overrun"] == t["frames"]
        assert t["accepted"] == 4     # 10, 240, 0, 1 -- all fit, slot idle
        assert t["overrun"] == 2      # 10 and 240, slot busy
        assert t["oversize"] == 2     # 241 twice


def test_a_zero_length_line_still_counts_as_a_frame(lib, dispositions):
    """An empty line is a legal thing to receive (a bare delimiter), and
    it is still an arrival -- silently not counting it would make frames
    disagree with what the radio actually heard."""
    with Counters(lib) as c:
        assert c.arrive(0) == dispositions["accept"]
        assert c.totals()["frames"] == 1
