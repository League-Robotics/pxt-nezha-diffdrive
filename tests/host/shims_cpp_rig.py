"""tests/host/shims_cpp_rig.py -- the compile recipe and ctypes binding for
the host build of the real src/shims.cpp (shims_cpp_shim.cpp).

The sources are shims.cpp plus everything it composes that links on the host:
the kernel, motion engine, velocity shaper, estimator (header-only),
board_nezha.cpp's real NezhaMotorPort pair, otos_port.cpp, vfp_guard.cpp,
microbit_i2c_bus.cpp and run_registry.cpp. The pxt-bound ones compile against
tests/host/pxt_host_stub/pxt.h, whose clock, fibers and uBit.i2c the shim
controls. protocol.cpp is the one thing faked, in the shim.

shims.cpp keeps its Rig in a process-lifetime singleton, so `ShimsRig` loads a
private copy of the built library per instance. Time starts at 1 s and moves
only when the test calls `advance_us()` or the real code sleeps.
"""

import ctypes
import pathlib
import shutil

_HERE = pathlib.Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"

SOURCES = [
    _SRC / "shims.cpp",
    _SRC / "core" / "diffdrive.cpp",
    _SRC / "motion" / "motion_engine.cpp",
    _SRC / "motion" / "velocity_shaper.cpp",
    _SRC / "platform" / "nezha_port.cpp",
    _SRC / "platform" / "board_nezha.cpp",
    _SRC / "platform" / "otos_port.cpp",
    _SRC / "platform" / "vfp_guard.cpp",
    _SRC / "platform" / "microbit_i2c_bus.cpp",
    _SRC / "comms" / "run_registry.cpp",
    _HERE / "shims_cpp_shim.cpp",
]

PRODUCTION_FLAGS = ["-I", str(_HERE / "pxt_host_stub"),
                    "-DDIFFDRIVE_HOST_BUILD"]

# diagValue() ordinals the estimator wiring reads
DIAG_BIAS = 42          # [cdeg/min]
DIAG_REJECTED = 43
DIAG_STEPS = 44
DIAG_CONFIG = 45        # 0 optical, 1 gyro, 2 encoders only
DIAG_DISTURBS = 46      # bumps and lifts seen at rest
DIAG_ACCEL_X, DIAG_ACCEL_Y, DIAG_ACCEL_Z = 48, 49, 50   # [mg]
DIAG_ACCEL_PEAK = 51    # [mg] largest per-axis jump since the last read
DIAG_I2C_FAULT = 8      # cycles where either wheel's sample did not advance
DIAG_BUS_FAIL, DIAG_STALE, DIAG_GLITCH = 52, 53, 54   # its causes, both wheels

OPTICAL, GYRO_ONLY, ENCODERS_ONLY = 0, 1, 2

_I, _F, _U64 = ctypes.c_int, ctypes.c_float, ctypes.c_uint64

_SIGNATURES = {
    "scInit": (None, [_I, _F]),
    "scNowUs": (_U64, []),
    "scAdvanceUs": (None, [_U64]),
    "scFiberCount": (_I, []),
    "scEnsure": (_I, []),
    "scDiag": (_I, [_I]),
    "scTick": (_I, []),
    "scIdleSense": (None, []),
    "scAccelSense": (None, []),
    "scSetAccel": (None, [_I, _I, _I]),
    "scNezhaFailReads": (None, [_I]),
    "scIdleSenseDuringNextNezhaWrite": (None, []),
    "scHookFires": (_I, []),
    "scIdleSenseDuringNextOtosWrite": (None, []),
    "scStartMove": (None, [_I, _I, _I, _I]),
    "scSeed": (None, [_I, _I, _I]),
    "scRebase": (None, []),
    "scPoseX": (_I, []),
    "scPoseY": (_I, []),
    "scPoseHeading": (_I, []),
    "scOtosBegin": (_I, []),
    "scOtosRead": (_I, []),
    "scOtosGet": (_I, [_I]),
    "scOtosBurstReads": (_I, []),
    "scOtosPoseWrites": (_I, []),
    "scOtosChipHeading": (_F, []),
    "scOtosSetPresent": (None, [_I]),
    "scOtosFailBursts": (None, [_I]),
    "scOtosMoveSensor": (None, [_F, _F]),
    "scOtosSetBias": (None, [_F]),
}


class ShimsRig:
    """One independent copy of the real shims.cpp over simulated hardware."""

    def __init__(self, built_lib, copy_dir, index, otos_present=True,
                 bias_rad_s=0.0):
        private = copy_dir / f"shims_cpp_{index}.so"
        shutil.copy(built_lib, private)
        self._lib = ctypes.CDLL(str(private))
        for name, (restype, argtypes) in _SIGNATURES.items():
            fn = getattr(self._lib, name)
            fn.restype = restype
            fn.argtypes = argtypes
        self._lib.scInit(1 if otos_present else 0, bias_rad_s)

    def __getattr__(self, name):
        return getattr(self._lib, "sc" + name[0].upper() + name[1:])

    def advance_us(self, us):
        self._lib.scAdvanceUs(us)

    def advance_s(self, seconds):
        self._lib.scAdvanceUs(int(seconds * 1e6))
