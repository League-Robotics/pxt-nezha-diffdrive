"""tests/host/test_wire_motion_verbs.py -- sprint 003 ticket 004: the six
motion verbs' wire decode/dispatch (WHEELS_X, WHEELS_V, MOVE_X, MOVE_V,
GO_TO_R, GO_TO_W), src/wire_adapter.h's WireAdapter, and STOP's `now`
token.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S4 (the Adapter interface), S5
(the DiffDrive adapter -- WHEELS_V real, five kUnknown), S6/S6.1 (the
verb table, outcome codes), S9.10 item 1 (why kUnknown, not
kUnimplemented).
radio-robot-lib/docs/design/motion-api.md S1 (arguments/units), S9.1
(the wire mapping table).

Two fixtures, two different concerns (see wire_motion_verb_shim.cpp's
own header comment for the full rationale):

- `wv` -- WireHandler + WireMockAdapter: decode arity (golden vectors)
  and degenerate/malformed input (wrong field count, an unparseable
  numeric field) for all six verbs, plus proof that the five
  not-yet-wired verbs' own `err 1` (ERR_UNKNOWN) is a MERITS rejection
  (ack + err), never a decode failure (nack + err).
- `wa` -- WireHandler + the REAL WireAdapter + a REAL DiffDrive kernel
  over FakeMotor: WHEELS_V's real effect (commanded left/right map to
  the correct velocity/twist and lease), WireAdapter's own GET/SET
  field-name table, and STOP/ESTOP's real effect on the kernel.

Run with::

    uv run pytest tests/host/test_wire_motion_verbs.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "diffdrive.cpp",
    _SRC_DIR / "wire_handler.cpp",
    _SRC_DIR / "wire_adapter.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
]

# Wire::Result's DECLARATION-ORDER ordinal (wire_handler.h) -- NOT the
# wire error code resultCode() maps it to. Mirrors test_wire_grammar.py's
# own RESULT_* constants.
RESULT_OK = 0
RESULT_UNKNOWN = 1
RESULT_BADARG = 2
RESULT_RANGE = 3

# Wire::DoneReason's DECLARATION-ORDER ordinal.
DONE_NONE = 0
_DONE_REASON_NAME = {DONE_NONE: "none"}

# DiffDrive::DifferentialDrive::Status's DECLARATION order (src/diffdrive.h).
STATUS_OK = 0

LEFT = 0
RIGHT = 1


def _ack(n, last_done=0, reason=DONE_NONE):
    return f"ack {n} {last_done} {_DONE_REASON_NAME[reason]}\n".encode()


def _nack(n, last_done=0, reason=DONE_NONE):
    return f"nack {n} {last_done} {_DONE_REASON_NAME[reason]}\n".encode()


def _err(code, id_):
    return f"err {code} #{id_}\n".encode()


def _bind(lib):
    """Attach ctypes argtypes/restype for every wire_motion_verb_shim.cpp
    export -- both the WvHandle (wv*) and WaHandle (wa*) surfaces."""
    # ---- WvHandle: WireHandler + WireMockAdapter ----
    lib.wvCreate.argtypes = []
    lib.wvCreate.restype = ctypes.c_void_p
    lib.wvDestroy.argtypes = [ctypes.c_void_p]
    lib.wvDestroy.restype = None
    lib.wvFeed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wvFeed.restype = None
    lib.wvMalformedCount.argtypes = [ctypes.c_void_p]
    lib.wvMalformedCount.restype = ctypes.c_uint32
    lib.wvSinkLength.argtypes = [ctypes.c_void_p]
    lib.wvSinkLength.restype = ctypes.c_int
    lib.wvSinkRead.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wvSinkRead.restype = ctypes.c_int
    lib.wvSinkClear.argtypes = [ctypes.c_void_p]
    lib.wvSinkClear.restype = None

    for name in (
        "wvSetWheelsVResult", "wvSetWheelsXResult", "wvSetMoveXResult",
        "wvSetMoveVResult", "wvSetGoToRResult", "wvSetGoToWResult",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
        fn.restype = None

    for name in (
        "wvWheelsVCalls", "wvWheelsXCalls", "wvMoveXCalls", "wvMoveVCalls",
        "wvGoToRCalls", "wvGoToWCalls",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_int

    for name in (
        "wvLastWheelsVLeft", "wvLastWheelsVRight", "wvLastWheelsXLeft",
        "wvLastWheelsXRight", "wvLastWheelsXCruise", "wvLastMoveXDistance",
        "wvLastMoveXRotation", "wvLastMoveXCruise", "wvLastMoveVVx",
        "wvLastMoveVOmega", "wvLastGoToRX", "wvLastGoToRY",
        "wvLastGoToRSpeed", "wvLastGoToRArrive", "wvLastGoToWX",
        "wvLastGoToWY",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float

    for name in (
        "wvLastWheelsVDuration", "wvLastWheelsVId", "wvLastWheelsXTimeout",
        "wvLastMoveXTimeout", "wvLastMoveVDuration", "wvLastGoToRTimeout",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_uint32

    # ---- WaHandle: WireHandler + the real WireAdapter + a real kernel ----
    lib.waCreate.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.waCreate.restype = ctypes.c_void_p
    lib.waDestroy.argtypes = [ctypes.c_void_p]
    lib.waDestroy.restype = None
    lib.waFeed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waFeed.restype = None
    lib.waMalformedCount.argtypes = [ctypes.c_void_p]
    lib.waMalformedCount.restype = ctypes.c_uint32
    lib.waSinkLength.argtypes = [ctypes.c_void_p]
    lib.waSinkLength.restype = ctypes.c_int
    lib.waSinkRead.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waSinkRead.restype = ctypes.c_int
    lib.waSinkClear.argtypes = [ctypes.c_void_p]
    lib.waSinkClear.restype = None
    lib.waSetMaxDuty.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.waSetMaxDuty.restype = None
    lib.waSetFullDutyVelocity.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.waSetFullDutyVelocity.restype = None
    lib.waBegin.argtypes = [ctypes.c_void_p]
    lib.waBegin.restype = ctypes.c_int
    lib.waStep.argtypes = [ctypes.c_void_p]
    lib.waStep.restype = None
    lib.waMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waMotorLastStagedDuty.restype = ctypes.c_float

    return lib


@pytest.fixture(scope="session")
def motion_verb_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libwire_motion_verb_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class WireVerbMock:
    """Thin Pythonic wrapper around one wvCreate()/wvDestroy() handle."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.wvCreate()

    def close(self):
        self._lib.wvDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def feed(self, data: bytes):
        self._lib.wvFeed(self._handle, data, len(data))

    @property
    def malformed_count(self):
        return self._lib.wvMalformedCount(self._handle)

    def take_sink(self) -> bytes:
        length = self._lib.wvSinkLength(self._handle)
        if length == 0:
            return b""
        buf = ctypes.create_string_buffer(length)
        n = self._lib.wvSinkRead(self._handle, buf, length)
        assert n == length
        data = buf.raw[:length]
        self._lib.wvSinkClear(self._handle)
        return data

    def set_wheels_v_result(self, result):
        self._lib.wvSetWheelsVResult(self._handle, result)

    def set_wheels_x_result(self, result):
        self._lib.wvSetWheelsXResult(self._handle, result)

    def set_move_x_result(self, result):
        self._lib.wvSetMoveXResult(self._handle, result)

    def set_move_v_result(self, result):
        self._lib.wvSetMoveVResult(self._handle, result)

    def set_go_to_r_result(self, result):
        self._lib.wvSetGoToRResult(self._handle, result)

    def set_go_to_w_result(self, result):
        self._lib.wvSetGoToWResult(self._handle, result)

    @property
    def wheels_v_calls(self):
        return self._lib.wvWheelsVCalls(self._handle)

    @property
    def wheels_x_calls(self):
        return self._lib.wvWheelsXCalls(self._handle)

    @property
    def move_x_calls(self):
        return self._lib.wvMoveXCalls(self._handle)

    @property
    def move_v_calls(self):
        return self._lib.wvMoveVCalls(self._handle)

    @property
    def go_to_r_calls(self):
        return self._lib.wvGoToRCalls(self._handle)

    @property
    def go_to_w_calls(self):
        return self._lib.wvGoToWCalls(self._handle)

    @property
    def last_wheels_v(self):
        return (
            self._lib.wvLastWheelsVLeft(self._handle),
            self._lib.wvLastWheelsVRight(self._handle),
            self._lib.wvLastWheelsVDuration(self._handle),
            self._lib.wvLastWheelsVId(self._handle),
        )

    @property
    def last_wheels_x(self):
        return (
            self._lib.wvLastWheelsXLeft(self._handle),
            self._lib.wvLastWheelsXRight(self._handle),
            self._lib.wvLastWheelsXCruise(self._handle),
            self._lib.wvLastWheelsXTimeout(self._handle),
        )

    @property
    def last_move_x(self):
        return (
            self._lib.wvLastMoveXDistance(self._handle),
            self._lib.wvLastMoveXRotation(self._handle),
            self._lib.wvLastMoveXCruise(self._handle),
            self._lib.wvLastMoveXTimeout(self._handle),
        )

    @property
    def last_move_v(self):
        return (
            self._lib.wvLastMoveVVx(self._handle),
            self._lib.wvLastMoveVOmega(self._handle),
            self._lib.wvLastMoveVDuration(self._handle),
        )

    @property
    def last_go_to_r(self):
        return (
            self._lib.wvLastGoToRX(self._handle),
            self._lib.wvLastGoToRY(self._handle),
            self._lib.wvLastGoToRSpeed(self._handle),
            self._lib.wvLastGoToRArrive(self._handle),
            self._lib.wvLastGoToRTimeout(self._handle),
        )

    @property
    def last_go_to_w(self):
        return (
            self._lib.wvLastGoToWX(self._handle),
            self._lib.wvLastGoToWY(self._handle),
        )


