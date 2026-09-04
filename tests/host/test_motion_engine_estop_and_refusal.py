"""tests/host/test_motion_engine_estop_and_refusal.py -- two independent
MotionEngine fixes, both entirely within the host-portable
motion_engine.cpp (no pxt.h, no CODAL, no shims.cpp involvement).

(a) serviceMove() did not end on e-stop. Its end condition
(distDone && yawDone) || expired || stallHalted || wrongWay never
checked Output.estopped, even though the kernel forces neutral under
the e-stop latch the same way it does under the stall latch. Measured
(docs/code-review/2026-08-26/raw/stop_probe.cpp scenario B): 1230
further ticks (29.5 s) of isMoveActive() == true after the latch, on a
30 s-timeout move -- the wheels were already safe, but every
`while (driveTick())` loop spun to the deadline anyway. This was
previously masked only by shims.cpp's estopAll() calling
engine.endMove() BEFORE kernel.estop() -- an ordering this class must
not depend on (kernel.emergencyStopMotors() latches the e-stop as a
side effect that bypasses that ordering entirely). The test below
proves the fix WITHOUT going through anything resembling that ordering:
it calls kernel.estop() directly, never engine.endMove().

(b) startSegment() armed move_.active regardless of what kernel_.drive()
returned. DifferentialDrive::drive() returns a Status (kOk,
kRefusedUnconfigured, kRefusedNotBegun, kRefusedEstopped,
kRefusedNonFinite -- src/core/diffdrive.h); startSegment() used to
discard it and set move_.active = true unconditionally. A refused move
still reported progress, still spun to its own deadline, and resolved
as kStop on the wire -- indistinguishable from a move that actually
ran. The fix captures the Status and arms move_.active only on kOk.

src/core/diffdrive.{h,cpp} is vendored and byte-stable -- this file only
reads its existing public surface (Output.estopped, the Status enum,
drive()'s existing return value), never modifies it.

Run with::

    uv run pytest tests/host/test_motion_engine_estop_and_refusal.py
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

# DiffDrive::DifferentialDrive::Status's DECLARATION order (src/core/diffdrive.h).
STATUS_OK = 0
STATUS_REFUSED_UNCONFIGURED = 1

FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# Well beyond this test's handful of ticks -- the point of the e-stop
# fix is that the move ends immediately, not at this deadline.
_LONG_TIMEOUT_MS = 30_000


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

    lib.meMoveX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meMoveX.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int

    lib.meOutEstopped.argtypes = [ctypes.c_void_p]
    lib.meOutEstopped.restype = ctypes.c_int
    lib.meKernelEstop.argtypes = [ctypes.c_void_p]
    lib.meKernelEstop.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_estop_and_refusal_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    same shape as the other motion_engine_shim.cpp test files' own
    Engine wrappers, limited to the surface this file needs."""

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

    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def out_estopped(self):
        return bool(self._lib.meOutEstopped(self._handle))

    def kernel_estop(self):
        self._lib.meKernelEstop(self._handle)


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == STATUS_OK


# ---- (a) serviceMove() ends on e-stop -----------------------------------


