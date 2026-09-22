"""tests/host/conftest.py -- the one place this directory compiles the
motion-engine shim.

Thirteen test files here drive the same shared library: the same four
translation units (`diffdrive.cpp` + `motion_engine.cpp` +
`velocity_shaper.cpp` + `motion_engine_shim.cpp`) behind the same
`meCreate()`/`meDestroy()` handle. Until sprint 034 ticket 010 each of
those thirteen carried its own copy of the source list and its own
session-scoped `motion_lib` fixture with its own `out_name`, so the
identical compile ran thirteen times per pytest session -- and thirteen
copies of one source list is thirteen chances for one of them to drift
away from the others when a new `src/motion/` file joins the link (the
list has already grown `velocity_shaper.cpp` since the harness was
written).

MEASURED 2026-09-06 on this checkout, `uv run pytest tests/host
tests/tools -q`: 1719 passed in 75.30 s before this consolidation;
1722 passed in 57.88 s and 58.47 s after (two runs; the three extra
tests are this ticket's own). Twelve compiles of the same four
translation units is what went away.

What lives here now:

- `MOTION_SHIM_SOURCES` -- the source list, in exactly one place.
- `_bind_motion_lib()` -- the union of the thirteen files' own former
  `_bind()`/`_bind_probe()`/`_bind_reconcile()` functions: 70 symbols,
  every one of which was bound identically wherever it was bound twice
  (checked before merging; no two files disagreed about a signature).
  It is the ctypes mirror of `motion_engine_shim.cpp`'s `extern "C"`
  surface, so it belongs beside the compile recipe rather than being
  re-derived per test file.
- `motion_lib` -- the session-scoped fixture every one of those files
  now takes from here by name.

Consequence worth knowing: all those files share ONE `ctypes.CDLL`
object now, not thirteen. Binding is idempotent and the shim keeps no
module-level state (every handle comes from `meCreate()`), so this is
safe -- but a test that mutates `lib.<symbol>.argtypes` at call time
(`test_segment_lazy_origin.py`'s `_bind_rebase()`) is mutating shared
state. Keep such binders signature-compatible with the union above.

The kernel/wire/run-queue shims are NOT consolidated here: those are
different source lists driving different classes, and each has one
owner file. This fixture exists because thirteen files wanted the same
library, not as a general "put fixtures in conftest" policy -- see
`tests/host/DESIGN.md` §4.
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

# tests/host/conftest.py -> host -> tests -> repo root
_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

#: The motion-engine shim's source list. The single source of truth --
#: every test file that used to carry its own copy now takes the
#: `motion_lib` fixture below instead.
MOTION_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

# MotionLimits' ten getters and their ten matching setters -- bound by
# loop rather than by name because the shim exposes them as one uniform
# family (all `float(handle)` / `void(handle, float)`).
_LIMITS_GETTERS = (
    "meLimitsAccel", "meLimitsDecel", "meLimitsJerk", "meLimitsVMax",
    "meLimitsOmegaMax", "meLimitsVFloor", "meLimitsOmegaFloor",
    "meLimitsStopDistance", "meLimitsArriveDist", "meLimitsArriveYaw",
)
_LIMITS_SETTERS = (
    "meLimitsSetAccel", "meLimitsSetDecel", "meLimitsSetJerk",
    "meLimitsSetVMax", "meLimitsSetOmegaMax", "meLimitsSetVFloor",
    "meLimitsSetOmegaFloor", "meLimitsSetStopDistance",
    "meLimitsSetArriveDist", "meLimitsSetArriveYaw",
)


def _bind_motion_lib(lib):
    """Attach ctypes argtypes/restype for every `motion_engine_shim.cpp`
    export, then return `lib`.

    Grouped by which test file first needed each block, because that is
    the only ordering the merge preserved and it is what makes a symbol
    findable again. The groups are not scopes: every test file sees the
    whole surface.
    """
    # -- surface first needed by test_motion_engine_primitives.py
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None
    lib.meSetMaxDuty.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetMaxDuty.restype = None
    lib.meSetFullDutyVelocity.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetFullDutyVelocity.restype = None
    lib.meBegin.argtypes = [ctypes.c_void_p]
    lib.meBegin.restype = ctypes.c_int
    lib.meStep.argtypes = [ctypes.c_void_p]
    lib.meStep.restype = None
    lib.meOutLeaseExpired.argtypes = [ctypes.c_void_p]
    lib.meOutLeaseExpired.restype = ctypes.c_int
    lib.meClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.meClockSetNow.restype = None
    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float
    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float
    lib.meTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meTrackWidth.restype = ctypes.c_float
    lib.meTravelCalib.argtypes = [ctypes.c_void_p]
    lib.meTravelCalib.restype = ctypes.c_float
    lib.meRotationalSlip.argtypes = [ctypes.c_void_p]
    lib.meRotationalSlip.restype = ctypes.c_float
    lib.meSetTrackWidth.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetTrackWidth.restype = None
    lib.meSetTravelCalib.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetTravelCalib.restype = None
    lib.meSetRotationalSlip.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetRotationalSlip.restype = None
    lib.meWheelsV.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meWheelsV.restype = None
    lib.meWheelsX.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meWheelsX.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meMotorArmPosition.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64]
    lib.meMotorArmPosition.restype = None

    # -- surface first needed by test_goto_block_regression.py
    lib.meProbeRunToCompletion.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32, ctypes.c_uint32]
    lib.meProbeRunToCompletion.restype = ctypes.c_uint32
    lib.meProbeX.argtypes = [ctypes.c_void_p]
    lib.meProbeX.restype = ctypes.c_float
    lib.meProbeY.argtypes = [ctypes.c_void_p]
    lib.meProbeY.restype = ctypes.c_float
    lib.meProbeHeading.argtypes = [ctypes.c_void_p]
    lib.meProbeHeading.restype = ctypes.c_float

    # -- surface first needed by test_goto_turn_rate_reconciliation.py
    lib.meReconcileCruise.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.meReconcileCruise.restype = ctypes.c_float
    lib.meReconcileDistDuration.argtypes = lib.meReconcileCruise.argtypes
    lib.meReconcileDistDuration.restype = ctypes.c_float
    lib.meReconcileYawDuration.argtypes = lib.meReconcileCruise.argtypes
    lib.meReconcileYawDuration.restype = ctypes.c_float
    lib.meDecomposeGoToRBearingRaw.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRBearingRaw.restype = ctypes.c_float
    lib.meDecomposeGoToRTheta.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRTheta.restype = ctypes.c_float
    lib.meDecomposeGoToRChord.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRChord.restype = ctypes.c_float
    lib.meDecomposeGoToRArcLength.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRArcLength.restype = ctypes.c_float
    lib.meDecomposeGoToRWillSplit.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRWillSplit.restype = ctypes.c_int

    # -- surface first needed by test_motion_engine_acceleration_profile.py
    lib.meMoveX.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meMoveX.restype = None
    lib.meWrongWayCount.argtypes = [ctypes.c_void_p]
    lib.meWrongWayCount.restype = ctypes.c_uint32
    lib.meLimitsSetAccel.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetAccel.restype = None
    lib.meLimitsSetDecel.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetDecel.restype = None
    lib.meLimitsSetVMax.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetVMax.restype = None
    lib.meDefaultCruiseForDistance.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meDefaultCruiseForDistance.restype = ctypes.c_float
    lib.meDominantAxisTravelMm.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
    lib.meDominantAxisTravelMm.restype = ctypes.c_float

    # -- surface first needed by test_motion_engine_estop_and_refusal.py
    lib.meOutEstopped.argtypes = [ctypes.c_void_p]
    lib.meOutEstopped.restype = ctypes.c_int
    lib.meKernelEstop.argtypes = [ctypes.c_void_p]
    lib.meKernelEstop.restype = None

    # -- surface first needed by test_motion_engine_gotow.py
    lib.mePoseSourceSetPose.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.mePoseSourceSetPose.restype = None
    lib.meGoToW.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meGoToW.restype = None
    lib.meOdometrySetPose.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.meOdometrySetPose.restype = None
    lib.meOdometryX.argtypes = [ctypes.c_void_p]
    lib.meOdometryX.restype = ctypes.c_float
    lib.meOdometryY.argtypes = [ctypes.c_void_p]
    lib.meOdometryY.restype = ctypes.c_float
    lib.meOdometryHeading.argtypes = [ctypes.c_void_p]
    lib.meOdometryHeading.restype = ctypes.c_float
    lib.meGoToWViaOdometry.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meGoToWViaOdometry.restype = None
    lib.meSelectPoseSourceX.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meSelectPoseSourceX.restype = ctypes.c_float

    # -- surface first needed by test_motion_engine_reductions.py
    lib.meSetTwistHoldGain.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetTwistHoldGain.restype = None
    lib.meOutVelocityLeft.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityLeft.restype = ctypes.c_float
    lib.meOutVelocityRight.argtypes = [ctypes.c_void_p]
    lib.meOutVelocityRight.restype = ctypes.c_float
    lib.meMoveV.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meMoveV.restype = None
    lib.meGoToR.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meGoToR.restype = None
    lib.meEndMove.argtypes = [ctypes.c_void_p]
    lib.meEndMove.restype = None
    lib.meProgress.argtypes = [ctypes.c_void_p]
    lib.meProgress.restype = ctypes.c_int

    # -- surface first needed by test_motion_engine_settle.py
    lib.meSettleToRest.argtypes = [ctypes.c_void_p]
    lib.meSettleToRest.restype = ctypes.c_uint32
    lib.meArmSettleProfile.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_uint64), ctypes.c_int]
    lib.meArmSettleProfile.restype = None
    lib.meDisarmSettleProfile.argtypes = [ctypes.c_void_p]
    lib.meDisarmSettleProfile.restype = None

    # -- surface first needed by test_motion_engine_shaping_fields.py
    for getter in _LIMITS_GETTERS:
        fn = getattr(lib, getter)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float
    for setter in _LIMITS_SETTERS:
        fn = getattr(lib, setter)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_float]
        fn.restype = None

    # -- surface first needed by test_profile_probe.py
    lib.meIsDriving.argtypes = [ctypes.c_void_p]
    lib.meIsDriving.restype = ctypes.c_int
    lib.meLimitsAccel.argtypes = [ctypes.c_void_p]
    lib.meLimitsAccel.restype = ctypes.c_float
    lib.meLimitsVFloor.argtypes = [ctypes.c_void_p]
    lib.meLimitsVFloor.restype = ctypes.c_float
    lib.meLimitsSetLag.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetLag.restype = None
    lib.meApplyStictionProbeKernelConfig.argtypes = [ctypes.c_void_p]
    lib.meApplyStictionProbeKernelConfig.restype = None
    lib.meSetPidGains.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.meSetPidGains.restype = None
    lib.meTwistReferenceCounts.argtypes = [ctypes.c_void_p]
    lib.meTwistReferenceCounts.restype = ctypes.c_float

    # -- surface first needed by test_motion_engine_pulse.py (sprint 039
    # ticket 001, SUC-001)
    lib.mePulseWheels.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_int32]
    lib.mePulseWheels.restype = None
    lib.mePulseLeftCounts.argtypes = [ctypes.c_void_p]
    lib.mePulseLeftCounts.restype = ctypes.c_float
    lib.mePulseRightCounts.argtypes = [ctypes.c_void_p]
    lib.mePulseRightCounts.restype = ctypes.c_float
    lib.meMotorDutyHistoryCount.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorDutyHistoryCount.restype = ctypes.c_int
    lib.meMotorDutyHistoryAt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.meMotorDutyHistoryAt.restype = ctypes.c_float
    lib.meMotorClearDutyHistory.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorClearDutyHistory.restype = None
    lib.meArmEstopAfterSleepCall.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meArmEstopAfterSleepCall.restype = None
    lib.meDisarmEstopAfterSleepCall.argtypes = [ctypes.c_void_p]
    lib.meDisarmEstopAfterSleepCall.restype = None

    # -- surface first needed by test_stop_move_zeros_continuous_drive.py
    lib.meEndMoveOldStopSequence.argtypes = [ctypes.c_void_p]
    lib.meEndMoveOldStopSequence.restype = None
    lib.meEndMoveFixedStopSequence.argtypes = [ctypes.c_void_p]
    lib.meEndMoveFixedStopSequence.restype = None
    # -- surface first needed by test_status_active_after_soft_stop.py
    # (sprint 039 ticket 002)
    lib.meEndMoveSettledStopSequence.argtypes = [ctypes.c_void_p]
    lib.meEndMoveSettledStopSequence.restype = None
    # -- surface first needed by test_motion_engine_stall_rearm.py
    lib.meSetStall.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    lib.meSetStall.restype = None
    lib.meOutStallHalted.argtypes = [ctypes.c_void_p]
    lib.meOutStallHalted.restype = ctypes.c_int
    lib.meStallReported.argtypes = [ctypes.c_void_p]
    lib.meStallReported.restype = ctypes.c_int
    lib.meClearStallReport.argtypes = [ctypes.c_void_p]
    lib.meClearStallReport.restype = None
    lib.meIsDriving.argtypes = [ctypes.c_void_p]
    lib.meIsDriving.restype = ctypes.c_int

    # -- surface first needed by test_motion_engine_nudge.py (sprint 039
    # ticket 004)
    lib.meBeginNudge.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.meBeginNudge.restype = None
    lib.meIsNudgeActive.argtypes = [ctypes.c_void_p]
    lib.meIsNudgeActive.restype = ctypes.c_int
    lib.meNudgePulseCount.argtypes = [ctypes.c_void_p]
    lib.meNudgePulseCount.restype = ctypes.c_int32
    lib.meNudgeMaxPulses.argtypes = [ctypes.c_void_p]
    lib.meNudgeMaxPulses.restype = ctypes.c_int32
    lib.meNudgeAmplitude.argtypes = [ctypes.c_void_p]
    lib.meNudgeAmplitude.restype = ctypes.c_float
    lib.meSetNudgeAmplitude.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetNudgeAmplitude.restype = None
    lib.meNudgeWidthTicks.argtypes = [ctypes.c_void_p]
    lib.meNudgeWidthTicks.restype = ctypes.c_int32
    lib.meSetNudgeWidthTicks.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    lib.meSetNudgeWidthTicks.restype = None
    lib.meNudgeSettle.argtypes = [ctypes.c_void_p]
    lib.meNudgeSettle.restype = ctypes.c_float
    lib.meSetNudgeSettle.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetNudgeSettle.restype = None

    # -- surface first needed by test_nudge_block_regression.py (sprint
    # 039 ticket 005)
    lib.meNudgeMeasuredDistance.argtypes = [ctypes.c_void_p]
    lib.meNudgeMeasuredDistance.restype = ctypes.c_float
    lib.meNudgeMeasuredRotation.argtypes = [ctypes.c_void_p]
    lib.meNudgeMeasuredRotation.restype = ctypes.c_float

    # -- surface first needed by test_wheel_command_tap.py (sprint 040
    # ticket 003)
    lib.meTapInstall.argtypes = [ctypes.c_void_p]
    lib.meTapInstall.restype = None
    lib.meTapUninstall.argtypes = [ctypes.c_void_p]
    lib.meTapUninstall.restype = None
    lib.meTapClear.argtypes = [ctypes.c_void_p]
    lib.meTapClear.restype = None
    lib.meTapRecordCount.argtypes = [ctypes.c_void_p]
    lib.meTapRecordCount.restype = ctypes.c_int
    lib.meTapRecordKind.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meTapRecordKind.restype = ctypes.c_int
    lib.meTapRecordLeft.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meTapRecordLeft.restype = ctypes.c_float
    lib.meTapRecordRight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meTapRecordRight.restype = ctypes.c_float
    lib.meTapRecordPhase.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meTapRecordPhase.restype = ctypes.c_int
    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    """Compile the motion-engine shim ONCE per pytest session and return
    the fully bound `ctypes.CDLL`.

    Mirrors `test_kernel_harness.py`'s own `kernel_lib` fixture -- same
    `compile_shared_lib()` recipe, same session scope -- and replaces
    the thirteen per-file copies of it this directory used to carry.
    """
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=MOTION_SHIM_SOURCES,
        out_name="libmotion_engine_shim.so",
    )
    return _bind_motion_lib(ctypes.CDLL(str(lib_path)))
