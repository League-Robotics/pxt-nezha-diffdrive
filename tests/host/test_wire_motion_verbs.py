"""tests/host/test_wire_motion_verbs.py -- sprint 003 tickets 004/011/012:
the six motion verbs' wire decode/dispatch (WHEELS_X, WHEELS_V, MOVE_X,
MOVE_V, GO_TO_R, GO_TO_W), src/wire_adapter.h's WireAdapter, and STOP's
`now` token.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S4 (the Adapter interface), S5
(the DiffDrive adapter -- WHEELS_V real, five kUnknown), S6/S6.1 (the
verb table, outcome codes), S9.10 item 1 (why kUnknown, not
kUnimplemented).
radio-robot-lib/docs/design/motion-api.md S1 (arguments/units), S1.1
(cruise == 0 means "the configured default"), S2 (move_v/go_to_r/go_to_w
as reductions onto wheels_v/move_x), S3.4 (move_v's duration IS the
lease, exactly like wheels_v), S3.6 (go_to_w's pluggable pose source),
S9.1 (the wire mapping table, including the mrad<->rad conversion seam
MOVE_X's `rotation` AND MOVE_V's `omega` both need).

Two fixtures, two different concerns (see wire_motion_verb_shim.cpp's
own header comment for the full rationale):

- `wv` -- WireHandler + WireMockAdapter: decode arity (golden vectors)
  and degenerate/malformed input (wrong field count, an unparseable
  numeric field) for all six verbs, plus proof that a MERITS rejection
  (`err 1`, ERR_UNKNOWN) is never a decode failure (nack + err).
- `wa` -- WireHandler + the REAL WireAdapter + a REAL DiffDrive kernel
  AND MotionEngine over FakeMotor: real effect for all SIX motion verbs
  (sprint 003 tickets 004/011/012 -- commanded left/right, distance/
  rotation, v_x/omega, or x/y/speed all map to the correct velocity/
  twist/lease or move-engine segment), the cruise/speed==0 "configured
  default" substitution and the cruise/speed<0 range refusal
  (motion-api.md S1.1), MOVE_X's/MOVE_V's mrad->rad conversion tested in
  both turn directions, GO_TO_W's real effect via a FakePoseSource and
  its honest refusal (ERR_UNIMPLEMENTED) with none available,
  WireAdapter's own GET/SET field-name table, STOP/ESTOP's real effect
  on the kernel, and the motion-obligation flag (ticket 012's own
  arm-from-every-verb bug fix, wire_adapter.h's own header comment) via
  a real nowMs wired in through waSetNowMs()/waHasLiveMotionObligation().

Run with::

    uv run pytest tests/host/test_wire_motion_verbs.py
"""

import ctypes
import math
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

# Wire::TlmMode's DECLARATION-ORDER ordinal (wire_handler.h) -- sprint
# 004 ticket 004's own telemetry projection tests.
TLM_OFF = 0
TLM_POSE = 1
TLM_FULL = 2
TLM_NOW = 3
TLM_AUTO = 4
TLM_BUFFER = 5

