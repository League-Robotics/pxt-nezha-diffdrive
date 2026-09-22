"""tests/host/test_board_nezha_diag.py -- host coverage for
`diffDrive::nezhaBoardDiagValue()` (src/platform/nezha_port.h/.cpp),
the free function sprint 040 ticket 001 (the board-composition seam,
docs/design/cutebot-pro-support.md S2.1/S4) factored the Nezha-only
diag-ordinal field mapping into.

WHY THIS EXISTS. Before this ticket, `shims.cpp`'s `diagValue()` read
ordinals 21/22/23/24/27/35-40 directly off `ensure().left`/`.right` as
a concrete `NezhaMotorPort` -- untestable on the host, since
`shims.cpp` includes `pxt.h` and cannot be compiled here at all. The
board-composition seam (`platform/board.h`) moves that switch behind a
per-board hook (`boardDiagValue()`, `platform/board_nezha.cpp`), which
is STILL not host-linkable as a whole (its `NezhaBoard` singleton
constructs its ports through the target-only default `I2CBus`
argument -- see that file's own header comment). What ticket 001
extracted INTO a host-testable shape is the actual field-mapping
computation, `nezhaBoardDiagValue()`, which takes two already-
constructed ports by reference and touches no I2C at all.

WHAT THIS FILE PROVES. That `nezhaBoardDiagValue()` reads the exact
same fields, at the exact same ordinals, that `shims.cpp`'s
`diagValue()` read directly before this ticket:

  - 21/22 (maxDrivenStreak_), 23/24 (glitchCount_), 27
    (rebaselineCount_ summed) -- driven directly through this file's
    own shim, since those three counters are public data members with
    no I2C behind them.
  - 35-38 (wiredPort()/wiredSign()) -- driven by constructing the two
    ports with different port/sign arguments, exactly as the real
    `NezhaBoard` construction does; these two accessors read straight
    off the constructor arguments, no bus involved.
  - An ordinal this function has no mapping for still falls through to
    the same `default: return 0` diagValue() itself uses.

WHAT THIS FILE CANNOT PROVE. That `board_nezha.cpp`'s own
`boardDiagValue()` hook, and `shims.cpp`'s `diagValue()` switch, still
call this function for exactly ordinals 21/22/23/24/27/35-40 with no
ordinal dropped or misrouted -- both files are hex-checkpoint-only.
`test_board_seam_source_pin.py` pins that wiring as source text
instead; together the two tests cover the same ground the OLD
untested-but-inline switch case bodies did.

Run with::

    uv run pytest tests/host/test_board_nezha_diag.py
"""

import ctypes
import pathlib
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_HERE = pathlib.Path(__file__).resolve().parent

_SOURCES = [
    _HERE / "nezha_board_diag_shim.cpp",
    _SRC_DIR / "platform" / "nezha_port.cpp",
]


def _compile(tmp_path_factory):
    """Compile `_SOURCES` into a shared library with
    `-DDIFFDRIVE_HOST_BUILD`, mirroring `sim_tour.py`'s own `build()` --
    `tests/host/test_kernel_harness.compile_shared_lib()` has no way to
    pass that define, and nezha_port.cpp needs it to exclude the
    CODAL-only fault handlers (which reach `pxt.h`, absent on the
    host)."""
    build_dir = tmp_path_factory.mktemp("board_nezha_diag_build")
    lib_path = build_dir / "libboard_nezha_diag.so"
    objects = []
    for index, source in enumerate(_SOURCES):
        obj = build_dir / f"{source.stem}.{index}.o"
        cmd = ["/usr/bin/c++", "-std=c++11", "-Wall", "-Wextra", "-fPIC",
               "-O0", "-DDIFFDRIVE_HOST_BUILD", "-c"]
        if not source.resolve().is_relative_to(_SRC_DIR.resolve()):
            cmd += ["-I", str(_SRC_DIR), "-I", str(_HERE)]
        cmd += [str(source), "-o", str(obj)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"host compile failed for {source}:\ncommand: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        objects.append(obj)
    link_cmd = (["/usr/bin/c++", "-shared", "-fPIC", "-o", str(lib_path)]
               + [str(o) for o in objects])
    result = subprocess.run(link_cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"host link failed:\ncommand: {' '.join(link_cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return lib_path


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = _compile(tmp_path_factory)
    handle = ctypes.CDLL(str(path))
    handle.nbdCreate.argtypes = []
    handle.nbdCreate.restype = ctypes.c_void_p
    handle.nbdDestroy.argtypes = [ctypes.c_void_p]
    handle.nbdDestroy.restype = None
    handle.nbdSetLeftCounters.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    handle.nbdSetLeftCounters.restype = None
    handle.nbdSetRightCounters.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    handle.nbdSetRightCounters.restype = None
    handle.nbdDiagValue.argtypes = [ctypes.c_void_p, ctypes.c_int]
    handle.nbdDiagValue.restype = ctypes.c_int
    return handle


@pytest.fixture()
def board(lib):
    handle = lib.nbdCreate()
    yield lib, handle
    lib.nbdDestroy(handle)


def test_ordinals_21_22_read_max_driven_streak(board):
    lib, handle = board
    lib.nbdSetLeftCounters(handle, 13, 0, 0)
    lib.nbdSetRightCounters(handle, 7, 0, 0)
    assert lib.nbdDiagValue(handle, 21) == 13
    assert lib.nbdDiagValue(handle, 22) == 7


def test_ordinals_23_24_read_glitch_count(board):
    lib, handle = board
    lib.nbdSetLeftCounters(handle, 0, 4, 0)
    lib.nbdSetRightCounters(handle, 0, 9, 0)
    assert lib.nbdDiagValue(handle, 23) == 4
    assert lib.nbdDiagValue(handle, 24) == 9


def test_ordinal_27_sums_both_wheels_rebaseline_count(board):
    lib, handle = board
    lib.nbdSetLeftCounters(handle, 0, 0, 2)
    lib.nbdSetRightCounters(handle, 0, 0, 3)
    assert lib.nbdDiagValue(handle, 27) == 5


def test_ordinals_35_38_read_wired_port_and_sign(board):
    # Constructed 1/-1 (left), 2/+1 (right) -- the shim's own fixed
    # construction, matching NezhaBoard's tracked default exactly.
    lib, handle = board
    assert lib.nbdDiagValue(handle, 35) == 1
    assert lib.nbdDiagValue(handle, 36) == -1
    assert lib.nbdDiagValue(handle, 37) == 2
    assert lib.nbdDiagValue(handle, 38) == 1


def test_ordinals_39_40_read_raw_count_default_zero(board):
    """rawCount() before any encoder read is 0 -- this shim never ticks
    the ports, so it can only prove the ordinal reaches rawCount() at
    its untouched default, not a live value. See this file's own
    module doc comment for what is and isn't proved here."""
    lib, handle = board
    assert lib.nbdDiagValue(handle, 39) == 0
    assert lib.nbdDiagValue(handle, 40) == 0


@pytest.mark.parametrize("ordinal", [0, 20, 26, 41, 100])
def test_unmapped_ordinal_returns_zero(board, ordinal):
    lib, handle = board
    assert lib.nbdDiagValue(handle, ordinal) == 0
