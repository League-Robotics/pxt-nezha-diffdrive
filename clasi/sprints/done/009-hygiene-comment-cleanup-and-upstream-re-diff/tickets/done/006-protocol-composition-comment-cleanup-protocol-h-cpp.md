---
id: '006'
title: Protocol composition comment cleanup (protocol.h/.cpp)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol composition comment cleanup (protocol.h/.cpp)

## Description

Apply `comment-audit.md`'s `protocol.h` (6 REWRITE) and `protocol.cpp`
(7 REWRITE) items, corrected per `verify-comments.md` (R15 CHALLENGE
applies to the identity-constants item).

**Two items in this file are stale relative to *closed* gaps, not just
stale relative to a refactor — read current content before applying
either:**

1. `protocol.h`'s retired-TLM note (audit item 47-61) proposes a
   "KNOWN GAP: v6 has no data-bearing telemetry frame yet" comment.
   That gap was **closed in sprint 004** — `thdr`/`t` frames exist and
   `WireAdapter::buildSnapshot()` (ticket 004's cluster, this sprint)
   projects real telemetry. Applying the audit's proposed text
   verbatim would put a **false claim** into the codebase — exactly
   the regression this sprint exists to avoid. Rewrite this comment to
   state that the telemetry frame is real and shipped, with only the
   genuinely-still-open gap (`tools/`'s scripts haven't been retrofitted
   onto it — sprint 005's scope) surviving as the KNOWN GAP.
2. `protocol.cpp`'s identity-constants essay (audit item 30-63)
   proposes text including "`kVersion` is a manually-synced mirror of
   `pxt.json`'s version — bump together... the sync is currently
   broken (1.0.0 vs 1.0.10)." Sprint 008 fixed that exact drift —
   `kVersion` is now single-sourced or drift-tested against
   `pxt.json`. Do not reintroduce the "currently broken" claim; state
   the fixed relationship instead. Apply verify-comments.md's R15
   correction (add the `kDrivetrain`/`kProfile` line the audit's
   5-line replacement drops) on top of this fix.

## Acceptance Criteria

- [x] `protocol.h`'s v5-retirement inventory (1-16) is replaced with
      the audit's 3-line Protocol description.
- [x] The RUN carve-out paragraph (18-33) and radio carve-out
      paragraph (35-45) are compressed per the audit, keeping the
      stated invariants (legacy `RUN:` coexistence, radio RX being
      RUN-only). **Correction**: "radio RX being RUN-only" is itself
      stale — sprint 004 ticket 001 gave radio a full v6 `WireHandler`
      (`wireHandlerRadio_`) over the same `wireAdapter_`; the audit's
      proposed text for both paragraphs predates that and was declined
      verbatim. Compressed text states the current, correct invariant
      instead (radio speaks full v6; RUN: is a preserved fallback,
      not the only accepted form) — see report below.
- [x] The retired-TLM note (47-61) is corrected per the Description
      above — states telemetry as shipped, not pending.
- [x] The identity NSDMI/timing essay (144-165), NSDMI comment
      (210-216), and `protocol()` comment (227-240) are compressed per
      the audit.
- [x] `protocol.cpp`'s cstdio comment (4-7) is compressed (cross-
      reference `wire_handler.cpp`'s identical comment — ticket 003).
- [x] The `tickDrive()` forward-decl essay (12-26) is compressed per
      the audit.
- [x] The identity-constants essay (30-63) is corrected per the
      Description above (kVersion fix) plus verify-comments.md's R15
      addition (kDrivetrain/kProfile line).
- [x] The poll/emit-cadence comment (71-79), the
      `radioTransport_.begin()` comment (195-200), the v6-feed comment
      (236-245), and the `startProtocol` comment (314-321) are
      compressed per the audit.
- [x] All KEEP blocks (`protocol.h` ×9: `start()`/`emitLine()`/
      `runText()` docs, RUN slot-ring/dedupe, `SerialSink` newline-
      strip contract; `protocol.cpp` ×13: `kOldRunPrefix`,
      `kRunEventSource`, `protocolEmitLine` PXT-radio-dependency trap,
      `handleRun` sanitize+dedupe, `wireNowMs` safety note, fiber_sleep
      note, `gProtocol`) are confirmed present and untouched.

## C++11 gate coverage

**Neither file is covered by `test_cxx11_syntax_gate.py`** —
`protocol.cpp` includes `pxt.h` (CODAL), which excludes it from the
four-TU syntax gate. C++11 buildability for this ticket's edits is
proven only by ticket 012's flashable-hex build checkpoint.

## Testing

- **Existing tests to run**: no host-portable tests exercise this file
  directly; run `uv run pytest tests/host/test_wire_constants_drift.py`
  (the `kVersion`/`RUN_EVENT_SOURCE` drift tests read this file as
  text) plus the full suite to confirm no unrelated regression.
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_wire_constants_drift.py`