# diagValue()'s own field-ordinal contract (shims.cpp / wire_adapter.cpp's
# kDiag* constants) -- sprint 004 ticket 004's own diag-override tests.
DIAG_READY = 0
DIAG_ESTOPPED = 1
DIAG_STALL_HALTED = 2
DIAG_LEASE_EXPIRED = 3
DIAG_CONN_LEFT = 4
DIAG_CONN_RIGHT = 5
DIAG_WEDGE_LEFT = 6
DIAG_WEDGE_RIGHT = 7
DIAG_I2C_FAULT = 8
DIAG_LEASE_EXPIRY_COUNT = 9
DIAG_POSITION_LEFT = 10
DIAG_POSITION_RIGHT = 11
DIAG_APPLIED_DUTY_LEFT = 12
DIAG_APPLIED_DUTY_RIGHT = 13
DIAG_CYCLE_COUNT = 16
DIAG_CYCLE_OVERRUN_COUNT = 19
DIAG_WRONG_WAY_COUNT = 25


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

    # ---- sprint 003 ticket 012: real nowMs + motion-obligation, and
    # GO_TO_W's FakePoseSource ----
    lib.waSetNowMs.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.waSetNowMs.restype = None
    lib.waHasLiveMotionObligation.argtypes = [ctypes.c_void_p]
    lib.waHasLiveMotionObligation.restype = ctypes.c_int
    lib.waSetPose.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ]
    lib.waSetPose.restype = None
    lib.waSetPoseSourceAvailable.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waSetPoseSourceAvailable.restype = None

    # ---- sprint 004 ticket 004: telemetry projection (buildSnapshot(),
    # the five new raw setters, diagValue() overrides, TLM mode, and
    # emitTelemetry() readback) ----
    lib.waSetPoseRaw.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ]
    lib.waSetPoseRaw.restype = None
    lib.waSetOtosRaw.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ]
    lib.waSetOtosRaw.restype = None
    lib.waSetOtosConnected.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waSetOtosConnected.restype = None
    lib.waSetWheelSpeed.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.waSetWheelSpeed.restype = None
    lib.waSetDiagOverride.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ]
    lib.waSetDiagOverride.restype = None
    lib.waBuildSnapshot.argtypes = [ctypes.c_void_p]
    lib.waBuildSnapshot.restype = ctypes.c_void_p
    lib.waSnapshotCount.argtypes = [ctypes.c_void_p]
    lib.waSnapshotCount.restype = ctypes.c_int
    lib.waSnapshotColumnName.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waSnapshotColumnName.restype = ctypes.c_char_p
    lib.waSnapshotColumnValue.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waSnapshotColumnValue.restype = ctypes.c_int32
    lib.waSnapshotColumnHex.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waSnapshotColumnHex.restype = ctypes.c_int
    lib.waEmitTelemetry.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.waEmitTelemetry.restype = None
    lib.waOnTlm.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waOnTlm.restype = ctypes.c_int
    lib.waHasLiveTelemetry.argtypes = [ctypes.c_void_p]
    lib.waHasLiveTelemetry.restype = ctypes.c_int

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

    # ---- sprint 003 ticket 012: real nowMs + motion-obligation, and
    # GO_TO_W's FakePoseSource ----
    def set_now_ms(self, ms):
        self._lib.waSetNowMs(self._handle, ms)

    def has_live_motion_obligation(self):
        return bool(self._lib.waHasLiveMotionObligation(self._handle))

    def set_pose(self, x, y, heading):
        self._lib.waSetPose(self._handle, x, y, heading)

    def set_pose_source_available(self, available):
        self._lib.waSetPoseSourceAvailable(self._handle, 1 if available else 0)

    # ---- sprint 004 ticket 004: telemetry projection ----------------

    def set_pose_raw(self, x_mm, y_mm, heading_cdeg):
        """poseX()/poseY()/poseHeading()'s raw settable state -- plain
        integers, no rad/float conversion in the way (see
        wire_motion_verb_shim.cpp's own header comment on why this is
        SEPARATE from set_pose(), which backs GO_TO_W's own OTOS-shaped
        PoseSource instead)."""
        self._lib.waSetPoseRaw(self._handle, x_mm, y_mm, heading_cdeg)

    def set_otos_raw(self, x_01mm, y_01mm, heading_cdeg):
        """otosGet(0)/(1)/(2)'s raw settable state -- 0.1 mm for x/y
        (buildSnapshot() itself divides by 10), already-cdeg for
        heading."""
        self._lib.waSetOtosRaw(self._handle, x_01mm, y_01mm, heading_cdeg)

    def set_otos_connected(self, connected):
        """otosGet(7)'s raw settable state -- independent of
        set_otos_raw()'s x/y/heading, since a disconnected OTOS can
        still report a stale cached pose (this ticket's own R-22 test
        requirement)."""
        self._lib.waSetOtosConnected(self._handle, 1 if connected else 0)

    def set_wheel_speed(self, left_mms, right_mms):
        """wheelSpeed(0)/(1)'s raw settable state -- mm/s, unscaled."""
        self._lib.waSetWheelSpeed(self._handle, left_mms, right_mms)

    def set_diag_override(self, what, value):
        """Arms an exact diagValue(`what`) return value -- lets a scale
        test pin i2cf/lexc/posl/posr/dutl/dutr/cyc/cycovr/wrng (ordinals
        8/9/10/11/12/13/16/19/25) or any of the eight boolean flags
        ordinals (0-7) without driving real kernel/engine state there."""
        self._lib.waSetDiagOverride(self._handle, what, value)

    def build_snapshot(self):
        """Calls the REAL WireAdapter::buildSnapshot() and returns a
        thin Python wrapper over the resulting Wire::Snapshot -- valid
        only until the next build_snapshot() call, same "member, not a
        temporary" contract the C++ method itself documents."""
        ptr = self._lib.waBuildSnapshot(self._handle)
        return Snapshot(self._lib, ptr)

    def emit_telemetry(self, snapshot):
        """Calls the REAL WireHandler::emitTelemetry(snapshot) -- writes
        thdr (if due), t, then the reliability keepalive into this
        handle's own sink, exactly as protocol.cpp's periodic-emission
        block does in production."""
        self._lib.waEmitTelemetry(self._handle, snapshot.ptr)

    def on_tlm(self, mode):
        """Calls WireAdapter::onTlm(mode) directly -- bypasses the wire
        grammar entirely (that dispatch path is test_wire_grammar.py's
        own scope); this ticket only needs mode_ SET, not decoded."""
        return self._lib.waOnTlm(self._handle, mode)

    def has_live_telemetry(self):
        return bool(self._lib.waHasLiveTelemetry(self._handle))


