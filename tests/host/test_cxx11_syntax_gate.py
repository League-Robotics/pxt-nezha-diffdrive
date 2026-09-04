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
(src/comms/wire_handler.h, ticket 004) are legal C++20 but disqualify it from
being a C++11 aggregate -- so the ~20 `columns_[i++] = {...}`
brace-assignment sites in WireAdapter::buildSnapshot()
(src/comms/wire_adapter.cpp) compiled clean against 253 passing host tests
while being uncompilable for the actual robot. This test would have
caught that before it cost a bench checkpoint to surface.

**Scope, deliberately narrow**: originally exactly the four production
files already known to have no pxt.h/CODAL dependency (confirmed by
repo grep and by their own header comments) -- the same four files
test_kernel_harness.py's own compile_shared_lib() already compiles
successfully at -std=c++20. This only adds a SECOND, syntax-only
compile of the identical files at the target's real standard:
`-fsyntax-only` needs no `-shared -fPIC -o`, no shim, and no link step.
Do NOT extend this to protocol.{h,cpp}, radio_transport.{h,cpp},
serial_transport.{h,cpp}, shims.cpp, nezha_port.{h,cpp}, or
otos_port.{h,cpp} -- all of those include pxt.h (directly or
transitively via platform_ports.h) and cannot be syntax-checked without
the CODAL toolchain, which this repo's host suite does not have.

**Sprint 006** widens this scope in one specific way: new host-portable
*helper headers* extracted from an otherwise pxt.h-bound module (the
same extraction pattern `EncoderGlitchArmor`/`heading_wrap.h` use --
see src/DESIGN.md S1/S11) get covered here too, each via its own small
dedicated syntax-check translation unit under tests/host/ (a header has
no natural .cpp of its own the way motion_engine.h rides along with
motion_engine.cpp). `heading_wrap.h` (ticket 004) is the first of
these, via `heading_wrap_syntax_check.cpp`. This does not narrow the
gap above: the actual call sites (`otos_port.cpp`, `nezha_port.cpp`,
`shims.cpp`) still include pxt.h and stay outside this gate entirely --
only the extracted, dependency-free math is covered.

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
_TEST_DIR = pathlib.Path(__file__).resolve().parent

# The original fixed four-file list this ticket's own sizing note
# required -- not a moving target, and not "everything under src/".
# Each of these is confirmed host-portable (no pxt.h, directly or
# transitively) by its own header comment and by
# test_kernel_harness.py's existing -std=c++20 compile of the same
# files.
_CXX11_PORTABLE_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "comms" / "wire_handler.cpp",
    _SRC_DIR / "comms" / "wire_adapter.cpp",
    # WiFi transport (2026-09-02): the Ai-WB2-12F AT state machine is
    # host-portable by construction (see src/comms/wifi_link.h) -- only
    # wifi_uart.cpp, its NRF_UARTE1 byte pipe, includes pxt.h.
    _SRC_DIR / "comms" / "wifi_link.cpp",
    # Sprint 006 ticket 004: heading_wrap.h has no pxt.h dependency (it
    # is the extracted, host-portable half of OtosPort::setPose()'s
    # heading-wrap fix -- see src/core/heading_wrap.h's own header comment)
    # but no natural .cpp of its own, so this dedicated translation
    # unit exists solely to give this gate something to compile.
    _TEST_DIR / "heading_wrap_syntax_check.cpp",
    # Sprint 006 ticket 005: encoder_glitch_armor.h has no pxt.h
    # dependency (it is the extracted, host-portable half of
    # NezhaMotorPort::collect()'s rebaseline-on-discontinuity fix --
    # see src/core/encoder_glitch_armor.h's own header comment) but no
    # natural .cpp of its own, so this dedicated translation unit
    # exists solely to give this gate something to compile.
    _TEST_DIR / "encoder_glitch_armor_syntax_check.cpp",
    # Sprint 006 ticket 007: encoder_pose_source.h has no pxt.h
    # dependency (it depends only on motion_engine.h, itself already
    # covered above via motion_engine.cpp) but no natural .cpp of its
    # own, so this dedicated translation unit exists solely to give
    # this gate something to compile.
    _TEST_DIR / "encoder_pose_source_syntax_check.cpp",
    _TEST_DIR / "run_queue_syntax_check.cpp",
    # emit_queue.h has no pxt.h dependency (a host-portable outbound-
    # line ring for the protocol's single-serial/radio-producer
    # restructuring -- see src/comms/emit_queue.h's own header comment)
    # but no natural .cpp of its own, so this dedicated translation
    # unit exists solely to give this gate something to compile.
    _TEST_DIR / "emit_queue_syntax_check.cpp",
    # Sprint 029 ticket 002 (motion profile unification): motion_limits.h
    # has no pxt.h dependency (a host-portable value object -- see its
    # own header comment) but no natural .cpp of its own, so this
    # dedicated translation unit exists solely to give this gate
    # something to compile.
    _TEST_DIR / "motion_limits_syntax_check.cpp",
    # velocity_shaper.cpp has no pxt.h dependency (host-portable --
    # see its own header comment) and, unlike motion_limits.h/the
    # syntax-check-only headers above, has a natural .cpp of its own,
    # so it is compiled directly, the same way motion_engine.cpp is.
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
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
