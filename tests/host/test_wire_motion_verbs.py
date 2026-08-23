"""tests/host/test_wire_motion_verbs.py -- sprint 003 tickets 004/011: the
six motion verbs' wire decode/dispatch (WHEELS_X, WHEELS_V, MOVE_X, MOVE_V,
GO_TO_R, GO_TO_W), src/wire_adapter.h's WireAdapter, and STOP's `now`
token.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S4 (the Adapter interface), S5
(the DiffDrive adapter -- WHEELS_V real, five kUnknown), S6/S6.1 (the
verb table, outcome codes), S9.10 item 1 (why kUnknown, not
kUnimplemented).
radio-robot-lib/docs/design/motion-api.md S1 (arguments/units), S1.1
(cruise == 0 means "the configured default"), S9.1 (the wire mapping
table, including the ONE mrad<->rad conversion seam MOVE_X's `rotation`
needs).

Two fixtures, two different concerns (see wire_motion_verb_shim.cpp's
own header comment for the full rationale):

- `wv` -- WireHandler + WireMockAdapter: decode arity (golden vectors)
  and degenerate/malformed input (wrong field count, an unparseable
  numeric field) for all six verbs, plus proof that a MERITS rejection
  (`err 1`, ERR_UNKNOWN) is never a decode failure (nack + err).
- `wa` -- WireHandler + the REAL WireAdapter + a REAL DiffDrive kernel
  AND MotionEngine over FakeMotor: WHEELS_V's/WHEELS_X's/MOVE_X's real
  effect (sprint 003 tickets 004/011 -- commanded left/right, or
  distance/rotation, map to the correct velocity/twist/lease or
  move-engine segment), the cruise==0 "configured default" substitution
  and the cruise<0 range refusal (motion-api.md S1.1), MOVE_X's
  mrad->rad conversion tested in both turn directions, WireAdapter's own
  GET/SET field-name table, and STOP/ESTOP's real effect on the kernel.
  MOVE_V/GO_TO_R/GO_TO_W are still not-yet-wired (ticket 012).

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
    _SRC_DIR / "motion_engine.cpp",
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
    lib.waCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.waCountsPerMm.restype = ctypes.c_float
    lib.waEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.waEffectiveTrackWidth.restype = ctypes.c_float
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

    def counts_per_mm(self):
        return self._lib.waCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.waEffectiveTrackWidth(self._handle)

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
# WHEELS_X's real effect (sprint 003 ticket 011): a ratio-locked per-wheel
# distance command dispatched onto MotionEngine::wheelsX(). Verified the
# same way test_motion_engine_primitives.py verifies wheelsX() directly --
# FakeMotor's own LAST STAGED DUTY after exactly one step(), with the
# kernel configured so duty is pure feedforward (only maxDuty/
# fullDutyVelocity set, motion-api.md S3.1). wheelsX() is a PRIMITIVE, not
# the move engine -- there is no acceleration-ramp scaling on its first
# tick the way there is for MOVE_X below.
# ---------------------------------------------------------------------------


def _expected_wheels_x_duty_pair(left, right, cruise, cpm, fdv):
    """Mirrors MotionEngine::wheelsX()'s own ratio math (motion_engine.cpp):
    the DOMINANT wheel (larger magnitude) reaches exactly `cruise`; the
    other follows the same ratio."""
    dominant = max(abs(left), abs(right))
    left_speed = (left / dominant) * cruise    # [mm/s]
    right_speed = (right / dominant) * cruise  # [mm/s]
    return left_speed * cpm / fdv, right_speed * cpm / fdv


# Chosen large enough that every commanded speed below (through
# MotionEngine's real countsPerMm(), unlike WHEELS_V's own test double
# above which fixes countsPerLength at 1.0) stays well under the
# maxDuty=100% rail -- mirrors test_motion_engine_primitives.py's own
# identical choice and rationale: no assertion here is secretly checking
# a clamped value in disguise.
_WHEELS_X_FULL_DUTY_VELOCITY = 5000.0  # [counts/s]


def test_wheels_x_real_effect_straight_line(wa):
    """wheels_x(d, d) is a straight line -- both wheels at ratio 1, so
    both run at exactly `cruise` (motion-api.md S2.1's own degenerate
    case)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.feed(b"WHEELS_X 200 200 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, 150.0, cpm, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


def test_wheels_x_real_effect_ratio_locked_dominant_wheel(wa):
    """A non-degenerate case: the DOMINANT wheel (larger magnitude, here
    left at 200mm vs right's 100mm) is the one that reaches `cruise`; the
    other follows the same ratio (motion-api.md S3.1: "both wheels finish
    together")."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.feed(b"WHEELS_X 200 100 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 100.0, 150.0, cpm, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)
    assert wa.motor_last_staged_duty(LEFT) > wa.motor_last_staged_duty(RIGHT)


def test_wheels_x_real_effect_sign_convention_both_directions(wa):
    """CCW-positive (motion-api.md S2.1): wheels_x(+d, -d) is a pivot,
    each wheel commanded the full cruise ceiling in its OWN direction --
    written explicitly, in both signs, so a future cable-order "fix"
    fails this test instead of shipping (this project has shipped that
    exact bug and patched it four times downstream)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    fdv = _WHEELS_X_FULL_DUTY_VELOCITY

    wa.feed(b"WHEELS_X 150 -150 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(100.0 * cpm / fdv)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        -100.0 * cpm / fdv)

    wa.feed(b"WHEELS_X -150 150 100 5000 #2\n")
    assert wa.take_sink() == _ack(2)
    wa.step()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        -100.0 * cpm / fdv)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(100.0 * cpm / fdv)


def test_wheels_x_negative_cruise_is_range_error(wa):
    """A speed ceiling has no sign -- refused outright (kRange), not
    silently taken as a magnitude or as wheelsX()'s own non-positive-
    cruise no-op."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_X 100 100 -50 3000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_x_cruise_zero_uses_configured_default(wa):
    """motion-api.md S1.1: "Pass 0 for the configured default" -- this
    robot's own configured full_duty_velocity (the same ceiling GET
    full_duty_velocity reports), converted to mm/s."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    default_cruise = 1000.0 / cpm  # fullDutyVelocity [counts/s] -> [mm/s]

    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, default_cruise, cpm, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)
    # A straight line commanded at exactly the configured ceiling should
    # stage exactly full duty -- an independent sanity check that the
    # substitution landed on the right number, not merely a nonzero one.
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(1.0)


