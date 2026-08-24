"""tests/host/test_wire_grammar.py -- protocol v6 wire grammar mechanics
for src/wire_handler.{h,cpp}: line reassembly, tokenizing,
case-as-direction, and the grammar edge cases (240-byte line cap, lone
'\\r' stripping, blank-line handling) -- ticket 002's own scope -- PLUS
(sprint 003 ticket 003) golden wire vectors, both directions, for the
nine non-motion sequenced verbs this ticket wires up: ID, VER, STATUS,
HELP, GET, SET, TLM, STOP, RUN. HELLO/PING/ESTOP stay unsequenced
(protocol.md S8.3) and are exercised here exactly as ticket 002 left
them. The reliability layer's OWN state machine (the three-way id
classification, decode-failure-is-NAK, gap stalling/self-healing) is
tested separately in test_wire_reliability.py, which reuses this file's
`wire_lib` fixture and `WireGrammar` wrapper rather than duplicating the
ctypes binding table.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S2 (the grammar), S2.1 (case is
direction), S3.1 (feed() must survive being handed anything), S3.2
(parsing is split-in-place, no allocation), S6/S6.1 (the verb catalog
and outcome/error-code vocabulary), S8/S8.9 (the reliability layer).

Reuses ticket 001's compile_shared_lib() (test_kernel_harness.py)
against this ticket's own source list (wire_handler.cpp +
wire_grammar_shim.cpp) instead of inventing new build plumbing.

Run with::

    uv run pytest tests/host/test_wire_grammar.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "wire_handler.cpp",
    _TEST_DIR / "wire_grammar_shim.cpp",
]

# Wire::Result's DECLARATION-ORDER ordinal (wire_handler.h) -- NOT the
# wire error code resultCode() maps it to (see RESULT_UNIMPLEMENTED=5
# here vs. wire code 6, etc.). Mirrors radio-robot-lib/tests/protocol/
# test_protocol_harness.py's own RESULT_* constants.
RESULT_OK = 0
RESULT_UNKNOWN = 1
RESULT_BADARG = 2
RESULT_RANGE = 3
RESULT_FULL = 4
RESULT_UNIMPLEMENTED = 5
RESULT_NOTREADY = 6
RESULT_BUSY = 7

# Wire::DoneReason's DECLARATION-ORDER ordinal.
DONE_NONE = 0
DONE_STOP = 1
DONE_TIMEOUT = 2
DONE_ESTOP = 3
DONE_ABORTED = 4

_DONE_REASON_NAME = {
    DONE_NONE: "none",
    DONE_STOP: "stop",
    DONE_TIMEOUT: "timeout",
    DONE_ESTOP: "estop",
    DONE_ABORTED: "aborted",
}

# Wire::TlmMode's DECLARATION-ORDER ordinal.
TLM_OFF = 0
TLM_POSE = 1
TLM_FULL = 2
TLM_NOW = 3
TLM_AUTO = 4
TLM_BUFFER = 5


def _ack(n, last_done=0, reason=DONE_NONE):
    return f"ack {n} {last_done} {_DONE_REASON_NAME[reason]}\n".encode()


def _nack(n, last_done=0, reason=DONE_NONE):
    return f"nack {n} {last_done} {_DONE_REASON_NAME[reason]}\n".encode()


def _bind(lib):
    """Attach ctypes argtypes/restype for every wire_grammar_shim.cpp
    export. Mirrors radio-robot-lib/tests/protocol/
    test_protocol_harness.py's own binding conventions (phFeed/
    phSinkLength/phSinkRead's argtypes shape), widened (ticket 003) past
    ticket 002's original three-verb surface to the full WireMockAdapter
    surface both this file and test_wire_reliability.py share."""
    lib.wgCreate.argtypes = []
    lib.wgCreate.restype = ctypes.c_void_p
    lib.wgDestroy.argtypes = [ctypes.c_void_p]
    lib.wgDestroy.restype = None

    lib.wgFeed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wgFeed.restype = None

    lib.wgSendBanner.argtypes = [ctypes.c_void_p]
    lib.wgSendBanner.restype = None
    # Ticket 003: emitTelemetry(snapshot) now takes a Column array as
    # three parallel arrays (name/value/hex) plus a count -- see
    # wire_grammar_shim.cpp's own wgEmitTelemetry() comment for why
    # parallel arrays rather than a mirrored struct.
    lib.wgEmitTelemetry.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_int,
    ]
    lib.wgEmitTelemetry.restype = None
    lib.wgEmitReliability.argtypes = [ctypes.c_void_p]
    lib.wgEmitReliability.restype = None

    lib.wgMalformedCount.argtypes = [ctypes.c_void_p]
    lib.wgMalformedCount.restype = ctypes.c_uint32

    lib.wgSinkLength.argtypes = [ctypes.c_void_p]
    lib.wgSinkLength.restype = ctypes.c_int
    lib.wgSinkRead.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wgSinkRead.restype = ctypes.c_int
    lib.wgSinkClear.argtypes = [ctypes.c_void_p]
    lib.wgSinkClear.restype = None
    # Ticket 003: per-Sink::write()-call lengths, for byte-exact
    # ordering assertions independent of the concatenated buffer.
    lib.wgSinkWriteCount.argtypes = [ctypes.c_void_p]
    lib.wgSinkWriteCount.restype = ctypes.c_int
    lib.wgSinkWriteLength.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSinkWriteLength.restype = ctypes.c_int

    # ---- WireMockAdapter canned-response setup ----
    lib.wgSetIdentity.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p,
    ]
    lib.wgSetIdentity.restype = None
    lib.wgSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.wgSetNow.restype = None
    lib.wgSetStatus.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32,
        ctypes.c_char_p,
    ]
    lib.wgSetStatus.restype = None
    lib.wgSetGetOverride.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_float,
    ]
    lib.wgSetGetOverride.restype = None
    lib.wgSetStopResult.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetStopResult.restype = None
    lib.wgSetSetResult.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetSetResult.restype = None
    lib.wgSetTlmResult.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetTlmResult.restype = None
    lib.wgSetRunResult.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetRunResult.restype = None
    lib.wgSetRunHasResult.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetRunHasResult.restype = None
    lib.wgSetRunResultText.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.wgSetRunResultText.restype = None
    lib.wgSetLastDone.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.wgSetLastDone.restype = None
    lib.wgSetLastDoneReason.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wgSetLastDoneReason.restype = None

    # ---- WireMockAdapter call-log readback ----
    lib.wgEstopCalls.argtypes = [ctypes.c_void_p]
    lib.wgEstopCalls.restype = ctypes.c_int
    lib.wgStopCalls.argtypes = [ctypes.c_void_p]
    lib.wgStopCalls.restype = ctypes.c_int
    lib.wgLastStopId.argtypes = [ctypes.c_void_p]
    lib.wgLastStopId.restype = ctypes.c_uint32
    lib.wgLastStopImmediate.argtypes = [ctypes.c_void_p]
    lib.wgLastStopImmediate.restype = ctypes.c_int
    lib.wgGetCalls.argtypes = [ctypes.c_void_p]
    lib.wgGetCalls.restype = ctypes.c_int
    lib.wgSetCalls.argtypes = [ctypes.c_void_p]
    lib.wgSetCalls.restype = ctypes.c_int
    lib.wgLastSetValue.argtypes = [ctypes.c_void_p]
    lib.wgLastSetValue.restype = ctypes.c_float
    lib.wgLastSetId.argtypes = [ctypes.c_void_p]
    lib.wgLastSetId.restype = ctypes.c_uint32
    lib.wgLastSetNameMatches.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.wgLastSetNameMatches.restype = ctypes.c_int
    lib.wgTlmCalls.argtypes = [ctypes.c_void_p]
    lib.wgTlmCalls.restype = ctypes.c_int
    lib.wgLastTlmMode.argtypes = [ctypes.c_void_p]
    lib.wgLastTlmMode.restype = ctypes.c_int
    lib.wgRunCalls.argtypes = [ctypes.c_void_p]
    lib.wgRunCalls.restype = ctypes.c_int
    lib.wgLastRunNameMatches.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.wgLastRunNameMatches.restype = ctypes.c_int
    lib.wgLastRunArgc.argtypes = [ctypes.c_void_p]
    lib.wgLastRunArgc.restype = ctypes.c_int
    lib.wgLastRunArgMatches.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p,
    ]
    lib.wgLastRunArgMatches.restype = ctypes.c_int
    lib.wgIdentityCalls.argtypes = [ctypes.c_void_p]
    lib.wgIdentityCalls.restype = ctypes.c_int
    lib.wgNowCalls.argtypes = [ctypes.c_void_p]
    lib.wgNowCalls.restype = ctypes.c_int
    lib.wgStatusCalls.argtypes = [ctypes.c_void_p]
    lib.wgStatusCalls.restype = ctypes.c_int

    return lib


@pytest.fixture(scope="session")
def wire_lib(tmp_path_factory):
    """Compile wire_handler.cpp + wire_grammar_shim.cpp exactly once for
    the whole pytest session, reusing ticket 001's compile_shared_lib()
    against this ticket's own source list rather than the kernel's."""
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libwire_grammar_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class WireGrammar:
    """Thin Pythonic wrapper around one wgCreate()/wgDestroy() handle --
    keeps test bodies readable without bare ctypes calls everywhere,
    mirroring test_kernel_harness.py's own Kernel wrapper."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.wgCreate()

    def close(self):
        self._lib.wgDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def feed(self, data: bytes):
        self._lib.wgFeed(self._handle, data, len(data))

    def send_banner(self):
        self._lib.wgSendBanner(self._handle)

    def emit_telemetry(self, columns):
        """The telemetry frame (protocol.md S5.2, ticket 003):
        `columns` is an iterable of (name: bytes, value: int, hex:
        bool) triples, hand-built by the test -- this class has no
        robot state of its own to project (that is ticket 004's WireAdapter
        projection, a separate concern). Marshals the three fields into
        parallel ctypes arrays wgEmitTelemetry() expects."""
        count = len(columns)
        names = (ctypes.c_char_p * count)(*[c[0] for c in columns])
        values = (ctypes.c_int32 * count)(*[c[1] for c in columns])
        hex_flags = (ctypes.c_int * count)(*[1 if c[2] else 0 for c in columns])
        self._lib.wgEmitTelemetry(self._handle, names, values, hex_flags, count)

    def emit_reliability(self):
        """The reliability layer's own periodic emission (protocol.md
        S8.5) -- calling this with NO intervening feed() is exactly how
        a lost ack/nack is proven to self-heal with no timer of this
        class's own (see test_wire_reliability.py). Ticket 003 split
        this out of the old argument-less emitTelemetry() so it stays
        callable with no Snapshot involved at all (surviving `TLM
        OFF`)."""
        self._lib.wgEmitReliability(self._handle)

    @property
    def malformed_count(self):
        return self._lib.wgMalformedCount(self._handle)

    def set_identity(self, name: bytes, serial: bytes, drivetrain: bytes = b"",
                      profile: bytes = b"", version: bytes = b""):
        self._lib.wgSetIdentity(self._handle, name, serial, drivetrain,
                                 profile, version)

    def set_now(self, now: int):
        self._lib.wgSetNow(self._handle, now)

    def set_status(self, ready=False, active=False, conn_left=False,
                    conn_right=False, otos=False, wedge=False, flags=0,
                    tlm: bytes = b"off"):
        self._lib.wgSetStatus(self._handle, int(ready), int(active),
                               int(conn_left), int(conn_right), int(otos),
                               int(wedge), flags, tlm)

    def set_get_override(self, name: bytes, value: float):
        self._lib.wgSetGetOverride(self._handle, name, value)

    def set_stop_result(self, result: int):
        self._lib.wgSetStopResult(self._handle, result)

    def set_set_result(self, result: int):
        self._lib.wgSetSetResult(self._handle, result)

    def set_tlm_result(self, result: int):
        self._lib.wgSetTlmResult(self._handle, result)

    def set_run_result(self, result: int):
        self._lib.wgSetRunResult(self._handle, result)

    def set_run_has_result(self, has_result: bool):
        self._lib.wgSetRunHasResult(self._handle, int(has_result))

    def set_run_result_text(self, text: bytes):
        self._lib.wgSetRunResultText(self._handle, text)

    def set_last_done(self, last_done: int, reason: int = DONE_NONE):
        self._lib.wgSetLastDone(self._handle, last_done)
        self._lib.wgSetLastDoneReason(self._handle, reason)

    @property
    def estop_calls(self):
        return self._lib.wgEstopCalls(self._handle)

    @property
    def stop_calls(self):
        return self._lib.wgStopCalls(self._handle)

    @property
    def last_stop_id(self):
        return self._lib.wgLastStopId(self._handle)

    @property
    def last_stop_immediate(self):
        return bool(self._lib.wgLastStopImmediate(self._handle))

    @property
    def get_calls(self):
        return self._lib.wgGetCalls(self._handle)

    @property
    def set_calls(self):
        return self._lib.wgSetCalls(self._handle)

    @property
    def last_set_value(self):
        return self._lib.wgLastSetValue(self._handle)

    @property
    def last_set_id(self):
        return self._lib.wgLastSetId(self._handle)

    def last_set_name_matches(self, name: bytes) -> bool:
        return bool(self._lib.wgLastSetNameMatches(self._handle, name))

    @property
    def tlm_calls(self):
        return self._lib.wgTlmCalls(self._handle)

    @property
    def last_tlm_mode(self):
        return self._lib.wgLastTlmMode(self._handle)

    @property
    def run_calls(self):
        return self._lib.wgRunCalls(self._handle)

    def last_run_name_matches(self, name: bytes) -> bool:
        return bool(self._lib.wgLastRunNameMatches(self._handle, name))

    @property
    def last_run_argc(self):
        return self._lib.wgLastRunArgc(self._handle)

    def last_run_arg_matches(self, index: int, value: bytes) -> bool:
        return bool(self._lib.wgLastRunArgMatches(self._handle, index, value))

    @property
    def identity_calls(self):
        return self._lib.wgIdentityCalls(self._handle)

    @property
    def now_calls(self):
        return self._lib.wgNowCalls(self._handle)

    @property
    def status_calls(self):
        return self._lib.wgStatusCalls(self._handle)

    def take_sink(self) -> bytes:
        """Everything the sink has captured since the last call, as raw
        bytes -- then clears it."""
        length = self._lib.wgSinkLength(self._handle)
        if length == 0:
            return b""
        buf = ctypes.create_string_buffer(length)
        n = self._lib.wgSinkRead(self._handle, buf, length)
        assert n == length
        data = buf.raw[:length]
        self._lib.wgSinkClear(self._handle)
        return data

    def take_sink_writes(self) -> list:
        """Everything the sink has captured since the last call, as a
        LIST of separate bytes objects -- one per Sink::write() call, in
        order -- then clears it. Ticket 003: lets a test assert
        byte-exact ordering (e.g. thdr -> t -> ack/nack) on the actual
        call boundaries, not just on the concatenated buffer, so a bug
        that accidentally merged two writes into one would still be
        caught."""
        length = self._lib.wgSinkLength(self._handle)
        data = b""
        if length > 0:
            buf = ctypes.create_string_buffer(length)
            n = self._lib.wgSinkRead(self._handle, buf, length)
            assert n == length
            data = buf.raw[:length]
        count = self._lib.wgSinkWriteCount(self._handle)
        lengths = [self._lib.wgSinkWriteLength(self._handle, i) for i in range(count)]
        self._lib.wgSinkClear(self._handle)
        writes = []
        pos = 0
        for one_len in lengths:
            writes.append(data[pos:pos + one_len])
            pos += one_len
        assert pos == len(data)
        return writes


