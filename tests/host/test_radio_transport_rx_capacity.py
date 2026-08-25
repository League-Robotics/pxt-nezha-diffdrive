"""tests/host/test_radio_transport_rx_capacity.py -- host test for
src/radio_transport.h's radioRxLineFits() (sprint 010 ticket 001,
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
onDatagram() itself, and RadioTransport's rxLine_/rxOversizeDropped_
bookkeeping around it, are review-verified only -- see
radio_transport.cpp's onDatagram() for that wiring.

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
    return loaded


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
