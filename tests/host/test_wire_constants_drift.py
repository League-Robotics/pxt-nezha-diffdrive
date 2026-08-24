"""tests/host/test_wire_constants_drift.py -- sprint 008 ticket 002:
recurrence guards for four independent instances of the SAME failure
mode (code review 2026-08-23, R-17 + R-21 -- WIRE-01, MOD-01, BLK-09,
WIRE-05, MOD-05): a hand-mirrored constant with nothing but a comment
enforcing agreement between two files. Every one of the four had
already drifted by the time the review found it:

1. **kVersion** (`protocol.cpp`) hardcoded "1.0.0" beside a "keep in
   sync with pxt.json" comment while `pxt.json` had moved to "1.0.10"
   -- ten bumps drifted, misreporting the build on every ID/VER wire
   reply and defeating the mbdeploy -> VER deploy-verification flow.
2. **The line cap**: `emitLine()` clipped at a bare `200` while
   `SerialTransport::kMaxLineBytes` had been raised to `240` (sprint
   004 ticket 005); `radio_transport.h`'s own doc comment kept
   claiming its cap "equals" that bound after the raise made that
   false.
3. **RUN_EVENT_SOURCE / kRunEventSource**: `0x2001` hand-typed
   independently in `main.ts` and `protocol.cpp`.
4. **kDiag\\* ordinals**: `wire_adapter.cpp`'s named `kDiagXxx`
   constants and `shims.cpp`'s `diagValue()` switch encode the same
   ordinal -> meaning mapping in two independently maintained places.

**Why these are text-based, not compiled, drift tests.** Three of the
four files involved -- `protocol.cpp`, `main.ts`, and (transitively,
via `pxt.h`) `shims.cpp` -- are outside tests/host/'s compile reach by
construction (src/DESIGN.md S1's layering table: `protocol.cpp`
includes `pxt.h` via `platform_ports.h`; `shims.cpp` is CODAL-bound
throughout; `main.ts` is TypeScript, not even the same language). This
is the ticket in this sprint with the largest gap between "host tests
pass" and "target-build evidence" -- see this repo's own build-
checkpoint ticket for the only thing that proves these files still
compile/link for the robot. A drift test that reads the relevant
source files as plain text and compares literals needs no compiler
invocation and no CODAL toolchain, which is exactly what makes it
possible to cover these four pairs from a desktop host at all -- the
same shape `test_pxt_manifest_completeness.py` already uses for
`pxt.json` vs `src/`'s file listing, and the same technique the
issue's own "What to do" section names explicitly ("a host test can
read main.ts as text if need be -- cheap and effective").

`radio_transport.h` (unlike `radio_transport.cpp`) does NOT itself
include `pxt.h` -- its public interface declares no CODAL types, only
`<cstddef>`/`<cstdint>` -- so `kMaxPayloadBytes`'s value could in
principle be pinned by a compiled `static_assert` the way
`heading_wrap.h`/`encoder_glitch_armor.h` are covered by
`test_cxx11_syntax_gate.py`. That gate's own top-of-file comment,
however, explicitly says "Do NOT extend this to ... radio_transport.
{h,cpp} ..." as a deliberate, previously-reviewed scope boundary (on
the mistaken premise that the header itself includes `pxt.h`, which it
does not -- see this ticket's own completion notes for that
correction). Widening an existing, deliberately-scoped gate is a
choice that deserves its own review, not something to fold into this
ticket opportunistically -- so this file pins `kMaxPayloadBytes` the
same text-based way as the other three pairs instead.

Run with::

    uv run pytest tests/host/test_wire_constants_drift.py
"""

import json
import pathlib
import re

# tests/host/test_wire_constants_drift.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_PXT_JSON = _REPO_ROOT / "pxt.json"


def _read(name):
    return (_SRC_DIR / name).read_text()


# ---------------------------------------------------------------------------
# 1. kVersion (protocol.cpp) vs pxt.json's "version" -- WIRE-01/MOD-01/
#    BLK-09/R-17.
# ---------------------------------------------------------------------------


