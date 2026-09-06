"""tests/host/test_transport_sink.py -- host test for
src/comms/transport_sink.h: `wireLineContentLength()` and the one
`TransportSink` all three transports are now reached through.

**What moved, and why this is testable at all.** `Protocol` used to
carry three hand-copied `Wire::Sink` subclasses (`SerialSink`,
`RadioSink`, `WifiSink`), each with the same one-line body: drop the
last byte, hand the rest to its own transport, which appends its own
delimiter. `protocol.cpp` includes `pxt.h` transitively, so none of
that was reachable from a host test -- three copies of an off-by-one
decision that nothing could execute. Consolidating them onto one
class in a header with no CODAL dependency (only `wire_handler.h`'s
`Sink` interface and `<cstddef>`) makes the decision executable here,
against the real code, through the same `Wire::Sink&` the wire stack
holds.

**What is still NOT covered, and must not be claimed.**
`SerialTransport`, `RadioTransport` and `Protocol` themselves include
`pxt.h` and cannot be compiled into any host test (src/DESIGN.md S1's
layering table). So the pairing of a sink with a particular transport,
`RadioTransport`'s enable/enabled gate, and the deletion of the
transports' two-writer guards are verified by code review only, first
exercised live at the next bench session -- src/DESIGN.md S6/S8's own
standing convention for this layer. This file covers the terminator
decision and the sink's own dispatch, and nothing beyond that.

Run with::

    uv run pytest tests/host/test_transport_sink.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

_SHIM_SOURCES = [_TEST_DIR / "transport_sink_shim.cpp"]

# The wire grammar's own line ceiling (Wire::WireHandler::kMaxLineBytes,
# and equal to both transports' own caps -- pinned four ways by
# test_wire_constants_drift.py). Used here as "the longest line the sink
# can ever be handed", the case where an off-by-one is most likely to
# overflow something rather than merely lose a byte.
_MAX_LINE_BYTES = 240


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libtransport_sink_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.transportSinkContentLength.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    loaded.transportSinkContentLength.restype = ctypes.c_size_t
    loaded.transportSinkCreate.argtypes = []
    loaded.transportSinkCreate.restype = ctypes.c_void_p
    loaded.transportSinkDestroy.argtypes = [ctypes.c_void_p]
    loaded.transportSinkDestroy.restype = None
    loaded.transportSinkWrite.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    loaded.transportSinkWrite.restype = None
    loaded.transportSinkLastContentLength.argtypes = [ctypes.c_void_p]
    loaded.transportSinkLastContentLength.restype = ctypes.c_size_t
    loaded.transportSinkWriteCount.argtypes = [ctypes.c_void_p]
    loaded.transportSinkWriteCount.restype = ctypes.c_size_t
    loaded.transportSinkOnWire.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    loaded.transportSinkOnWire.restype = ctypes.c_size_t
    return loaded


@pytest.fixture
def sink(lib):
    handle = lib.transportSinkCreate()
    yield handle
    lib.transportSinkDestroy(handle)


def _content_length(lib, line: bytes) -> int:
    return lib.transportSinkContentLength(line, len(line))


def _write(lib, handle, line: bytes):
    lib.transportSinkWrite(handle, line, len(line))


def _on_wire(lib, handle) -> bytes:
    buf = ctypes.create_string_buffer(1024)
    written = lib.transportSinkOnWire(handle, buf, len(buf))
    return buf.raw[:written]


# ---------------------------------------------------------------------------
# The pure decision: how much of a written line is content.


def test_terminated_line_loses_exactly_its_terminator(lib):
    """The ordinary case, and the reason a sink drops a byte at all:
    WireHandler terminates every line it writes, and the transport
    appends its own, so passing both through would double the '\\n'."""
    assert _content_length(lib, b"pong 12 #1\n") == len(b"pong 12 #1")


def test_unterminated_line_keeps_every_byte(lib):
    """The case each of the three old copies got wrong identically:
    they stripped the last byte without ever looking at it. A line that
    arrives WITHOUT its terminator -- a frame whose formatter ran out of
    buffer before it could append one -- must lose nothing, or a
    plausible, wrong number goes out in place of the right one.

    Producing such a line is the wire minors' own fix (a later ticket
    bounds the frame append and writes the '\\n' last); this seam is what
    makes handling one correct here regardless."""
    assert _content_length(lib, b"t 1 2 3") == len(b"t 1 2 3")


def test_crlf_line_keeps_its_carriage_return(lib):
    """Only the '\\n' is the terminator. A '\\r' before it is content:
    the transport re-appends exactly one '\\n', so a CRLF line goes out
    with the bytes it came in with rather than being silently
    rewritten."""
    assert _content_length(lib, b"ack #1\r\n") == len(b"ack #1\r")


def test_empty_line_does_not_underflow(lib):
    """Zero length must answer zero, not wrap around to SIZE_MAX -- the
    one input where a naive `length - 1` is not merely wrong but
    catastrophic."""
    assert _content_length(lib, b"") == 0


def test_lone_terminator_is_an_empty_line(lib):
    assert _content_length(lib, b"\n") == 0


def test_maximum_length_line_keeps_every_content_byte(lib):
    """A full-width line plus its terminator: the content is the whole
    240 bytes, nothing truncated off the end."""
    line = b"x" * _MAX_LINE_BYTES + b"\n"
    assert _content_length(lib, line) == _MAX_LINE_BYTES


def test_maximum_length_line_without_a_terminator_keeps_its_last_byte(lib):
    """The two failure modes meeting: a maximum-width line that lost its
    terminator on the way in must still deliver its final byte."""
    line = b"y" * _MAX_LINE_BYTES
    assert _content_length(lib, line) == _MAX_LINE_BYTES


# ---------------------------------------------------------------------------
# The sink itself, called through the Wire::Sink& the wire stack holds.


def test_sink_hands_the_transport_the_content_only(lib, sink):
    _write(lib, sink, b"hello nezha #1\n")
    assert lib.transportSinkWriteCount(sink) == 1
    assert lib.transportSinkLastContentLength(sink) == len(b"hello nezha #1")


def test_sink_round_trips_the_line_it_was_given(lib, sink):
    """End to end for the whole point of the strip: what the sink hands
    the transport, plus the single delimiter the transport appends, must
    be byte-identical to what WireHandler wrote."""
    line = b"t 1 -2 3000 #7\n"
    _write(lib, sink, line)
    assert _on_wire(lib, sink) == line


def test_sink_round_trips_an_unterminated_line_by_adding_one(lib, sink):
    """The same round trip for a line that arrived without its
    terminator: nothing is lost, and the transport's own delimiter
    completes it."""
    _write(lib, sink, b"t 1 -2 3000")
    assert _on_wire(lib, sink) == b"t 1 -2 3000\n"


def test_sink_round_trips_a_maximum_length_line(lib, sink):
    line = b"z" * _MAX_LINE_BYTES + b"\n"
    _write(lib, sink, line)
    assert _on_wire(lib, sink) == line


def test_sink_writes_an_empty_line_as_just_the_delimiter(lib, sink):
    """A degenerate empty write still reaches the transport -- once,
    with zero content bytes -- rather than being swallowed here. The
    transport's own delimiter is what goes out."""
    _write(lib, sink, b"\n")
    assert lib.transportSinkWriteCount(sink) == 1
    assert lib.transportSinkLastContentLength(sink) == 0
    assert _on_wire(lib, sink) == b"\n"


def test_sink_writes_once_per_line(lib, sink):
    """One call in, one transport write out: the transport owns line
    framing, so a sink must never split a line across writes (which
    would frame it as two lines) or coalesce two into one."""
    for i in range(4):
        _write(lib, sink, b"ack #%d\n" % i)
    assert lib.transportSinkWriteCount(sink) == 4
    assert _on_wire(lib, sink) == b"ack #3\n"