@pytest.fixture
def wg(wire_lib):
    with WireGrammar(wire_lib) as w:
        yield w


# ---------------------------------------------------------------------------
# HELLO / PING / ESTOP golden vectors, both directions.
# ---------------------------------------------------------------------------


def test_hello_replies_lowercase_banner(wg):
    wg.set_identity(b"testbot", b"SN001")
    wg.feed(b"HELLO\n")
    assert wg.take_sink() == b"device NEZHA2 robot testbot SN001\n"
    assert wg.malformed_count == 0


def test_hello_banner_matches_unsolicited_send_banner(wg):
    """HELLO's reply is byte-identical to the unsolicited boot banner
    (protocol.md S4/S6) -- proven by comparing the two paths directly
    against the same identity."""
    wg.set_identity(b"otherbot", b"SN999")
    wg.send_banner()
    unsolicited = wg.take_sink()
    wg.feed(b"HELLO\n")
    replied = wg.take_sink()
    assert unsolicited == replied == b"device NEZHA2 robot otherbot SN999\n"


def test_ping_replies_pong_with_adapter_now(wg):
    wg.set_now(38472)
    wg.feed(b"PING\n")
    assert wg.take_sink() == b"pong 38472\n"
    assert wg.malformed_count == 0


def test_estop_replies_bare_estop_and_invokes_adapter(wg):
    wg.feed(b"ESTOP\n")
    assert wg.take_sink() == b"estop\n"
    assert wg.estop_calls == 1
    assert wg.malformed_count == 0