def _pxt_json_version():
    manifest = json.loads(_PXT_JSON.read_text())
    return manifest["version"]


def _protocol_cpp_k_version():
    text = _read("protocol.cpp")
    match = re.search(r'constexpr const char\*\s*kVersion\s*=\s*"([^"]*)"', text)
    assert match, "protocol.cpp's kVersion declaration was not found by this test's regex"
    return match.group(1)


def test_k_version_matches_pxt_json_version():
    """protocol.cpp's kVersion literal, reported on every ID/VER wire
    reply, must match pxt.json's "version" field exactly. This constant
    had drifted ten pxt.json version bumps behind its own "keep in sync"
    comment (1.0.0 vs 1.0.10) with nothing catching it -- this test is
    what now catches a forgotten bump immediately instead of silently,
    restoring the mbdeploy -> VER deploy-verification flow's own
    precondition (a host actually learns which build it is talking to)."""
    pxt_version = _pxt_json_version()
    wire_version = _protocol_cpp_k_version()
    assert wire_version == pxt_version, (
        f"protocol.cpp's kVersion (\"{wire_version}\") has drifted from "
        f"pxt.json's \"version\" (\"{pxt_version}\") -- every ID/VER wire "
        f"reply now misreports the build. Update protocol.cpp's kVersion "
        f"to match pxt.json's version (this project's C++ build has no "
        f"build-time substitution mechanism, so this is a manual edit, "
        f"not a generated file)."
    )


# ---------------------------------------------------------------------------
# 2. emitLine()'s line cap vs RadioTransport::kMaxPayloadBytes --
#    WIRE-05/R-21.
# ---------------------------------------------------------------------------


def _radio_transport_max_payload_bytes():
    text = _read("radio_transport.h")
    match = re.search(r"kMaxPayloadBytes\s*=\s*(\d+)", text)
    assert match, "radio_transport.h's kMaxPayloadBytes declaration was not found"
    return int(match.group(1))


def _radio_transport_max_payload_bytes_is_public():
    text = _read("radio_transport.h")
    # Walk the class body's access-specifier sections in declaration
    # order and report which one kMaxPayloadBytes's declaration falls
    # under -- the same "which section owns this line" check a reviewer
    # would do by eye, done here so a future edit that moves the
    # declaration back under `private:` (or introduces a new `private:`
    # between the two) fails loudly instead of silently.
    class_match = re.search(
        r"class RadioTransport \{(.*)\};", text, re.DOTALL
    )
    assert class_match, "RadioTransport class body was not found"
    body = class_match.group(1)
    current_access = "private"  # C++ default for `class`, before any label
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "public:":
            current_access = "public"
        elif stripped == "private:":
            current_access = "private"
        elif "kMaxPayloadBytes" in stripped and "=" in stripped:
            return current_access
    raise AssertionError("kMaxPayloadBytes declaration line was not found while walking the class body")


def test_radio_max_payload_bytes_is_pinned_at_200():
    """RadioTransport::kMaxPayloadBytes is radio's real on-air capacity
    ceiling (sprint 010's scope owns raising it, not this ticket) --
    pin the value here so a future edit that changes it is a deliberate,
    reviewed decision rather than an accidental one."""
    assert _radio_transport_max_payload_bytes() == 200, (
        "RadioTransport::kMaxPayloadBytes changed from the pinned value "
        "200 -- if this is a deliberate capacity change (sprint 010's "
        "scope), update this pinned test too; if not, it's a regression."
    )


def test_radio_max_payload_bytes_is_public():
    """emitLine() (protocol.cpp) references RadioTransport::
    kMaxPayloadBytes directly, which only compiles if the member is
    public. This is a source-text stand-in for that compile-time fact,
    since protocol.cpp itself is outside tests/host/'s compile reach
    (it includes pxt.h transitively via protocol.h -> platform_ports.h)
    -- see src/DESIGN.md S1. A regression back to `private` here would
    otherwise only be caught at the next real target build."""
    assert _radio_transport_max_payload_bytes_is_public() == "public", (
        "RadioTransport::kMaxPayloadBytes is no longer public -- "
        "protocol.cpp's Protocol::emitLine() references it by name and "
        "would fail to compile against a private member."
    )