@pytest.fixture
def wv(motion_verb_lib):
    with WireVerbMock(motion_verb_lib) as w:
        yield w


class WireAdapterHandle:
    """Thin Pythonic wrapper around one waCreate()/waDestroy() handle --
    the REAL WireAdapter over a REAL kernel/FakeMotor pair."""

    def __init__(self, lib, name=b"testbot", serial=b"SN001",
                 drivetrain=b"diffdrive", profile=b"nezha2",
                 version=b"6.0.0"):
        self._lib = lib
        # ctypes.c_char_p args are borrowed by the C++ side (Wire::
        # Identity's own contract) -- keep these bytes objects alive on
        # `self` for the handle's whole lifetime.
        self._name, self._serial = name, serial
        self._drivetrain, self._profile, self._version = (
            drivetrain, profile, version,
        )
        self._handle = lib.waCreate(name, serial, drivetrain, profile,
                                     version)

    def close(self):
        self._lib.waDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def feed(self, data: bytes):
        self._lib.waFeed(self._handle, data, len(data))

    @property
    def malformed_count(self):
        return self._lib.waMalformedCount(self._handle)

    def take_sink(self) -> bytes:
        length = self._lib.waSinkLength(self._handle)
        if length == 0:
            return b""
        buf = ctypes.create_string_buffer(length)
        n = self._lib.waSinkRead(self._handle, buf, length)
        assert n == length
        data = buf.raw[:length]
        self._lib.waSinkClear(self._handle)
        return data

    def set_max_duty(self, v):
        self._lib.waSetMaxDuty(self._handle, v)

    def set_full_duty_velocity(self, v):
        self._lib.waSetFullDutyVelocity(self._handle, v)

    def begin(self):
        return self._lib.waBegin(self._handle)

    def step(self):
        self._lib.waStep(self._handle)

    def motor_last_staged_duty(self, side):
        return self._lib.waMotorLastStagedDuty(self._handle, side)


