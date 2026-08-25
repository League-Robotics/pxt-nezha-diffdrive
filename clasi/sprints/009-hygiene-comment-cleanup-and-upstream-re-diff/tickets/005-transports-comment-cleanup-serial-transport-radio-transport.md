---
id: '005'
title: Transports comment cleanup (serial_transport.*, radio_transport.*)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Transports comment cleanup (serial_transport.*, radio_transport.*)

## Description

Apply `comment-audit.md`'s `serial_transport.h` (1 DELETE, 4 REWRITE —
the worst file in the audit at 83% noise), `serial_transport.cpp` (2
REWRITE), `radio_transport.h` (5 REWRITE), and `radio_transport.cpp` (2
REWRITE) items, corrected per `verify-comments.md`.

**`radio_transport.h`'s `kMaxPayloadBytes` item needs a fresh read
before anything else in this ticket.** The audit's item (118-125) and
even `verify-comments.md`'s R14 correction both assume the live
comment still claims `kMaxPayloadBytes` "equals SerialTransport's" —
false since ticket 005 (sprint 004) raised `SerialTransport`'s cap to
240 while radio's stayed 200. But **sprint 008 already fixed this
exact comment** as part of its own WIRE-05/R-21 single-sourcing work
(`protocol.cpp`'s `emitLine()` now names `RadioTransport::
kMaxPayloadBytes` directly, and the constant moved `private` →
`public` to make that possible; per `src/DESIGN.md` §14, "the comment
now states the true relationship: `kMaxPayloadBytes` is deliberately
the tighter of the two transports' caps"). Read the current comment
before applying R14's text. If sprint 008's fix already states the
tighter-cap relationship, this item is a **no-op** — confirm it meets
the dimension-6 bar as-is and move on; do not paste over a comment
that's already correct with `verify-comments.md`'s independently-worded
version.

## Acceptance Criteria

- [x] `serial_transport.h`'s stale header (1-12, "Protocol v5 wire
      link"/"COBS keyed on 0x0A" — protocol.h no longer documents
      either) is replaced with the audit's 4-line CODAL-leaf
      description.
- [x] `kMaxLineBytes` essay (20-32) is compressed per the audit,
      keeping the `== WireHandler::kMaxLineBytes (240)` equality
      invariant and the truncate-into-parseable-prefix hazard —
      AGREE per verify-comments.md R12.
- [x] `begin()`'s orphaned first paragraph (36-47) is **deleted** —
      confirm first that `readLine()` is genuinely absent from the
      class and the whole tree (grep the repo; verify-comments.md's
      D2 already did this and found only stale comment references at
      .h:58/60/67/77 and .cpp:60, which this ticket's remaining items
      clean up) before deleting; the real `begin()` doc (48-50) is
      **kept**, reworded only to swap "full binary v5 frame" for "a
      full line arriving as one burst."
- [x] `tryReadLine` doc (58-72) and the `partial_` comment (75-80) are
      compressed per the audit, dropping the dead `readLine()`
      comparisons.
- [x] `serial_transport.cpp`'s `begin()` comment (18-23, stale "one
      binary v5 frame (WHEELS is ~27 wire bytes)") and the
      truncate-not-overrun comment (59-61, stale `readLine()`
      reference) are rewritten per the audit.
- [x] `radio_transport.h`'s header (1-33), `sendLine` doc (43-59,
      stale COBS-at-0x0A reference), `sendFragmented` doc (84-93), and
      `kGroup`/`kChannel` comment (106-115, fleet facts — AGREE per
      verify-comments.md R13) are rewritten per the audit.
- [x] `kMaxPayloadBytes` comment (118-125) is handled per the
      Description above: read current text first; apply R14's
      corrected relationship **only if** the comment still states the
      stale equality claim, otherwise confirm the sprint-008 text
      already meets the bar and leave it as a verified no-op — record
      which case applied in this ticket's completion notes.
- [x] `radio_transport.cpp`'s header (1-12) and `sendLine` comment
      (127-132, stale COBS cross-ref) are rewritten per the audit.
- [x] All KEEP blocks (`serial_transport.h` ×1: `writeLine`;
      `serial_transport.cpp` ×4: ASYNC semantics, drained-break,
      delimiter handling, retained-partial note; `radio_transport.h`
      ×8: `tryReceiveLine` doc, `onDatagram`'s bench-measured
      recv-on-empty kill, member-scratch stack-overflow measurement,
      flag constants, `FLAG_ACK` note, `kFrameHeaderBytes`, RX
      diagnostics, `txSeq_`; `radio_transport.cpp` ×6) are confirmed
      present and untouched.

## Completion notes

- **R14 (kMaxPayloadBytes) was already fixed — confirmed no-op.**
  Read the live comment before touching anything else, per the
  Description's instruction. It already states "Deliberately the
  TIGHTER of the two transports' caps, not 'equal' to
  SerialTransport's own bound (this header used to claim equality —
  corrected here)" — sprint 008 ticket 002's WIRE-05/R-21 fix. Left
  untouched; it meets the dimension-6 bar as-is (real "why", not
  noise) despite its length.
- **New finding, not in the audit or verify-comments.md**: the old
  `radio_transport.h`/`.cpp` header comments and `sendLine()`'s doc
  claimed the module is "TX-only... no MICROBIT_RADIO_EVT_DATAGRAM
  listener is ever registered, no reassembly buffer exists" — this is
  factually false against the current file: `tryReceiveLine()`,
  `onDatagram()`, `rxReady_`/`rxLine_`, and `ensureRadioReady()`'s own
  `uBit.messageBus.listen(..., MICROBIT_RADIO_EVT_DATAGRAM, ...)` call
  all exist in the same files the stale claim sat in (RX landed via
  the now-`done` issue
  `clasi/issues/done/radio-rx-command-plane-run-over-bridge.md`,
  post-audit). Applying the audit's literal suggested header text
  ("TX-only... no datagram listener") would have **introduced** a
  false claim contradicting the audit's own KEEP list for the same
  file (`tryReceiveLine` doc, `onDatagram`, RX diagnostics — all
  audit-KEEP). Corrected instead: header/`.cpp`-header/`sendLine` doc
  now say TX + single-fragment RX, no multi-fragment reassembly (per
  `tryReceiveLine()`'s own kept doc), no ACK protocol either
  direction. `FLAG_ACK`'s KEEP comment ("TX-only, see top comment")
  was left untouched per the AC, and still resolves correctly since
  the ACK-unused fact is restated in the new header.
- Also caught and fixed while rewriting `sendLine()`'s doc: it stated
  "fixed group 10, **channel 0**, transmit power 7" — the real
  constant is `kChannel = 4`. Replaced the restated literals with a
  cross-reference to `kGroup`/`kChannel`/`kTransmitPower` so this
  can't drift again.
- Radio's stale COBS-safety rationale ("COBS here is keyed on 0x0A...
  see protocol.h") was dropped rather than replaced with a new
  technical claim — the codebase's v6 wire grammar is text/token
  based, not binary, so there is no verified current mechanism to
  cite in its place; the mechanical facts (append 0x0A, truncate not
  overflow) are kept.
- 528/528 tests pass (baseline unchanged — comment-only edit). A real
  `uv run python tools/make_deploy.py` build was run twice; both
  attempts hit exactly the two pre-declared benign failures (V1
  hex-merge `srec_cat` "contradictory value" error, then a `TS9200`
  packaging abort) and succeeded on attempt 2 with a flashable
  1,391,201-byte hex. `serial_transport.cpp` and `radio_transport.cpp`
  compiled with zero warnings both runs. No host test reaches these
  files (all four `#include "pxt.h"`, outside the C++11 syntax gate)
  — the build and the pytest baseline are the only evidence for this
  ticket, not test coverage.
- **Findings reported to team-lead, not acted on (out of this
  ticket's scope):**
  1. `radio_transport.h`'s public `rxFrames_`/`rxAccepted_` members
     and their "Read by `Protocol::formatDiag()` for the DIAG
     surface" comment (an audit-KEEP block, left untouched) describe
     dead code: neither member is ever incremented anywhere in
     `radio_transport.cpp`, and `Protocol::formatDiag()` does not
     exist in `protocol.h`/`protocol.cpp` (grepped both). Likely
     another casualty of v6's DIAG-verb retirement, same family as
     the already-flagged `wire_adapter.cpp` DIAG-narrowing item.
  2. `tryReceiveLine()`'s kept doc cites
     `clasi/issues/radio-rx-command-plane-run-over-bridge.md` for
     "multi-fragment inbound reassembly is deliberately out of
     scope" — that issue is now in `clasi/issues/done/`, and the
     currently-open tracking issue for the same residual gap is
     sprint 010's `radio-rx-capacity-fragmentation.md`. Left
     untouched (audit-KEEP block, out of this ticket's scope) but
     worth a follow-up citation fix.
  3. `radio-robot-elite` naming (already flagged by verify-comments.md
     N3 for `diffdrive.h`/`otos_port.h`) also appears in
     `radio_transport.h`/`.cpp`'s provenance citations
     ("`radio-robot-elite`'s `Platform::MicroBitRadioLink`",
     `src/firm/platform/microbit/microbit_radio_link.{h,cpp}`,
     "RadioRelay wire spec section 5"). A GitHub code search against
     `League-Robotics/radio-robot` found no match for
     `MicroBitRadioLink` or `RadioRelay`. Left the wording unchanged
     (no verified correct alternative, and out of this ticket's
     scope), but this extends N3's naming concern to a second pair of
     files and should be verified before anyone else bakes the same
     citation in further.
  4. Minor: the (untouched, audit-KEEP, verified-no-op)
     `kMaxPayloadBytes` comment cites
     `clasi/issues/radio-rx-capacity-fragmentation.md`, but that file
     actually lives at
     `clasi/sprints/010-.../issues/radio-rx-capacity-fragmentation.md`
     — a minor path imprecision, not a factual/hazard error, so left
     alone per the no-op decision above.

## C++11 gate coverage

**None of these four files are covered by
`test_cxx11_syntax_gate.py`** — all four `#include "pxt.h"` (CODAL),
which excludes them from the four-TU syntax gate by construction.
C++11 buildability for this ticket's edits is proven only by ticket
012's flashable-hex build checkpoint, not by any host-suite run in
this ticket.

## Testing

- **Existing tests to run**: no host-portable tests exercise these
  files directly (they are CODAL-facing); run the full `uv run pytest`
  to confirm no unrelated regression, since these files are outside
  every existing test's direct scope.
- **New tests to write**: none — comment-only change; not host-testable
  by construction (§1 of `src/DESIGN.md`'s layer map).
- **Verification command**: `uv run pytest`
