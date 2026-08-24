"""tests/host/test_cxx11_syntax_gate.py -- a narrow recurrence guard for
the exact defect that broke sprint 004 ticket 005's bench checkpoint
(sprint 004 ticket 007: "Wire::Column C++11 compile fix and
SerialTransport ring-size correction").

**What broke, and why the rest of this suite didn't catch it**:
tests/host/'s own compile_shared_lib() (test_kernel_harness.py) compiles
this project's portable C++ at -std=c++20, but BOTH real embedded build
targets (legacy mbed-classic/yotta bbc-microbit-classic-gcc and
codal-microbit-v2) compile at -std=c++11, baked into the pxt-microbit
target's own yotta/CMake toolchain files and not overridable from this
project's pxt.json. `Wire::Column`'s default member initializers
(src/wire_handler.h, ticket 004) are legal C++20 but disqualify it from
being a C++11 aggregate -- so the ~20 `columns_[i++] = {...}`
brace-assignment sites in WireAdapter::buildSnapshot()
(src/wire_adapter.cpp) compiled clean against 253 passing host tests
while being uncompilable for the actual robot. This test would have
caught that before it cost a bench checkpoint to surface.

**Scope, deliberately narrow**: exactly the four files already known to
have no pxt.h/CODAL dependency (confirmed by repo grep and by their own
header comments) -- the same four files test_kernel_harness.py's own
compile_shared_lib() already compiles successfully at -std=c++20. This
only adds a SECOND, syntax-only compile of the identical files at the
target's real standard: `-fsyntax-only` needs no `-shared -fPIC -o`, no
shim, and no link step. Do NOT extend this to protocol.{h,cpp},
radio_transport.{h,cpp}, serial_transport.{h,cpp}, shims.cpp,
nezha_port.{h,cpp}, or otos_port.{h,cpp} -- all of those include pxt.h
(directly or transitively via platform_ports.h) and cannot be
syntax-checked without the CODAL toolchain, which this repo's host
suite does not have.

This is a partial, non-systemic down payment on
host-tests-compile-newer-standard-than-target.md (filed against sprint
008, which owns the real fix: compiling the whole host suite at
-std=c++11, or gating a real build into CI/sprint-close). It does not
attempt that broader fix.

Run with::

    uv run pytest tests/host/test_cxx11_syntax_gate.py
"""

import pathlib
import subprocess

import pytest

# tests/host/test_cxx11_syntax_gate.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

# The exact, fixed four-file list this ticket's own sizing note requires
# -- not a moving target, and not "everything under src/". Each of these
# is confirmed host-portable (no pxt.h, directly or transitively) by its
# own header comment and by test_kernel_harness.py's existing
# -std=c++20 compile of the same files.
_CXX11_PORTABLE_SOURCES = [
    _SRC_DIR / "diffdrive.cpp",
    _SRC_DIR / "motion_engine.cpp",
    _SRC_DIR / "wire_handler.cpp",
    _SRC_DIR / "wire_adapter.cpp",
]


@pytest.mark.parametrize(
    "source", _CXX11_PORTABLE_SOURCES, ids=lambda p: p.name
)
def test_host_portable_source_compiles_at_cxx11(source):
    """A -std=c++11 -fsyntax-only compile of one host-portable source
    file must succeed -- the exact standard both real embedded build
    targets use, and nine language-standard versions below
    tests/host/'s own -std=c++20. No -shared/-fPIC/-o and no shim: a
    syntax-only check needs neither a link step nor fake ports."""
    cmd = [
        "/usr/bin/c++",
        "-std=c++11",
        "-fsyntax-only",
        "-I", str(_SRC_DIR),
        str(source),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{source.name} fails to compile at -std=c++11 (the real "
        f"embedded target standard) though it compiles at -std=c++20 "
        f"(tests/host/'s standard) -- this is the exact class of gap "
        f"that broke sprint 004 ticket 005's bench checkpoint. "
        f"command: {' '.join(cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