@pytest.mark.parametrize("line", [b"ESTOP\n", b"ESTOP 1 2 3\n", b"ESTOP #5\n"])
def test_estop_is_maximally_forgiving_of_trailing_junk(wg, line):
    """protocol.md S8.3: ESTOP, ESTOP 1 2 3, and ESTOP #5 all execute
    and reply identically -- a panic stop must never be refused over a
    syntax nit."""
    wg.feed(line)
    assert wg.take_sink() == b"estop\n"
    assert wg.estop_calls == 1
    assert wg.malformed_count == 0


@pytest.mark.parametrize("line", [b"PING\n", b"PING #7\n", b"PING extra junk\n"])
def test_ping_is_maximally_forgiving_of_trailing_junk(wg, line):
    wg.set_now(111)
    wg.feed(line)
    assert wg.take_sink() == b"pong 111\n"
    assert wg.malformed_count == 0


def test_hello_with_trailing_field_is_wrong_arity_and_silently_malformed(wg):
    """HELLO's own arity is strict zero-fields (protocol.md S8.3) --
    unlike PING/ESTOP, a HELLO with a trailing field is wrong arity: it
    increments malformedCount() and produces NO reply (there is no
    ack/nack to anchor an err against, since HELLO is outside the
    sequence entirely)."""
    wg.feed(b"HELLO extra\n")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