@pytest.fixture
def wa(motion_verb_lib):
    with WireAdapterHandle(motion_verb_lib) as h:
        yield h


# ---------------------------------------------------------------------------
# Golden wire vectors: decode arity, for all six motion verbs (WvHandle).
# ---------------------------------------------------------------------------


def test_wheels_x_golden_vector(wv):
    wv.set_wheels_x_result(RESULT_UNKNOWN)
    wv.feed(b"WHEELS_X 100 -50 200 3000 #1\n")
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert wv.wheels_x_calls == 1
    assert wv.last_wheels_x == pytest.approx((100.0, -50.0, 200.0, 3000.0))


def test_wheels_v_golden_vector(wv):
    wv.set_wheels_v_result(RESULT_OK)
    wv.feed(b"WHEELS_V 150 -75 2000 #1\n")
    assert wv.take_sink() == _ack(1)
    assert wv.wheels_v_calls == 1
    assert wv.last_wheels_v == (150.0, -75.0, 2000, 1)


def test_move_x_golden_vector(wv):
    wv.set_move_x_result(RESULT_UNKNOWN)
    wv.feed(b"MOVE_X 500 1571 300 4000 #1\n")
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert wv.move_x_calls == 1
    assert wv.last_move_x == pytest.approx((500.0, 1571.0, 300.0, 4000.0))


