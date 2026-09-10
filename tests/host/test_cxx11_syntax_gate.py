"""Both real targets compile at -std=c++11; the host suite uses c++20.
Syntax-check the host-portable sources at c++11 so a C++14+ construct
fails here, not at the hex checkpoint.

The list below is deliberate, not "everything under src/": a file
qualifies only if it reaches no `pxt.h` (directly or transitively via
platform_ports.h). A header with no natural `.cpp` of its own is
covered through a dedicated `*_syntax_check.cpp` translation unit in
this directory. The eight `pxt.h`-bound `.cpp` files nothing here can
compile, and what gates them instead, are named in tests/DESIGN.md
"Translation units nothing on the host compiles"; that list is held
against the tree by test_pxt_bound_exclusion_is_current.py.

Include policy matches compile_shared_lib() (test_kernel_harness.py):
production `src/` files get NO `-I`, exactly as the real PXT build
resolves them; only this directory's own syntax-check TUs -- host-only
scaffolding the real build never sees -- get `-I src` so they can reach
into `src/` at all.

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
    # motion/odometry.h has no pxt.h dependency (it depends only on
    # motion_engine.h, itself already covered above via
    # motion_engine.cpp) but no natural .cpp of its own, so this
    # dedicated translation unit exists solely to give this gate
    # something to compile. Replaced encoder_pose_source_syntax_check.cpp
    # when Odometry absorbed EncoderPoseSource (sprint 033 ticket 002).
    _TEST_DIR / "odometry_syntax_check.cpp",
    _TEST_DIR / "run_queue_syntax_check.cpp",
    # comms/run_bridge.cpp has no pxt.h dependency (the cleartext RUN
    # bridge's sanitize/dedupe/park rules, extracted out of the
    # pxt.h-bound protocol.cpp -- see src/comms/run_bridge.h's own
    # header comment) and, like velocity_shaper.cpp below, has a natural
    # .cpp of its own, so it is compiled directly rather than through a
    # dedicated syntax-check translation unit.
    _SRC_DIR / "comms" / "run_bridge.cpp",
    # comms/run_registry.cpp has no pxt.h dependency (the C++ mirror of
    # the block program's own onRun() registrations, which the FUNCS
    # wire verb enumerates -- see src/comms/run_registry.h's own header
    # comment) and, like run_bridge.cpp above, has a natural .cpp of its
    # own, so it is compiled directly. The dedicated syntax-check unit
    # beside it covers the header's TEMPLATE, which that .cpp only
    # instantiates once.
    _SRC_DIR / "comms" / "run_registry.cpp",
    _TEST_DIR / "run_registry_syntax_check.cpp",
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
    # Sprint 030 ticket 001 (bus-ownership guard): bus_guard.h has no
    # pxt.h dependency (it depends only on diffdrive.h, itself already
    # covered above via diffdrive.cpp) but no natural .cpp of its own,
    # so this dedicated translation unit exists solely to give this
    # gate something to compile.
    _TEST_DIR / "bus_guard_syntax_check.cpp",
    # Sprint 030 ticket 002 (fiber-identity check + kBlock motion
    # owner): motion_owner.h and fiber_identity.h have no pxt.h
    # dependency (both are pure headers with no CODAL type -- see their
    # own header comments) but no natural .cpp of their own, so these
    # dedicated translation units exist solely to give this gate
    # something to compile.
    _TEST_DIR / "motion_owner_syntax_check.cpp",
    _TEST_DIR / "fiber_identity_syntax_check.cpp",
    # comms/config_fields.h has no pxt.h dependency (it is the wire's
    # config-name/ordinal table and nothing else -- see its own header
    # comment) but no natural .cpp of its own, so this dedicated
    # translation unit exists solely to give this gate something to
    # compile. wire_adapter.cpp, above, also includes it.
    _TEST_DIR / "config_fields_syntax_check.cpp",
    # comms/transport_sink.h has no pxt.h dependency (the one Wire::Sink
    # every transport is reached through, plus the terminator decision
    # it makes -- see its own header comment) but no natural .cpp of its
    # own, so this dedicated translation unit exists solely to give this
    # gate something to compile. It instantiates the template, since a
    # class template that merely parses is not one that compiles.
    _TEST_DIR / "transport_sink_syntax_check.cpp",
    # comms/radio_transport.h is otherwise a pxt.h-bound module's
    # header, but two things in it are the extracted-helper exception
    # above: radioRxLineFits() and radioRxClassify()/RadioRxCounters,
    # the RX path's whole accept/drop decision and its counters. Their
    # one real call site (onDatagram()) is CODAL-bound, so this
    # translation unit is the only thing standing between them and a
    # construct that is legal at the host suite's C++20 and not at the
    # target's C++11.
    _TEST_DIR / "radio_rx_classify_syntax_check.cpp",
    # Sprint 038 ticket 002 (flash-backed WiFi credential store):
    # comms/wifi_credential_store.cpp has no pxt.h dependency -- it
    # reaches only platform/wifi_flash_port.h (the abstract seam, itself
    # host-portable; the CODAL-coupled implementation is
    # platform/wifi_flash_port.cpp, excluded below, tests/DESIGN.md) --
    # and has a natural .cpp of its own, so it is compiled directly.
    _SRC_DIR / "comms" / "wifi_credential_store.cpp",
]


@pytest.mark.parametrize(
    "source", _CXX11_PORTABLE_SOURCES, ids=lambda p: p.name
)
def test_host_portable_source_compiles_at_cxx11(source):
    """A -std=c++11 -fsyntax-only compile of one host-portable source
    file must succeed -- the exact standard both real embedded build
    targets use, and nine language-standard versions below
    tests/host/'s own -std=c++20. No -shared/-fPIC/-o and no shim: a
    syntax-only check needs neither a link step nor fake ports.

    A production `src/` source is compiled with NO `-I`, the way the
    real PXT build resolves it (compile_shared_lib() draws the same
    line, and test_include_paths_match_target.py enforces the rule
    over the whole tree). Only this directory's own syntax-check TUs
    get `-I src`: they are host-only scaffolding nothing under `src/`
    includes, and without a search path they cannot name a `src/`
    header at all."""
    is_production_source = source.resolve().is_relative_to(_SRC_DIR.resolve())
    cmd = ["/usr/bin/c++", "-std=c++11", "-fsyntax-only"]
    if not is_production_source:
        cmd += ["-I", str(_SRC_DIR)]
    cmd += [str(source)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{source.name} fails to compile at -std=c++11 (the real "
        f"embedded target standard) though it compiles at -std=c++20 "
        f"(tests/host/'s standard) -- this is the exact class of gap "
        f"that broke sprint 004 ticket 005's bench checkpoint. "
        f"command: {' '.join(cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
