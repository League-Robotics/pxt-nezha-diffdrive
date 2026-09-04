"""tests/host/test_wire_motion_verbs.py --
the six motion verbs' wire decode/dispatch (WHEELS_X, WHEELS_V, MOVE_X,
MOVE_V, GO_TO_R, GO_TO_W), src/comms/wire_adapter.h's WireAdapter, and STOP's
`now` token.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S4 (the Adapter interface), S5
(the DiffDrive adapter), S6/S6.1 (the
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
  (commanded left/right, distance/
  rotation, v_x/omega, or x/y/speed all map to the correct velocity/
  twist/lease or move-engine segment), the cruise/speed==0 "configured
  default" substitution and the cruise/speed<0 range refusal
  (motion-api.md S1.1), MOVE_X's/MOVE_V's mrad->rad conversion tested in
  both turn directions, GO_TO_W's real effect via a FakePoseSource and
  its honest refusal (ERR_UNIMPLEMENTED) with none available,
  WireAdapter's own GET/SET field-name table, STOP/ESTOP's real effect
  on the kernel, and the motion-obligation flag (the
  arm-from-every-verb bug fix, wire_adapter.h's own header comment) via
  a real nowMs wired in through waSetNowMs()/waHasLiveMotionObligation().

Run with::

    uv run pytest tests/host/test_wire_motion_verbs.py
"""

import ctypes
import math
import pathlib
import re

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _SRC_DIR / "comms" / "wire_handler.cpp",
    _SRC_DIR / "comms" / "wire_adapter.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
]

# Wire::Result's DECLARATION-ORDER ordinal (wire_handler.h) -- NOT the
# wire error code resultCode() maps it to. Mirrors test_wire_grammar.py's
# own RESULT_* constants.
RESULT_OK = 0
RESULT_UNKNOWN = 1
RESULT_BADARG = 2
RESULT_RANGE = 3

# Wire::DoneReason's DECLARATION-ORDER ordinal (wire_handler.h). Sprint
# 005 ticket 004 (closing wire-motion-completion-signal.md/R-23): the
# real WireAdapter now actually PRODUCES every one of these (previously
# only DONE_NONE was ever reachable through this fixture, since
# lastDone()/lastDoneReason() were permanently inert) -- see
# test_wire_motion_completion.py for the tests driving each one.
DONE_NONE = 0
DONE_STOP = 1
DONE_TIMEOUT = 2
DONE_ESTOP = 3
DONE_ABORTED = 4
DONE_STALL = 5
_DONE_REASON_NAME = {
    DONE_NONE: "none",
    DONE_STOP: "stop",
    DONE_TIMEOUT: "timeout",
    DONE_ESTOP: "estop",
    DONE_ABORTED: "aborted",
    DONE_STALL: "stall",
}