def test_move_v_golden_vector(wv):
    wv.set_move_v_result(RESULT_UNKNOWN)
    wv.feed(b"MOVE_V 200 -300 1500 #1\n")
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert wv.move_v_calls == 1
    assert wv.last_move_v == pytest.approx((200.0, -300.0, 1500.0))


def test_go_to_r_golden_vector(wv):
    wv.set_go_to_r_result(RESULT_UNKNOWN)
    wv.feed(b"GO_TO_R 300 -400 250 20 5000 #1\n")
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert wv.go_to_r_calls == 1
    assert wv.last_go_to_r == pytest.approx((300.0, -400.0, 250.0, 20.0, 5000.0))


def test_go_to_w_golden_vector(wv):
    wv.set_go_to_w_result(RESULT_UNKNOWN)
    wv.feed(b"GO_TO_W 300 -400 250 20 5000 #1\n")
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert wv.go_to_w_calls == 1
    assert wv.last_go_to_w == pytest.approx((300.0, -400.0))


# ---------------------------------------------------------------------------
# WHEELS does not appear anywhere in the new verb table -- WHEELS_V is the
# only spelling (an otherwise well-formed bare WHEELS is simply an
# unrecognized verb: a decode failure, per S8.9).
# ---------------------------------------------------------------------------


def test_bare_wheels_is_unrecognized_not_wheels_v(wv):
    wv.feed(b"WHEELS 100 100 2000 #1\n")
    assert wv.take_sink() == _nack(1) + _err(1, 1)
    assert wv.wheels_v_calls == 0
    assert wv.malformed_count == 1


# ---------------------------------------------------------------------------
# Degenerate/malformed arity for all six verbs: wrong field count, or an
# unparseable numeric field, must NACK (decode failure) per ticket 003's
# S8.9 rule -- never silently dispatch.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", [
    b"WHEELS_X 100 -50 200 #1\n",          # missing timeout
    b"WHEELS_X 100 -50 200 3000 999 #1\n",  # one field too many
    b"WHEELS_X notanumber -50 200 3000 #1\n",
    b"WHEELS_X 100 -50 200 -3000 #1\n",     # timeout must be unsigned
])
def test_wheels_x_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.wheels_x_calls == 0
    assert wv.malformed_count == 1


@pytest.mark.parametrize("line", [
    b"WHEELS_V 150 -75 #1\n",               # missing duration
    b"WHEELS_V 150 -75 2000 999 #1\n",      # one field too many
    b"WHEELS_V 150 abc 2000 #1\n",
    b"WHEELS_V 150 -75 -2000 #1\n",         # duration must be unsigned
])
def test_wheels_v_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.wheels_v_calls == 0
    assert wv.malformed_count == 1


@pytest.mark.parametrize("line", [
    b"MOVE_X 500 1571 300 #1\n",
    b"MOVE_X 500 1571 300 4000 1 #1\n",
    b"MOVE_X 500 xyz 300 4000 #1\n",
])
def test_move_x_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.move_x_calls == 0
    assert wv.malformed_count == 1


@pytest.mark.parametrize("line", [
    b"MOVE_V 200 -300 #1\n",
    b"MOVE_V 200 -300 1500 1 #1\n",
    b"MOVE_V 2.5 -300 1500 #1\n",
])
def test_move_v_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.move_v_calls == 0
    assert wv.malformed_count == 1