# ---------------------------------------------------------------------------
# Case is direction (protocol.md S2.1) -- the security property.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [b"hello\n", b"ping\n", b"estop\n", b"pInG\n"],
)
def test_lowercase_led_verb_is_dropped_silently(wg, line):
    """A verb STARTING lowercase is another robot's reply on a shared
    channel and must be dropped SILENTLY -- no reply, and does NOT
    increment malformedCount() (protocol.md S2.1). "pInG" starts with a
    lowercase 'p' and is lowercase-led even though it isn't ALL
    lowercase -- only the first letter decides direction."""
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 0
    assert wg.estop_calls == 0


def test_a_reply_can_never_be_reread_as_a_command(wg):
    """The security property in one round trip: feed the exact bytes
    HELLO/PING/ESTOP's own replies would produce back into the handler
    and confirm none of them execute anything -- a reply can never
    parse as a command under this grammar (the flood scenario S2.1
    exists to close off structurally)."""
    for reply in (b"device NEZHA2 robot testbot SN001\n", b"pong 5\n", b"estop\n"):
        wg.feed(reply)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 0
    assert wg.estop_calls == 0


@pytest.mark.parametrize("line", [b"Ping\n", b"Hello\n", b"Estop\n"])
def test_verb_lookup_is_case_sensitive_for_unknown_mixed_case(wg, line):
    """A verb that isn't a recognized UPPERCASE command and doesn't
    start lowercase either is simply unrecognized -- malformed, not
    silently dispatched to a same-named verb under different casing.
    Each of these starts with an uppercase letter (so it is NOT the
    lowercase-led reply case above) but does not exactly match "PING"/
    "HELLO"/"ESTOP" byte-for-byte."""
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1
    assert wg.estop_calls == 0


