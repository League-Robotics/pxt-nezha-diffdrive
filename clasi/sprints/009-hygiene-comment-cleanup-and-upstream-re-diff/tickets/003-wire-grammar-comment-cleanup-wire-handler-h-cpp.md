---
id: '003'
title: Wire grammar comment cleanup (wire_handler.h/.cpp)
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire grammar comment cleanup (wire_handler.h/.cpp)

## Description

Apply `comment-audit.md`'s `wire_handler.h` (7 REWRITE) and
`wire_handler.cpp` (3 REWRITE) items, corrected per
`verify-comments.md` (all 3 sampled items from this file — none — were
directly sampled, but the wire-layer cluster generally scored well:
apply the same load-bearing check to every unsampled item regardless).

**Re-check before applying, not after**: sprint 008 added a shared
decode-time `duration`/`timeout` clamp for all six motion verbs
(WIRE-02/KERN-06 and WIRE-10 closure) in the exact region the audit's
`wire_handler.cpp` items 433-437 ("Unrecognized verb...") and 741-749
(motion section banner) sit near. Read the current content of both
regions first. If sprint 008 already documents the clamp accurately,
the audit's proposed text — written before that clamp existed —
either doesn't apply to what's there now or would need to be merged
with, not replace, the newer clamp documentation. Do not silently
overwrite a newer, correct comment with pre-008 text.

## Acceptance Criteria

- [ ] `wire_handler.h`'s header REWRITE (1-87) is applied per the
      audit: the reliability-layer summary (lines ~14-68 in the
      audited version) is genuine wire-format documentation and is
      **kept**; only the trailing "Sprint 003 ticket 004 adds..."
      paragraph (audited ~70-87) — stale (all six verbs are real,
      per `wire_adapter.cpp`) and ticket-archaeology — is replaced
      with the milliradian-integers + host-portable-constraint
      statement the audit specifies. Re-anchor by content match.
- [ ] `Sink` comment (95-100), `Identity` comment (107-113),
      `DoneReason` comment (169-174 — confirm "carried here even
      though this ticket wires up no motion verb yet" is still stale;
      it should be, since all six verbs dispatch), `Adapter` comment
      (183-198), `kCommandTable` comment (423-430), and the motion
      decode/exec banner (482-490) are re-anchored and rewritten per
      the audit — all AGREE per verify-comments.md's general
      assessment of this cluster, but each still gets the load-bearing
      check since none of the 16 samples came from this file.
  - [ ] All ×23 KEEP blocks are confirmed present, in particular the
      `feed()` doc (NUL characterization + overflow rule) and the
      completion-channel/`kMaxFieldTokens`/stand-ins notes — these are
      explicitly called out as exemplary and must not be touched.
- [ ] `wire_handler.cpp`'s cstdio/`strtof` comment (10-22) is
      compressed per the audit (drop the discovery narrative, keep the
      newlib-nano namespace fact — cross-reference `protocol.cpp`'s
      identical comment, ticket 006).
- [ ] The "Unrecognized verb" comment (audit's 433-437) and the motion
      section banner (audit's 741-749) are checked against sprint
      008's decode-clamp addition first (see Description); apply the
      audit's stale→current correction only where the current text
      still needs it, and preserve or fold in the decode-clamp
      documentation if present rather than deleting it.
- [ ] All ×32 KEEP blocks (parse-helper strictness, `formatConfigValue`
      NaN-UB analysis, sanitize/overflow/blank-line/NUL guards,
      case-is-direction, ESTOP/PING/HELLO handling, id classification,
      `-Wswitch` note, `execRun`'s `kMaxLineBytes+1` subtlety,
      `emitTelemetry`) are confirmed present and untouched.

## C++11 gate coverage

`wire_handler.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `wire_handler.h` is included by it and is covered
indirectly. No new gate registration needed.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_grammar.py tests/host/test_wire_reliability.py tests/host/test_wire_motion_verbs.py tests/host/test_wire_constants_drift.py tests/host/test_cxx11_syntax_gate.py`
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_wire_grammar.py tests/host/test_wire_reliability.py tests/host/test_wire_motion_verbs.py tests/host/test_cxx11_syntax_gate.py`