@pytest.mark.parametrize("line", [
    b"GO_TO_R 300 -400 250 20 #1\n",
    b"GO_TO_R 300 -400 250 20 5000 1 #1\n",
    b"GO_TO_R 300 -400 250 20 -5000 #1\n",
])
def test_go_to_r_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.go_to_r_calls == 0
    assert wv.malformed_count == 1


@pytest.mark.parametrize("line", [
    b"GO_TO_W 300 -400 250 20 #1\n",
    b"GO_TO_W 300 -400 250 20 5000 1 #1\n",
    b"GO_TO_W 300 -400 250 20 -5000 #1\n",
])
def test_go_to_w_decode_failures_nack(wv, line):
    wv.feed(line)
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.go_to_w_calls == 0
    assert wv.malformed_count == 1


# ---------------------------------------------------------------------------
# The five not-yet-wired verbs: `ack <id> ...` followed by `err 1 #<id>`
# (ERR_UNKNOWN) -- a MERITS rejection, NOT a decode failure, since the
# line itself decoded fine.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb,line", [
    ("wheels_x", b"WHEELS_X 100 100 200 3000 #1\n"),
    ("move_x", b"MOVE_X 500 0 300 4000 #1\n"),
    ("move_v", b"MOVE_V 200 0 1500 #1\n"),
    ("go_to_r", b"GO_TO_R 300 400 250 20 5000 #1\n"),
    ("go_to_w", b"GO_TO_W 300 400 250 20 5000 #1\n"),
])
def test_unwired_motion_verbs_ack_then_err_unknown(wv, verb, line):
    setter = getattr(wv, f"set_{verb}_result")
    setter(RESULT_UNKNOWN)
    wv.feed(line)
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert getattr(wv, f"{verb}_calls") == 1
    assert wv.malformed_count == 0


# ---------------------------------------------------------------------------
# STOP `[now]` -- both spellings decode correctly; the `now` token is the
# literal string "now" only, anything else in that position is a decode
# failure. (test_wire_grammar.py already covers the golden-vector shape
# of both; these two guard the "now" position specifically against a
# lookalike token, ticket 004's own acceptance criterion.)
# ---------------------------------------------------------------------------


def test_stop_lookalike_now_token_is_decode_failure(wv):
    wv.feed(b"STOP later #1\n")
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.malformed_count == 1


def test_stop_now_uppercase_is_decode_failure(wv):
    """The literal string "now" only -- not case-insensitive."""
    wv.feed(b"STOP NOW #1\n")
    assert wv.take_sink() == _nack(1) + _err(2, 1)
    assert wv.malformed_count == 1


# ---------------------------------------------------------------------------
# WHEELS_V's real effect (src/wire_adapter.h's WireAdapter, over a real
# DiffDrive kernel + FakeMotor): commanded left/right map to the correct
# velocity/twist and lease. This is ticket 004's own required proof --
# every other verb's dispatch shape is covered above via WireMockAdapter.
# ---------------------------------------------------------------------------


def test_wheels_v_real_effect_pure_forward(wa):
    """left == right (no twist): both wheels stage the identical duty
    velocity/fullDutyVelocity implies (zero-kp feedforward-only path,
    same as test_kernel_harness.py's own smoke test)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 200 200 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.2)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.2)


def test_wheels_v_real_effect_differential_reconstructs_left_right(wa):
    """left != right: velocity=(left+right)/2, twist=(right-left)/2
    (half-differential, CCW-positive) reconstruct the ORIGINAL per-wheel
    commanded values through the kernel's own velocity+twist split
    (target_left = velocity-twist, target_right = velocity+twist) -- a
    sign-convention regression guard: swapping left/right in either
    setWheelsTimed() or the kernel's own split would flip which wheel
    gets which duty, and this test would then fail with the two duties
    swapped rather than merely being "off" by a common factor."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 100 300 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.1)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.3)