# DiffDrive::DifferentialDrive::Status's DECLARATION order (src/core/diffdrive.h).
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
        # Sprint 008 (wire-timeout-hardening.md): GO_TO_W's own timeout
        # accessor -- previously missing, the only one of the six motion
        # verbs with no exported timeout/duration getter on WvHandle (see
        # wvLastGoToWTimeout's own doc comment, wire_motion_verb_shim.cpp).
        "wvLastGoToWTimeout",
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
    # Sprint 007 ticket 003 (closing R-11/BLK-03/API-03): direct
    # test-setup setter for the test double's own defaultCruiseMmS
    # field, mirroring waSetFullDutyVelocity's binding exactly.
    lib.waSetDefaultCruise.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.waSetDefaultCruise.restype = None
    # SUC-003: direct test-setup setters for the real MotionEngine's own
    # aDecelMmS2_/vMaxMmS_/brakeFrac_ -- lets a test switch this
    # handle's engine into shaped mode and confirm onMoveX()/onGoToR()/
    # onGoToW() branch onto the distance-aware resolver while onWheelsX()
    # stays on the flat default above.
    for name in ("waSetADecelMmS2", "waSetVMaxMmS", "waSetBrakeFrac"):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_float]
        fn.restype = None
    lib.waCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.waCountsPerMm.restype = ctypes.c_float
    lib.waEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.waEffectiveTrackWidth.restype = ctypes.c_float
    lib.waBegin.argtypes = [ctypes.c_void_p]
    lib.waBegin.restype = ctypes.c_int
    lib.waStep.argtypes = [ctypes.c_void_p]
    lib.waStep.restype = None
    # Sprint 005 ticket 004: engine.serviceMove() and FakeMotor position
    # arming -- lets a test drive a move-engine move to a REAL completion
    # (goal reached / deadline expired / stalled), not just its first tick.
    lib.waServiceMove.argtypes = [ctypes.c_void_p]
    lib.waServiceMove.restype = ctypes.c_int
    lib.waArmMotorPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.waArmMotorPosition.restype = None
    lib.waMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.waMotorLastStagedDuty.restype = ctypes.c_float

    # ---- sprint 008 ticket 003 (host-harness-double-drift.md/R-25):
    # FakeMotor wedge/wedgeSuspect setters, and MotionEngine's own
    # isMoveActive() readback (the observable proof cancelMove() ran) ----
    lib.waSetMotorWedged.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.waSetMotorWedged.restype = None
    lib.waSetMotorWedgeSuspect.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ]
    lib.waSetMotorWedgeSuspect.restype = None
    lib.waEngineMoveActive.argtypes = [ctypes.c_void_p]
    lib.waEngineMoveActive.restype = ctypes.c_int

    # ---- sprint 003 ticket 012: real nowMs + motion-obligation, and
    # GO_TO_W's FakePoseSource ----
    lib.waSetNowMs.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.waSetNowMs.restype = None
    lib.waHasLiveMotionObligation.argtypes = [ctypes.c_void_p]
    lib.waHasLiveMotionObligation.restype = ctypes.c_int
    # Sprint 005 ticket 004: the real WireAdapter::lastDone()/
    # lastDoneReason() -- polls the completion channel directly.
    lib.waLastDone.argtypes = [ctypes.c_void_p]
    lib.waLastDone.restype = ctypes.c_uint32
    lib.waLastDoneReason.argtypes = [ctypes.c_void_p]
    lib.waLastDoneReason.restype = ctypes.c_int
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

    # sprint 028 ticket 002: `rebase`/`estop_clear` -- the real kernel's
    # own positionEpochLeft/Right (the observable proof rebasePosition()
    # actually ran).
    lib.waOutputPositionEpochLeft.argtypes = [ctypes.c_void_p]
    lib.waOutputPositionEpochLeft.restype = ctypes.c_uint32
    lib.waOutputPositionEpochRight.argtypes = [ctypes.c_void_p]
    lib.waOutputPositionEpochRight.restype = ctypes.c_uint32

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
            # Sprint 008: previously missing (see wvLastGoToWTimeout's own
            # doc comment, wire_motion_verb_shim.cpp) -- appended, not
            # inserted, so this tuple's first two positions stay backward
            # compatible with test_go_to_w_golden_vector's existing
            # pytest.approx((300.0, -400.0)) assertion above.
            self._lib.wvLastGoToWTimeout(self._handle),
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

    def set_default_cruise(self, v):
        """Sprint 007 ticket 003: the test double's own
        defaultCruiseMmS field -- see engineDefaultCruiseMmS()'s
        test-double definition (wire_motion_verb_shim.cpp)."""
        self._lib.waSetDefaultCruise(self._handle, v)

    def set_a_decel_mm_s2(self, v):
        """SUC-003: forwards to the real MotionLimits::setDecel()
        (motion_limits.h). Sprint 029 ticket 003: this used to switch
        MOVE_X/GO_TO_R/GO_TO_W's `cruise`/`speed == 0` resolution over to
        the distance-aware v_default(D) at a nonzero value ("shaped
        mode"); MotionLimits::decel defaults to 400 (never 0 -- design
        S8: "now always active, no legacy mode"), so that resolution is
        now UNCONDITIONAL -- see engineADecelMmS2()'s own comment,
        wire_motion_verb_shim.cpp. Kept for tests that want a specific
        decel value; no longer a mode switch."""
        self._lib.waSetADecelMmS2(self._handle, v)

    def set_v_max_mm_s(self, v):
        self._lib.waSetVMaxMmS(self._handle, v)

    def set_brake_frac(self, v):
        """RETIRED (sprint 029 ticket 003, design S8's wire-name table):
        the new v_default(D) formula (defaultCruiseForDistance(),
        motion_engine.cpp) has no brake_frac term at all -- this is now
        an inert no-op (waSetBrakeFrac()'s own comment,
        wire_motion_verb_shim.cpp), kept only so the many existing
        call sites below stay valid, harmless setup lines."""
        self._lib.waSetBrakeFrac(self._handle, v)

    def land_first_command(self):
        """Sprint 029 ticket 003 (design S6.5's lazy start): a fresh
        Segment (MOVE_X/WHEELS_X/GO_TO_R/GO_TO_W) no longer drives the
        kernel synchronously -- see test_motion_engine_reductions.py's
        own Engine.land_first_command() for the full explanation this
        file mirrors."""
        self.step()
        self.service_move()
        self.step()

    def land_steady_state_command(self, start_ms=0, ticks=60, tick_ms=24):
        """For a fresh Segment (MOVE_X/GO_TO_R/GO_TO_W/WHEELS_X), with NO
        encoder position armed (so `remain` never shrinks and the
        segment never falsely arrives): runs `ticks` REALISTIC (24 ms,
        matching tickDrive()'s own cadence) step()+service_move() cycles
        so the shaper's own accel ramp (400 mm/s^2) climbs from the
        floor to its real target (whatever `cruise`/cap/vMax resolves
        to) and PLATEAUS there -- unlike land_first_command()
        (design S6.1's floor, the transient FIRST tick) or
        land_steady_state_hold() (a single huge `dt`, safe only for a
        Hold's unbounded `remain < 0`; a Segment's bounded `remain`
        would falsely trigger arrival under a huge dt instead)."""
        t = start_ms
        self.set_now_ms(t)
        self.step()
        for _ in range(ticks):
            t += tick_ms
            self.set_now_ms(t)
            self.service_move()
            self.step()

    def land_steady_state_hold(self, start_ms=0, advance_ms=1_000):
        """For a continuous WHEELS_V/MOVE_V hold -- see
        test_motion_engine_reductions.py's own
        Engine.land_steady_state_hold() for the full explanation. Caller
        must have set_now_ms(start_ms) BEFORE the WHEELS_V/MOVE_V verb
        was fed."""
        self.step()
        self.set_now_ms(start_ms + advance_ms)
        self.service_move()
        self.step()

    def counts_per_mm(self):
        return self._lib.waCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.waEffectiveTrackWidth(self._handle)

    def begin(self):
        return self._lib.waBegin(self._handle)

    def step(self):
        self._lib.waStep(self._handle)

    def service_move(self):
        """MotionEngine::serviceMove() (sprint 005 ticket 004) -- unlike
        step() above (kernel.step() only), this is the OTHER half of
        production's tickDrive() pair, needed to drive a move-engine
        move (MOVE_X/GO_TO_R/GO_TO_W) to a real completion. Returns
        whether the move is still active after this call."""
        return bool(self._lib.waServiceMove(self._handle))

    def arm_motor_position(self, side, position_counts, sample_time_us=1):
        """Directly arms a FakeMotor's NEXT step()'s committed position
        (fake_ports.h's own armed-then-committed contract) -- lets a
        test simulate 'the wheel has physically reached this encoder
        count' without a duty-to-position physics model. Mirrors
        test_motion_engine_reductions.py's own Engine.arm_motor_position()."""
        self._lib.waArmMotorPosition(
            self._handle, side, position_counts, sample_time_us)

    def motor_last_staged_duty(self, side):
        return self._lib.waMotorLastStagedDuty(self._handle, side)

    # ---- sprint 008 ticket 003 (host-harness-double-drift.md/R-25) ----
    def set_motor_wedged(self, side, wedged):
        """FakeMotor's LATCHED wedge signal (fake_ports.h's own
        wedgedValue) -- independent of set_motor_wedge_suspect() below,
        the same way diffdrive.h declares wedgeLeft/Right and
        wedgeSuspectLeft/Right as two genuinely different Output
        fields."""
        self._lib.waSetMotorWedged(self._handle, side, 1 if wedged else 0)

    def set_motor_wedge_suspect(self, side, suspect):
        """FakeMotor's SUSPECT wedge signal (wedgeSuspectValue) -- the
        pair production's real diagValue() (shims.cpp) actually reads
        for ordinals 6/7, per this ticket's own fix."""
        self._lib.waSetMotorWedgeSuspect(
            self._handle, side, 1 if suspect else 0)

    def engine_move_active(self):
        """MotionEngine::isMoveActive() -- the real, public observable
        proof a move-engine move (MOVE_X/MOVE_V/GO_TO_R/GO_TO_W) is
        currently in flight, and the only external hook available to
        prove the PRIVATE cancelMove() ran (see setWheelsTimed()'s own
        comment, wire_motion_verb_shim.cpp)."""
        return bool(self._lib.waEngineMoveActive(self._handle))

    # ---- sprint 003 ticket 012: real nowMs + motion-obligation, and
    # GO_TO_W's FakePoseSource ----
    def set_now_ms(self, ms):
        self._lib.waSetNowMs(self._handle, ms)

    def has_live_motion_obligation(self):
        return bool(self._lib.waHasLiveMotionObligation(self._handle))

    def last_done(self):
        """The real WireAdapter::lastDone() -- polled directly, without
        needing a subsequent sequenced verb's own ack/nack to observe
        it (sprint 005 ticket 004)."""
        return self._lib.waLastDone(self._handle)

    def last_done_reason(self):
        """The real WireAdapter::lastDoneReason(), as Wire::DoneReason's
        DECLARATION-ORDER ordinal (see this file's own DONE_* constants)."""
        return self._lib.waLastDoneReason(self._handle)

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
        thdr (if due) then t into this handle's own sink, exactly as
        protocol.cpp's telemetry-subscribed branch does in production.
        No reliability line rides along (2026-08-26, protocol.md S8.5:
        the piggyback is deleted; sprint 024 ticket 001 had already
        deleted the free-running non-subscribed form)."""
        self._lib.waEmitTelemetry(self._handle, snapshot.ptr)

    def on_tlm(self, mode):
        """Calls WireAdapter::onTlm(mode) directly -- bypasses the wire
        grammar entirely (that dispatch path is test_wire_grammar.py's
        own scope); this ticket only needs mode_ SET, not decoded."""
        return self._lib.waOnTlm(self._handle, mode)

    def has_live_telemetry(self):
        return bool(self._lib.waHasLiveTelemetry(self._handle))

    # ---- sprint 028 ticket 002: rebase/estop_clear ----------------------

    def output_position_epoch_left(self):
        """kernel.output().positionEpochLeft -- changes only alongside a
        REAL kernel.rebasePosition() call, on the kernel's own NEXT
        step() (the request is deferred by design). Read after step()."""
        return self._lib.waOutputPositionEpochLeft(self._handle)

    def output_position_epoch_right(self):
        return self._lib.waOutputPositionEpochRight(self._handle)


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
    # Sprint 008: last_go_to_w grew a third element (timeout) -- see
    # wvLastGoToWTimeout's own doc comment, wire_motion_verb_shim.cpp.
    assert wv.last_go_to_w[:2] == pytest.approx((300.0, -400.0))
    assert wv.last_go_to_w[2] == 5000


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
# WHEELS_V's real effect (src/comms/wire_adapter.h's WireAdapter, over a real
# DiffDrive kernel + FakeMotor): commanded left/right map to the correct
# velocity/twist and lease. This is ticket 004's own required proof --
# every other verb's dispatch shape is covered above via WireMockAdapter.
#
# Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25, PY-03
# item 2): setWheelsTimed() now calls the REAL MotionEngine::wheelsV()
# (same as production's shims.cpp), so it applies the REAL countsPerMm()
# scaling like WHEELS_X's own tests already account for (see
# _expected_wheels_x_duty_pair's own comment) -- there is no more
# "countsPerLength fixed at 1.0" shortcut for THIS verb either. The duty
# numbers below were quietly WRONG relative to production before this
# fix: they modeled an uncalibrated 1:1 mm/s->counts/s robot that does
# not exist (travelCalib_'s real default is 0.7878 mm/deg, i.e.
# countsPerMm() != 1.0) -- these tests were passing while describing a
# robot production could never produce. `full_duty_velocity` is bumped
# to `_WHEELS_V_FULL_DUTY_VELOCITY` (matching _WHEELS_X_FULL_DUTY_VELOCITY's
# own choice/rationale) so the larger, cpm-scaled demand stays well
# clear of the maxDuty=100% rail -- an unsaturated feedforward reading,
# not a clamped one wearing an unsaturated one's numbers.
# ---------------------------------------------------------------------------

_WHEELS_V_FULL_DUTY_VELOCITY = 5000.0  # [counts/s]


def _expected_wheels_v_duty(left_mm_s, right_mm_s, cpm, fdv):
    """Mirrors MotionEngine::wheelsV()'s own math (motion_engine.cpp): a
    direct per-wheel VELOCITY hold, no ratio-lock/dominant-wheel
    normalization the way wheelsX() has -- target_left/target_right
    reconstruct the ORIGINAL commanded left/right exactly (velocity=
    mean, twist=half-diff, then kernel_.drive()'s own velocity-+-twist
    split undoes it), each then scaled by cpm and normalized by fdv."""
    return left_mm_s * cpm / fdv, right_mm_s * cpm / fdv


def test_wheels_v_real_effect_pure_forward(wa):
    """left == right (no twist): both wheels stage the identical duty
    velocity/fullDutyVelocity implies (zero-kp feedforward-only path,
    same as test_kernel_harness.py's own smoke test)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.set_now_ms(0)
    wa.feed(b"WHEELS_V 200 200 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

    expected_left, expected_right = _expected_wheels_v_duty(
        200.0, 200.0, cpm, _WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


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
    wa.set_full_duty_velocity(_WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    # Sprint 029 ticket 003: a continuous hold's dominant-wheel target is
    # now capped at MotionLimits::vMax (design S5's hold branch: `cap =
    # limits.vMax`), 250 mm/s by default -- below this test's own 300
    # mm/s dominant (right) wheel. Raised here so the ORIGINAL (100, 300)
    # values -- chosen for the sign-convention proof below -- reach their
    # full commanded speed instead of being silently capped.
    wa.set_v_max_mm_s(1000.0)

    wa.set_now_ms(0)
    wa.feed(b"WHEELS_V 100 300 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

    expected_left, expected_right = _expected_wheels_v_duty(
        100.0, 300.0, cpm, _WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


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
    wa.set_full_duty_velocity(_WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.set_now_ms(0)
    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

    expected_left, _ = _expected_wheels_v_duty(
        100.0, 100.0, cpm, _WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)


# ---------------------------------------------------------------------------
# WIRE-08 (code review 2026-08-23, sprint 007 ticket 007): unclamped
# float->int casts at the wire boundary. `parseInt32` (wire_handler.cpp)
# accepts the wire's full int32 grammar with no ceiling of its own, but
# `static_cast<float>(left/right)` then `static_cast<int>(...)` back
# (WireAdapter::onWheelsV() -> shims.cpp's setWheelsTimed()) is UB
# whenever the intermediate float rounds outside int32's representable
# range -- which happens BEFORE int32's own limit, since float's 24-bit
# mantissa cannot represent every integer near 2^31:
# `static_cast<float>(2147483647)` itself rounds UP to 2147483648.0f
# (2^31, one past INT32_MAX). Casting that back used to saturate
# (benign) on the Cortex-M target's VCVT but yield INT32_MIN on the x86
# host's cvttss2si -- a max-FORWARD wire command reading back as a
# full-speed REVERSE, host and target disagreeing in SIGN. The fix
# refuses (kRange) before either cast ever runs, so host and target can
# no longer disagree: neither one ever computes a duty for a value this
# extreme.
# ---------------------------------------------------------------------------


def test_wheels_v_extreme_positive_value_is_range_refused_not_sign_flip(wa):
    """`WHEELS_V 2147483647 0 1000 #1` sits exactly in WIRE-08's own
    named danger zone ([2147483584, 2147483647]) -- decodes fine at the
    grammar level, but is now refused (ERR_RANGE) by the adapter before
    any cast runs. Before this fix, this host process's own
    static_cast<int>(2147483648.0f) would have produced INT32_MIN, and
    the motor would have staged a full-REVERSE duty for a
    max-FORWARD-looking wire command -- the exact host/target sign
    disagreement WIRE-08 found (benign saturation on the Cortex-M
    target's VCVT, INT32_MIN on this host's cvttss2si)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V 2147483647 0 1000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    # Refused -- the kernel must never have been commanded in EITHER
    # direction (this is exactly the sign-flip scenario WIRE-08 found:
    # a max-forward-looking wire value producing a full-reverse duty).
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_v_extreme_negative_value_is_range_refused(wa):
    """The clamp (kWireBoundaryCastCeiling, wire_adapter.h) is
    symmetric -- a wire value far below the negative bound is refused
    the same way, rather than the policy relying on the negative side
    happening to avoid the exact rounding-past-range case the positive
    side hits (it does, since -2^31 is itself exactly representable as
    a float, but the refusal here does not depend on that fact holding
    for every possible target/compiler)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_V -2100000000 0 1000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_stop_real_effect_returns_duty_to_zero(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.set_now_ms(0)
    wa.feed(b"WHEELS_V 200 200 5000 #1\n")
    wa.land_steady_state_hold()
    expected_left, _ = _expected_wheels_v_duty(
        200.0, 200.0, cpm, _WHEELS_V_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)

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
    other follows the same ratio. Still correct for wheelsX()'s STEADY
    STATE (design S6.1's shaper eventually reaches `cruise`, capped by
    vMax) -- see _first_tick_wheels_x_duty_pair() below for the FIRST
    tick, which floors instead (sprint 029 ticket 003: wheelsX() is now
    closed-loop, Segment-based, and lazily started like moveX(), design
    S12/S6.5)."""
    dominant = max(abs(left), abs(right))
    left_speed = (left / dominant) * cruise    # [mm/s]
    right_speed = (right / dominant) * cruise  # [mm/s]
    return left_speed * cpm / fdv, right_speed * cpm / fdv


_V_FLOOR_MM_S = 70.0
_OMEGA_FLOOR_DEG_S = 20.0


def _first_tick_wheels_x_duty_pair(left, right, cpm, b, fdv):
    """Sprint 029 ticket 003 (design S6.1): wheelsX()'s FIRST real
    command (landed via wa.land_first_command()) floors instead of
    reaching `cruise` -- v_floor for a straight/blended pair, or
    omega_floor (converted to the dominant wheel's own mm/s, design
    S6.2) for a pure pivot (left == -right)."""
    dominant = max(abs(left), abs(right))
    pure_turn = (left == -right and left != 0.0)
    if pure_turn:
        floor_mm_s = _OMEGA_FLOOR_DEG_S * math.pi / 180.0 * b * 0.5
    else:
        floor_mm_s = _V_FLOOR_MM_S
    left_speed = (left / dominant) * floor_mm_s
    right_speed = (right / dominant) * floor_mm_s
    return left_speed * cpm / fdv, right_speed * cpm / fdv


# Chosen large enough that every commanded speed below (through
# MotionEngine's real countsPerMm() -- sprint 008 ticket 003 put
# WHEELS_V's own real-effect tests, above, on the SAME real cpm too;
# neither verb's double fixes countsPerLength at 1.0 any more) stays
# well under the maxDuty=100% rail -- mirrors test_motion_engine_primitives.py's
# own identical choice and rationale: no assertion here is secretly
# checking a clamped value in disguise.
_WHEELS_X_FULL_DUTY_VELOCITY = 5000.0  # [counts/s]


def test_wheels_x_real_effect_straight_line(wa):
    """wheels_x(d, d) is a straight line -- both wheels at ratio 1, so
    both run at exactly `cruise` (motion-api.md S2.1's own degenerate
    case)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    b = wa.effective_track_width()
    wa.feed(b"WHEELS_X 200 200 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_first_command()

    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 200.0, cpm, b, _WHEELS_X_FULL_DUTY_VELOCITY)
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

    b = wa.effective_track_width()
    wa.feed(b"WHEELS_X 200 100 150 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_first_command()

    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 100.0, cpm, b, _WHEELS_X_FULL_DUTY_VELOCITY)
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
    b = wa.effective_track_width()
    fdv = _WHEELS_X_FULL_DUTY_VELOCITY
    floor_mm_s = _OMEGA_FLOOR_DEG_S * math.pi / 180.0 * b * 0.5

    wa.feed(b"WHEELS_X 150 -150 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_first_command()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        floor_mm_s * cpm / fdv)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        -floor_mm_s * cpm / fdv)

    wa.feed(b"WHEELS_X -150 150 100 5000 #2\n")
    assert wa.take_sink() == _ack(2)
    wa.land_first_command()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        -floor_mm_s * cpm / fdv)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        floor_mm_s * cpm / fdv)


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
    """Sprint 007 ticket 003 (closing R-11/BLK-03/API-03,
    cruise-zero-sentinel-full-duty-lunge.md): motion-api.md S1.1's
    "Pass 0 for the configured default" now resolves through the wire
    layer's OWN `default_cruise` field (shims.cpp's `defaultCruiseMmS_`
    / this double's `defaultCruiseMmS`), NOT `full_duty_velocity`.
    `full_duty_velocity` is deliberately set here to a value whose OLD
    (retired) derivation -- fullDutyVelocity/cpm =~ 405 mm/s -- differs
    clearly from the new default (150 mm/s): if the double (or the
    real function) ever reverted to the old contract, this test would
    fail on the wrong NUMBER, not merely "still nonzero". Uses the same
    large full_duty_velocity as the WHEELS_X real-effect tests above
    (_WHEELS_X_FULL_DUTY_VELOCITY's own rationale: wheelsX() is a
    PRIMITIVE with no ramp scaling, so 150 mm/s must stay well under
    the maxDuty=100% rail on its own, unlike MOVE_X's first-tick 0.25
    floor)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    default_cruise = 150.0  # [mm/s] -- NOT fullDutyVelocity/cpm

    b = wa.effective_track_width()
    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_first_command()

    # The FIRST tick floors (v_floor), regardless of what `default_cruise`
    # resolved to -- design S6.1. `default_cruise` (150 mm/s) is still
    # what governs the STEADY STATE the shaper ramps toward, not this
    # tick; see _expected_wheels_x_duty_pair()'s own comment.
    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 200.0, cpm, b, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


def test_wheels_x_cruise_zero_without_configured_default_is_range_error(wa):
    """`default_cruise` explicitly forced to 0 via the test double's
    direct setter -- unlike before this ticket, merely never calling
    set_full_duty_velocity no longer suffices: production seeds
    `defaultCruiseMmS_`/this double's `defaultCruiseMmS` to 150.0f, so
    a fresh Rig now HAS a configured default. `full_duty_velocity` is
    set to a healthy nonzero value here specifically to prove the
    refusal is driven by `default_cruise` alone, independent of
    `fullDutyVelocity` -- under the OLD (retired) contract this would
    have produced a valid ~81 mm/s default and NOT refused."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(0.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_wheels_x_cruise_zero_sentinel_unaffected_by_shaping_fields(wa):
    """SUC-003's own explicit carve-out, pinned so a future change
    cannot silently widen scope here: WHEELS_X's `cruise == 0`
    resolution stays the flat engineDefaultCruiseMmS() UNCONDITIONALLY
    -- wheelsX()'s two independent per-wheel distances have no single
    "leg length" the distance-aware v_default(D) formula is defined
    over. Setting aDecelMmS2_/vMaxMmS_/brakeFrac_ to values that would
    resolve MOVE_X's identical sentinel to a markedly DIFFERENT speed
    (see test_move_x_cruise_zero_shaped_mode_uses_distance_aware_default
    just above) must leave THIS verb reading the flat default,
    unchanged."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)
    wa.set_a_decel_mm_s2(700.0)
    wa.set_brake_frac(0.375)
    wa.set_v_max_mm_s(1000.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    default_cruise = 150.0  # [mm/s] -- must stay this, not v_default(200)

    b = wa.effective_track_width()
    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_first_command()

    # The FIRST tick floors (v_floor), regardless of what `default_cruise`
    # resolved to -- design S6.1. `default_cruise` (150 mm/s) is still
    # what governs the STEADY STATE the shaper ramps toward, not this
    # tick; see _expected_wheels_x_duty_pair()'s own comment.
    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 200.0, cpm, b, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


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


def _first_tick_move_x_duty_pair(distance_mm, rotation_rad, cpm, b, fdv):
    """Sprint 029 ticket 003 (design S6.1/S6.5): moveX()'s FIRST real
    command, landed via wa.land_first_command() -- floors instead of
    the OLD `cruise * 0.25` ramp fraction (see this file's own
    _first_tick_wheels_x_duty_pair() for the identical formula/
    rationale, restated here for moveX()'s distance/rotation
    parameterization)."""
    left, right, dominant = _move_x_segment(distance_mm, rotation_rad, cpm, b)
    pure_turn = (distance_mm == 0.0 and rotation_rad != 0.0)
    if pure_turn:
        floor_mm_s = _OMEGA_FLOOR_DEG_S * math.pi / 180.0 * b * 0.5
    else:
        floor_mm_s = _V_FLOOR_MM_S
    floor_counts = floor_mm_s * cpm
    raw_left = (left / dominant) * floor_counts
    raw_right = (right / dominant) * floor_counts
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
    wa.land_first_command()

    expected_left, expected_right = _first_tick_move_x_duty_pair(
        200.0, 0.0, cpm, b, 1000.0)
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
    wa.land_first_command()

    expected_left, expected_right = _first_tick_move_x_duty_pair(
        0.0, rotation_mrad / 1000.0, cpm, b, 1000.0)
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
    wa.land_first_command()

    expected_left, expected_right = _first_tick_move_x_duty_pair(
        0.0, rotation_mrad / 1000.0, cpm, b, 1000.0)
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


# ---------------------------------------------------------------------------
# SUC-003: MOVE_X's `cruise == 0` sentinel. Sprint 029 ticket 003 (design
# S8): resolves through MotionEngine::defaultCruiseForDistance() --
# v_default(D) = min(vMax, sqrt(decel*D)) -- UNCONDITIONALLY now, using
# this call's OWN `distance` argument (or wheel-travel, for a pure pivot)
# as D. There is no more "legacy vs shaped mode" toggle to select this
# (design S8: "accel/decel ... now always active, no legacy mode") --
# MotionLimits::decel defaults to 400 and can never be set back to 0, so
# the flat `default_cruise` field (still real, still settable, still what
# WHEELS_X's own cruise==0 sentinel reads unconditionally -- see
# test_wheels_x_cruise_zero_uses_configured_default above) is simply
# never consulted by MOVE_X/GO_TO_R/GO_TO_W any more. This is a genuine,
# ticket-3-forced behavior change (not a choice made here): shims.cpp's
# own wire-layer selector (`engineADecelMmS2() > 0.0f ? distance-aware :
# flat`, wire_adapter.cpp's resolveMoveXCruise()) is UNCHANGED code, but
# now always takes the distance-aware branch since limits().decel is
# never 0. The five tests below replace the old
# test_move_x_cruise_zero_uses_configured_default/
# _without_configured_default_is_range_error/_shaped_mode_*/
# _legacy_mode_unaffected_by_shaping_fields, whose own premises (a flat
# default MOVE_X could fall back to, and a toggleable "shaped mode") no
# longer exist.
#
# Verification note: the resolved cruise is a STEADY-STATE value -- the
# segment's own FIRST tick always floors regardless of what cruise
# resolves to (design S6.1: "from rest, the first command is exactly the
# floor"), so these tests use land_steady_state_command() (not
# land_first_command()) to let the shaper's accel ramp actually reach
# the resolved cruise before reading duty.
# ---------------------------------------------------------------------------


_SHAPED_FULL_DUTY_VELOCITY = 5000.0  # [counts/s] -- large enough that
                                      # the resolved cruises below stay
                                      # well under the maxDuty=100% rail
                                      # at full (unscaled) steady-state
                                      # duty, not just the old 0.25 ramp
                                      # floor.


def test_move_x_cruise_zero_always_uses_distance_aware_default(wa):
    """MOVE_X's `cruise == 0` now always resolves through
    defaultCruiseForDistance() -- `default_cruise` (set here to a
    deliberately DIFFERENT value) is never consulted."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # must NOT be the value used below --
                                   # proves it is genuinely ignored now
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    distance = 100.0  # sqrt(decel*D) stays comfortably under vMax (250)
    resolved_cruise = math.sqrt(400.0 * distance)  # design S8, limits().decel
    assert resolved_cruise != pytest.approx(150.0)

    wa.feed(f"MOVE_X {distance:.0f} 0 0 5000 #1\n".encode())
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_command()

    expected_left, expected_right = _expected_move_x_duty_pair(
        distance, 0.0, resolved_cruise, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


def test_move_x_cruise_zero_reverse_distance_uses_magnitude(wa):
    """A reverse move's `distance` arrives NEGATIVE on the wire -- the
    resolver's own D must be this call's distance MAGNITUDE (the
    braking formula is defined over a length), not the signed value,
    which would otherwise clamp to 0 inside defaultCruiseForDistance()
    and wrongly refuse every reverse default-speed move."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    distance = -100.0
    resolved_cruise = math.sqrt(400.0 * abs(distance))

    wa.feed(f"MOVE_X {distance:.0f} 0 0 5000 #1\n".encode())
    assert wa.take_sink() == _ack(1)  # NOT a range refusal
    wa.land_steady_state_command()

    expected_left, expected_right = _expected_move_x_duty_pair(
        distance, 0.0, resolved_cruise, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


def test_move_x_cruise_zero_pure_pivot_uses_wheel_travel_default(wa):
    """A pure-pivot MOVE_X (distance == 0) has a REAL wheel-travel
    distance even though the chassis itself does not translate: each
    wheel moves |rotation_rad| * effectiveTrackWidth() / 2 mm. Every
    pivot in a tour is exactly this call -- resolving D from |distance|
    alone would always see D == 0 here and refuse every default-speed
    pivot. D must come from MotionEngine::dominantAxisTravel(), the same
    `dominant` quantity beginSegment() itself reduces to -- so this call
    succeeds, resolved from the pivot's own wheel travel, not refused."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # must NOT be the value used below
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    rotation_mrad = 300
    rotation_rad = rotation_mrad / 1000.0
    wheel_travel = abs(rotation_rad) * b / 2.0
    resolved_cruise = math.sqrt(400.0 * wheel_travel)
    assert resolved_cruise != pytest.approx(150.0)

    wa.feed(f"MOVE_X 0 {rotation_mrad} 0 5000 #1\n".encode())
    assert wa.take_sink() == _ack(1)  # NOT a range refusal
    wa.land_steady_state_command()

    expected_left, expected_right = _expected_move_x_duty_pair(
        0.0, rotation_rad, resolved_cruise, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


def test_move_x_cruise_zero_both_zero_is_range_error(wa):
    """The one genuinely degenerate case: distance == 0 AND rotation ==
    0 -- no wheel travel on EITHER axis, so D == 0 and the resolved
    default is refused (kRange), the same way an explicit `cruise <= 0`
    already is -- never a silently-accepted zero-speed command that
    reports success while commanding nothing."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(150.0)  # irrelevant either way now
    assert wa.begin() == STATUS_OK

    wa.feed(b"MOVE_X 0 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert not wa.engine_move_active()
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
    """SET and GET now answer an unknown field name IDENTICALLY
    (2026-08-27). This test used to show the asymmetry in adjacent
    lines -- SET errored, GET acked and said nothing -- which is the
    clearest statement of why it was wrong: same config plane, same
    mistake, two different answers, one of them silent."""
    wa.feed(b"SET nosuch_field 1.0 #1\n")
    assert wa.take_sink() == _ack(1) + _err(1, 1)  # ERR_UNKNOWN

    wa.feed(b"GET nosuch_field #2\n")
    assert wa.take_sink() == _ack(2) + _err(1, 2)  # ERR_UNKNOWN, same


def test_set_value_times_1000_overflow_is_range_refused(wa):
    """WIRE-08 (code review 2026-08-23, sprint 007 ticket 007):
    `parseFloatField` (wire_handler.cpp) accepts any finite float with
    no ceiling of its own, but `onSet()`'s x1000 scaling convention
    (mirroring setKernelValue()'s own, shims.cpp) can turn an
    absurd-but-legal field value into a product that overflows `long`'s
    32-bit range before std::lround() ever runs. `SET pid_kp 3000000`
    scales to 3e9 -- refused (ERR_RANGE) rather than landing an
    unspecified/garbage gain in the kernel from an acked, in-grammar
    line. Verified against `pid_kp` specifically because that is the
    exact field WIRE-08 names, and because its kernel default (0.0,
    DifferentialDrive::Config's own default) makes "unwritten" and
    "written to something absurd" unambiguous to tell apart on
    readback."""
    wa.feed(b"SET pid_kp 3000000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE

    # Refused -- the kernel's own pid_kp must still read back its
    # unwritten, uncalibrated default, never the garbage product of an
    # overflowed x1000 scale-then-round.
    wa.feed(b"GET pid_kp #2\n")
    reply = wa.take_sink()
    prefix = _ack(2) + b"get pid_kp "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)


def test_set_value_large_but_sane_is_still_accepted(wa):
    """The new WIRE-08 clamp must not be so tight it starts refusing
    ordinary (if unusually large) configured gains -- a value whose
    x1000 product (2e6) sits comfortably inside the +-2e9 cast-safe
    range must still be accepted and round-trip through GET, same
    shape as test_get_set_field_name_table_round_trips above. (Chosen
    small enough that GET's OWN, unrelated, pre-existing x1000 cast
    -- getConfigValue()'s `static_cast<int>(c.kp * 1000.0f)`, not
    touched by this ticket -- also stays comfortably in range, so this
    test isolates the SET-side clamp this ticket adds.)"""
    wa.feed(b"SET pid_kp 2000 #1\n")  # x1000 -> 2e6, well inside range
    assert wa.take_sink() == _ack(1)

    wa.feed(b"GET pid_kp #2\n")
    reply = wa.take_sink()
    prefix = _ack(2) + b"get pid_kp "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(2000.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Sprint 010 ticket 006 (closing get-full-duty-velocity-returns-
# garbage.md): formatConfigValue()'s (wire_handler.cpp) scaling
# intermediate used to overflow a `uint32_t` for ANY field whose real
# magnitude reached ~4295 (kDivisor's own 10^6 scale against uint32_t's
# own range), always clamping to the SAME wrong constant, 4294.967040,
# independent of the field's real value -- full_duty_velocity (10795.0)
# was simply the first of today's kFields entries large enough to cross
# that line (confirmed by reading every seeded Config value in
# shims.cpp's ensure()). This sweep proves the fix generically, across
# EVERY field wire_adapter.cpp's kFields table declares, not just that
# one -- field names are discovered dynamically off a bare `GET #<id>`
# dump (never hardcoded, and never assumed to be exactly however many
# entries kFields happens to have today -- sprint 009's own guideline:
# a hardcoded field count rots the moment a field is added or removed),
# so this test tracks kFields automatically.
# ---------------------------------------------------------------------------

# One representative value per kFields entry, chosen to exercise
# formatConfigValue()'s six-fixed-digit formatting honestly for that
# field's own real semantics. Most are plain gains/thresholds (an
# ordinary SET/GET round trip) -- several are deliberately the SAME
# values get-full-duty-velocity-returns-garbage.md's own root-cause
# section reads off shims.cpp's ensure() (max_duty, pid_ki, pid_i_max,
# pid_max, pos_err_max, stall_speed, stall_demand, stall_window,
# twist_hold_gain), so this sweep exercises the SAME real magnitudes
# production actually seeds, not arbitrary numbers. `v_floor`'s own
# value (893.2) is NOT one of these any more (sprint 029 ticket 004):
# ordinal 8 no longer reaches the kernel's own vMin/ensure() seed at
# all -- it is a plain positive MotionLimits::vFloor round trip now,
# kept at its historical value only for continuity across the rename.
# Two
# fields are NOT plain stored values and are called out individually:
#   - lambda_enabled: setKernelValue() case 13 (wire_motion_verb_shim.cpp,
#     mirroring shims.cpp) coerces ANY nonzero SET to a stored 1.0
#     (`k.setLambdaEnabled(v != 0.0f)`) -- 1.0 is the representative
#     value a round trip can actually land on exactly.
#   - stall_clear: a WRITE-TRIGGERED ACTION wearing a config-field's
#     clothes (setKernelValue() case 17) -- its GET side reads
#     `kernel.output().stallHalted`, NOT the value just SET. 0.0 is a
#     legitimate no-op SET (only a nonzero value triggers
#     clearStallLatch()) whose honest GET readback on a freshly created,
#     never-stalled kernel is 0.0 -- this sweep proves formatConfigValue()
#     formats that 0.0 correctly, not that this field round-trips an
#     arbitrary value (it structurally cannot; this file's own dedicated
#     stall_clear tests elsewhere already cover its real write-then-clear
#     behavior).
#   - estop_clear (sprint 028 ticket 002): the same write-triggered-
#     action shape as stall_clear immediately above -- its GET side
#     reads `kernel.output().estopped`, NOT the value just SET. 0.0 is a
#     legitimate no-op SET (only a nonzero value calls kernel.
#     estopClear()) whose honest GET readback on a freshly created,
#     never-estopped kernel is 0.0. `rebase` (ordinal 32) has NO entry
#     here at all, deliberately -- it never appears in `names` in the
#     first place, since its GET is refused outright rather than
#     answering a convenience 0.0 (see wire_adapter.cpp's onGet() and
#     test_rebase_get_is_refused).
# crawl_pulse's own documented range is [-1, 1] (diffdrive.h) -- 0.75
# stays inside it rather than picking an arbitrary out-of-contract value.
_KFIELDS_REPRESENTATIVE_VALUES = {
    "max_duty": 100.0,
    "full_duty_velocity": 10795.0,  # the issue's own reported value
    "pid_kp": 42.5,
    "pid_ki": 6.0,
    "pid_i_max": 765.6,
    "accel_kaff": 3.25,
    "pid_max": 1276.0,
    "twist_hold_gain": 2.0,
    # Sprint 029 ticket 004 (design motion-profile-unification.md S4.7):
    # renamed from speed_floor -- same ordinal (8), now MotionLimits::
    # vFloor (mm/s) instead of the kernel's own vMin (counts/s); see K5
    # (this ordinal's own round-trip value is unaffected by the unit
    # reinterpretation -- it is still just a positive number this test
    # round-trips, not a physically-checked speed).
    "v_floor": 893.2,
    "pos_err_max": 127.6,
    "stall_speed": 191.4,
    "stall_demand": 510.4,
    "stall_window": 500.0,
    "lambda_enabled": 1.0,
    "crawl_pulse": 0.75,
    "default_cruise": 150.0,
    "rotational_slip": 0.952,
    "stall_clear": 0.0,
    # renamed from pivot_overrun (ordinal 18 unchanged) -- vevov's
    # measured value (motion_limits.h's own MotionLimits::stopDistance
    # comment).
    "stop_distance": 2.2,
    # Sprint 029 ticket 004 (design S4.7): accel/decel/v_max keep their
    # names, now backed by MotionLimits instead of the deleted
    # MotionEngine shaping fields. Values chosen inside each field's own
    # documented/validated range (motion_limits.h) -- none is the
    # field's shipped default, so a round trip that silently no-ops
    # (validation rejecting the SET) would show up as a mismatch against
    # the field's real default instead of passing by coincidence.
    "accel": 500.0,
    "decel": 700.0,
    "v_max": 300.0,
    "jerk": 4000.0,
    # renamed from max_yaw_rate (ordinal 30 unchanged).
    "omega_max": 90.0,
    # NEW ordinals this ticket adds (34-36, design S4.7) -- same
    # non-default-value rationale as accel/decel/v_max above.
    "omega_floor": 25.0,
    "arrive_dist": 2.5,
    "arrive_yaw": 0.6,
    # Sprint 029 ticket 009 (design S4.1/S6.1/S10.2): NEW ordinal (37) --
    # the drivetrain's own first-order response lag, [s]. Same
    # non-default-value rationale as accel/decel/v_max above.
    "lag": 0.08,
    "estop_clear": 0.0,
}


def _bare_get_field_names(wa, seq_id):
    """Discovers every field name the adapter's bare `GET #<id>` dump
    reports, in wire order -- derived from the wire itself so this never
    hardcodes kFields' own count. Returns (names, next_seq_id)."""
    wa.feed(f"GET #{seq_id}\n".encode())
    reply = wa.take_sink()
    ack = _ack(seq_id)
    assert reply.startswith(ack), reply
    body = reply[len(ack):]
    names = []
    for line in body.split(b"\n"):
        if not line:
            continue
        assert line.startswith(b"get "), line
        names.append(line.split(b" ")[1].decode())
    return names, seq_id + 1


# Sprint 029 ticket 003 left eight kFields names (brake_frac,
# dist_taper, yaw_taper, dist_floor, turn_floor, ramp_ms,
# plateau_min_s, profile_exit) in wire_adapter.cpp's own table with
# their BACKING MotionEngine fields already deleted -- SET acked but
# GET no longer read back what was set, a one-release migration gap
# that ticket ticket 003 explicitly left for ticket 004 to close.
# Ticket 004 (this sprint) closes it: wire_adapter.cpp's kFields no
# longer names any of those eight at all, so `_bare_get_field_names()`
# never reports them here in the first place, and every name this
# sweep DOES see now genuinely round-trips -- no more excluded-name
# special case needed. See test_config_descriptor_table.py for the
# dedicated `err 1` coverage of those eight retired names (both GET and
# SET), which this sweep does not (and should not) exercise on its own.


def test_get_set_sweeps_every_kfields_entry_without_overflow(wa):
    """Sprint 010 ticket 006's own sweep AC: loop over EVERY field
    wire_adapter.cpp's kFields table declares (not a single field), SET
    each to a representative value through the real adapter, and assert
    GET's reply round-trips it -- proving formatConfigValue()'s overflow
    fix is generic, not a full_duty_velocity-specific patch. The set
    equality assertion below (rather than a plain per-name dict lookup)
    catches BOTH directions of drift: a kFields entry added with no
    matching representative value here, and a stale representative-value
    entry for a field kFields no longer declares.

    Round-trip tolerance mirrors test_get_set_field_name_table_round_
    trips' own documented precedent immediately above (that scaling
    convention -- onSet()/onGet()'s SEPARATE, pre-existing x1000/x0.001
    float32 round trip in wire_adapter.cpp, untouched by this ticket --
    was never bit-exact); this test's own dedicated exact-value proof of
    formatConfigValue() ITSELF lives in test_wire_grammar.py instead
    (isolated from that unrelated imprecision via WireMockAdapter's
    onGet() override)."""
    names, seq_id = _bare_get_field_names(wa, 1)
    assert set(names) == set(_KFIELDS_REPRESENTATIVE_VALUES), (
        "wire_adapter.cpp's kFields table has drifted from this sweep's "
        "own representative-value table (a field was added, removed, or "
        "renamed) -- update _KFIELDS_REPRESENTATIVE_VALUES above to "
        "match before trusting this sweep again.\n"
        f"kFields (wire):        {sorted(names)}\n"
        f"representative table:  {sorted(_KFIELDS_REPRESENTATIVE_VALUES)}"
    )
    assert len(names) == len(set(names)), "kFields dump reported a duplicate field name"

    for name in names:
        value = _KFIELDS_REPRESENTATIVE_VALUES[name]
        wa.feed(f"SET {name} {value} #{seq_id}\n".encode())
        assert wa.take_sink() == _ack(seq_id), name
        seq_id += 1

        wa.feed(f"GET {name} #{seq_id}\n".encode())
        reply = wa.take_sink()
        prefix = _ack(seq_id) + f"get {name} ".encode()
        assert reply.startswith(prefix), (name, reply)
        got = float(reply[len(prefix):])
        assert got == pytest.approx(value, rel=1e-3, abs=1e-3), (
            f"{name}: SET {value}, GET read back {got} -- "
            f"formatConfigValue() scaling regression "
            f"(get-full-duty-velocity-returns-garbage.md)"
        )
        # The overflow bug's own signature: EVERY field whose real
        # magnitude crossed ~4295 clamped to this SAME wrong constant,
        # regardless of its actual value. Never allowed to appear here,
        # on ANY field, not just full_duty_velocity.
        assert not reply.endswith(b"4294.967040\n"), (
            f"{name}: GET reply is the OLD uint32_t-overflow sentinel "
            f"value -- the exact defect this ticket fixes"
        )
        seq_id += 1


# ---------------------------------------------------------------------------
# MOVE_V's real effect (sprint 003 ticket 012): the plain wheelsV
# reduction -- move_v(v_x, omega) == wheels_v(v_x - omega*b/2,
# v_x + omega*b/2) (motion-api.md S2) -- dispatched onto
# MotionEngine::moveV() via WireAdapter::onMoveV(). Verified the same way
# WHEELS_X's own real-effect tests above are: FakeMotor's LAST STAGED
# DUTY after exactly one step(), computed through this handle's REAL
# countsPerMm()/effectiveTrackWidth() -- same real cpm scaling WHEELS_V's
# own dedicated real-effect tests further above now also use (sprint 008
# ticket 003: setWheelsTimed()'s test double calls the REAL
# MotionEngine::wheelsV(), the same class MOVE_V/WHEELS_X/MOVE_X already
# go through, so there is no more "fixed at 1.0" double anywhere in this
# file). No ramp/taper scaling either -- wheelsV() is a PRIMITIVE, not a
# move-engine segment.
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

    wa.set_now_ms(0)
    wa.feed(b"MOVE_V 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

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
    wa.set_now_ms(0)
    wa.feed(b"MOVE_V 0 300 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

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
    wa.set_now_ms(0)
    wa.feed(b"MOVE_V 0 -300 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

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

    wa.set_now_ms(0)
    wa.feed(b"MOVE_V 150 200 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

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

    wa.set_now_ms(0)
    wa.feed(b"MOVE_V 100 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_hold()

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
    wa.land_first_command()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    assert abs(theta) < math.radians(50.0)
    expected_left, expected_right = _first_tick_move_x_duty_pair(
        s, theta, cpm, b, 1000.0)
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


def test_go_to_r_speed_zero_uses_chord_distance_default(wa):
    """motion-api.md S1.1's "configured default" substitution, exercised
    through GO_TO_R's own path. Sprint 029 ticket 003 (design S8):
    GO_TO_R's `speed == 0` now always resolves through
    defaultCruiseForDistance() using the chord hypot(x, y) as D --
    `default_cruise` (set here to a deliberately DIFFERENT value) is
    never consulted, the same behavior change MOVE_X's own cruise==0
    sentinel gets (see test_move_x_cruise_zero_always_uses_distance_
    aware_default's own comment for why). GO_TO_R's `(x, y)` are already
    BODY-frame -- exactly the chord goToR() itself drives, whether it
    takes the plain-arc branch (this test's own choice of (x, y) stays
    well under the 50 deg pivot-first split threshold) or the
    pivot-then-chord split -- so hypot(x, y) is D with no approximation,
    unlike GO_TO_W below. Verified at STEADY STATE (land_steady_state_
    command()), not the first tick -- see that method's own comment."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # must NOT be the value used below
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    x, y = 200.0, 50.0
    chord = math.hypot(x, y)
    # design S8: v_default(D) = min(vMax, sqrt(decel*D)) -- this chord's
    # own sqrt(400*206.16)=287 mm/s exceeds the default vMax (250), so
    # the resolved speed is vMax-clamped, not the raw formula value.
    resolved_speed = min(250.0, math.sqrt(400.0 * chord))
    assert resolved_speed != pytest.approx(150.0)

    wa.feed(b"GO_TO_R 200 50 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_command()

    theta, s = _go_to_r_theta_s(x, y)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, resolved_speed, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


def test_go_to_r_speed_zero_shaped_mode_same_position_is_range_error(wa):
    """A target AT the current position ((0, 0), a legitimate no-op
    goToR() itself would normally absorb via its own `arrive` gate)
    resolves D == hypot(0, 0) == 0, hence v_default(0) == 0 -- refused
    (kRange) at the WIRE layer, before goToR() ever runs and could
    recognize the no-op. This is the same D == 0 outcome this ticket's
    acceptance criteria call for, applied to GO_TO_R specifically; it
    is a real, deliberately-accepted behavior difference from legacy
    mode, where the identical call would have resolved to the flat
    default and let goToR()'s own arrive gate no-op successfully."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # would have succeeded in legacy mode
    wa.set_a_decel_mm_s2(700.0)
    wa.set_brake_frac(0.375)
    wa.set_v_max_mm_s(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"GO_TO_R 0 0 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    wa.step()

    assert not wa.engine_move_active()
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
    wa.land_first_command()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    expected_left, expected_right = _first_tick_move_x_duty_pair(
        s, theta, cpm, b, 1000.0)
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
    wa.land_first_command()

    body_x, body_y = _world_to_body(target_x - pose_x, target_y - pose_y,
                                    heading)
    theta, s = _go_to_r_theta_s(body_x, body_y)
    assert abs(theta) < math.radians(50.0)
    expected_left, expected_right = _first_tick_move_x_duty_pair(
        s, theta, cpm, b, 1000.0)
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


def test_go_to_w_speed_zero_uses_target_distance_default(wa):
    """GO_TO_W's own speed==0 substitution, gated on a real pose source
    being available (motion-api.md S3.6). Sprint 029 ticket 003 (design
    S8): resolves through defaultCruiseForDistance() using the TRUE
    chord from the robot's current pose to the target
    (engineGoToWChordMm(), shims.cpp) as D -- `default_cruise` (set here
    to a deliberately DIFFERENT value) is never consulted, the same
    behavior change MOVE_X/GO_TO_R get (see
    test_move_x_cruise_zero_always_uses_distance_aware_default's own
    comment). Identity pose (0, 0, 0), same as
    test_go_to_w_identity_pose_matches_go_to_r above, so the body-frame
    target equals GO_TO_R's own (200, 50) case and the chord is exactly
    hypot(200, 50), no approximation. Verified at STEADY STATE."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # must NOT be the value used below
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    wa.set_pose_source_available(True)
    wa.set_pose(0.0, 0.0, 0.0)

    x, y = 200.0, 50.0
    chord = math.hypot(x, y)
    resolved_speed = min(250.0, math.sqrt(400.0 * chord))
    assert resolved_speed != pytest.approx(150.0)

    wa.feed(b"GO_TO_W 200 50 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_command()

    theta, s = _go_to_r_theta_s(x, y)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, resolved_speed, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


def test_go_to_w_speed_zero_uses_true_chord_not_world_origin_distance(wa):
    """FIXED defect: onGoToW()'s (x, y) are WORLD-frame absolute target
    coordinates (unlike onGoToR()'s already-body-frame (x, y)), so the
    resolver must NOT use hypot(x, y) of the target alone -- that would
    be the target's distance from the WORLD ORIGIN, not this call's
    actual travel distance, and would resolve an unbrakeable speed for
    a short local hop whenever the robot sits far from the origin
    (exactly this rig's own +-67/+-45 cm playfield frame). D must be
    the TRUE chord from the robot's CURRENT pose to the target -- proven
    here with a robot sitting well away from the origin (500, 500)
    asked for a genuinely SHORT 5 mm local hop: the resolved speed must
    come from that 5 mm chord, not the ~707 mm distance-from-origin the
    old, broken resolution would have used."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_SHAPED_FULL_DUTY_VELOCITY)
    wa.set_default_cruise(150.0)  # must NOT be the value used below
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    pose_x, pose_y, heading = 500.0, 500.0, 0.0
    target_x, target_y = 505.0, 500.0
    wa.set_pose(pose_x, pose_y, heading)

    real_chord = math.hypot(target_x - pose_x, target_y - pose_y)
    world_origin_distance = math.hypot(target_x, target_y)
    assert real_chord == pytest.approx(5.0)
    assert world_origin_distance > 700.0  # the WRONG distance, pre-fix

    resolved_speed = math.sqrt(400.0 * real_chord)
    wrong_speed_from_origin = min(250.0, math.sqrt(400.0 * world_origin_distance))
    # The corrected speed is small and sane for a 5 mm hop; the
    # pre-fix speed would have been far larger -- this is the failure
    # SUC-003 exists to prevent, now avoided.
    assert resolved_speed < 60.0
    assert resolved_speed < wrong_speed_from_origin

    wa.feed(b"GO_TO_W 505 500 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.land_steady_state_command()

    body_x, body_y = _world_to_body(
        target_x - pose_x, target_y - pose_y, heading)
    theta, s = _go_to_r_theta_s(body_x, body_y)
    # design S6.1's floor is "the ONLY floor in the system" -- it wins
    # even over a resolved cruise below it (this 5 mm hop's own 44.7
    # mm/s resolved speed is under v_floor's 70 mm/s), so the ACTUAL
    # steady-state driving speed is v_floor, not the raw resolved value.
    driven_speed = max(_V_FLOOR_MM_S, resolved_speed)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, driven_speed, cpm, b, _SHAPED_FULL_DUTY_VELOCITY,
        scale=1.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-3)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-3)


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


# ---------------------------------------------------------------------------
# Sprint 008 (wire-timeout-hardening.md, R-06 + R-18, code review
# 2026-08-23): timeout/duration boundary hardening. One shared decode-time
# clamp (wire_handler.cpp's clampMotionTimeout()) now runs ahead of every
# one of the six motion verbs' own Adapter dispatch, replacing what used to
# be two disagreeing, untested behaviors for `timeout`/`duration == 0`
# (WHEELS_X's stale ~10s kernel lease left armed with no live obligation
# tracking it -- R-06; MOVE_X's/GO_TO_R's/GO_TO_W's instant silent no-op)
# and an unreachable-by-any-prior-test starvation-kill class for any value
# above 2^31-1 (R-18: WireAdapter's own
# `motionObligationDeadlineMs_ = nowMs_() + timeout` wraps negative, the
# ticket-011 pattern resurrected). `0` is now refused outright
# (Result::kRange, err 3, matching the existing `cruise <= 0` refusal
# precedent); a value above 2^31-1 is silently clamped down to it.
#
# The existing boundary-value coverage above (WHEELS_V's own
# kWheelsVDurationCeiling tests, maxing at 5000/5001 ms) is UNCHANGED --
# neither of those two values is anywhere near 2^31-1, so this ticket's own
# clamp never touches them; the sections below are new, adjacent coverage
# rather than edits to that existing parametrize (0's "rejected outright,
# no dispatch at all" shape and the ~24.8-day clamp ceiling do not fit
# test_every_motion_verb_arms_motion_obligation's own "armed, then expires
# within `window_ms`" body without breaking its own single-purpose shape).
# ---------------------------------------------------------------------------

# (verb id, wire line template with a `{t}` timeout/duration placeholder,
# whether this verb ALSO enforces WireAdapter's own separate
# kWheelsVDurationCeiling (5000 ms) downstream of the shared clamp above --
# WHEELS_V/MOVE_V's own "duration IS the lease, a dead host cannot mean a
# runaway" ceiling, unrelated to and unchanged by this ticket, but relevant
# here because it means neither verb can ever reach the accepted side of
# the NEW 2^31-1 ceiling: both ceilings apply, and 5000 is the tighter one;
# and the timeout/duration field's own INDEX into that verb's `last_<verb>`
# tuple above -- NOT always the last element: last_wheels_v's own tuple
# ends with `id`, not `duration`, so `last[-1]` would silently check the
# wrong field for that one verb).
_MOTION_VERB_TIMEOUT_CASES = [
    ("wheels_x", "WHEELS_X 100 100 150 {t} #1\n", False, 3),
    ("wheels_v", "WHEELS_V 100 100 {t} #1\n", True, 2),
    ("move_x", "MOVE_X 200 0 150 {t} #1\n", False, 3),
    ("move_v", "MOVE_V 100 0 {t} #1\n", True, 2),
    ("go_to_r", "GO_TO_R 200 50 150 0 {t} #1\n", False, 4),
    ("go_to_w", "GO_TO_W 200 50 150 0 {t} #1\n", False, 2),
]

# wire_handler.cpp's own kMaxMotionTimeoutMs (2^31 - 1) -- restated here,
# not imported: this suite hardcodes its own wire-level literals throughout
# (e.g. WHEELS_V's 5000 ms ceiling above), matching that existing
# convention rather than introducing a new cross-language constant-sharing
# mechanism for one test file.
_MAX_MOTION_TIMEOUT_MS = 2147483647  # 2^31 - 1


@pytest.mark.parametrize("verb,line_template,has_duration_ceiling,timeout_index",
                          _MOTION_VERB_TIMEOUT_CASES)
def test_motion_verb_timeout_zero_is_rejected_not_dispatched(
        wv, verb, line_template, has_duration_ceiling, timeout_index):
    """R-06, generalized to all six verbs via the mock adapter (`wv`):
    timeout/duration == 0 is now a MERITS rejection (ack + err 3) at the
    shared wire_handler.cpp clamp, BEFORE the Adapter is ever called --
    `*_calls` stays 0, proving this is a single choke point every verb goes
    through identically, not six independently-agreeing Adapter checks."""
    del has_duration_ceiling, timeout_index  # decode/dispatch-only check
    setter = getattr(wv, f"set_{verb}_result")
    setter(RESULT_UNKNOWN)  # would be visible in the reply if reached
    wv.feed(line_template.format(t=0).encode())
    assert wv.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE, not ERR_UNKNOWN
    assert getattr(wv, f"{verb}_calls") == 0
    assert wv.malformed_count == 0  # a merits rejection, not a decode failure


@pytest.mark.parametrize("timeout_value", [
    2**31,      # one past the ceiling -- clamps
    2**32 - 1,  # uint32-max -- clamps to the same ceiling
])
@pytest.mark.parametrize("verb,line_template,has_duration_ceiling,timeout_index",
                          _MOTION_VERB_TIMEOUT_CASES)
def test_motion_verb_timeout_above_ceiling_clamps_before_dispatch(
        wv, verb, line_template, has_duration_ceiling, timeout_index,
        timeout_value):
    """R-18, generalized via the mock adapter: a timeout/duration above
    2^31-1 is silently clamped DOWN to it before the Adapter ever sees it --
    proven by reading back the exact value the mock adapter recorded
    (last_<verb>'s own timeout/duration field, at its own index -- see
    _MOTION_VERB_TIMEOUT_CASES's own comment on why that index is not
    always -1), not merely by the wire-level outcome (which
    kWheelsVDurationCeiling alone could also explain for WHEELS_V/MOVE_V)."""
    del has_duration_ceiling
    setter = getattr(wv, f"set_{verb}_result")
    setter(RESULT_UNKNOWN)
    wv.feed(line_template.format(t=timeout_value).encode())
    assert wv.take_sink() == _ack(1) + _err(1, 1)  # ERR_UNKNOWN: dispatched
    assert getattr(wv, f"{verb}_calls") == 1
    last = getattr(wv, f"last_{verb}")
    assert last[timeout_index] == _MAX_MOTION_TIMEOUT_MS  # clamped, not raw


@pytest.mark.parametrize("verb,line_template,has_duration_ceiling,timeout_index",
                          _MOTION_VERB_TIMEOUT_CASES)
def test_motion_verb_timeout_at_ceiling_is_unchanged(
        wv, verb, line_template, has_duration_ceiling, timeout_index):
    """2^31-1 itself is the inclusive top of the accepted range -- passes
    through byte-for-byte, unclamped: this ticket's own "values in the
    previously-tested range are unchanged" contract, extended to the new
    ceiling's own boundary rather than only the old 1..5000 ms range."""
    del has_duration_ceiling
    setter = getattr(wv, f"set_{verb}_result")
    setter(RESULT_UNKNOWN)
    wv.feed(line_template.format(t=_MAX_MOTION_TIMEOUT_MS).encode())
    assert wv.take_sink() == _ack(1) + _err(1, 1)
    assert getattr(wv, f"{verb}_calls") == 1
    last = getattr(wv, f"last_{verb}")
    assert last[timeout_index] == _MAX_MOTION_TIMEOUT_MS


@pytest.mark.parametrize("timeout_value", [
    0, _MAX_MOTION_TIMEOUT_MS, 2**31, 2**32 - 1,
])
@pytest.mark.parametrize("verb,line_template,has_duration_ceiling,timeout_index",
                          _MOTION_VERB_TIMEOUT_CASES)
def test_motion_verb_timeout_boundary_values_real_adapter_obligation(
        wa, verb, line_template, has_duration_ceiling, timeout_index,
        timeout_value):
    """The same four boundary values, this time through the REAL
    WireAdapter + a real clock (`wa`), asserting the motion-obligation
    flag protocol.cpp's fiber loop actually polls -- the acceptance
    criterion's own "asserting the documented reject/clamp/unchanged
    behavior for each" verb, at each boundary value, via
    hasLiveMotionObligation() rather than only the mock adapter's recorded
    argument. For the two duration-ceiling verbs (WHEELS_V/MOVE_V), every
    one of these four values is refused (0 by the new clamp; the other
    three by the pre-existing, unchanged 5000 ms ceiling, since clamping
    down to 2^31-1 still leaves them far above it) -- so those two verbs
    never reach the "obligation armed" branch at all, which is itself the
    proof that ceiling and clamp compose correctly rather than the new
    clamp accidentally bypassing the old ceiling."""
    del timeout_index  # this test reads the obligation flag, not last_<verb>
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose(0.0, 0.0, 0.0)  # only read by GO_TO_W; harmless otherwise

    base_ms = 1_000_000
    wa.set_now_ms(base_ms)
    assert not wa.has_live_motion_obligation()

    wa.feed(line_template.format(t=timeout_value).encode())

    if timeout_value == 0 or has_duration_ceiling:
        # 0: rejected for every verb (R-06). Otherwise: the clamped value
        # (<=2^31-1) still exceeds WHEELS_V/MOVE_V's own 5000 ms ceiling.
        assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
        assert not wa.has_live_motion_obligation()
        return

    # Accepted -- armed immediately (R-18's own bug would show FALSE here,
    # from the wrapped-negative deadline computed at arm time).
    assert wa.take_sink() == _ack(1)
    assert wa.has_live_motion_obligation()

    # ...and still armed a good deal past the ~150 ms starvation-watchdog
    # window R-18's bug would have missed entirely (this ticket's own
    # acceptance criterion: "the move keeps running past ~150 ms").
    wa.set_now_ms(base_ms + 200)
    assert wa.has_live_motion_obligation()


# ---------------------------------------------------------------------------
# R-06's own named sequence (issue text, wire-timeout-hardening.md): WHEELS_X
# specifically, since it is the ONE verb (of the six) whose own lease
# computation (MotionEngine::wheelsX()'s dead-reckoned
# `lease = dominant/cruise*1000`) silently substituted a LONGER lease than
# `timeoutMs` when `timeoutMs == 0` -- `if (timeoutMs > 0 && timeoutMs <
# lease) lease = timeoutMs;` never fires at 0, so the kernel used to stay
# armed with a multi-second command while WireAdapter's own obligation
# window read `now + 0 == now` (already expired). This is a stronger proof
# than the flag-only check above: it proves the KERNEL itself was never
# even commanded, by observing the motor never receives a nonzero duty
# across several subsequent, unrelated ticks -- exactly the "a subsequent
# unrelated tick does not resume a stale move" acceptance criterion.
# ---------------------------------------------------------------------------


def test_wheels_x_timeout_zero_leaves_no_stale_kernel_lease_armed(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    wa.set_now_ms(1_000_000)

    wa.feed(b"WHEELS_X 200 200 150 0 #1\n")
    assert wa.take_sink() == _ack(1) + _err(3, 1)  # ERR_RANGE
    assert not wa.has_live_motion_obligation()

    # Pre-fix, MotionEngine::wheelsX() would still have been called with
    # timeoutMs == 0 and armed the kernel with its own multi-second
    # dead-reckoned lease -- these "unrelated" ticks (protocol.cpp's fiber
    # loop resuming for some other reason entirely; here, simply advancing
    # time and stepping) would then have resumed that stale command. Post-
    # fix, engineWheelsX() is never even called for a refused timeout, so
    # the motor never receives a nonzero duty at all.
    for elapsed_ms in (10, 1000, 8000):
        wa.set_now_ms(1_000_000 + elapsed_ms)
        wa.step()
        assert wa.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
        assert not wa.has_live_motion_obligation()


# ---------------------------------------------------------------------------
# R-18's own named sequence (issue text, wire-timeout-hardening.md; the
# code-review annex's own extra-derivation note, verify-wire.md's "WIRE-02
# -- extra derivation detail"): WHEELS_X with a timeout STRICTLY greater
# than 2^31 -- the annex's own re-derivation of the wraparound arithmetic
# found the pre-fix break threshold is exact and easy to get one-off wrong:
# `(int32_t)(now - (now + t))` is INT32_MIN (still "< 0", i.e. still
# reported live) at t == 2^31 EXACTLY, and only flips to "dead on arrival"
# for t > 2^31 -- so a test at exactly 2^31 would NOT have been red
# pre-fix, and is not used here for that reason (the boundary-value
# parametrize above still covers t == 2^31 for the POST-fix "clamped and
# accepted" contract, which holds regardless of this pre-fix coincidence).
# uint32-max (4294967295) sits unambiguously past the threshold on both
# sides of that off-by-one, matching the value the annex's own derivation
# table uses to illustrate "dead on arrival".
# ---------------------------------------------------------------------------


def test_wheels_x_timeout_above_2_31_survives_starvation_window(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    wa.set_now_ms(1_000_000)

    # 4294967295 (uint32-max): pre-fix, `now + 4294967295` wraps to
    # `now - 1`, so hasLiveMotionObligation() reads FALSE from the very
    # first poll (verify-wire.md's own derivation: t = 4294967295 -> 1,
    # "dead on arrival") -- protocol.cpp's fiber never ticks, and the
    # ~100-150 ms starvation watchdog port-stops the motors despite the
    # move having just been acked. Post-fix, the shared clamp reduces this
    # to kMaxMotionTimeoutMs (2^31-1) before WireAdapter ever computes a
    # deadline, so the wrap never happens.
    wa.feed(b"WHEELS_X 200 200 150 4294967295 #1\n")
    assert wa.take_sink() == _ack(1)  # accepted, not refused
    assert wa.has_live_motion_obligation()

    b = wa.effective_track_width()
    wa.land_first_command()
    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 200.0, wa.counts_per_mm(), b, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)

    # Past the ~150 ms starvation-watchdog window the pre-fix wrap would
    # have left this move stranded inside -- still armed, still driving.
    # service_move() first (not step() alone) to refresh service()'s own
    # rolling 500 ms kernel lease at the new time -- see
    # test_motion_engine_reductions.py's own
    # test_move_x_timeout_is_a_real_backstop_on_a_blocked_robot for why.
    wa.set_now_ms(1_000_000 + 200)
    assert wa.has_live_motion_obligation()
    assert wa.service_move()
    wa.step()
    # A real 200 ms has now passed (unlike land_first_command()'s own
    # ~0 ms first tick), long enough for the shaper's accel ramp
    # (400 mm/s^2) to climb all the way from the floor to this segment's
    # own cruise (150 mm/s) and plateau there -- so this checkpoint now
    # reads the STEADY-STATE duty, not the floor.
    steady_left, steady_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, 150.0, wa.counts_per_mm(), _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(steady_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(steady_right)


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
    """A bare-GET dump lists only the ConfigField-equivalent wire names
    (wire_adapter.cpp's kFields table) -- confirms the old multi-pair
    CONFIG batch verb's ordinal set is fully covered under new names,
    and that no WHEELS-named entry leaked into the config table
    (WHEELS_V is a motion verb, not a config field). Sprint 007 ticket
    001 added `stall_clear` (ordinal 17) at the end; ticket 003 added
    `default_cruise` (ordinal 15) just before it; ticket 005 (this one,
    closing R-14/API-06) fills in `rotational_slip` (ordinal 16) between
    the two. The function name's stale "sixteen" now undercounts by
    quite a bit more and is left as-is rather than renamed mid-sprint
    (same call made for ticket 003's own `default_cruise` addition).

    Sprint 029 ticket 004 (design motion-profile-unification.md S4.7):
    `speed_floor` -> `v_floor`, `pivot_overrun` -> `stop_distance`,
    `max_yaw_rate` -> `omega_max` (all three same ordinal, renamed);
    `brake_frac`/`dist_taper`/`yaw_taper`/`dist_floor`/`turn_floor`/
    `ramp_ms`/`plateau_min_s`/`profile_exit` are REMOVED (no row in
    kFields at all any more); `omega_floor`/`arrive_dist`/`arrive_yaw`
    are NEW, appended after `estop_clear` (ordinals 34-36, declared
    after `rebase`/`estop_clear` in kFields -- see that table's own
    declaration order)."""
    wa.feed(b"GET #1\n")
    lines = wa.take_sink().split(b"\n")
    names = [line.split(b" ")[1] for line in lines if line.startswith(b"get ")]
    assert names == [
        b"max_duty", b"full_duty_velocity", b"pid_kp", b"pid_ki",
        b"pid_i_max", b"accel_kaff", b"pid_max", b"twist_hold_gain",
        b"v_floor", b"pos_err_max", b"stall_speed", b"stall_demand",
        b"stall_window", b"lambda_enabled", b"crawl_pulse",
        b"default_cruise", b"rotational_slip", b"stall_clear",
        b"stop_distance",   # ordinal 18, renamed from pivot_overrun
        # this ticket: ordinals 19-21, 28, 30 -- accel/decel/v_max/
        # jerk/omega_max, in kFields declaration order. 22-27, 29, 31
        # (the removed ordinals) have no row and so never appear here.
        b"accel", b"decel", b"v_max",
        b"jerk",
        b"omega_max",   # renamed from max_yaw_rate, ordinal 30 unchanged
        # sprint 028 ticket 002: ordinal 32 (rebase) is deliberately
        # ABSENT here -- its GET is refused (WireAdapter::onGet(),
        # wire_adapter.cpp), so it never appears in a bare dump; see
        # test_rebase_get_is_refused below. Ordinal 33 (estop_clear) DOES
        # have a real GET (a convenience readback of the live estop
        # flag, same shape stall_clear's own GET already uses), so it is
        # appended here in ordinal order like every field above it.
        b"estop_clear",
        # this ticket: ordinals 34-36 (omega_floor/arrive_dist/
        # arrive_yaw), NEW, declared after estop_clear in kFields.
        b"omega_floor", b"arrive_dist", b"arrive_yaw",
        # sprint 029 ticket 009 (design S4.1/S6.1/S10.2): ordinal 37
        # (lag), NEW, declared after arrive_yaw in kFields.
        b"lag",
    ]
    assert b"wheels" not in b" ".join(names).lower()


def test_default_cruise_wire_field_round_trips_and_feeds_the_zero_sentinel(wa):
    """Sprint 007 ticket 003 (closing R-11/BLK-03/API-03): proves
    `default_cruise` is settable/gettable via the wire's own SET/GET
    verbs (the acceptance criterion the generic `set config` block
    reaches through the same setKernelValue()/getConfigValue() path,
    ordinal 15) AND that a value set that way is exactly what a
    subsequent cruise==0 command resolves to -- end to end, not just a
    round-tripped number sitting unused. Uses the same large
    full_duty_velocity as the WHEELS_X real-effect tests (see
    _WHEELS_X_FULL_DUTY_VELOCITY's own rationale) so 200 mm/s stays
    well under the maxDuty=100% rail through wheelsX()'s un-ramped
    primitive path."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(_WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()

    wa.feed(b"SET default_cruise 200.0 #1\n")
    assert wa.take_sink() == _ack(1)

    wa.feed(b"GET default_cruise #2\n")
    reply = wa.take_sink()
    prefix = _ack(2) + b"get default_cruise "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(200.0, abs=1e-3)

    wa.feed(b"WHEELS_X 200 200 0 5000 #3\n")
    assert wa.take_sink() == _ack(3)
    b = wa.effective_track_width()
    wa.land_first_command()

    expected_left, expected_right = _first_tick_wheels_x_duty_pair(
        200.0, 200.0, cpm, b, _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)

    # SET default_cruise 0 is a silent no-op over the wire (same ">0"
    # validation setGeometry() uses) -- the PREVIOUS value survives.
    wa.feed(b"SET default_cruise 0 #4\n")
    assert wa.take_sink() == _ack(4)
    wa.feed(b"GET default_cruise #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get default_cruise "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(200.0, abs=1e-3)


def test_rotational_slip_wire_field_round_trips_and_reaches_effective_track_width(wa):
    """Sprint 007 ticket 005 (closing R-14/API-06): proves
    `rotational_slip` is settable/gettable via the wire's own SET/GET
    verbs -- the same setKernelValue()/getConfigValue() path (ordinal
    16) the generic `set config` block reaches through -- AND that a
    value set that way actually lands on the REAL
    MotionEngine::rotationalSlip_, not a shadow copy: effectiveTrackWidth
    (== trackWidth_/rotationalSlip_, motion_engine.h) is read back before
    and after, and trackWidth_ is back-derived from that first reading
    rather than hard-coded, so this test does not depend on either
    constant's current measured value. Also proves the setter's own
    ">0, else keep the prior value" validation (motion_engine.h) is
    reachable end to end over the wire, mirroring
    test_default_cruise_wire_field_round_trips_and_feeds_the_zero_sentinel's
    own zero-sentinel check above."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"GET rotational_slip #1\n")
    reply = wa.take_sink()
    prefix = _ack(1) + b"get rotational_slip "
    assert reply.startswith(prefix)
    default_slip = float(reply[len(prefix):])
    default_b = wa.effective_track_width()
    # trackWidth_ = effectiveTrackWidth() * rotationalSlip_ -- back-derived,
    # not hard-coded (motion_engine.h's own effectiveTrackWidth() comment).
    track_width = default_b * default_slip

    new_slip = default_slip * 0.5  # deliberately different from the default
    wa.feed(f"SET rotational_slip {new_slip} #2\n".encode())
    assert wa.take_sink() == _ack(2)

    wa.feed(b"GET rotational_slip #3\n")
    reply = wa.take_sink()
    prefix = _ack(3) + b"get rotational_slip "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(new_slip, abs=1e-3)

    # The wire SET reached the REAL MotionEngine, not a shadow copy:
    # effectiveTrackWidth() moves with it, in the opposite direction
    # (halving the slip must double b).
    assert wa.effective_track_width() == pytest.approx(
        track_width / new_slip, rel=1e-3)

    # SET rotational_slip 0 is a silent no-op over the wire (same ">0"
    # validation setRotationalSlip() applies) -- the PREVIOUS value
    # (new_slip) survives, and so does the effectiveTrackWidth it
    # produced.
    wa.feed(b"SET rotational_slip 0 #4\n")
    assert wa.take_sink() == _ack(4)
    wa.feed(b"GET rotational_slip #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get rotational_slip "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(new_slip, abs=1e-3)
    assert wa.effective_track_width() == pytest.approx(
        track_width / new_slip, rel=1e-3)


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

    # Sprint 029 ticket 003 (design S6.5's lazy start): wheelsV() no
    # longer drives the kernel synchronously -- service_move() must run
    # to actually stage the demand before a step() can land it, so this
    # is the first tick that establishes "demanding && still", not a
    # bare step(). service() also now reissues its own rolling 500 ms
    # kernel lease on every tick (design S5), so the demand must be kept
    # ALIVE with periodic service_move() calls across the whole window
    # below, not just two isolated snapshots -- an un-reissued command
    # would expire (and the kernel auto-neutral) well before 600 ms.
    wa.service_move()
    wa.step()  # first "demanding && still" observation, since=1000ms

    wa.feed(b"GET stall_clear #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)

    # Keep the demand alive every 24 ms (a realistic tickDrive() cadence)
    # up to +600 ms > stall_window -- the latch trips once the kernel's
    # own updateLatch() sees the condition sustained that long.
    t_ms = 1000
    while t_ms < 1600:
        t_ms += 24
        wa.set_now_ms(t_ms)
        wa.service_move()
        wa.step()

    # Sprint 005 ticket 004 (closing wire-motion-completion-signal.md/
    # R-23): the REAL stall latch this step() just tripped is exactly
    # what WireAdapter's own completion channel now observes for the
    # still-pending WHEELS_V (#4) -- resolvePendingReason() checks
    # diagValue(stallHalted) before anything else, so THIS ack is the
    # first one to report it: (4, stall), not the inert (0, none) every
    # ack reported before this ticket.
    wa.feed(b"GET stall_clear #6\n")
    reply = wa.take_sink()
    prefix = _ack(6, 4, DONE_STALL) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(1.0, abs=1e-3)

    # Once resolved, WHEELS_V #4's outcome is FROZEN (it reports what
    # the motion actually ended with, not the live diagValue() state) --
    # `SET stall_clear 1` clearing the latch below does not retroactively
    # turn this back into "none": the completion channel and the
    # stall_clear wire field are two independent things this test
    # exercises together, and clearing one must not un-resolve the
    # other.
    wa.feed(b"SET stall_clear 1 #7\n")
    assert wa.take_sink() == _ack(7, 4, DONE_STALL)
    wa.step()  # consumes the clearStallReq_ handshake

    wa.feed(b"GET stall_clear #8\n")
    reply = wa.take_sink()
    prefix = _ack(8, 4, DONE_STALL) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Sprint 028 ticket 002 (closing no-wire-verb-reaches-rebaseposition-so-
# tours-cannot-zero-their-frame.md): `rebase` (ordinal 32) and
# `estop_clear` (ordinal 33), the same write-triggered-action-wearing-a-
# config-field's-clothes shape stall_clear (ordinal 17, tested above)
# already established.
# ---------------------------------------------------------------------------


def test_rebase_is_sequenced_and_reaches_kernel_rebase_position(wa):
    """`SET rebase 1` reaches the REAL kernel.rebasePosition() -- a
    DEFERRED request (diffdrive.h) that only takes effect on the
    kernel's own NEXT step(), observable there as
    positionEpochLeft/Right both changing (this handle's own
    waOutputPositionEpochLeft/Right), the same "prove the real kernel
    method ran via a real Output field" shape
    test_stall_clear_wire_field_clears_latch_and_reads_back above uses
    for clearStallLatch()/stallHalted.

    Also proves the field PARTICIPATES in the mandatory `#<id>`
    ack/nack reliability layer, not merely accepts one (this ticket's
    own acceptance criterion: "must be confirmed by a host test, not
    assumed") -- a GAPPED id (here, #2 arriving first, with
    expectedNext_ still 1) nacks and the underlying onSet() is never
    called at all, so the epoch does not move even across a step().
    Only once the missing #1 arrives does the request actually reach
    the kernel.
    """
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.step()  # baseline step so the epoch pair reads a stable value

    before_left = wa.output_position_epoch_left()
    before_right = wa.output_position_epoch_right()

    # Gap: #2 arrives first -> nack, onSet() never runs.
    wa.feed(b"SET rebase 1 #2\n")
    assert wa.take_sink() == _nack(1)
    wa.step()
    assert wa.output_position_epoch_left() == before_left
    assert wa.output_position_epoch_right() == before_right

    # The missing #1 arrives, in order -> ack, request armed but still
    # DEFERRED (no step() has run yet).
    wa.feed(b"SET rebase 1 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.output_position_epoch_left() == before_left
    assert wa.output_position_epoch_right() == before_right

    # The kernel's own next step() applies the deferred request.
    wa.step()
    assert wa.output_position_epoch_left() == before_left + 1
    assert wa.output_position_epoch_right() == before_right + 1


def test_rebase_shims_cpp_zeroes_encoder_frame_and_reseeds_otos():
    """rebase's OTOS re-seed and encoder-frame zero (the acceptance
    criterion behind wire_adapter.cpp's kFields comment: "the
    platform-layer pose-seed path seedPose() already uses so both pose
    sources stay agreed at the zero point") live entirely in shims.cpp's
    real setKernelValue() case 32 -- unlike every other case this file's
    WaHandle mirrors, OtosPort cannot be compiled into ANY host test at
    all (otos_port.h includes pxt.h unconditionally; wire_adapter.cpp's
    own forward-declaration comment documents this same gap for GO_TO_W's
    OTOS PoseSource). This is a text-based check instead, the same
    "read the other file as text, no compiler needed" shape
    test_wire_constants_drift.py already uses throughout: confirms case
    32's own body calls kernel.rebasePosition(), zeroes x/y/heading, AND
    re-seeds OTOS to that same zero -- so a future edit cannot silently
    drop the OTOS half while the encoder half keeps passing every other
    (compiled) test in this file."""
    shims_text = (_SRC_DIR / "shims.cpp").read_text()
    match = re.search(r"case 32:\s*\{?\s*if \(v != 0\.0f\) \{(.*?)\}\s*break;",
                      shims_text, re.DOTALL)
    assert match, "shims.cpp's setKernelValue() case 32 (rebase) body was not found"
    body = match.group(1)
    assert "k.rebasePosition();" in body, body
    assert "r.x = 0.0f;" in body and "r.y = 0.0f;" in body and \
        "r.heading = 0.0f;" in body, body
    assert "otosRef().setPose(0.0f, 0.0f, 0.0f);" in body, body


def test_rebase_get_is_refused(wa):
    """rebase has no stored value and no boolean latch worth reading
    back (unlike estop_clear immediately below) -- WireAdapter::onGet()
    refuses it outright, the identical `err 1` (ERR_UNKNOWN) reply an
    unrecognized field name gets
    (test_get_set_unknown_field_name_is_unknown above), and it is
    absent from a bare GET dump
    (test_get_bare_dumps_all_sixteen_fields_no_wheels_entry above)."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.feed(b"GET rebase #1\n")
    assert wa.take_sink() == _ack(1) + _err(1, 1)


def test_estop_clear_reaches_kernel_estop_clear_and_reads_back(wa):
    """`SET estop_clear 1` reaches the REAL kernel.estopClear() -- an
    ESTOP first latches Output.estopped (via the real onEstop()'s own
    estopAll()), GET estop_clear reads that live flag back (1 while
    estopped, matching test_stall_clear's own "GET reads the live flag,
    not a stored value" shape), then SET estop_clear clears it and a
    subsequent GET/step confirms it stayed cleared.

    Also confirms estop_clear is sequenced the same direct way rebase's
    own test above proves it with a gap: immediately re-sending the SAME
    #<id> a second time (the host never saw the first ack) re-acks
    WITHOUT re-executing (S2.2's own stale-retransmit row --
    test_stale_retransmit_reacks_already_accepted_id_and_does_not_reexecute,
    tests/host/test_wire_reliability.py) rather than nacking or silently
    dropping it. wire_handler.cpp always echoes `expectedNext_ - 1` for
    a stale id, not literally the id resent -- so the retransmit below
    reuses #2 right after its own first send, while #2 is still that
    exact value, rather than resending an older id once the sequence has
    moved further on.
    """
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.step()

    wa.feed(b"ESTOP\n")
    assert wa.take_sink() == b"estop\n"
    wa.step()  # Output.estopped only updates on the kernel's next step()

    wa.feed(b"GET estop_clear #1\n")
    reply = wa.take_sink()
    prefix = _ack(1) + b"get estop_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(1.0, abs=1e-3)

    wa.feed(b"SET estop_clear 1 #2\n")
    assert wa.take_sink() == _ack(2)

    # The host never saw that ack and resends the SAME line, same id --
    # re-acks #2 again (still expectedNext_ - 1) without re-executing.
    wa.feed(b"SET estop_clear 1 #2\n")
    assert wa.take_sink() == _ack(2)

    wa.step()

    wa.feed(b"GET estop_clear #3\n")
    reply = wa.take_sink()
    prefix = _ack(3) + b"get estop_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)


def test_rebase_and_estop_clear_refused_busy_during_live_motion(wa):
    """Both new fields are refused (kBusy, wire err 10), not silently
    accepted or ignored, while a motion obligation or move-engine move
    is live -- the acceptance criterion this ticket adds for the first
    time to any SET field. MOVE_X arms BOTH hasLiveMotionObligation()
    (this class's own wire-motion-lease bookkeeping) and
    engineMoveActive() (the shared MotionEngine's own move state); this
    test proves the refusal via the observable side effect staying
    inert -- kernel.rebasePosition() is never actually reached (the
    position epoch does not move across a step()) -- not merely via
    the wire error code, the same "prove the real effect, not just the
    reply" standard test_rebase_is_sequenced_and_reaches_kernel_rebase_position
    above holds itself to.
    """
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.step()

    before_left = wa.output_position_epoch_left()
    before_right = wa.output_position_epoch_right()

    wa.feed(b"MOVE_X 500 0 100 4000 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.has_live_motion_obligation()
    assert wa.engine_move_active()

    wa.feed(b"SET rebase 1 #2\n")
    assert wa.take_sink() == _ack(2) + _err(10, 2)
    wa.step()
    assert wa.output_position_epoch_left() == before_left
    assert wa.output_position_epoch_right() == before_right

    wa.feed(b"SET estop_clear 1 #3\n")
    assert wa.take_sink() == _ack(3) + _err(10, 3)

    # Once the move ends (STOP clears both signals), the SAME fields are
    # accepted again -- the refusal tracks live motion, not a permanent
    # lockout. STOP's OWN ack is formatted BEFORE onStop() resolves
    # anything (dispatch() replies ack, then executes -- the same
    # ordering test_explicit_stop_ends_a_pending_goal_directed_motion_as_stop
    # in test_wire_motion_completion.py pins), so it still reports the
    # PRE-stop default; the NEXT ack (#5 below) is the first to report
    # MOVE_X #1's own resolution.
    wa.feed(b"STOP #4\n")
    assert wa.take_sink() == _ack(4)
    assert not wa.has_live_motion_obligation()
    assert not wa.engine_move_active()

    wa.feed(b"SET rebase 1 #5\n")
    assert wa.take_sink() == _ack(5, 1, DONE_STOP)
    wa.step()
    assert wa.output_position_epoch_left() == before_left + 1
    assert wa.output_position_epoch_right() == before_right + 1


def test_move_x_immediately_after_a_successful_rebase_delivers_its_full_commanded_rotation(wa):
    """Sprint 028 ticket 002 hardware acceptance re-open (gopiv,
    2026-09-02): `SET rebase 1` defers kernel.rebasePosition() to the
    kernel's own NEXT step() (diffdrive.cpp's rebaseReq_/
    seenRebaseReq_ check, honoured before that step()'s own command
    processing). A MOVE_X issued right after a SUCCESSFUL rebase -- no
    motion active in between, so the busy gate
    (test_rebase_and_estop_clear_refused_busy_during_live_motion above)
    never fires -- has its own startSegment() (motion_engine.cpp)
    capture posLeft0/posRight0 from the kernel's STILL-OLD, pre-rebase
    Output; the very step() that first drives this move is ALSO the
    step() that finally honours the deferred rebase, resetting the
    kernel's own encoder samples out from under that snapshot (and, on
    real hardware, NezhaMotorPort::rebaseline() genuinely zeroes
    position() -- nezha_port.cpp -- unlike FakeMotor's own no-op
    rebaseline(), fake_ports.h, which this test works around by arming
    the post-rebase position explicitly, below).

    PRE-FIX, diffing the fresh near-zero post-rebase position against
    the stale pre-rebase baseline produced a huge signed delta that
    satisfied serviceMove()'s completion margin on the move's own
    FIRST serviced tick -- MEASURED gopiv 2026-09-02,
    captures/gopiv-acceptance-028-20260902/step_e_transcript.txt (Step
    E.2): `MOVE_X 0 -900 60 3000` sent right after a successful `SET
    rebase 1` delivered 11 of ~5160 commanded centidegrees and reported
    itself complete (`vl=vr=0` within one tick). The fix
    (motion_engine.{h,cpp}: MoveState::epochLeft0/epochRight0, captured
    alongside posLeft0/posRight0 in startSegment() and checked at the
    top of serviceMove()) re-anchors the baseline to the fresh
    post-rebase position instead -- distTarget/yawTarget are RELATIVE
    displacements and stay untouched, only the reference point they are
    measured from moves, so the move keeps driving and still reaches
    its own full commanded target.
    """
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.set_now_ms(1000)
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()

    # The robot already has real accumulated position from an earlier
    # move (e.g. a prior pivot, matching Step E.1's own pivot before its
    # rebase) -- ASYMMETRIC left/right (a real pivot's own encoder
    # split), not merely large: the bug lives entirely on the YAW
    # (differential, right-minus-left) axis a pure pivot's completion
    # check reads, so a SYMMETRIC prior position (equal on both wheels)
    # would cancel out of that difference and mask the very regression
    # this test exists to catch, however large its magnitude.
    prior_left, prior_right = -4000.0, 4000.0
    wa.arm_motor_position(LEFT, prior_left, sample_time_us=1)
    wa.arm_motor_position(RIGHT, prior_right, sample_time_us=1)
    wa.step()

    before_left_epoch = wa.output_position_epoch_left()
    before_right_epoch = wa.output_position_epoch_right()

    # SET rebase 1 -- deferred, no step() yet: matches the real
    # Protocol::run() loop exactly (protocol.cpp's serviceOnce()/run()),
    # which only calls tickDrive() while hasLiveMotionObligation() is
    # true, and a bare rebase (no move active yet) never arms that flag.
    wa.feed(b"SET rebase 1 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.output_position_epoch_left() == before_left_epoch
    assert wa.output_position_epoch_right() == before_right_epoch

    # MOVE_X issued immediately after, no gap -- a pure pivot
    # (distance == 0), matching Step E.2's own -900 mrad pivot.
    # startSegment() runs synchronously inside this feed() call, before
    # any step() -- so it captures posLeft0/posRight0 from the
    # still-8000-count, pre-rebase Output.
    wa.feed(b"MOVE_X 0 -900 60 3000 #2\n")
    assert wa.take_sink() == _ack(2)
    assert wa.engine_move_active()

    # Simulate the real NezhaMotorPort::rebaseline() contract (position
    # reads a genuine 0 immediately after -- nezha_port.cpp) landing on
    # the SAME step() that also first drives the newly-issued move.
    wa.arm_motor_position(LEFT, 0.0, sample_time_us=2)
    wa.arm_motor_position(RIGHT, 0.0, sample_time_us=2)
    wa.step()  # applies the deferred rebase AND the move's first drive tick

    assert wa.output_position_epoch_left() == before_left_epoch + 1
    assert wa.output_position_epoch_right() == before_right_epoch + 1

    # THE FIX: the move must NOT resolve as complete on this first
    # post-rebase tick. Pre-fix, the stale-baseline delta satisfied the
    # completion margin here and this call returned False with
    # essentially none of the commanded rotation delivered.
    still_active = wa.service_move()
    assert still_active, (
        "move reported complete on its first post-rebase tick -- the "
        "stale pre-rebase baseline bug has regressed"
    )
    assert wa.engine_move_active()

    # Drive the move the rest of the way to a REAL completion, proving
    # it still reaches its own full commanded target from the freshly
    # re-anchored baseline -- not merely that it failed to end early.
    rotation_rad = -900.0 * 0.001  # MOVE_X's own mrad -> rad, mradToRad()
    yaw_target_counts = rotation_rad * 0.5 * b * cpm
    left_target = -yaw_target_counts   # distance == 0: left = -yawTarget
    right_target = yaw_target_counts   #                right = +yawTarget
    wa.arm_motor_position(LEFT, left_target, sample_time_us=3)
    wa.arm_motor_position(RIGHT, right_target, sample_time_us=3)
    wa.step()
    still_active = wa.service_move()
    assert not still_active
    assert not wa.engine_move_active()
    assert wa.last_done_reason() == DONE_STOP  # polls resolvePendingIfDue()


# ---------------------------------------------------------------------------
# Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25, code
# review 2026-08-23, PY-03 CONFIRMED all three): the WaHandle test double
# claimed to mirror shims.cpp "field-for-field" in three places it
# actually did not -- see this ticket's own Description for the full
# citation trail (shims.cpp:850/1021/345 vs the pre-fix
# wire_motion_verb_shim.cpp). Each test below was verified RED against
# the PRE-fix double (temporarily reverting just that one fix, one at a
# time) and GREEN again once restored -- see this ticket's own notes.
#
# What these tests mechanically detect vs. merely regression-check:
#   - The wedge pair and command-supersession tests are TRUE drift
#     tests: they exercise the double's OWN field/call choice against an
#     independently-reasoned expectation (which Motor signal a given
#     ordinal reads; whether a REAL, observable side effect -- move
#     cancellation -- occurred). Either one would fail again if a future
#     edit reintroduced the wrong field or bypassed the engine, with no
#     production change required to trip them.
#   - The config-rounding test is NARROWER: it is a regression test for
#     ONE verified-by-direct-probe divergent input (v=0.251f), not a
#     structural check that the double calls std::lround() specifically
#     (there is no observable way to distinguish "rounds correctly by
#     construction" from "rounds correctly by coincidence at every OTHER
#     input" from outside the shim). It reliably catches a REVERT back
#     to the truncating float32 path (proven below), but would not catch
#     a different, non-truncating rounding bug that still agreed with
#     production at v=0.251. This is the honest limit of a black-box
#     test against a private arithmetic choice.
# ---------------------------------------------------------------------------


def test_wheels_v_supersedes_in_flight_move_x_via_cancel_move(wa):
    """R-25/PY-03 item 2: production's real setWheelsTimed() (shims.cpp)
    calls `r.engine.wheelsV(...)`, whose FIRST act is cancelMove()
    (motion_engine.cpp, motion-api.md S6: "wheels_* clears the
    planner") -- WHEELS supersedes any in-flight move-engine move. The
    pre-fix double called `kernel.drive()` directly, bypassing
    MotionEngine (and cancelMove()) entirely, so an in-flight MOVE_X
    would have kept running underneath a WHEELS_V that should have
    superseded it -- untested and untestable as wired. cancelMove()
    itself is PRIVATE on MotionEngine, so isMoveActive() (public) is the
    only external hook available to prove it ran: MOVE_X arms it,
    WHEELS_V must clear it.

    Demonstrated red pre-fix: temporarily reverting setWheelsTimed() to
    call `kernel.drive()` directly (this ticket's own pre-fix body)
    while keeping this test made `wa.engine_move_active()` read True
    after the WHEELS_V feed below -- the assertion failed as expected.
    Restoring the engine.wheelsV() call made it pass again."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.feed(b"MOVE_X 500 0 100 4000 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    wa.feed(b"WHEELS_V 100 100 500 #2\n")
    assert wa.take_sink() == _ack(2)
    assert not wa.engine_move_active()


def test_status_wedge_reports_suspect_not_latched(wa):
    """R-25/PY-03 item 1: production's real diagValue() (shims.cpp)
    reads wedgeSuspectLeft/Right for ordinals 6/7, which STATUS's own
    `wedge` field folds together (wire_adapter.cpp's status()). Both
    wedgeLeft/Right (LATCHED, wedged()) and wedgeSuspectLeft/Right
    (wedgeSuspect()) exist independently on diffdrive.h's Output struct
    and on FakeMotor -- this is not a compile-time impossibility, it is
    reading the wrong one of two real signals. Set SUSPECT true but
    LATCHED false: the correct double must still report wedge=1.

    Demonstrated red pre-fix: temporarily reverting diagValue()'s case
    6/7 to read wedgeLeft/wedgeRight (this ticket's own pre-fix body)
    made this test's STATUS reply come back `wedge=0` -- assertion
    failed as expected. Restoring the wedgeSuspectLeft/Right read made
    it pass again."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.set_motor_wedge_suspect(LEFT, True)
    wa.set_motor_wedged(LEFT, False)
    wa.step()

    wa.feed(b"STATUS #1\n")
    reply = wa.take_sink().decode()
    assert " wedge=1 " in reply


def test_status_wedge_ignores_latched_when_suspect_clear(wa):
    """The mirror image of test_status_wedge_reports_suspect_not_latched
    above: LATCHED true but SUSPECT false. The correct double must
    report wedge=0 -- if it were still reading the (wrong) latched pair,
    this would instead read wedge=1. Together the two tests discriminate
    in BOTH directions, not just one."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    wa.set_motor_wedged(LEFT, True)
    wa.set_motor_wedge_suspect(LEFT, False)
    wa.step()

    wa.feed(b"STATUS #1\n")
    reply = wa.take_sink().decode()
    assert " wedge=0 " in reply


def test_config_rounding_matches_double_precision_lround(wa):
    """R-25/PY-03 item 3: production's real getConfigValue() (shims.cpp)
    returns `static_cast<int>(std::lround(v * 1000.0))` -- a
    DOUBLE-precision product, round-to-nearest. The pre-fix double
    returned `static_cast<int>(v * 1000.0f)` -- SINGLE-precision,
    truncating. v=0.251f is a verified divergence point, found by a
    direct exhaustive probe over 3-decimal-digit values (NOT the code
    review's own illustrative v=2.3f example, which this ticket's
    execution found does NOT actually diverge under either path --
    2.3f*1000.0f itself rounds to exactly 2300.0f in float32, matching
    lround's result; see this ticket's own notes):
    static_cast<int>(0.251f * 1000.0f) == 250 (truncating float32 path)
    vs. static_cast<int>(std::lround((double)0.251f * 1000.0)) == 251
    (production's double path). Reached through the REAL wire GET verb
    (default_cruise, ordinal 15, WaHandle::defaultCruiseMmS set directly
    via waSetDefaultCruise() so the exact float32 bit pattern survives
    into getConfigValue() unshaped by SET's own x1000 round trip), not a
    raw accessor -- this proves the fix end to end through the same path
    a bench GET command uses.

    Demonstrated red pre-fix: temporarily reverting getConfigValue()'s
    return to `static_cast<int>(v * 1000.0f)` (this ticket's own pre-fix
    body) made this test's GET reply come back `0.250000` -- assertion
    failed as expected. Restoring the std::lround(v * 1000.0) double
    path made it pass again."""
    wa.set_default_cruise(0.251)

    wa.feed(b"GET default_cruise #1\n")
    reply = wa.take_sink()
    prefix = _ack(1) + b"get default_cruise "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.251, abs=1e-4)
