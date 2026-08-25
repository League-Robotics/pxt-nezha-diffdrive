---
id: '005'
title: Transports comment cleanup (serial_transport.*, radio_transport.*)
status: open
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

- [ ] `serial_transport.h`'s stale header (1-12, "Protocol v5 wire
      link"/"COBS keyed on 0x0A" — protocol.h no longer documents
      either) is replaced with the audit's 4-line CODAL-leaf
      description.
- [ ] `kMaxLineBytes` essay (20-32) is compressed per the audit,
      keeping the `== WireHandler::kMaxLineBytes (240)` equality
      invariant and the truncate-into-parseable-prefix hazard —
      AGREE per verify-comments.md R12.
- [ ] `begin()`'s orphaned first paragraph (36-47) is **deleted** —
      confirm first that `readLine()` is genuinely absent from the
      class and the whole tree (grep the repo; verify-comments.md's
      D2 already did this and found only stale comment references at
      .h:58/60/67/77 and .cpp:60, which this ticket's remaining items
      clean up) before deleting; the real `begin()` doc (48-50) is
      **kept**, reworded only to swap "full binary v5 frame" for "a
      full line arriving as one burst."
- [ ] `tryReadLine` doc (58-72) and the `partial_` comment (75-80) are
      compressed per the audit, dropping the dead `readLine()`
      comparisons.
- [ ] `serial_transport.cpp`'s `begin()` comment (18-23, stale "one
      binary v5 frame (WHEELS is ~27 wire bytes)") and the
      truncate-not-overrun comment (59-61, stale `readLine()`
      reference) are rewritten per the audit.
- [ ] `radio_transport.h`'s header (1-33), `sendLine` doc (43-59,
      stale COBS-at-0x0A reference), `sendFragmented` doc (84-93), and
      `kGroup`/`kChannel` comment (106-115, fleet facts — AGREE per
      verify-comments.md R13) are rewritten per the audit.
- [ ] `kMaxPayloadBytes` comment (118-125) is handled per the
      Description above: read current text first; apply R14's
      corrected relationship **only if** the comment still states the
      stale equality claim, otherwise confirm the sprint-008 text
      already meets the bar and leave it as a verified no-op — record
      which case applied in this ticket's completion notes.
- [ ] `radio_transport.cpp`'s header (1-12) and `sendLine` comment
      (127-132, stale COBS cross-ref) are rewritten per the audit.
- [ ] All KEEP blocks (`serial_transport.h` ×1: `writeLine`;
      `serial_transport.cpp` ×4: ASYNC semantics, drained-break,
      delimiter handling, retained-partial note; `radio_transport.h`
      ×8: `tryReceiveLine` doc, `onDatagram`'s bench-measured
      recv-on-empty kill, member-scratch stack-overflow measurement,
      flag constants, `FLAG_ACK` note, `kFrameHeaderBytes`, RX
      diagnostics, `txSeq_`; `radio_transport.cpp` ×6) are confirmed
      present and untouched.

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