# ---------------------------------------------------------------------------
# Run-of-spaces collapsing; leading/trailing whitespace ignored.
# ---------------------------------------------------------------------------


def test_leading_and_trailing_whitespace_on_the_line_is_ignored(wg):
    wg.set_now(7)
    wg.feed(b"   PING   \n")
    assert wg.take_sink() == b"pong 7\n"
    assert wg.malformed_count == 0


@pytest.mark.parametrize("spaces", [b" ", b"   ", b"        "])
def test_trailing_run_of_spaces_produces_no_extra_field_tokens(wg, spaces):
    """A run of trailing spaces after HELLO, with nothing following it,
    must not be tokenized into any field at all -- leading/trailing
    whitespace is ignored and a run of spaces is ONE separator, not one
    per space -- so HELLO still sees zero fields and replies its banner
    normally, regardless of how many trailing spaces preceded the
    newline."""
    wg.set_identity(b"spacer", b"SN7")
    wg.feed(b"HELLO" + spaces + b"\n")
    assert wg.take_sink() == b"device NEZHA2 robot spacer SN7\n"
    assert wg.malformed_count == 0


@pytest.mark.parametrize("spaces", [b" ", b"   ", b"        "])
def test_run_of_spaces_between_verb_and_field_collapses_to_one_separator(wg, spaces):
    """A run of N spaces between HELLO and a trailing field collapses to
    ONE separator (protocol.md S2/S3.2): HELLO is rejected as wrong
    arity regardless of how many spaces preceded the extra field."""
    wg.feed(b"HELLO" + spaces + b"EXTRA\n")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


# ---------------------------------------------------------------------------
# feed() / line reassembly (protocol.md S3.1).
# ---------------------------------------------------------------------------


def test_several_complete_lines_in_one_block(wg):
    wg.set_now(1)
    wg.feed(b"PING\nPING\nPING\n")
    assert wg.take_sink() == b"pong 1\npong 1\npong 1\n"
    assert wg.malformed_count == 0


def test_block_ending_mid_line_is_buffered_to_the_next_feed(wg):
    wg.set_now(2)
    wg.feed(b"PIN")
    assert wg.take_sink() == b""
    wg.feed(b"G\n")
    assert wg.take_sink() == b"pong 2\n"


def test_block_that_is_only_a_line_fragment_produces_no_reply(wg):
    wg.feed(b"HELLO")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 0


def test_fragment_split_byte_by_byte_across_many_feed_calls(wg):
    wg.set_identity(b"bytewise", b"SN42")
    for byte in b"HELLO\n":
        wg.feed(bytes([byte]))
    assert wg.take_sink() == b"device NEZHA2 robot bytewise SN42\n"


def test_lone_cr_immediately_before_lf_is_stripped(wg):
    wg.set_now(3)
    wg.feed(b"PING\r\n")
    assert wg.take_sink() == b"pong 3\n"
    assert wg.malformed_count == 0