def test_estop_mid_move_ends_service_move_on_the_very_next_call(motion_lib):
    """A move latched by kernel.estop() -- called directly, never through
    engine.endMove() or anything resembling shims.cpp's estopAll()
    ordering -- must make serviceMove() return false and isMoveActive()
    read false as soon as the latch is actually published (one step()
    later, matching this class's own "step() is always the caller's,
    once per tick, before serviceMove()" contract), not 1230 further
    ticks later at the move's own deadline."""
    with Engine(motion_lib) as e:
        _ready(e)

        # No motor position is ever armed, so distDone never becomes
        # true on its own -- the only way this move ends is expired
        # (30 s away) or the e-stop this test latches. FakeMotor's own
        # defaults (fake_ports.h) make this safe: an unarmed position
        # simply never advances.
        e.move_x(1000.0, 0.0, 100.0, _LONG_TIMEOUT_MS)

        for _ in range(3):  # a few ordinary ticks -- genuinely mid-move
            e.step()
            still_active = e.service_move()
        assert still_active, (
            "Sanity check failed: the move already ended on its own "
            "before the e-stop, so this test cannot distinguish 'the "
            "e-stop fix worked' from 'there was nothing left to end'."
        )
        assert e.is_move_active()
        assert not e.out_estopped()  # not latched yet -- another sanity check

        e.kernel_estop()  # THE latch -- direct, no endMove() involved

        e.step()  # publishes Output.estopped=true AND forces the
                  # kernel's own commanded mode to neutral this same tick
        assert e.out_estopped(), (
            "Sanity check failed: the latch never actually published -- "
            "see DifferentialDrive::estop()/publishOutput() in "
            "diffdrive.cpp. Without this, the assertions below would "
            "prove nothing about the estopped condition specifically."
        )

        result = e.service_move()  # the very next call
        assert result is False, (
            "serviceMove() must end the move on out.estopped, the same "
            "way it already does on out.stallHalted -- this is the fix "
            "this ticket adds."
        )
        assert not e.is_move_active()


# ---- (b) startSegment() honours a refused drive() -----------------------


def test_refused_drive_does_not_arm_move_active(motion_lib):
    """maxDuty == 0 is Status::kRefusedUnconfigured's own documented
    trigger (diffdrive.h). begin() itself refuses under that
    configuration too, but begun_ is still set (readiness is begin()'s
    to grant, not start()'s -- diffdrive.h's own Status comment), so the
    SAME refusal reaches moveX() -> service()'s own kernel_.drive() call.

    REWRITTEN sprint 029 ticket 003 (design S6.5's lazy start): moveX()
    no longer calls kernel_.drive() synchronously at all -- beginSegment()
    only arms seg_ and issues no command, so a refused drive() can only
    ever be discovered on the segment's own FIRST service() tick, when
    service() finally issues it, never at moveX() call time. seg_.active
    therefore reads true immediately after moveX() (nothing has been
    attempted yet, so nothing has been refused yet) -- the assertion
    this test used to make right there no longer holds, and is not a
    regression: service() itself now checks kernel_.drive()'s own
    Status on every tick (motion_engine.cpp) and ends the segment the
    first time it comes back refused, which is what this test now
    proves instead. Without that check a permanently-refused drive()
    would re-issue every tick forever and spin the segment to its own
    deadline exactly like a move that actually ran -- the original bug
    this test was written to catch, still caught, one tick later."""
    with Engine(motion_lib) as e:
        e.set_max_duty(0.0)  # deliberately refused: no fullDutyVelocity
        # set either -- maxDuty alone is enough to trigger
        # kRefusedUnconfigured (diffdrive.cpp's checkCommandable()).
        assert e.begin() == STATUS_REFUSED_UNCONFIGURED

        e.move_x(200.0, 0.0, 100.0, 5000)
        assert e.is_move_active(), (
            "Sanity: armed immediately (design S6.5's lazy start) -- "
            "nothing has been attempted, let alone refused, yet."
        )

        e.step()
        still_active = e.service_move()
        assert not still_active, (
            "service()'s own first tick must detect the refused "
            "kernel_.drive() and end the segment -- not keep re-issuing "
            "a command that can never succeed and spinning to the "
            "segment's own deadline exactly like a move that actually "
            "ran."
        )
        assert not e.is_move_active()

    # Contrast, in a fresh engine: the SAME call, properly configured,
    # must still arm move_.active on a successful drive() -- proving the
    # assertion above is not vacuously true because moveX() never arms
    # active regardless of Status.
    with Engine(motion_lib) as e:
        _ready(e)
        e.move_x(200.0, 0.0, 100.0, 5000)
        assert e.is_move_active(), (
            "Sanity check failed: a properly configured moveX() call "
            "must still arm move_.active on a successful drive() -- "
            "otherwise the refusal test above proves nothing about "
            "Status specifically."
        )