class Snapshot:
    """Thin Python wrapper over a `const Wire::Snapshot*` returned by
    WireAdapterHandle.build_snapshot() -- read-only, valid only until the
    next build_snapshot() call on the SAME handle (borrowed, per
    Wire::Snapshot's own doc comment, wire_handler.h)."""

    def __init__(self, lib, ptr):
        self._lib = lib
        self.ptr = ptr

    @property
    def count(self):
        return self._lib.waSnapshotCount(self.ptr)

    def name(self, index):
        return self._lib.waSnapshotColumnName(self.ptr, index).decode()

    def value(self, index):
        return self._lib.waSnapshotColumnValue(self.ptr, index)

    def hex(self, index):
        return bool(self._lib.waSnapshotColumnHex(self.ptr, index))

    def columns(self):
        """[(name, value, hex), ...] for every column, in order."""
        return [
            (self.name(i), self.value(i), self.hex(i))
            for i in range(self.count)
        ]


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
# Generic proof, via the configurable WireMockAdapter (`wv`, independent
# of whatever the REAL WireAdapter does with any of these verbs -- see
# the real-effect sections further below for that): a MERITS rejection
# is `ack <id> ...` followed by `err <code> #<id>`, NOT a decode failure,
# since the line itself decoded fine. Illustrated here with a canned
# ERR_UNKNOWN; the real WireAdapter's own merits rejections use
# different codes (ERR_RANGE, ERR_UNIMPLEMENTED) for its own reasons --
# this test is about the ack-then-err SHAPE, not about which verbs are
# wired.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb,line", [
    ("wheels_x", b"WHEELS_X 100 100 200 3000 #1\n"),
    ("move_x", b"MOVE_X 500 0 300 4000 #1\n"),
    ("move_v", b"MOVE_V 200 0 1500 #1\n"),
    ("go_to_r", b"GO_TO_R 300 400 250 20 5000 #1\n"),
    ("go_to_w", b"GO_TO_W 300 400 250 20 5000 #1\n"),
])
def test_merits_rejection_is_ack_then_err_not_nack(wv, verb, line):
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
# MOVE_V's real effect (sprint 003 ticket 012): the plain wheelsV
# reduction -- move_v(v_x, omega) == wheels_v(v_x - omega*b/2,
# v_x + omega*b/2) (motion-api.md S2) -- dispatched onto
# MotionEngine::moveV() via WireAdapter::onMoveV(). Verified the same way
# WHEELS_X's own real-effect tests above are: FakeMotor's LAST STAGED
# DUTY after exactly one step(), computed through this handle's REAL
# countsPerMm()/effectiveTrackWidth() (unlike WHEELS_V's own dedicated
# real-effect tests further above, whose test-double setWheelsTimed()
# fixes countsPerLength at 1.0 -- MOVE_V goes through the REAL
# MotionEngine, same as WHEELS_X/MOVE_X, so its own real cpm scaling
# applies here too). No ramp/taper scaling either -- wheelsV() is a
# PRIMITIVE, not a move-engine segment.
# ---------------------------------------------------------------------------