def test_blank_line_is_ignored_silently_not_malformed(wg):
    wg.feed(b"\n")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 0


def test_all_whitespace_line_is_ignored_silently_not_malformed(wg):
    wg.feed(b"       \n")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 0


def test_overlong_line_is_discarded_to_next_newline_and_counted_malformed(wg):
    """protocol.md S2/S3.1: a line over the 240-byte cap (including the
    terminator) is discarded to the next '\\n' -- never truncated into a
    still-parseable prefix. A line built from a real "HELLO" prefix
    followed by 300 filler bytes proves this: if the handler instead
    truncated, this would risk dispatching a valid-looking HELLO; it
    must not, and no banner is ever sent."""
    overlong = b"HELLO " + b"x" * 300 + b"\n"
    wg.feed(overlong)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1
    # Recovery: the NEXT well-formed line dispatches normally, and the
    # discarded overlong line counted exactly once.
    wg.set_now(8)
    wg.feed(b"PING\n")
    assert wg.take_sink() == b"pong 8\n"
    assert wg.malformed_count == 1


def test_exactly_240_byte_line_is_accepted(wg):
    """The boundary itself: a line whose content + '\\n' is exactly
    kMaxLineBytes (240) must NOT be treated as overlong. PING is
    maximally forgiving of trailing content, so padding it out to
    exactly the cap must still dispatch normally."""
    wg.set_now(9)
    junk_len = 240 - len(b"PING ") - len(b"\n")
    line = b"PING " + b"x" * junk_len + b"\n"
    assert len(line) == 240
    wg.feed(line)
    assert wg.take_sink() == b"pong 9\n"
    assert wg.malformed_count == 0


def test_241_byte_line_is_overlong(wg):
    junk_len = 241 - len(b"PING ") - len(b"\n")
    line = b"PING " + b"x" * junk_len + b"\n"
    assert len(line) == 241
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


def test_ten_kb_blast_with_no_newline_never_crashes_and_is_not_yet_malformed(wg):
    """protocol.md S3.1's own adversarial example: feed() must survive a
    multi-KB blast with no terminator at all. Nothing has COMPLETED a
    line yet, so malformedCount() stays 0 until a '\\n' finally arrives
    -- at which point the whole overlong blast counts as exactly ONE
    malformed line, not one per discarded byte."""
    wg.feed(b"x" * 10_000)
    assert wg.malformed_count == 0
    assert wg.take_sink() == b""
    wg.feed(b"\n")
    assert wg.malformed_count == 1
    assert wg.take_sink() == b""
    # The handler recovers cleanly for the next line.
    wg.set_now(4)
    wg.feed(b"PING\n")
    assert wg.take_sink() == b"pong 4\n"
    assert wg.malformed_count == 1


# ---------------------------------------------------------------------------
# Embedded NULs -- must never crash. This file's own C-string-based
# characterization (protocol.md S9.4) is pinned exactly, matching
# radio-robot-lib's own reference behavior, plus one safety guard this
# file adds beyond the reference's own documented characterization (see
# wire_handler.cpp's onLineComplete()).
# ---------------------------------------------------------------------------


def test_embedded_nul_mid_verb_never_dispatches(wg):
    """"PI\\0NG\\n" -- the NUL truncates the verb to "PI" for every
    C-string comparison, which matches no known verb and isn't
    lowercase-led either, so it is simply malformed."""
    wg.feed(b"PI\x00NG\n")
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


def test_embedded_nul_immediately_after_verb_matches_bare_verb(wg):
    """Pinned characterization (radio-robot-lib/docs/design/protocol.md
    S9.4): every wire-touching comparison in this handler operates on
    NUL-terminated C strings (the no-allocation, no-std::string
    constraint, S3.2). strcmp()'s own forward scan stops at the first
    NUL, so "PING\\0extra" compares EQUAL to "PING" and dispatches
    exactly like a bare PING, silently discarding "extra" with no
    malformed-count increment. This is NOT a bug to fix here -- see
    wire_handler.h's own feed() doc comment."""
    wg.set_now(5)
    wg.feed(b"PING\x00extra\n")
    assert wg.take_sink() == b"pong 5\n"
    assert wg.malformed_count == 0


def test_embedded_nul_in_estop_trailing_junk_still_estops(wg):
    """ESTOP's own forgiveness means this one is unaffected by the NUL
    characterization either way -- included as an adversarial-set
    completeness check (embedded NULs) rather than a new behavior."""
    wg.feed(b"ESTOP\x00garbage\n")
    assert wg.take_sink() == b"estop\n"
    assert wg.estop_calls == 1


