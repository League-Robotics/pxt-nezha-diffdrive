"""tests/host/test_protocol_stack_canary_source_pin.py -- pins the
stack-canary fill scaffold in src/comms/protocol.cpp (the measurement
scaffold a paired hardware bench session needs).

**What this is NOT.** Source-text pinning, the same precedent
test_staged_stop_source_pin.py and test_run_abort_source_pin.py
document: `tests/host/` cannot compile `protocol.cpp` at all (it
includes `pxt.h`, directly and transitively), so this proves the
source SHAPE is present and correctly gated, not that the fill loop
behaves correctly against a real CODAL fiber's stack on real hardware.
No host test can prove that; only a pyOCD read against a real board
can, and that is the paired hardware session's own job.

**What this fixes.** `Protocol::run()` -- the protocol fiber's entry
point -- gained `paintStackCanary()`, a debug-build-only fill of this
fiber's own currently-unused stack region with a fixed byte pattern,
so an offline memory read can later find the deepest point any call in
the fiber's own call chain actually reached. It must:
  - be gated behind the SAME macro the existing fault-forensics code in
    nezha_port.cpp already uses, so a normal build compiles a no-op and
    a debug bench build compiles the real fill;
  - run as literally the first statement of run(), before this fiber's
    own frame grows any deeper than it has to.

Run with::

    uv run pytest tests/host/test_protocol_stack_canary_source_pin.py
"""
import pathlib
import re

# tests/host/test_protocol_stack_canary_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_NEZHA_PORT_CPP = _REPO_ROOT / "src" / "platform" / "nezha_port.cpp"

_SOURCE = _PROTOCOL_CPP.read_text()


def _between(text, start_marker, end_marker, label):
    start = text.find(start_marker)
    assert start != -1, f"{label}: start marker {start_marker!r} not found"
    end = text.find(end_marker, start)
    assert end != -1, f"{label}: end marker {end_marker!r} not found after start"
    return text[start:end]


def test_fault_forensics_macro_gates_both_files_identically():
    """The gating macro protocol.cpp uses for paintStackCanary() must be
    the SAME one nezha_port.cpp already uses for its own debug-only
    fault-spin forensics -- one macro, one meaning ("this is a bench
    forensics build"), not two independent flags that can drift apart."""
    nezha_source = _NEZHA_PORT_CPP.read_text()
    nezha_macros = set(re.findall(r"#ifdef\s+(DIFFDRIVE_\w+)", nezha_source))
    assert nezha_macros, "nezha_port.cpp: no #ifdef DIFFDRIVE_* macro found at all"
    protocol_macros = set(re.findall(r"#ifdef\s+(DIFFDRIVE_\w+)", _SOURCE))
    assert protocol_macros, "protocol.cpp: no #ifdef DIFFDRIVE_* macro found at all"
    shared = nezha_macros & protocol_macros
    assert shared, (
        f"protocol.cpp's gating macro(s) {protocol_macros} share none with "
        f"nezha_port.cpp's {nezha_macros} -- paintStackCanary() must reuse "
        f"the existing forensics-build flag"
    )


def test_paint_stack_canary_is_a_noop_outside_the_gated_branch():
    """Outside the `#ifdef`, paintStackCanary() must be a plain empty
    function -- a normal build must never run any fill loop, not even a
    cheap one."""
    ifdef_pos = _SOURCE.find("#ifdef DIFFDRIVE_FAULT_SPIN")
    assert ifdef_pos != -1, "protocol.cpp: no #ifdef DIFFDRIVE_FAULT_SPIN found"
    else_pos = _SOURCE.find("#else", ifdef_pos)
    assert else_pos != -1, "protocol.cpp: no matching #else found"
    endif_pos = _SOURCE.find("#endif", else_pos)
    assert endif_pos != -1, "protocol.cpp: no matching #endif found"
    else_branch = _SOURCE[else_pos:endif_pos]
    assert re.search(
        r"void\s+Protocol::paintStackCanary\s*\(\s*\)\s*\{\s*\}", else_branch
    ), (
        f"protocol.cpp: the #else branch's paintStackCanary() is not an "
        f"empty no-op:\n{else_branch}"
    )


def test_paint_stack_canary_fills_between_stack_bottom_and_the_local_ceiling():
    """The gated (real) branch must read the CURRENT fiber's own
    stack_bottom/stack_top (currentFiber, the same CODAL global
    defaultCurrentFiber() already reaches) and must clamp its fill
    ceiling to a value no higher than the running call's own frame, so
    it can never overwrite memory this very call is still using."""
    body = _between(
        _SOURCE,
        "#ifdef DIFFDRIVE_FAULT_SPIN",
        "#else",
        "protocol.cpp DIFFDRIVE_FAULT_SPIN branch",
    )
    assert "currentFiber->stack_bottom" in body, (
        f"paintStackCanary(): does not read currentFiber->stack_bottom:\n{body}"
    )
    assert "currentFiber->stack_top" in body, (
        f"paintStackCanary(): does not read currentFiber->stack_top:\n{body}"
    )
    assert re.search(r"if\s*\(\s*ceiling\s*<\s*high\s*\)\s*high\s*=\s*ceiling\s*;", body), (
        f"paintStackCanary(): does not clamp its fill ceiling below the "
        f"caller's own frame -- this would let the fill loop overwrite "
        f"memory the running call is still using:\n{body}"
    )


def test_run_calls_paint_stack_canary_as_its_first_statement():
    """paintStackCanary() must run before anything else in run() -- the
    whole point is to paint the fiber's stack while its own frame is as
    shallow as it will ever be."""
    m = re.search(r"void\s+Protocol::run\s*\(\s*\)\s*\{", _SOURCE)
    assert m, "protocol.cpp: Protocol::run() not found"
    # First non-comment, non-blank statement after the opening brace.
    tail = _SOURCE[m.end():]
    for raw_line in tail.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        assert line == "paintStackCanary();", (
            f"Protocol::run(): first statement is {line!r}, expected "
            f"paintStackCanary() to run before anything else"
        )
        break