# Same rationale as _WHEELS_X_FULL_DUTY_VELOCITY above: large enough that
# every commanded speed below stays well under the maxDuty=100% rail once
# real cpm scaling (not a fixed 1.0) is applied, and with no ramp scaling
# to soften a first tick the way MOVE_X's 0.25 floor does.
_MOVE_V_FULL_DUTY_VELOCITY = 5000.0  # [counts/s]


def _expected_move_v_duty_pair(vx, omega_rad, cpm, b, fdv):
    """Mirrors MotionEngine::moveV()'s own reduction (motion_engine.cpp):
    twist = omega*0.5*b [mm/s] CCW+, then wheels_v(vx-twist, vx+twist) --
    wheelsV()'s own velocity/twist reconstruction (mean/half-diff) gives
    back exactly (vx-twist)*cpm, (vx+twist)*cpm as each wheel's target
    [counts/s]; duty is that target over fullDutyVelocity (feedforward
    only, kp=0, same convention every other real-effect test in this
    file uses)."""
    twist = omega_rad * 0.5 * b
    return (vx - twist) * cpm / fdv, (vx + twist) * cpm / fdv


def test_move_v_real_effect_pure_forward_no_omega(wa):
    """omega == 0: no twist -- move_v(v_x, 0) == wheels_v(v_x, v_x), both
    wheels stage the identical duty."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.feed(b"MOVE_V 200 0 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_v_duty_pair(
        200.0, 0.0, cpm, b, _MOVE_V_FULL_DUTY_VELOCITY)
    assert expected_left == pytest.approx(expected_right)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


def test_move_v_mrad_to_rad_conversion_positive_omega_turns_left(wa):
    """The wire's OTHER mrad->rad conversion seam (motion-api.md S9.1),
    checked physically like MOVE_X's own equivalent test above: a
    POSITIVE wire `omega` must turn LEFT -- the right wheel faster, the
    left wheel slower (CCW-positive) -- via move_v's own twist = omega*
    b/2 reduction. An off-by-1000 or a flipped sign here fails this test
    instead of shipping."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    omega_mrad = 300  # -> 0.300 rad/s if the conversion is exact
    wa.feed(b"MOVE_V 0 300 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_v_duty_pair(
        0.0, omega_mrad / 1000.0, cpm, b, _MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) > wa.motor_last_staged_duty(LEFT)