@pytest.mark.parametrize("line", [b"\x00PING\n", b"\x00\n", b"   \x00HELLO\n"])
def test_line_whose_first_non_space_byte_is_an_embedded_nul_is_malformed(wg, line):
    """Regression for a real memory-safety hazard found while writing
    this ticket's adversarial tests: a line whose first non-space byte
    IS an embedded NUL (e.g. "\\0PING\\n") is non-blank by the
    byte-by-byte "any non-space content" check, but tokenizeLine()'s own
    NUL-terminated-string view of that same buffer sees an EMPTY string
    at that position and returns zero tokens -- reading tokens[0] in
    that state would dereference an uninitialized pointer.
    wire_handler.cpp's onLineComplete() guards this explicitly: it is
    malformed, not silently dropped (it is not the grammar's own
    narrowly-defined blank-line/lowercase-reply exception), and above
    all it must never crash."""
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1
    assert wg.estop_calls == 0
    # The handler recovers cleanly for the next line.
    wg.set_now(6)
    wg.feed(b"PING\n")
    assert wg.take_sink() == b"pong 6\n"


def test_binary_garbage_never_crashes_the_handler(wg):
    """Arbitrary binary bytes, including every value 0-255, fed as one
    block with no structure at all -- feed() must survive it (protocol.md
    S3.1) without crashing, and a well-formed line after it must still
    dispatch normally."""
    garbage = bytes(range(256)) * 4
    wg.feed(garbage)
    wg.set_now(6)
    wg.feed(b"\nPING\n")
    tail = wg.take_sink()
    assert tail.endswith(b"pong 6\n")


# ---------------------------------------------------------------------------
# Sequenced verbs with NO id at all cannot be sequence-classified, so
# they are still simply malformed with no reply (protocol.md S8.4 items
# 1-2) -- unchanged by ticket 003's reliability layer. A well-formed id
# on an unrecognized verb (e.g. SEED/CAL -- explicitly deferred per
# sprint.md's Out of Scope) is a different case entirely: a DECODE
# FAILURE that nacks and errs (protocol.md S8.9) -- see
# test_wire_reliability.py's own decode-failure section for that
# behavior; it is not "silently malformed" any more.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", [b"ID\n", b"STATUS\n", b"NOTAVERB\n"])
def test_sequenced_verb_with_no_id_at_all_is_malformed_no_reply(wg, line):
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


def test_unrecognized_verb_with_id_is_a_decode_failure_not_silent(wg):
    """SEED/CAL are explicitly deferred (sprint.md Out of Scope) and so
    are still unrecognized by kCommandTable even after ticket 004 adds
    the six motion verbs -- WITH a well-formed in-order id, an
    unrecognized verb is a DECODE FAILURE (nack + err 1), not the silent
    malformed-with-no-reply ticket 002 left behind. (WHEELS_V and its
    five siblings were this same case before ticket 004 wired them in --
    see test_wire_motion_verbs.py for their own now-real dispatch.)"""
    wg.feed(b"SEED 100 100 #1\n")
    assert wg.take_sink() == _nack(1) + b"err 1 #1\n"
    assert wg.malformed_count == 1


# ---------------------------------------------------------------------------
# Golden wire vectors, both directions, for the nine non-motion sequenced
# verbs this ticket wires up: ID, VER, STATUS, HELP, GET, SET, TLM,
# STOP, RUN. Each includes its mandatory #<id> per protocol.md S8.
# ---------------------------------------------------------------------------


def test_id_golden_vector(wg):
    wg.set_identity(b"testbot", b"SN001", b"diffdrive", b"nezha2", b"6.0.0")
    wg.feed(b"ID #1\n")
    assert wg.take_sink() == _ack(1) + b"id diffdrive nezha2 6.0.0\n"
    assert wg.malformed_count == 0


def test_ver_golden_vector(wg):
    wg.set_identity(b"testbot", b"SN001", b"diffdrive", b"nezha2", b"6.0.0")
    wg.feed(b"VER #1\n")
    assert wg.take_sink() == _ack(1) + b"ver 6.0.0\n"


def test_status_golden_vector(wg):
    wg.set_status(ready=True, active=False, conn_left=True, conn_right=True,
                  otos=False, wedge=False, flags=0xA, tlm=b"pose")
    wg.feed(b"STATUS #1\n")
    assert wg.take_sink() == (
        _ack(1) +
        b"status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 "
        b"flags=a tlm=pose next=2\n"
    )


