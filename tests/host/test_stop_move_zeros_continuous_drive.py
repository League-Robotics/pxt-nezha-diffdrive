"""tests/host/test_stop_move_zeros_continuous_drive.py -- `stop move`
must stop a continuous drive command, not just clear move-engine
bookkeeping.

THE BUG: `src/shims.cpp`'s `endMove()` free function (the `stop move`
block's entry point) used to read `rig->engine.endMove();
deliverStopNow(*rig);` -- no `kernel.neutral()`. `MotionEngine::
endMove()` only stages `kernel_.neutral()` when a move-engine move
(`startMove`/`startGoTo`) is active; after a continuous-drive command
(`setWheelSpeeds`/`driveTwist`, which call `wheelsV()` -> `cancelMove()`
on the way in) no move-engine move is active, so nothing is staged.
`deliverStopNow()`'s port-level zero write (`Motor::emergencyStop()`) is
momentary -- the kernel's held commanded velocity mode (a lease up to
`kLeaseMax`, one hour) is untouched, so the very next `step()`
re-commands the pre-stop duty. Measured in
`docs/code-review/2026-08-26/raw/stop_probe.cpp` (scenario A, with a
full PID configuration): duty back at 23.5% one tick later and climbing
to 24.3% ten ticks later.

THE FIX (this ticket): `endMove()` adds `rig->kernel.neutral();` between
`rig->engine.endMove();` and `deliverStopNow(*rig);` -- the same
three-call shape `stopAll()` already uses. `kernel.neutral()` stages the
kernel's commanded mode to neutral, so the next `step()` computes zero
duty instead of re-deriving the old commanded velocity.

WHAT THIS FILE CANNOT PROVE (read before "simplifying" this file):
`src/shims.cpp` includes `pxt.h` (CODAL/PXT platform types) and cannot
be host-compiled at all -- see `tests/host/README.md` and
`test_cross_fiber_stop_settle_window.py`'s own header comment for this
project's standing convention on that boundary. So this file does NOT
call `shims.cpp::endMove()` itself; it exercises the mechanism through
two hand-mirrored call sequences added to `motion_engine_shim.cpp`
(`meEndMoveOldStopSequence`/`meEndMoveFixedStopSequence`), built from
the same host-portable primitives `shims.cpp` composes (a real
`DiffDrive::DifferentialDrive` kernel + `diffDrive::MotionEngine` over
`FakeMotor`). Those two shim functions must be kept in sync BY HAND with
`shims.cpp::endMove()`'s actual call sequence -- there is no compiler
link between the two files.

This file's kernel configuration is pure feedforward (only maxDuty/
fullDutyVelocity set, kp=ki=0 -- the same configuration
test_motion_engine_primitives.py's own header comment documents), unlike
stop_probe.cpp's full PID setup. That is a deliberate simplification:
the bug is about whether the kernel's commanded MODE survives a stop,
not about PID integral windup, so a deterministic feedforward duty
(constant, not climbing) still proves the mechanism -- see
stop_probe.cpp itself for confirmation that a full PID configuration
also climbs, which is the manual/bench confirmation this ticket's
acceptance criteria call for separately.

Run with::

    uv run pytest tests/host/test_stop_move_zeros_continuous_drive.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

STATUS_OK = 0

LEFT = 0
RIGHT = 1

# Large enough that every commanded speed below stays well under the
# maxDuty=100% rail -- mirrors test_motion_engine_primitives.py's own
# choice, so no assertion here is secretly checking a clamped value.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# A long lease (well beyond this test's handful of ticks), mirroring
# stop_probe.cpp's own use of kLeaseMax for the "continuous drive, never
# expires on its own" setup this bug requires.
_LONG_LEASE_MS = 60_000


def _bind(lib):
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
    lib.meClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.meClockSetNow.restype = None

    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float

    lib.meWheelsV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meWheelsV.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int

    lib.meEndMoveOldStopSequence.argtypes = [ctypes.c_void_p]
    lib.meEndMoveOldStopSequence.restype = None
    lib.meEndMoveFixedStopSequence.argtypes = [ctypes.c_void_p]
    lib.meEndMoveFixedStopSequence.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libstop_move_zeros_continuous_drive_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    same shape as test_motion_engine_primitives.py's own Engine, extended
    with this ticket's two stop-sequence mirrors."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def set_max_duty(self, v):
        self._lib.meSetMaxDuty(self._handle, v)

    def set_full_duty_velocity(self, v):
        self._lib.meSetFullDutyVelocity(self._handle, v)

    def begin(self):
        return self._lib.meBegin(self._handle)

    def step(self):
        self._lib.meStep(self._handle)

    def set_clock(self, now_us):
        self._lib.meClockSetNow(self._handle, now_us)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def land_steady_state_hold(self, start_us=0, advance_us=1_000_000):
        """Sprint 029 ticket 003 (design S4.4/S6.1) -- see
        test_motion_engine_reductions.py's own
        Engine.land_steady_state_hold() for the full explanation this
        file mirrors: a continuous wheelsV() hold is shaped now, so
        seeing its full-rate duty needs a large `dt` on its first
        service() tick, not a single step()."""
        self.step()
        self.set_clock(start_us + advance_us)
        self.service_move()
        self.step()

    def end_move_old_stop_sequence(self):
        self._lib.meEndMoveOldStopSequence(self._handle)

    def end_move_fixed_stop_sequence(self):
        self._lib.meEndMoveFixedStopSequence(self._handle)


def _drive_to_nonzero_duty(engine):
    """Configure the kernel for pure feedforward duty (see this file's
    header comment), begin it, issue a long-lived continuous drive
    command (wheelsV, mirroring setWheelSpeeds()), and land its duty via
    one step(). Returns nothing; asserts the sanity check itself so a
    caller cannot mistake "there was never anything to stop" for "the
    stop worked" (same guard test_cross_fiber_stop_settle_window.py's
    own _drive_to_nonzero_duty() uses)."""
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == STATUS_OK

    engine.set_clock(0)
    engine.wheels_v(200.0, 200.0, _LONG_LEASE_MS)
    engine.land_steady_state_hold()

    assert engine.motor_last_staged_duty(LEFT) != pytest.approx(0.0), (
        "Sanity check failed: the motor was already at zero before the "
        "stop sequence, so this test cannot distinguish 'the stop "
        "worked' from 'there was never anything to stop'."
    )
    assert engine.motor_last_staged_duty(RIGHT) != pytest.approx(0.0)


def test_fixed_stop_sequence_zeros_continuous_drive_and_stays_zero(motion_lib):
    """This ticket's fix: mirroring shims.cpp's POST-fix endMove()
    (engine.endMove() + kernel.neutral() + deliverStopNow()) against a
    continuous drive must zero duty within one tick and hold it there --
    the kernel's commanded velocity mode is disarmed by kernel.neutral(),
    so it never re-commands the old duty."""
    with Engine(motion_lib) as e:
        _drive_to_nonzero_duty(e)

        e.end_move_fixed_stop_sequence()

        e.step()  # one tick later
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)

        for _ in range(10):  # ten ticks later -- must not climb back up
            e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_old_stop_sequence_leaves_duty_nonzero_after_one_tick(motion_lib):
    """Regression pin, ORIGINALLY written against the sprint 006-era bug:
    the OLD sequence -- engine.endMove() (a no-op back then after a
    continuous-drive command, since the pre-029 MotionEngine::endMove()
    only ever checked move_.active, which wheelsV() never set) plus
    deliverStopNow()'s port-level zero, WITHOUT an explicit
    kernel.neutral() -- used to zero duty only momentarily: the kernel's
    commanded velocity mode survived, so the very next step()
    re-commanded the pre-stop duty.

    MEASURED against this ticket's engine: that gap is now closed one
    layer earlier. Sprint 029 ticket 003's own MotionEngine::endMove()
    (motion_engine.cpp) checks `seg_.active || hold_.active` -- design
    S4.4's own table entry ("endMove(): neutral + shaper_.reset() +
    clear both seg_/hold_") -- so it now stages kernel_.neutral() for a
    live continuous hold too, not only a position-mode Segment. The
    meEndMoveOldStopSequence() shim this test drives
    (motion_engine_shim.cpp) calls this SAME real engine.endMove(), so
    it inherits the fix regardless of never calling kernel.neutral()
    itself -- there is no longer an "old" vs. "fixed" behavioral
    difference to observe through this particular pair of shims for the
    continuous-drive case (shims.cpp's own production endMove() still
    calls kernel.neutral() explicitly in addition, unchanged by this
    ticket, so the real robot's behavior is unaffected either way). This
    test now pins THAT (a genuine improvement), rather than a
    difference that no longer exists."""
    with Engine(motion_lib) as e:
        _drive_to_nonzero_duty(e)

        e.end_move_old_stop_sequence()

        # Momentary: the port-level write lands immediately, with no
        # step() needed -- same as deliverStopNow()'s own contract
        # (test_cross_fiber_stop_settle_window.py).
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)

        e.step()  # one tick later -- MotionEngine::endMove() already
                  # staged kernel_.neutral() for the hold, so this stays
                  # zero (see this test's own docstring for why that is
                  # no longer the historical bug).
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)

        for _ in range(10):  # ten ticks later -- stays zero
            e.step()
        assert e.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert e.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)