def test_emit_line_clips_to_shared_constant_not_a_bare_literal():
    """protocol.cpp's emitLine() must clip to RadioTransport::
    kMaxPayloadBytes by name, not to a re-declared bare integer literal
    -- the exact defect (a bare `200` that silently stopped matching
    what the transports actually carry) this ticket fixes. Scoped to
    the emitLine() function body specifically, not the whole file, so
    an unrelated `200` elsewhere in protocol.cpp can't produce a false
    pass or false failure."""
    text = _read("protocol.cpp")
    match = re.search(
        r"void Protocol::emitLine\(const char\* text\) \{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert match, "Protocol::emitLine() body was not found in protocol.cpp"
    body = match.group(1)
    assert "RadioTransport::kMaxPayloadBytes" in body, (
        "Protocol::emitLine() no longer references "
        "RadioTransport::kMaxPayloadBytes by name -- this is the fix "
        "this ticket makes; a bare literal here can silently drift from "
        "the transports' real caps again exactly as it did before."
    )
    # No standalone bare-200 (or other bare integer) length-comparison
    # literal should remain in the clip loop itself.
    clip_loop = re.search(r"while \(text\[len\][^;]*;", body)
    assert clip_loop, "emitLine()'s length-clip while-loop was not found"
    assert "200" not in clip_loop.group(0), (
        "emitLine()'s clip loop still contains a bare 200 literal "
        "alongside the named constant -- single-source the cap, don't "
        "duplicate it."
    )


def test_radio_transport_doc_comment_states_tighter_not_equal():
    """radio_transport.h's doc comment for kMaxPayloadBytes must state
    the true relationship to SerialTransport's cap (deliberately
    tighter) and must no longer claim the two are "equal" or "the
    same" -- that claim went false the moment sprint 004 ticket 005
    raised SerialTransport::kMaxLineBytes to 240 while this constant
    stayed 200 (WIRE-05/R-21)."""
    text = _read("radio_transport.h")
    assert "sized the same as serialtransport" not in text.lower(), (
        "radio_transport.h still claims parity with SerialTransport's "
        "bound -- false since sprint 004 ticket 005 raised "
        "SerialTransport::kMaxLineBytes to 240 while this constant "
        "stayed 200."
    )
    assert "tighter" in text.lower(), (
        "radio_transport.h's doc comment should state that "
        "kMaxPayloadBytes is deliberately the tighter of the two "
        "transports' caps, not merely that it is unchanged."
    )


# ---------------------------------------------------------------------------
# 3. RUN_EVENT_SOURCE (main.ts) vs kRunEventSource (protocol.cpp) --
#    WIRE-01-adjacent minor, R-21/MOD-05.
# ---------------------------------------------------------------------------


def _main_ts_run_event_source():
    text = (_SRC_DIR / "main.ts").read_text()
    match = re.search(r"const RUN_EVENT_SOURCE\s*=\s*(0x[0-9a-fA-F]+|\d+)", text)
    assert match, "main.ts's RUN_EVENT_SOURCE declaration was not found"
    return int(match.group(1), 0)


def _protocol_cpp_k_run_event_source():
    text = _read("protocol.cpp")
    match = re.search(r"constexpr int kRunEventSource\s*=\s*(0x[0-9a-fA-F]+|\d+)", text)
    assert match, "protocol.cpp's kRunEventSource declaration was not found"
    return int(match.group(1), 0)


def test_run_event_source_matches_between_main_ts_and_protocol_cpp():
    """main.ts's RUN_EVENT_SOURCE and protocol.cpp's kRunEventSource are
    two independently hand-typed copies of the same custom MessageBus
    event source id -- the C++ side raises it (Protocol::handleRun()),
    the TS side listens for it (wireRunDispatch()'s control.onEvent()
    call), and nothing but a comment in each file has ever kept them
    aligned. No shared-constant mechanism crosses the TS/C++ boundary in
    this project, so this drift test (reading both files as plain text)
    is the fix, not single-sourcing."""
    ts_value = _main_ts_run_event_source()
    cpp_value = _protocol_cpp_k_run_event_source()
    assert ts_value == cpp_value, (
        f"main.ts's RUN_EVENT_SOURCE (0x{ts_value:x}) and protocol.cpp's "
        f"kRunEventSource (0x{cpp_value:x}) have diverged -- the C++ "
        f"RUN bridge (Protocol::handleRun()) and the TS dispatcher "
        f"(wireRunDispatch()) would no longer agree on which MessageBus "
        f"event carries a RUN command's payload slot."
    )


# ---------------------------------------------------------------------------
# 4. wire_adapter.cpp's kDiag* ordinals vs shims.cpp's diagValue()
#    switch -- MOD-05 (spot-checked in the code review, same pattern as
#    R-17/R-21).
#
# Design choice, per this ticket's own Design Rationale: prefer a drift
# test of this shape over restructuring shims.cpp to #include
# wire_adapter.h for the shared constants. That coupling is a legitimate
# option under src/DESIGN.md S1's layering table (shims.cpp is the
# composition root and may depend on everything -- nothing there
# forbids it) but is a real design choice deserving its own review, not
# something to fold into this Minor's execution. A drift test closes the
# same gap without taking on that review.
#
# Scope note: the acceptance criterion's own phrasing groups
# shims.cpp's diagValue()/setKernelValue() switches together, but
# source inspection (this ticket's own execution) shows they are NOT
# the same ordinal space: setKernelValue()'s switch (and its
# getConfigValue() counterpart) encodes the wire's ConfigField ordinals
# (0-17, e.g. case 2 == pid_kp), which wire_adapter.cpp already names
# via a SEPARATE, existing {name, ordinal} table with its own
# ConfigField-referencing comments (kFields, wire_adapter.cpp ~line
# 106-154) -- an already-addressed, unrelated drift surface. The kDiag*
# named constants (wire_adapter.cpp ~line 184-209) only overlap with
# diagValue()'s switch (shims.cpp), which is what this test pins.
# ---------------------------------------------------------------------------

# Pinned snapshot of wire_adapter.cpp's kDiag* constants: the ordinal
# each name is bound to, AND the (normalized, substring-matched) token
# each ordinal's shims.cpp diagValue() case body must read from --
# extracted from both files as of this ticket. A change to either side
# without updating this pin, or a divergence between the two files
# themselves, fails one of the two tests below.
_KDIAG_ORDINALS = {
    "kDiagReady": 0,
    "kDiagEstopped": 1,
    "kDiagStallHalted": 2,
    "kDiagLeaseExpired": 3,
    "kDiagConnLeft": 4,
    "kDiagConnRight": 5,
    "kDiagWedgeLeft": 6,
    "kDiagWedgeRight": 7,
    "kDiagI2cFault": 8,
    "kDiagLeaseExpiryCount": 9,
    "kDiagPositionLeft": 10,
    "kDiagPositionRight": 11,
    "kDiagAppliedDutyLeft": 12,
    "kDiagAppliedDutyRight": 13,
    "kDiagVelocityLeft": 14,
    "kDiagVelocityRight": 15,
    "kDiagCycleCount": 16,
    "kDiagCycleOverrunCount": 19,
    "kDiagWrongWayCount": 25,
}

# Per-ordinal token expected to appear on shims.cpp diagValue()'s
# matching `case N:` line (or the following line, for the multi-line
# case bodies) -- ties each kDiag* NAME to the specific kernel/engine
# field shims.cpp actually reads for it, not merely to a matching
# ordinal number (which alone would not catch two cases being swapped).
_KDIAG_EXPECTED_TOKEN = {
    0: "out.ready",
    1: "out.estopped",
    2: "out.stallHalted",
    3: "out.leaseExpired",
    4: "out.connectedLeft",
    5: "out.connectedRight",
    6: "out.wedgeSuspectLeft",
    7: "out.wedgeSuspectRight",
    8: "out.i2cFaultCount",
    9: "out.leaseExpiryCount",
    10: "out.positionLeft",
    11: "out.positionRight",
    12: "out.appliedDutyLeft",
    13: "out.appliedDutyRight",
    14: "out.velocityLeft",
    15: "out.velocityRight",
    16: "out.cycleCount",
    19: "out.cycleOverrunCount",
    25: "wrongWayCount",
}


def _wire_adapter_kdiag_ordinals():
    text = _read("wire_adapter.cpp")
    return {
        name: int(value)
        for name, value in re.findall(
            r"constexpr int (kDiag\w+)\s*=\s*(\d+);", text
        )
    }


def _shims_cpp_diag_value_body():
    text = _read("shims.cpp")
    match = re.search(
        r"int diagValue\(int what\) \{(.*?)\n\}", text, re.DOTALL
    )
    assert match, "shims.cpp's diagValue() function body was not found"
    return match.group(1)


def _shims_cpp_diag_value_cases():
    """Maps each `case N:` in diagValue()'s switch to the source text of
    that case (through the next `case`/`default`), so a token can be
    searched for within just that case's own body."""
    body = _shims_cpp_diag_value_body()
    cases = {}
    matches = list(re.finditer(r"case (\d+):", body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        cases[int(m.group(1))] = body[start:end]
    return cases


def test_wire_adapter_kdiag_constants_match_pinned_snapshot():
    """wire_adapter.cpp's kDiag* named constants must exactly match this
    test's pinned snapshot (name -> ordinal). If this fails because
    wire_adapter.cpp legitimately changed, update BOTH this dict and
    _KDIAG_EXPECTED_TOKEN together, deliberately -- that is the "shared
    named constants ... documented in this ticket's own notes" choice
    point the acceptance criteria call for."""
    actual = _wire_adapter_kdiag_ordinals()
    assert actual == _KDIAG_ORDINALS, (
        f"wire_adapter.cpp's kDiag* constants have changed from this "
        f"test's pinned snapshot.\npinned:  {_KDIAG_ORDINALS}\n"
        f"actual:  {actual}"
    )


def test_shims_cpp_diag_value_switch_matches_kdiag_ordinals():
    """Every kDiag* ordinal wire_adapter.cpp names must have a matching
    `case N:` in shims.cpp's diagValue() switch that reads the SAME
    field this ticket's pinned token map expects -- catching both an
    ordinal shims.cpp no longer implements (wire_adapter.cpp would
    silently always read 0 for it) and two cases' bodies being swapped
    (the ordinal survives, but the meaning doesn't) -- the same
    ordinal-to-meaning-mapping-in-two-places pattern the other three
    pairs in this file guard against."""
    cases = _shims_cpp_diag_value_cases()
    missing_case = []
    wrong_token = []
    for name, ordinal in _KDIAG_ORDINALS.items():
        expected_token = _KDIAG_EXPECTED_TOKEN[ordinal]
        if ordinal not in cases:
            missing_case.append((name, ordinal))
            continue
        if expected_token not in cases[ordinal]:
            wrong_token.append((name, ordinal, expected_token))
    assert not missing_case, (
        f"wire_adapter.cpp names kDiag* ordinal(s) with no matching "
        f"`case N:` in shims.cpp's diagValue() switch: {missing_case} "
        f"-- these would silently always read 0."
    )
    assert not wrong_token, (
        f"shims.cpp's diagValue() switch case(s) no longer read the "
        f"field wire_adapter.cpp's kDiag* name expects at that ordinal "
        f"(name, ordinal, expected token): {wrong_token} -- the ordinal "
        f"numbers still line up, but the meaning behind them has "
        f"drifted, e.g. from two cases' bodies being reordered."
    )