def test_help_golden_vector(wg):
    """Generated by walking kCommandTable, so it cannot drift from the
    dispatcher -- this exact 18-verb listing is ticket 004's own
    catalog: the original 12 (HELLO/PING/ESTOP unsequenced, ID/VER/
    STATUS/HELP/GET/SET/TLM/STOP/RUN sequenced) plus the six motion
    verbs (WHEELS_X/WHEELS_V/MOVE_X/MOVE_V/GO_TO_R/GO_TO_W) inserted
    between TLM and STOP, matching protocol.md S6's own canonical
    ordering. WHEELS does not appear anywhere in this listing --
    WHEELS_V is the only spelling."""
    wg.feed(b"HELP #1\n")
    assert wg.take_sink() == (
        _ack(1) +
        b"help HELLO PING ID VER STATUS HELP GET SET TLM WHEELS_X "
        b"WHEELS_V MOVE_X MOVE_V GO_TO_R GO_TO_W STOP ESTOP RUN\n"
    )


def test_get_bare_golden_vector_dumps_every_field(wg):
    """WireMockAdapter's default field table (wire_mock_adapter.h)."""
    wg.feed(b"GET #1\n")
    assert wg.take_sink() == (
        _ack(1) +
        b"get group.alpha 1.500000\n"
        b"get group.beta -2.250000\n"
        b"get group.gamma 0.000000\n"
        b"get group.delta 100.000000\n"
    )
    assert wg.get_calls == 4


def test_get_named_golden_vector(wg):
    wg.feed(b"GET group.beta #1\n")
    assert wg.take_sink() == _ack(1) + b"get group.beta -2.250000\n"


def test_get_unknown_name_acks_with_no_get_line(wg):
    wg.feed(b"GET nosuch.field #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.malformed_count == 0


def test_set_golden_vector(wg):
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.beta 3.5 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1
    assert wg.last_set_name_matches(b"group.beta")
    assert wg.last_set_value == pytest.approx(3.5)
    assert wg.last_set_id == 1


def test_tlm_golden_vector(wg):
    wg.feed(b"TLM POSE #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.tlm_calls == 1
    assert wg.last_tlm_mode == TLM_POSE


def test_stop_bare_golden_vector(wg):
    wg.set_stop_result(RESULT_OK)
    wg.feed(b"STOP #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.stop_calls == 1
    assert wg.last_stop_id == 1
    assert wg.last_stop_immediate is False


def test_stop_now_golden_vector(wg):
    wg.set_stop_result(RESULT_OK)
    wg.feed(b"STOP now #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.last_stop_immediate is True


def test_run_void_golden_vector(wg):
    wg.set_run_has_result(False)
    wg.feed(b"RUN blink 3 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.run_calls == 1
    assert wg.last_run_name_matches(b"blink")
    assert wg.last_run_argc == 1
    assert wg.last_run_arg_matches(0, b"3")


def test_run_with_return_value_golden_vector(wg):
    wg.set_run_has_result(True)
    wg.set_run_result_text(b"42")
    wg.feed(b"RUN getX #1\n")
    assert wg.take_sink() == _ack(1) + b"ret 42 #1\n"


# ---------------------------------------------------------------------------
# Sprint 004 ticket 001's own RX-routing acceptance criterion: a
# `RUN:pivot:180`-style line (the OLD colon-separated cleartext form,
# now carved out on radio too, alongside serial) still dispatches
# through the unchanged handleRun()/MessageBus bridge, never the v6
# grammar. Protocol::run() -- where the literal-prefix branch that
# makes this routing decision actually lives -- is CODAL-bound and has
# no host shim (protocol.h pulls in pxt.h transitively), so that
# routing decision itself is verified by code review, per the ticket's
# own testing plan (a direct structural mirror of serial's own,
# already-tested branch). What IS host-testable, and is checked here,
# is the other half of why that routing decision matters: this old
# form is not itself valid v6 grammar, so if a caller's routing ever
# skipped the prefix check, this line would NOT reach RUN's real
# onRun() effect the way the routing's target (handleRun()) does --
# unlike the space-separated `RUN <name> ... #<id>` form the golden
# vectors above exercise, it carries no mandatory trailing `#<id>` at
# all, so the reliability layer cannot even classify it.
# ---------------------------------------------------------------------------


def test_colon_form_legacy_run_is_not_v6_grammar(wg):
    wg.feed(b"RUN:pivot:180\n")
    assert wg.take_sink() == b""
    assert wg.run_calls == 0
    assert wg.malformed_count == 1


# ---------------------------------------------------------------------------
# Regression guard for ticket 001's own harness (per the ticket's
# Testing plan: "confirms this ticket did not break it").
# ---------------------------------------------------------------------------


def test_kernel_harness_still_importable():
    """Smoke check that this file's own import of test_kernel_harness
    (for compile_shared_lib()) doesn't break that module's collection --
    the real regression coverage is running both files together, e.g.
    `uv run pytest tests/host/ -k "kernel_harness or wire_grammar"`."""
    import test_kernel_harness  # noqa: F401