def test_move_v_mrad_to_rad_conversion_negative_omega_turns_right(wa):
    """Mirror of the above in the OTHER direction: a NEGATIVE wire
    `omega` turns RIGHT -- the left wheel is the faster one."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    omega_mrad = -300
    wa.feed(b"MOVE_V 0 -300 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_v_duty_pair(
        0.0, omega_mrad / 1000.0, cpm, b, _MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)
    assert wa.motor_last_staged_duty(LEFT) > wa.motor_last_staged_duty(RIGHT)


def test_move_v_omega_slaved_to_vx_single_ratio(wa):
    """motion-api.md S1.1: 'omega is slaved to v_x -- the two are one
    ratio, held through the ramp.' Exercised here with BOTH v_x and
    omega nonzero at once, proving the reduction combines them by plain
    superposition (vx +/- twist) -- there is no separate profile/ceiling
    on omega that could bend that ratio."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.feed(b"MOVE_V 150 200 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_move_v_duty_pair(
        150.0, 0.200, cpm, b, _MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_move_v_duration_over_ceiling_is_range_error(wa):
    """Shares WHEELS_V's own ceiling (wire_adapter.h's
    kWheelsVDurationCeiling doc comment) -- the identical "duration IS
    the lease" V-form rationale (motion-api.md S3.4)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK

    wa.feed(b"MOVE_V 100 0 5001 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_move_v_duration_at_ceiling_is_accepted(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.feed(b"MOVE_V 100 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, _ = _expected_move_v_duty_pair(
        100.0, 0.0, cpm, b, _MOVE_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)


# ---------------------------------------------------------------------------
# GO_TO_R's real effect (sprint 003 ticket 012): the PLAIN spec reduction
# onto moveX (motion-api.md S3.5: turn angle phi = 2*atan2(y,x), arc
# length s), dispatched onto MotionEngine::goToR() via
# WireAdapter::onGoToR(). goToR()'s own arc-solve branches are already
# tested exhaustively at the engine level (test_motion_engine_reductions.py,
# ticket 007) -- this proves the WIRE dispatch feeds x/y/speed/arrive/
# timeout through correctly, the same "don't re-exercise an
# already-tested reduction's own branches" posture
# test_motion_engine_gotow.py takes for goToW() (ticket 010).
# ---------------------------------------------------------------------------


def _go_to_r_theta_s(x, y):
    """Mirrors MotionEngine::goToR()'s own arc solve (motion-api.md
    S3.5), including the near-zero-y straight-line special case --
    an independently-implemented mirror, NOT a call into the C++ under
    test, same convention test_motion_engine_gotow.py's own identical
    copy uses."""
    theta = 2.0 * math.atan2(y, x)
    if abs(y) < 0.1:
        s = x
    else:
        radius = (x * x + y * y) / (2.0 * y)
        s = radius * theta
    return theta, s


def test_go_to_r_real_effect_arc_solve(wa):
    """A representative (x, y) target chosen to stay off moveX()'s
    pivot-first split (turn angle well under 50 deg) -- proves x/y/speed
    reach MotionEngine::goToR()'s own arc-solve and then moveX()'s
    first-tick segment (0.25 ramp scale), via the SAME hand-computed
    formula test_move_x_real_effect_straight_line uses above."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.feed(b"GO_TO_R 200 50 150 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    assert abs(theta) < math.radians(50.0)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, 150.0, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_go_to_r_negative_speed_is_range_error(wa):
    """`speed` plays `cruise`'s role for the underlying moveX() call
    (wire_adapter.h's own onGoToR() doc comment) -- same <0 refusal."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"GO_TO_R 200 50 -150 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_go_to_r_speed_zero_uses_configured_default(wa):
    """motion-api.md S1.1's "configured default" substitution, exercised
    through GO_TO_R's own path -- same substitution onWheelsX()/onMoveX()
    already use."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    default_speed = 1000.0 / cpm

    wa.feed(b"GO_TO_R 200 50 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, default_speed, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_go_to_r_speed_zero_without_configured_default_is_range_error(wa):
    wa.set_max_duty(100.0)
    # full_duty_velocity deliberately left unset (default 0).
    assert wa.begin() == STATUS_OK

    wa.feed(b"GO_TO_R 200 50 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# GO_TO_W's real effect (sprint 003 ticket 012): the world-frame
# counterpart -- read pose -> world-to-body -> go_to_r (motion-api.md
# S2/S3.6) -- dispatched onto MotionEngine::goToW() via
# WireAdapter::onGoToW(), reading this handle's own FakePoseSource
# (wa.set_pose()) through engineGoToW()'s bridge. The world-to-body
# transform and goToR()'s own arc solve are already tested exhaustively
# at the engine level (test_motion_engine_gotow.py, ticket 010) -- this
# proves the WIRE dispatch bridges to a REAL PoseSource correctly, plus
# this class's own "no pose source" refusal, ticket 012's own required,
# explicit decision (ERR_UNIMPLEMENTED -- see wire_adapter.h's own
# onGoToW() doc comment for why).
# ---------------------------------------------------------------------------


def _world_to_body(dx, dy, heading):
    """Mirrors MotionEngine::goToW()'s own rotation -- an
    independently-implemented copy, NOT a call into the C++ under test,
    identical to test_motion_engine_gotow.py's own copy."""
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    body_x = dx * cos_h + dy * sin_h
    body_y = -dx * sin_h + dy * cos_h
    return body_x, body_y


def test_go_to_w_identity_pose_matches_go_to_r(wa):
    """pose == (0, 0, 0): the world-frame delta IS the body-frame delta
    -- GO_TO_W(x, y, ...) must match GO_TO_R(x, y, ...)'s own real-effect
    test above exactly."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    wa.set_pose(0.0, 0.0, 0.0)
    wa.feed(b"GO_TO_W 200 50 150 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, 150.0, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_go_to_w_real_effect_nonzero_pose_and_heading(wa):
    """The case ticket 010's own tests call out explicitly: a nonzero
    heading combined with a nonzero position is where sign and
    rotation-direction errors hide -- same pose/target/speed values
    test_motion_engine_gotow.py's own
    test_go_to_w_world_to_body_transform_nonzero_pose_and_heading
    already proved sane at the engine level; this proves the WIRE path
    reaches the same real effect."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    pose_x, pose_y, heading = 100.0, -50.0, math.radians(30.0)
    target_x, target_y = 500.0, 200.0
    wa.set_pose(pose_x, pose_y, heading)

    wa.feed(b"GO_TO_W 500 200 120 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    body_x, body_y = _world_to_body(target_x - pose_x, target_y - pose_y,
                                    heading)
    theta, s = _go_to_r_theta_s(body_x, body_y)
    assert abs(theta) < math.radians(50.0)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, 120.0, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_go_to_w_negative_speed_is_range_error(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose(0.0, 0.0, 0.0)

    wa.feed(b"GO_TO_W 200 50 -150 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_go_to_w_no_pose_source_is_unimplemented(wa):
    """motion-api.md S3.6 / ticket 010's own explicitly out-of-scope
    encoder-odometry fallback: with no OTOS fitted/connected, this class
    must refuse honestly rather than drive toward a garbage pose --
    wire_adapter.h's own documented DECISION is ERR_UNIMPLEMENTED (wire
    code 6: "recognized, not wired on this build"), not ERR_RANGE/
    ERR_UNKNOWN/ERR_NOT_CONFIGURED (see that file's own onGoToW() doc
    comment for why)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose_source_available(False)

    wa.feed(b"GO_TO_W 200 50 150 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(6, 1)  # ERR_UNIMPLEMENTED
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Motion-obligation arming (sprint 003 ticket 012's own bug fix --
# wire_adapter.h's own header comment): EVERY accepted motion verb now
# arms hasLiveMotionObligation(), not just WHEELS_V -- ticket 011 left
# WHEELS_X/MOVE_X dispatching real effect WITHOUT arming it, so
# protocol.cpp's fiber never ticked the kernel for them on hardware (the
# move aborted almost immediately via the starvation watchdog instead of
# actually running for its intended distance/time). Proven here with a
# REAL nowMs wired into the WireAdapter (waSetNowMs()) -- every OTHER
# test in this file leaves nowMs unset (nullptr), under which this flag
# can never answer anything but false.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line,window_ms", [
    (b"WHEELS_V 100 100 2000 #1\n", 2000),
    (b"WHEELS_X 100 100 150 3000 #1\n", 3000),
    (b"MOVE_X 200 0 150 4000 #1\n", 4000),
    (b"MOVE_V 100 0 1500 #1\n", 1500),
    (b"GO_TO_R 200 50 150 0 5000 #1\n", 5000),
    (b"GO_TO_W 200 50 150 0 5000 #1\n", 5000),
])
def test_every_motion_verb_arms_motion_obligation(wa, line, window_ms):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose(0.0, 0.0, 0.0)  # only read by GO_TO_W; harmless otherwise
    wa.set_now_ms(1_000_000)
    assert not wa.has_live_motion_obligation()

    wa.feed(line)
    assert wa.has_live_motion_obligation()

    # Still armed just before the window elapses...
    wa.set_now_ms(1_000_000 + window_ms - 1)
    assert wa.has_live_motion_obligation()

    # ...and clear once it has.
    wa.set_now_ms(1_000_000 + window_ms)
    assert not wa.has_live_motion_obligation()


def test_go_to_w_no_pose_source_does_not_arm_motion_obligation(wa):
    """The refused path (no pose source) must NOT arm the obligation --
    there is no move for protocol.cpp's fiber to keep ticking."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose_source_available(False)
    wa.set_now_ms(1_000_000)

    wa.feed(b"GO_TO_W 200 50 150 0 5000 #1\n")
    assert not wa.has_live_motion_obligation()


def test_get_bare_dumps_all_sixteen_fields_no_wheels_entry(wa):
    """A bare-GET dump lists only the 16 ConfigField-equivalent wire
    names (wire_adapter.cpp's kFields table) -- confirms the old
    multi-pair CONFIG batch verb's ordinal set is fully covered under
    new names, and that no WHEELS-named entry leaked into the config
    table (WHEELS_V is a motion verb, not a config field). Sprint 007
    ticket 001 adds `stall_clear` (ordinal 17) at the end -- the two
    ordinals in between (15/16: default_cruise/rotational_slip) land
    in tickets 003/005 and are not yet present."""
    wa.feed(b"GET #1\n")
    lines = wa.take_sink().split(b"\n")
    names = [line.split(b" ")[1] for line in lines if line.startswith(b"get ")]
    assert names == [
        b"max_duty", b"full_duty_velocity", b"pid_kp", b"pid_ki",
        b"pid_i_max", b"accel_kaff", b"pid_max", b"twist_hold_gain",
        b"speed_floor", b"pos_err_max", b"stall_speed", b"stall_demand",
        b"stall_window", b"lambda_enabled", b"crawl_pulse", b"stall_clear",
    ]
    assert b"wheels" not in b" ".join(names).lower()


def test_stall_clear_wire_field_clears_latch_and_reads_back(wa):
    """Sprint 007 ticket 001 (closing R-01/KERN-01): `stall_clear`'s
    end-to-end wire effect through the REAL WireAdapter + a REAL
    kernel over FakeMotor -- drives the kernel into the stall-latched
    state the same way test_kernel_harness.py's own kernel-level test
    does (sustained demand + still encoders past the configured
    window), then proves `SET stall_clear 1` clears it and `GET
    stall_clear` reads the latch's own state (1 while latched, 0
    after), not a stored config value.
    """
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"SET stall_speed 50 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.feed(b"SET stall_demand 200 #2\n")
    assert wa.take_sink() == _ack(2)
    wa.feed(b"SET stall_window 500 #3\n")
    assert wa.take_sink() == _ack(3)

    # WHEELS_V's real dispatch (setWheelsTimed()'s test double) ->
    # kernel.drive(velocity=500, twist=0, lease=5000ms) -- well above
    # stall_demand, with the lease nowhere near expiring for the rest
    # of this test.
    wa.set_now_ms(1000)  # never 0 -- see test_kernel_harness.py's own
                         # note on updateLatch()'s `since == 0` sentinel

    # Priming step: WaHandle's FakeMotors are never explicitly armed
    # (no such setter exists on this shim, unlike kernel_shim.cpp's
    # kdMotorArmPosition), so WheelSample::connected starts false and
    # only becomes true once refreshSample() has run once -- which
    # happens at the END of step(), AFTER controlStep() already
    # consumed the (still-default) sample for this cycle. One step
    # before drive() takes effect flips connected true for every step
    # after it, matching kernel_shim.cpp-based tests' own baseline-step
    # convention (test_kernel_harness.py).
    wa.step()

    wa.feed(b"WHEELS_V 500 500 5000 #4\n")
    assert wa.take_sink() == _ack(4)

    wa.step()  # first "demanding && still" observation, since=1000ms

    wa.feed(b"GET stall_clear #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)

    wa.set_now_ms(1600)  # +600ms > stall_window -> latches this step()
    wa.step()

    wa.feed(b"GET stall_clear #6\n")
    reply = wa.take_sink()
    prefix = _ack(6) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(1.0, abs=1e-3)

    wa.feed(b"SET stall_clear 1 #7\n")
    assert wa.take_sink() == _ack(7)
    wa.step()  # consumes the clearStallReq_ handshake

    wa.feed(b"GET stall_clear #8\n")
    reply = wa.take_sink()
    prefix = _ack(8) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)
