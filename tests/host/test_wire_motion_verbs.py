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
# WHEELS_V's real effect (src/wire_adapter.h's WireAdapter, over a real
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
# not exist (travelCalib_'s real default is 0.8102 mm/deg, i.e.
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

    wa.feed(b"WHEELS_V 200 200 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

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

    wa.feed(b"WHEELS_V 100 300 500 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

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

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

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

    wa.feed(b"WHEELS_V 200 200 5000 #1\n")
    wa.step()
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
    other follows the same ratio."""
    dominant = max(abs(left), abs(right))
    left_speed = (left / dominant) * cruise    # [mm/s]
    right_speed = (right / dominant) * cruise  # [mm/s]
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

    wa.feed(b"WHEELS_X 200 200 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, default_cruise, cpm, _WHEELS_X_FULL_DUTY_VELOCITY)
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
    primitive). Sprint 007 ticket 003: resolves through `default_cruise`,
    not `fullDutyVelocity` -- see
    test_wheels_x_cruise_zero_uses_configured_default's own comment for
    why full_duty_velocity is deliberately set to a DIFFERENT value."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(150.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    default_cruise = 150.0  # [mm/s] -- NOT fullDutyVelocity/cpm

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
    """See test_wheels_x_cruise_zero_without_configured_default_is_
    range_error's own comment: `default_cruise` must be explicitly
    forced to 0 now that production seeds it nonzero, and
    full_duty_velocity is set nonzero to prove the refusal doesn't
    depend on it."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(0.0)
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
    already use. Sprint 007 ticket 003: resolves through
    `default_cruise`, not `fullDutyVelocity` -- see
    test_wheels_x_cruise_zero_uses_configured_default's own comment for
    why full_duty_velocity is deliberately set to a DIFFERENT value."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(150.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    default_speed = 150.0  # [mm/s] -- NOT fullDutyVelocity/cpm

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
    """See test_wheels_x_cruise_zero_without_configured_default_is_
    range_error's own comment: `default_cruise` must be explicitly
    forced to 0 now that production seeds it nonzero, and
    full_duty_velocity is set nonzero to prove the refusal doesn't
    depend on it."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(0.0)
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


def test_go_to_w_speed_zero_uses_configured_default(wa):
    """The fourth verb R-11/BLK-03/API-03 (cruise-zero-sentinel-full-
    duty-lunge.md) names explicitly ("all four verbs") -- GO_TO_W's own
    speed==0 substitution, gated on a real pose source being available
    (motion-api.md S3.6). Identity pose (0,0,0), same as
    test_go_to_w_identity_pose_matches_go_to_r above, so the body-frame
    target equals GO_TO_R's own (200, 50) case and this can reuse the
    same hand-computed formula. Sprint 007 ticket 003: resolves through
    `default_cruise`, not `fullDutyVelocity` -- see
    test_wheels_x_cruise_zero_uses_configured_default's own comment for
    why full_duty_velocity is deliberately set to a DIFFERENT value."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(150.0)
    assert wa.begin() == STATUS_OK
    cpm = wa.counts_per_mm()
    b = wa.effective_track_width()
    wa.set_pose_source_available(True)
    wa.set_pose(0.0, 0.0, 0.0)
    default_speed = 150.0  # [mm/s] -- NOT fullDutyVelocity/cpm

    wa.feed(b"GO_TO_W 200 50 0 0 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.step()

    theta, s = _go_to_r_theta_s(200.0, 50.0)
    expected_left, expected_right = _expected_move_x_duty_pair(
        s, theta, default_speed, cpm, b, 1000.0)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(
        expected_left, rel=1e-4)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(
        expected_right, rel=1e-4)


def test_go_to_w_speed_zero_without_configured_default_is_range_error(wa):
    """See test_wheels_x_cruise_zero_without_configured_default_is_
    range_error's own comment: `default_cruise` must be explicitly
    forced to 0 now that production seeds it nonzero, and
    full_duty_velocity is set nonzero to prove the refusal doesn't
    depend on it. A real pose source is available here (unlike
    test_go_to_w_no_pose_source_is_unimplemented below) so the refusal
    under test is unambiguously the cruise/speed range check, not the
    separate "no pose source" refusal."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.set_default_cruise(0.0)
    assert wa.begin() == STATUS_OK
    wa.set_pose_source_available(True)
    wa.set_pose(0.0, 0.0, 0.0)

    wa.feed(b"GO_TO_W 200 50 0 0 5000 #1\n")
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

    wa.step()
    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, 150.0, wa.counts_per_mm(), _WHEELS_X_FULL_DUTY_VELOCITY)
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)

    # Past the ~150 ms starvation-watchdog window the pre-fix wrap would
    # have left this move stranded inside -- still armed, still driving.
    wa.set_now_ms(1_000_000 + 200)
    assert wa.has_live_motion_obligation()
    wa.step()
    assert wa.motor_last_staged_duty(LEFT) == pytest.approx(expected_left)
    assert wa.motor_last_staged_duty(RIGHT) == pytest.approx(expected_right)


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
    the two. The function name's stale "sixteen" now undercounts by two
    and is left as-is rather than renamed mid-sprint (same call made for
    ticket 003's own `default_cruise` addition)."""
    wa.feed(b"GET #1\n")
    lines = wa.take_sink().split(b"\n")
    names = [line.split(b" ")[1] for line in lines if line.startswith(b"get ")]
    assert names == [
        b"max_duty", b"full_duty_velocity", b"pid_kp", b"pid_ki",
        b"pid_i_max", b"accel_kaff", b"pid_max", b"twist_hold_gain",
        b"speed_floor", b"pos_err_max", b"stall_speed", b"stall_demand",
        b"stall_window", b"lambda_enabled", b"crawl_pulse",
        b"default_cruise", b"rotational_slip", b"stall_clear",
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
    wa.step()

    expected_left, expected_right = _expected_wheels_x_duty_pair(
        200.0, 200.0, 200.0, cpm, _WHEELS_X_FULL_DUTY_VELOCITY)
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

    wa.step()  # first "demanding && still" observation, since=1000ms

    wa.feed(b"GET stall_clear #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get stall_clear "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)

    wa.set_now_ms(1600)  # +600ms > stall_window -> latches this step()
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