def test_wheels_v_duration_over_ceiling_is_range_error(wa):
    """motion-api.md S1 / protocol.md S5 point 1: duration's 5000 ms
    ceiling, enforced by the ADAPTER (the handler holds no bounds
    table) -- a merits rejection (ack + err), not a decode failure: the
    line itself parses fine, WireAdapter refuses it on its own terms."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 100 100 5001 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    # Refused -- the kernel must never have been commanded.
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_v_duration_at_ceiling_is_accepted(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.1)


def test_stop_real_effect_returns_duty_to_zero(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 200 200 5000 #1\n")
    wa.step()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.2)

    wa.take_sink()
    wa.feed(b"STOP #2\n")
    assert wa.take_sink() == _ack(2)
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_estop_real_effect_refuses_further_drive(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"ESTOP\n")
    assert wa.take_sink() == b"estop\n"

    wa.take_sink()
    wa.feed(b"WHEELS_V 200 200 5000 #1\n")
    # onWheelsV always answers kOk (setWheelsTimed() returns void, so
    # there is no adapter-observable refusal path) -- the KERNEL itself
    # refuses the drive() call underneath, which is what this test
    # actually verifies via the motor never staging a nonzero duty.
    assert wa.take_sink() == _ack(1)
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# WireAdapter's own GET/SET field-name table: addresses the same
# Rig/Config fields the old ConfigField enum named, one field per SET
# line (ticket 004's own acceptance criterion).
# ---------------------------------------------------------------------------


def test_get_set_field_name_table_round_trips(wa):
    """SET/GET address the field by NAME, round-tripping through the
    same x1000-scaled-int convention setKernelValue()/getConfigValue()
    already used for the old binary CONFIG/SET_FIELD/GET_CONFIG verbs
    (shims.cpp) -- checked with a tolerance, not exact-string equality,
    since that scaling convention was never bit-exact (it wasn't before
    this ticket either; SET_FIELD's own value went through the identical
    x1000 round trip)."""
    wa.feed(b"SET max_duty 55.5 #1\n")
    assert wa.take_sink() == _ack(1)

    wa.feed(b"GET max_duty #2\n")
    reply = wa.take_sink()
    prefix = _ack(2) + b"get max_duty "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(55.5, abs=1e-3)


def test_get_set_unknown_field_name_is_unknown(wa):
    wa.feed(b"SET nosuch_field 1.0 #1\n")
    assert wa.take_sink() == _ack(1) + _err(1, 1)  # ERR_UNKNOWN

    wa.feed(b"GET nosuch_field #2\n")
    assert wa.take_sink() == _ack(2)  # no `get` line -- unknown name


# ---------------------------------------------------------------------------
# The REAL WireAdapter (not WireMockAdapter) answers kUnknown for its own
# five not-yet-wired motion verbs -- ticket 004's own acceptance
# criterion, stated for WireAdapter specifically, not merely for "some
# Adapter implementation" (already shown generically above via `wv`).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", [
    b"WHEELS_X 100 100 200 3000 #1\n",
    b"MOVE_X 500 0 300 4000 #1\n",
    b"MOVE_V 200 0 1500 #1\n",
    b"GO_TO_R 300 400 250 20 5000 #1\n",
    b"GO_TO_W 300 400 250 20 5000 #1\n",
])
def test_real_wire_adapter_answers_unknown_for_unwired_motion_verbs(wa, line):
    wa.feed(line)
    assert wa.take_sink() == _ack(1) + _err(1, 1)
    assert wa.malformed_count == 0


def test_get_bare_dumps_all_fifteen_fields_no_wheels_entry(wa):
    """A bare-GET dump lists only the 15 ConfigField-equivalent wire
    names (wire_adapter.cpp's kFields table) -- confirms the old
    multi-pair CONFIG batch verb's ordinal set is fully covered under
    new names, and that no WHEELS-named entry leaked into the config
    table (WHEELS_V is a motion verb, not a config field)."""
    wa.feed(b"GET #1\n")
    lines = wa.take_sink().split(b"\n")
    names = [line.split(b" ")[1] for line in lines if line.startswith(b"get ")]
    assert names == [
        b"max_duty", b"full_duty_velocity", b"pid_kp", b"pid_ki",
        b"pid_i_max", b"accel_kaff", b"pid_max", b"twist_hold_gain",
        b"speed_floor", b"pos_err_max", b"stall_speed", b"stall_demand",
        b"stall_window", b"lambda_enabled", b"crawl_pulse",
    ]
    assert b"wheels" not in b" ".join(names).lower()
