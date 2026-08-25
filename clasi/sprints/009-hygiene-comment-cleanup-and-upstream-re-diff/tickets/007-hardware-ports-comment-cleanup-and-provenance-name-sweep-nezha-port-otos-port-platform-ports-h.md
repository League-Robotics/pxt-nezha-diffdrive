---
id: '007'
title: Hardware ports comment cleanup and provenance-name sweep (nezha_port.*, otos_port.*,
  platform_ports.h)
status: open
use-cases: []
depends-on: ["001"]
github-issue: ''
issue:
- comment-cleanup-work-order.md
- vendored-kernel-upstream-rediff.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware ports comment cleanup and provenance-name sweep (nezha_port.*, otos_port.*, platform_ports.h)

## Description

**Depends on ticket 001** — it points every provenance reference in
this ticket's files at the authoritative statement ticket 001 writes
into `src/DESIGN.md` §2.

Two coordinated tasks:

1. Apply `comment-audit.md`'s `nezha_port.h` (1 REWRITE, light) and
   `otos_port.h` (1 REWRITE, 1 DELETE) items, corrected per
   `verify-comments.md` (R7 CHALLENGE applies to `nezha_port.h`).
   `otos_port.cpp` and `platform_ports.h` get no changes (audit: KEEP,
   no changes).
2. **Sweep the `radio-robot-elite` provenance name** out of every
   *unaudited* live comment in this cluster. The re-diff issue's
   problem statement is broader than its "What to do" list: "both this
   repo's vendoring comments **and** two of the comment audit's
   proposed replacements name the unresolvable repo." Confirmed
   present during planning, none of them flagged by the audit as
   REWRITE/DELETE items (they're inside those files' KEEP tallies):
   - `otos_port.h` line 3 (`"ported from radio-robot-elite's
     battle-tested Hardware::RealOtos"`) and line 25 (a
     `radio-robot-elite docs/design/...` citation)
   - `otos_port.cpp` line 1 (`"Faithful port of radio-robot-elite
     Hardware::RealOtos"`)
   - `radio_transport.h` line 10 and `radio_transport.cpp` line 7 (both
     "radio-robot-elite's Platform::MicroBitRadioLink...") — these two
     files are ticket 005's audited-item cluster; touch **only** the
     bare repo name here if ticket 005 has already landed its own
     REWRITE over the same lines (re-anchor and check before editing;
     do not fight ticket 005's edit — if it already fixed the name in
     the course of its own REWRITE, this item is a no-op for those two
     files)
   - `nezha_port.cpp` lines 99 and 205 (both
     `"radio-robot-elite docs/knowledge/..."` / `"see radio-robot-elite
     docs/design/..."`)

   `nezha_port.h`'s own header already correctly says `radio-robot` —
   confirms the tree is internally inconsistent about its own
   upstream's name, not that the whole tree agrees on the wrong one.

## Acceptance Criteria

- [ ] `nezha_port.h`'s header (1-28) is compressed per
      `verify-comments.md`'s R7 correction, not the audit's raw text —
      the audit's proposed compression clips the sentence spanning
      lines 7-8 ("The write-shaping pipeline is NOT optional styling:
      each stage guards against a measured hardware failure") that
      frames the five-stage failure-mode list against future
      "simplification." Use R7's corrected preamble: `// Ported from
      radio-robot nezha_motor.cpp + motor_armor.h's wedge detector.
      The write-shaping pipeline is not optional styling -- each stage
      guards a measured hardware failure:` followed by the failure-mode
      list, kept verbatim.
- [ ] `otos_port.h`'s stale "NOT ported (yet): the software lever-arm
      transform" paragraph (17-19) is **deleted** — confirmed
      contradicted by the same header (setOffset/sensorToCentre/
      centreToSensor are declared below and implemented in
      `otos_port.cpp`; `setOffset()`'s own doc comment at 71-77
      already covers the lever arm).
- [ ] `otos_port.h`'s "Sprint 003 ticket 010" diff-narration paragraph
      (27-33) is **deleted** — the class declaration `: public
      PoseSource` already says it.
- [ ] Every `radio-robot-elite` occurrence listed in the Description
      is corrected to `radio-robot`, pointing at `src/DESIGN.md` §2
      (from ticket 001) as the authoritative path/repo statement
      instead of independently restating a path — check each against
      ticket 001 and (for the two `radio_transport.*` lines) ticket
      005 having already landed before editing, to avoid a double
      edit.
- [ ] No file in `src/` states `radio-robot-elite` as an upstream
      repository after this ticket (grep confirms zero remaining
      occurrences across `src/`).
- [ ] All KEEP blocks (`nezha_port.h` ×13; `nezha_port.cpp` ×15,
      `otos_port.h` ×11 minus the two removed above; `otos_port.cpp`
      ×8; `platform_ports.h` ×5) are confirmed present and untouched.

## C++11 gate coverage

**None of these files are covered by `test_cxx11_syntax_gate.py`** —
all `#include "pxt.h"` (CODAL, I2C-bound). C++11 buildability for this
ticket's edits is proven only by ticket 012's flashable-hex build
checkpoint.

## Testing

- **Existing tests to run**: no host-portable tests exercise these
  files directly (§1 of `src/DESIGN.md`'s layer map — hardware ports
  are not host-testable); run the full `uv run pytest` to confirm no
  unrelated regression.
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest`