def test_wheels_x_cruise_zero_without_configured_default_is_range_error(wa):
    """A fresh robot whose full_duty_velocity was never SET (still its
    zero/off default, diffdrive.h) has no configured default cruise to
    fall back to -- refused (kRange), not silently commanded to drive at
    zero speed forever."""
    wa.set_max_duty(100.0)
    # full_duty_velocity deliberately left unset (default 0).
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# MOVE_X's real effect (sprint 003 ticket 011): dispatched onto
# MotionEngine::moveX(), whose FIRST tick is scaled by the acceleration
# ramp's 0.25 floor (motion_engine.cpp's own `cmdScale = 0.25f` at segment
# start, mirrored from test_motion_engine_reductions.py's own identical
# convention) -- every hand-computed expectation below bakes that scale in
# explicitly rather than hiding it in a helper default.
# ---------------------------------------------------------------------------


def _move_x_segment(distance_mm, rotation_rad, cpm, b):
    """Mirrors MotionEngine::startSegment()'s own targets (motion-api.md
    S2's wheels_x reduction, restated as mean + half-differential)."""
    dist_target = distance_mm * cpm
    yaw_target = rotation_rad * 0.5 * b * cpm
    left = dist_target - yaw_target
    right = dist_target + yaw_target
    return left, right, max(abs(left), abs(right))


def _expected_move_x_duty_pair(distance_mm, rotation_rad, cruise, cpm, b,
                               fdv, scale=0.25):
    left, right, dominant = _move_x_segment(distance_mm, rotation_rad, cpm, b)
    cruise_counts = cruise * cpm
    raw_left = (left / dominant) * cruise_counts * scale
    raw_right = (right / dominant) * cruise_counts * scale
    return raw_left / fdv, raw_right / fdv


def test_move_x_real_effect_straight_line(wa):
    """move_x(d, 0) is a straight line -- both wheels at the same ratio
    (1:1), scaled by the initial 0.25 ramp floor on this, the move's
    first tick."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.feed(b"MOVE_X 200 0 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_x_duty_pair(
        200.0, 0.0, 150.0, cpm, b, 1000.0)
    assert expected_left == pytest.approx(expected_right, rel=1e-4)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_move_x_mrad_to_rad_conversion_positive_turns_left(wa):
    """The wire's ONE mrad->rad conversion seam (motion-api.md S9.1),
    checked with an actual physical assertion, not just a numeric one: a
    POSITIVE wire `rotation` must turn LEFT -- the right wheel faster,
    the left wheel slower (CCW-positive, motion-api.md S2.1) -- the same
    direction a positive block-API degree value already produces via
    shims.cpp's startMove(). The hand-computed expectation performs the
    CORRECT /1000 conversion independently in Python: if the binding
    used the wrong scale (e.g. treating milliradians as already radians,
    or as degrees) or the wrong sign, this would no longer match the
    measured duty -- an off-by-1000 fails a test instead of shipping."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    rotation_mrad = 300  # -> 0.300 rad if the conversion is exact
    wa.feed(b"MOVE_X 0 300 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_x_duty_pair(
        0.0, rotation_mrad / 1000.0, 150.0, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)
    # CCW-positive: a positive rotation turns LEFT -- the right wheel is
    # the faster one, the left wheel the slower one.
    assert wa.motor_last_staged_duty(RIGHT) > wa.motor_last_staged_duty(LEFT)


def test_move_x_mrad_to_rad_conversion_negative_turns_right(wa):
    """The mirror of the above, in the OTHER direction: a NEGATIVE wire
    `rotation` turns RIGHT -- the left wheel is the faster one."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    rotation_mrad = -300
    wa.feed(b"MOVE_X 0 -300 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_x_duty_pair(
        0.0, rotation_mrad / 1000.0, 150.0, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)
    assert wa.motor_last_staged_duty(LEFT) > wa.motor_last_staged_duty(RIGHT)


def test_move_x_negative_cruise_is_range_error(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"MOVE_X 200 0 -50 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_move_x_cruise_zero_uses_configured_default(wa):
    """motion-api.md S1.1's "configured default" substitution, exercised
    through MOVE_X's own move-engine path (not just WHEELS_X's plain
    primitive)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    default_cruise = 1000.0 / cpm

    wa.feed(b"MOVE_X 200 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_x_duty_pair(
        200.0, 0.0, default_cruise, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_move_x_cruise_zero_without_configured_default_is_range_error(wa):
    wa.set_max_duty(100.0)
    # full_duty_velocity deliberately left unset (default 0).
    assert wa.begin() == STATUS_OK

    wa.feed(b"MOVE_X 200 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
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
# The REAL WireAdapter (not WireMockAdapter) still answers kUnknown for its
# three remaining not-yet-wired motion verbs -- WHEELS_X/MOVE_X are real as
# of ticket 011 (see their own real-effect sections above); ticket 004's
# own acceptance criterion for the rest, stated for WireAdapter
# specifically, not merely for "some Adapter implementation" (already
# shown generically above via `wv`).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", [
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
