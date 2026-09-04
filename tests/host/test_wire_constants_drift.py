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

**Sprint 019's mirrored-constant sweep** (`duplicated-constants-across-
the-shim-boundary.md`) extended this file with five more guarded
cases, closing the loop this file's own docstring predicted --
"every mirrored constant gets a drift test, or gets merged":

5. **kCdegToRad / kRadToCdeg** (`shims.cpp`): a MERGE, not a
   cross-file drift test -- see that section below for why it is a
   single-file regression guard instead.
6. **`defaultCruise_`'s seed comment** (`shims.cpp`) vs
   `defaultSpeed` (`blocks/motion.ts`): NOT merged (the two are
   independently settable by design -- one a wire sentinel default,
   the other a block-layer move speed) -- the fix was correcting a
   comment that asserted an unmaintained "match" as fact. Guarded by
   pinning what the corrected comment must (and must not) say.
7. **The 24 ms tick cadence**: `shims.cpp`'s `cfg.cyclePeriod = 24`
   vs `blocks/sim.ts`'s `kSimTickPeriod = 24` -- two independently
   editable copies of the same fiber/tick period, one per language,
   with no shared boundary to merge them across.
8. **`trackWidth` / `rotationalSlip`**: `motion_engine.h`'s
   `trackWidth_`/`rotationalSlip_` defaults vs
   `docs/design/specification.md`'s constants table -- code vs. doc,
   not mergeable, guarded the same way `kVersion` guards code vs.
   `pxt.json`.
9. **`ConfigField` ordinals**: `blocks/motion.ts`'s `ConfigField` TS
   enum vs `wire_adapter.cpp`'s `kFields` name/ordinal table vs
   `shims.cpp`'s `setKernelValue()`/`getConfigValue()` switches --
   the same "ordinal -> meaning mapping in two-or-more independently
   maintained places" pattern case 4 above already guards for
   `kDiag*`, found by this sweep to also apply here and previously
   unguarded (case 4's own docstring had explicitly flagged this as
   "an already-addressed, unrelated drift surface" -- it was named,
   not yet fixed, until now).

Two more constants this same sweep found are deliberately NOT guarded
here:

- **`travelCalib`** (0.7878 mm/deg): tracked by sprint 017 ticket 002
  (`tests/tools/test_travel_calib_drift.py` guards the one remaining
  live mirror, `tools/tour_chart.py`'s `--travel-calib` default;
  `tools/tour_watch.py`'s old mirror was deleted outright, and
  `src/DESIGN.md`/`docs/design/specification.md`/
  `docs/design/usecases.md` were verified still consistent) -- listed
  here only so this file's own enumeration is complete, not
  re-implemented.
- **The simulator's yaw-rate divisor** (`blocks/sim.ts:99`'s `/ 115`
  vs hardware's `effectiveTrackWidth()` = 114.2 / 0.952 = 119.96, a
  real ~4.3% VALUE discrepancy, not merely an unguarded-but-correct
  duplicate): asserting equality here would pin something false.
  Tracked as its own issue instead
  (`simulator-yaw-rate-divisor-diverges-from-hardware-track-width.md`).

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
_DOCS_DESIGN_DIR = _REPO_ROOT / "docs" / "design"


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
    text = _read("comms/protocol.cpp")
    match = re.search(r'constexpr const char\*\s*kVersion\s*=\s*"([^"]*)"', text)
    assert match, "protocol.cpp's kVersion declaration was not found by this test's regex"
    return match.group(1)


def test_k_version_is_the_uninjected_placeholder():
    """protocol.cpp's checked-in kVersion must stay a PLACEHOLDER.

    As of 2026-08-27 it is injected at deploy time by
    tools/make_deploy.py's _inject_version(), from pyproject.toml's
    `0.YYYYMMDD.n` build version -- the same scratch-copy-only mechanism
    kProfile and kChannel use. So the literal in the repo is never a
    real build's version, and a hex reporting `unbaked` over VER is a
    hex that did not come through make_deploy.py.

    This REPLACES test_k_version_matches_pxt_json_version. kVersion used
    to mirror pxt.json's `1.0.10`-style EXTENSION semver, and that test
    guarded the mirror. The mirror itself was the problem: the extension
    version moves only on release, so every firmware built between two
    releases answered VER identically. On 2026-08-27 two robots running
    visibly different builds both reported `ver 1.0.10` with nothing on
    the wire able to separate them, and the misdiagnosis cost hours.
    pxt.json's semver is unchanged and still governs MakeCode's
    extension resolution -- it simply is not what VER answers any more.
    """
    wire_version = _protocol_cpp_k_version()
    assert wire_version == "unbaked", (
        f"protocol.cpp's kVersion is \"{wire_version}\", expected the "
        f"placeholder \"unbaked\". A real version baked into the "
        f"checked-in source means a build could ship a stale, "
        f"hand-edited version string instead of the injected one -- the "
        f"exact drift class this file exists to catch."
    )


def test_make_deploy_can_still_find_k_version():
    """The injection is a regex substitution against protocol.cpp's
    text, so it breaks SILENTLY if that declaration's shape changes --
    make_deploy would exit loudly at build time, but only for whoever
    next runs a deploy. This catches it on every host run instead.

    Same "read the other file as text" shape as the rest of this module,
    and the same reason: neither file is in tests/host/'s compile reach.
    """
    make_deploy = (pathlib.Path(__file__).resolve().parents[2]
                   / "tools" / "make_deploy.py").read_text()
    match = re.search(r"_K_VERSION_RE = re\.compile\(\s*\n?\s*r'([^']+)'",
                      make_deploy)
    assert match, (
        "tools/make_deploy.py's _K_VERSION_RE was not found -- if the "
        "version injection was removed, kVersion silently reverts to "
        "shipping the placeholder on every build."
    )
    pattern = re.compile(match.group(1))
    text = _read("comms/protocol.cpp")
    hits = pattern.findall(text)
    assert len(hits) == 1, (
        f"make_deploy.py's _K_VERSION_RE matches {len(hits)} times in "
        f"protocol.cpp, expected exactly 1 -- the injection would "
        f"fail the build (n != 1) or bake the wrong constant."
    )
# ---------------------------------------------------------------------------
# 2. emitLine()'s line cap vs RadioTransport::kMaxPayloadBytes --
#    WIRE-05/R-21.
# ---------------------------------------------------------------------------


def _radio_transport_max_payload_bytes():
    text = _read("comms/radio_transport.h")
    match = re.search(r"kMaxPayloadBytes\s*=\s*(\d+)", text)
    assert match, "radio_transport.h's kMaxPayloadBytes declaration was not found"
    return int(match.group(1))


def _radio_transport_max_payload_bytes_is_public():
    text = _read("comms/radio_transport.h")
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


def test_radio_max_payload_bytes_is_pinned_at_240():
    """RadioTransport::kMaxPayloadBytes is radio's real on-air capacity
    ceiling. Sprint 010 ticket 002 raised it from 200 to 240, closing
    the gap with SerialTransport::kMaxLineBytes / Wire::WireHandler::
    kMaxLineBytes (both already 240) that this same file's test 2 used
    to document as a deliberate inequality -- see
    test_radio_serial_wire_capacity_constants_are_equal_at_240, below,
    for the four-way equality this raise establishes. Pin the value
    here too so a future edit that changes it again is a deliberate,
    reviewed decision rather than an accidental one."""
    assert _radio_transport_max_payload_bytes() == 240, (
        "RadioTransport::kMaxPayloadBytes changed from the pinned value "
        "240 -- if this is a deliberate capacity change, update this "
        "pinned test (and the four-way equality test below) too; if "
        "not, it's a regression."
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
    text = _read("comms/protocol.cpp")
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


def _radio_transport_max_payload_bytes_doc_comment():
    """The block of `//` comment lines directly above kMaxPayloadBytes's
    declaration, so the two tests below can check what this comment
    says without a false pass/fail from unrelated text elsewhere in the
    file (the same "scope the check to one function body" technique
    test_emit_line_clips_to_shared_constant_not_a_bare_literal, above,
    uses for protocol.cpp)."""
    text = _read("comms/radio_transport.h")
    match = re.search(
        r"((?:^[ \t]*//[^\n]*\n)+)[ \t]*static constexpr size_t kMaxPayloadBytes",
        text,
        re.MULTILINE,
    )
    assert match, (
        "No comment block was found directly above kMaxPayloadBytes's "
        "declaration in radio_transport.h"
    )
    return match.group(1)


def test_radio_transport_doc_comment_states_equality_not_tighter():
    """radio_transport.h's doc comment for kMaxPayloadBytes must state
    the CURRENT relationship to SerialTransport::kMaxLineBytes / Wire::
    WireHandler::kMaxLineBytes -- equal, both 240, as of sprint 010
    ticket 002 -- not the pre-ticket "deliberately tighter" relationship
    (sprint 008, WIRE-05/R-21) that was only true while this constant
    was still 200. A comment claiming "tighter" after this ticket raised
    the value would be exactly the same kind of silent staleness this
    file's other tests already guard against for kVersion/
    RUN_EVENT_SOURCE/kDiag*."""
    comment = _radio_transport_max_payload_bytes_doc_comment().lower()
    assert "tighter" not in comment, (
        "radio_transport.h's kMaxPayloadBytes doc comment still "
        "describes this cap as 'tighter' than SerialTransport's -- that "
        "was true at the old value (200) and is no longer true now that "
        "sprint 010 ticket 002 raised it to 240, equal to "
        "SerialTransport::kMaxLineBytes and Wire::WireHandler::"
        "kMaxLineBytes."
    )
    assert "equal" in comment, (
        "radio_transport.h's kMaxPayloadBytes doc comment no longer "
        "states the four-way equality with SerialTransport::"
        "kMaxLineBytes / Wire::WireHandler::kMaxLineBytes / this "
        "class's own RX-capacity constant, now that sprint 010 ticket "
        "002 raised the value to 240."
    )


# ---------------------------------------------------------------------------
# 2b. The four-way line-capacity equality itself (sprint 010 ticket 002,
#     radio-rx-capacity-fragmentation.md): RadioTransport's TX cap
#     (kMaxPayloadBytes, above) and its own private RX cap (kMaxLineBytes,
#     sprint 010 ticket 001) must equal the wire grammar's own ceiling
#     (Wire::WireHandler::kMaxLineBytes) and SerialTransport's line
#     capacity (its own independent kMaxLineBytes, serial_transport.h --
#     see that file's own "MUST stay ==" comment). These three constants
#     have already drifted apart twice (sprint 003 raised the wire's cap
#     without radio's TX bound; radio_transport.h then claimed equality
#     that was false for five sprints, per this ticket's own writeup) --
#     this test is what makes a THIRD silent drift fail loudly instead.
# ---------------------------------------------------------------------------


def _radio_transport_rx_capacity():
    """Ticket 001's own local RX-capacity constant: radio_transport.h's
    PRIVATE `kMaxLineBytes` (rxLine_'s array bound), distinct from the
    public `kMaxPayloadBytes` this ticket raises but required to stay
    numerically equal to it. Read as text (not compiled/linked) exactly
    like this file's other checks, so a private member is no obstacle --
    see this file's own module docstring for why these are text-based
    drift tests in the first place."""
    text = _read("comms/radio_transport.h")
    matches = re.findall(r"kMaxLineBytes\s*=\s*(\d+)", text)
    assert matches, (
        "radio_transport.h's kMaxLineBytes (RX capacity) declaration "
        "was not found"
    )
    assert len(matches) == 1, (
        f"Expected exactly one `kMaxLineBytes = <N>` assignment in "
        f"radio_transport.h, found {len(matches)}: {matches} -- this "
        f"test's regex assumes there is only one so it can't "
        f"accidentally match the wrong one."
    )
    return int(matches[0])


def _wire_handler_max_line_bytes():
    text = (_SRC_DIR / "comms" / "wire_handler.h").read_text()
    match = re.search(r"kMaxLineBytes\s*=\s*(\d+)", text)
    assert match, "wire_handler.h's kMaxLineBytes declaration was not found"
    return int(match.group(1))


def _serial_transport_max_line_bytes():
    text = (_SRC_DIR / "comms" / "serial_transport.h").read_text()
    match = re.search(r"kMaxLineBytes\s*=\s*(\d+)", text)
    assert match, "serial_transport.h's kMaxLineBytes declaration was not found"
    return int(match.group(1))


def test_radio_serial_wire_capacity_constants_are_equal_at_240():
    """The four independently-declared line/payload capacity numbers
    this project carries -- RadioTransport::kMaxPayloadBytes (TX),
    RadioTransport's own private kMaxLineBytes (RX, ticket 001),
    SerialTransport::kMaxLineBytes, and Wire::WireHandler::
    kMaxLineBytes -- must all equal 240. This is the ticket 002
    deliverable itself: raising RadioTransport::kMaxPayloadBytes to 240
    closes the last of the three-times-drifted gaps, and this test is
    what stops a fourth drift from being silent. Changing ANY ONE of
    the four values (without changing the other three to match) must
    fail this test."""
    radio_tx = _radio_transport_max_payload_bytes()
    radio_rx = _radio_transport_rx_capacity()
    serial = _serial_transport_max_line_bytes()
    wire = _wire_handler_max_line_bytes()
    assert radio_tx == radio_rx == serial == wire == 240, (
        f"The four line-capacity constants have drifted apart -- "
        f"RadioTransport::kMaxPayloadBytes (TX) = {radio_tx}, "
        f"RadioTransport's private RX kMaxLineBytes = {radio_rx}, "
        f"SerialTransport::kMaxLineBytes = {serial}, "
        f"Wire::WireHandler::kMaxLineBytes = {wire}. All four must be "
        f"240; see radio-rx-capacity-fragmentation.md for why this has "
        f"already happened twice before."
    )


# ---------------------------------------------------------------------------
# 3. (deleted) RUN_EVENT_SOURCE (run.ts) vs kRunEventSource (protocol.cpp).
#    The executor inversion deletes the MessageBus event path these two
#    literals named -- run.ts's dispatcher is now invoked directly by
#    protocol.cpp's dispatchJob()/handleRun() bypass, via a registered
#    callback, so there is no longer a shared numeric id for the two
#    sides to agree on. This pin is deleted with the code it pinned, not
#    left vacuously passing against constants that no longer exist.
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
    text = _read("comms/wire_adapter.cpp")
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


# ---------------------------------------------------------------------------
# 5. kCdegToRad / kRadToCdeg (shims.cpp): the merge side of the mirrored-
#    constant rule -- eight sites (driveTwist(), driveTwistTimed(),
#    startMove() x2, otosSetOffset(), seedPose(), poseHeading(),
#    otosGet()'s own local re-declaration) used to open-code the
#    centidegree<->radian boundary conversion (`0.01f * 3.14159265f /
#    180.0f`, or its inverse) independently. All eight now defer to two
#    named constants defined once at file scope, beside shims.cpp's own
#    "Boundary convention" header comment. This is a "merge", not a
#    "drift test between two files" -- the guard against regression is a
#    single-file check that the pi literal has not crept back in
#    anywhere except the two definitions themselves.
# ---------------------------------------------------------------------------


def _shims_cpp_text():
    return _read("shims.cpp")


def test_shims_cpp_pi_literal_only_in_kcdegtorad_definition():
    """The literal `3.14159265f` must appear exactly once in shims.cpp:
    inside `kCdegToRad`'s own definition. `kRadToCdeg` is derived from
    `kCdegToRad` (`1.0f / kCdegToRad`), not from a second copy of pi, so
    a correctly-merged file has exactly one occurrence. A future edit
    that open-codes a ninth cdeg<->rad conversion site (or re-adds
    otosGet()'s old local `kRadToCdeg = 18000.0f / 3.14159265f`) raises
    this count and fails here instead of silently reintroducing the
    duplication this ticket removed."""
    text = _shims_cpp_text()
    occurrences = [
        line_no
        for line_no, line in enumerate(text.splitlines(), start=1)
        if "3.14159265f" in line
    ]
    assert occurrences == [] or len(occurrences) == 1, (
        f"shims.cpp's pi literal (3.14159265f) appears on lines "
        f"{occurrences}, expected exactly one occurrence (kCdegToRad's "
        f"own definition) -- an open-coded cdeg<->rad conversion site "
        f"has crept back in. Use the shared kCdegToRad/kRadToCdeg "
        f"constants instead of a fresh literal."
    )
    if occurrences:
        line = text.splitlines()[occurrences[0] - 1]
        assert "kCdegToRad" in line, (
            f"shims.cpp's sole remaining pi literal is on line "
            f"{occurrences[0]} (\"{line.strip()}\"), which is not the "
            f"kCdegToRad definition -- an open-coded conversion site has "
            f"replaced the named constant."
        )


def test_shims_cpp_defines_kcdegtorad_and_kradtocdeg_exactly_once():
    """kCdegToRad and kRadToCdeg must each be defined exactly once, as
    file-scope constexpr floats -- not re-declared locally inside a
    function (the exact defect otosGet()'s old local kRadToCdeg was)."""
    text = _shims_cpp_text()
    cdeg_to_rad_defs = re.findall(
        r"constexpr float kCdegToRad\s*=", text
    )
    rad_to_cdeg_defs = re.findall(
        r"constexpr float kRadToCdeg\s*=", text
    )
    assert len(cdeg_to_rad_defs) == 1, (
        f"Expected exactly one `constexpr float kCdegToRad = ...` "
        f"definition in shims.cpp, found {len(cdeg_to_rad_defs)}."
    )
    assert len(rad_to_cdeg_defs) == 1, (
        f"Expected exactly one `constexpr float kRadToCdeg = ...` "
        f"definition in shims.cpp, found {len(rad_to_cdeg_defs)} -- "
        f"otosGet() must not re-declare its own local copy."
    )


def test_shims_cpp_conversion_sites_use_named_constants():
    """Each of the eight known cdeg<->rad boundary-conversion call sites
    must reference the shared kCdegToRad/kRadToCdeg constant by name.
    Scoped per-function (like this file's other case-body checks) so an
    unrelated open-coded formula elsewhere can't produce a false pass."""
    text = _shims_cpp_text()

    def body_of(signature_pattern):
        match = re.search(
            signature_pattern + r"\s*\{(.*?)\n\}", text, re.DOTALL
        )
        assert match, f"Function body not found for pattern: {signature_pattern}"
        return match.group(1)

    forward_sites = {
        "driveTwist": r"void driveTwist\(int speed, int yawRate\)",
        "driveTwistTimed": r"void driveTwistTimed\(int speed, int yawRate,\n\s*uint32_t duration\)",
        "startMove": r"void startMove\(int distance, int yaw, int speed, int yawRate\)",
        "otosSetOffset": r"void otosSetOffset\(int x, int y, int yaw\)",
        "seedPose": r"void seedPose\(int x, int y, int heading\)",
    }
    for name, pattern in forward_sites.items():
        body = body_of(pattern)
        assert "kCdegToRad" in body, (
            f"{name}() no longer references kCdegToRad by name -- has "
            f"an open-coded conversion crept back in?"
        )

    inverse_sites = {
        "poseHeading": r"int poseHeading\(\)",
        "otosGet": r"int otosGet\(int what\)",
    }
    for name, pattern in inverse_sites.items():
        body = body_of(pattern)
        assert "kRadToCdeg" in body, (
            f"{name}() no longer references kRadToCdeg by name -- has "
            f"an open-coded conversion crept back in?"
        )


# ---------------------------------------------------------------------------
# 6. defaultCruise_'s seed comment (shims.cpp) vs defaultSpeed
#    (blocks/motion.ts) -- sprint 019 ticket 006, code review Q-05. The
#    two are legitimately independent by design (a wire sentinel
#    default vs. a block-layer move speed, both separately settable),
#    so this is NOT a merge -- it's a correction of a comment that used
#    to assert an unmaintained "match" as an enforced fact, plus a
#    stale `main.ts` citation (main.ts was retired; see D-07 in the
#    same review). This guards the CORRECTED comment's honesty, not a
#    numeric equality (asserting defaultSpeed == defaultCruise_
#    would itself be exactly the false-coupling claim this ticket
#    removed -- the two are independently settable and free to
#    diverge).
# ---------------------------------------------------------------------------


def _shims_cpp_default_cruise_seed_comment():
    """The block of `//` comment lines directly above
    `defaultCruise_`'s declaration, so the tests below can check
    what this comment says without a false pass/fail from unrelated
    text elsewhere in the file -- same technique
    _radio_transport_max_payload_bytes_doc_comment() uses above."""
    text = _read("shims.cpp")
    match = re.search(
        r"((?:^[ \t]*//[^\n]*\n|^[ \t]*//\n)+)[ \t]*float defaultCruise_",
        text,
        re.MULTILINE,
    )
    assert match, (
        "No comment block was found directly above defaultCruise_'s "
        "declaration in shims.cpp"
    )
    return match.group(1)


def test_default_cruise_seed_comment_does_not_cite_retired_main_ts():
    """The retired main.ts must not be cited as defaultSpeed's home --
    sprint 012 moved the block API to blocks/motion.ts; a citation of
    main.ts here would be exactly the stale-path class of drift
    D-07 (code review 2026-08-26) found 16 live instances of."""
    comment = _shims_cpp_default_cruise_seed_comment()
    assert "main.ts" not in comment, (
        "shims.cpp's defaultCruise_ seed comment still cites "
        "main.ts, retired in sprint 012 -- defaultSpeed now lives in "
        "blocks/motion.ts."
    )


def test_default_cruise_seed_comment_does_not_assert_an_enforced_match():
    """The comment must not claim defaultCruise_ and defaultSpeed
    are kept in agreement -- nothing enforces that, and they are
    independently settable (default_cruise over the wire,
    setDefaultSpeed() from a block). The comment must instead say so
    plainly, so a future reader does not treat the 150.0f seed as a
    maintained invariant."""
    comment = _shims_cpp_default_cruise_seed_comment().lower()
    assert "not an enforced invariant" in comment, (
        "shims.cpp's defaultCruise_ seed comment no longer states "
        "that its numeric match with blocks/motion.ts's defaultSpeed "
        "is NOT an enforced invariant -- restore that caveat (or a "
        "clearer replacement) so a future reader does not mistake the "
        "150.0f seed for a maintained coupling."
    )
    assert "independently settable" in comment, (
        "shims.cpp's defaultCruise_ seed comment no longer explains "
        "that this field and blocks/motion.ts's defaultSpeed are each "
        "independently settable (default_cruise over the wire, "
        "setDefaultSpeed() from a block) -- that's the reason the two "
        "are free to diverge, and why no equality is enforced."
    )


# ---------------------------------------------------------------------------
# 7. The 24 ms tick cadence: shims.cpp's cfg.cyclePeriod vs
#    blocks/sim.ts's kSimTickPeriod -- sprint 019 ticket 006. Two
#    independently-editable copies (one per language) of the same
#    fiber/tick period, kept in sync so a simulator-run program's
#    timing is observable the same way hardware's is (sim.ts's own
#    comment, right above kSimTickPeriod). No shared boundary exists
#    to merge them across (TypeScript vs C++), so this is a drift test,
#    not a merge.
# ---------------------------------------------------------------------------


def _shims_cpp_cycle_period():
    text = _read("shims.cpp")
    match = re.search(r"cfg\.cyclePeriod\s*=\s*(\d+);", text)
    assert match, "shims.cpp's cfg.cyclePeriod assignment was not found"
    return int(match.group(1))


def _sim_ts_tick_period_ms():
    text = _read("blocks/sim.ts")
    match = re.search(r"kSimTickPeriod\s*=\s*(\d+)", text)
    assert match, "sim.ts's kSimTickPeriod declaration was not found"
    return int(match.group(1))


def test_sim_tick_period_matches_hardware_cycle_period():
    """blocks/sim.ts's kSimTickPeriod must equal shims.cpp's
    cfg.cyclePeriod exactly -- a mismatch would make simulator-observed
    timing (e.g. how many ticks a fixed-duration move takes) diverge
    from hardware's, defeating the parity sim.ts's own comment states
    as the point of pacing to a fixed deadline at all."""
    hardware = _shims_cpp_cycle_period()
    simulator = _sim_ts_tick_period_ms()
    assert hardware == simulator, (
        f"shims.cpp's cfg.cyclePeriod ({hardware} ms) and blocks/sim.ts's "
        f"kSimTickPeriod ({simulator} ms) have diverged -- simulator "
        f"tick timing no longer matches hardware's fiber cadence."
    )


# ---------------------------------------------------------------------------
# 8. trackWidth / rotationalSlip: motion_engine.h's defaults vs
#    docs/design/specification.md's constants table -- sprint 019
#    ticket 006. Code vs. doc, not mergeable (a doc cannot #include a
#    header), guarded the same way kVersion guards protocol.cpp against
#    pxt.json.
# ---------------------------------------------------------------------------


def _motion_engine_h_text():
    return _read("motion/motion_engine.h")


def _motion_engine_h_track_width():
    match = re.search(r"trackWidth_\s*=\s*([0-9.]+)f;", _motion_engine_h_text())
    assert match, "motion_engine.h's trackWidth_ default was not found"
    return float(match.group(1))


def _motion_engine_h_rotational_slip():
    match = re.search(
        r"rotationalSlip_\s*=\s*([0-9.]+)f;", _motion_engine_h_text()
    )
    assert match, "motion_engine.h's rotationalSlip_ default was not found"
    return float(match.group(1))


def _specification_md_text():
    return (_DOCS_DESIGN_DIR / "specification.md").read_text()


def _specification_md_track_width():
    match = re.search(
        r"`trackWidth`[^|]*\|\s*([0-9.]+)\s*\|", _specification_md_text()
    )
    assert match, (
        "docs/design/specification.md's trackWidth constants-table row "
        "was not found"
    )
    return float(match.group(1))


def _specification_md_rotational_slip():
    match = re.search(
        r"`rotationalSlip`[^|]*\|\s*([0-9.]+)\s*\|", _specification_md_text()
    )
    assert match, (
        "docs/design/specification.md's rotationalSlip constants-table "
        "row was not found"
    )
    return float(match.group(1))


def test_specification_md_track_width_matches_motion_engine():
    """docs/design/specification.md's constants table is the
    authoritative reference doc (D-05, code review 2026-08-26, named
    this exact table); it must not drift from motion_engine.h's real
    trackWidth_ default the way it already drifted for travelCalib."""
    code_value = _motion_engine_h_track_width()
    doc_value = _specification_md_track_width()
    assert code_value == doc_value, (
        f"docs/design/specification.md's trackWidth table row "
        f"({doc_value}) has drifted from motion_engine.h's trackWidth_ "
        f"default ({code_value})."
    )


def test_specification_md_rotational_slip_matches_motion_engine():
    """Same guard as the trackWidth test above, for rotationalSlip --
    the only other MotionEngine geometry default this table publishes
    alongside travelCalib (already guarded by
    tests/tools/test_travel_calib_drift.py)."""
    code_value = _motion_engine_h_rotational_slip()
    doc_value = _specification_md_rotational_slip()
    assert code_value == doc_value, (
        f"docs/design/specification.md's rotationalSlip table row "
        f"({doc_value}) has drifted from motion_engine.h's "
        f"rotationalSlip_ default ({code_value})."
    )


# ---------------------------------------------------------------------------
# 9. ConfigField ordinals: blocks/motion.ts's ConfigField TS enum vs
#    wire_adapter.cpp's kFields name/ordinal table vs shims.cpp's
#    setKernelValue()/getConfigValue() switches -- sprint 019 ticket
#    006. The same three-way "ordinal -> meaning in independently
#    maintained places" pattern case 4 (above) guards for kDiag*; that
#    case's own docstring explicitly flagged this ConfigField space as
#    "an already-addressed, unrelated drift surface" (named, not
#    fixed) -- this sweep found it still had no guard, so it gets one
#    here. blocks/motion.ts's setConfigValue() passes the TS enum's
#    numeric value straight into _setKernelValue() (the shim=
#    diffDrive::setKernelValue binding) with no name-based translation
#    at the crossing -- so an ordinal drift here is silent exactly the
#    way the kDiag* case was.
# ---------------------------------------------------------------------------


def _motion_ts_config_field_ordinals():
    text = _read("blocks/motion.ts")
    match = re.search(r"enum ConfigField \{(.*?)\n\}", text, re.DOTALL)
    assert match, "blocks/motion.ts's ConfigField enum was not found"
    body = match.group(1)
    return {
        name: int(value)
        for name, value in re.findall(r"(\w+)\s*=\s*(\d+)", body)
    }


def _wire_adapter_kfields_entries():
    """Each kFields[] row as (wire_name, ordinal, ts_enum_name) --
    the ts_enum_name comes from that row's own trailing `// ConfigField.
    Name` comment, which wire_adapter.cpp already carries for every
    entry (see that file's kFields[] definition)."""
    text = _read("comms/wire_adapter.cpp")
    match = re.search(r"kFields\[\]\s*=\s*\{(.*?)\n\};", text, re.DOTALL)
    assert match, "wire_adapter.cpp's kFields[] table was not found"
    body = match.group(1)
    rows = re.findall(
        r'\{"(\w+)",\s*(\d+)\}.*?//\s*ConfigField\.(\w+)', body
    )
    assert rows, "No kFields[] rows with a ConfigField.<Name> comment were found"
    return [(name, int(ordinal), ts_name) for name, ordinal, ts_name in rows]


def test_wire_adapter_kfields_ordinals_match_config_field_enum():
    """Every wire_adapter.cpp kFields[] row's ordinal must equal the
    numeric value blocks/motion.ts's ConfigField enum assigns to the
    SAME name (per that row's own `// ConfigField.Name` comment) -- a
    mismatch means SET/GET-by-name (wire_adapter.cpp) and
    setConfigValue()-by-enum (motion.ts, over the same shim) would
    silently address two different kernel/engine fields."""
    ts_ordinals = _motion_ts_config_field_ordinals()
    mismatches = []
    for wire_name, wire_ordinal, ts_name in _wire_adapter_kfields_entries():
        ts_ordinal = ts_ordinals.get(ts_name)
        if ts_ordinal is None:
            mismatches.append((wire_name, ts_name, "not found in ConfigField enum"))
        elif ts_ordinal != wire_ordinal:
            mismatches.append((wire_name, ts_name, f"{wire_ordinal} != {ts_ordinal}"))
    assert not mismatches, (
        f"wire_adapter.cpp's kFields[] and blocks/motion.ts's "
        f"ConfigField enum have diverged on: {mismatches}"
    )


def _shims_cpp_limits_field_ordinals(text):
    """Sprint 029 ticket 004 (design motion-profile-unification.md
    S4.7): the ten shaping ordinals are no longer individual `case N:`
    lines in setKernelValue()/getConfigValue() -- they are rows in
    `kLimitsFields[]`, a small descriptor table both functions consult
    BEFORE their own switch runs (see that table's own header comment,
    shims.cpp). An ordinal covered by a `kLimitsFields` row is covered
    for BOTH GET and SET (one table, one gate, both functions)."""
    match = re.search(r"kLimitsFields\[\]\s*=\s*\{(.*?)\n\};", text, re.DOTALL)
    assert match, "shims.cpp's kLimitsFields[] table was not found"
    return {int(n) for n in re.findall(r"\{(\d+),\s*&MotionLimits::", match.group(1))}


def test_shims_cpp_set_and_get_config_value_cover_every_config_field_ordinal():
    """shims.cpp's setKernelValue() and getConfigValue() switches must
    each have a `case N:` for every ordinal blocks/motion.ts's
    ConfigField enum defines -- a missing case means
    setConfigValue()/that field's GET silently falls through to a
    default/no-op for that field, exactly the "ordinal wire_adapter.cpp
    names with no matching shims.cpp case" failure mode case 4 (above)
    guards diagValue() against. Sprint 029 ticket 004: an ordinal
    covered by `kLimitsFields[]` instead of a literal `case N:` counts
    too -- see `_shims_cpp_limits_field_ordinals()`'s own comment."""
    text = _read("shims.cpp")
    ts_ordinals = _motion_ts_config_field_ordinals()
    expected = set(ts_ordinals.values())
    limits_covered = _shims_cpp_limits_field_ordinals(text)

    def case_numbers(function_signature_pattern):
        match = re.search(
            function_signature_pattern + r"\s*\{(.*?)\n\}", text, re.DOTALL
        )
        assert match, f"Function body not found: {function_signature_pattern}"
        return {int(n) for n in re.findall(r"case (\d+):", match.group(1))}

    set_cases = case_numbers(r"void setKernelValue\(int field, int value\)") | limits_covered
    get_cases = case_numbers(r"int getConfigValue\(int field\)") | limits_covered

    missing_set = expected - set_cases
    missing_get = expected - get_cases
    assert not missing_set, (
        f"shims.cpp's setKernelValue() has no `case N:` for ConfigField "
        f"ordinal(s) {sorted(missing_set)} -- a SET for that field would "
        f"silently no-op."
    )
    assert not missing_get, (
        f"shims.cpp's getConfigValue() has no `case N:` for ConfigField "
        f"ordinal(s) {sorted(missing_get)} -- a GET for that field would "
        f"silently fall through to whatever the default case returns."
    )
