---
id: 009
title: Host test harness comment cleanup (tests/host/*.h/.cpp, README.md)
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host test harness comment cleanup (tests/host/*.h/.cpp, README.md)

## Description

Apply `comment-audit.md`'s items for `tests/host/README.md` (3
REWRITE), `fake_pose_source.h` (1 REWRITE, light),
`wire_mock_adapter.h` (2 REWRITE), `motion_engine_shim.cpp` (4 light
REWRITE), `wire_grammar_shim.cpp` (1 REWRITE, light), and
`wire_motion_verb_shim.cpp` (1 DELETE, 7 light REWRITE), corrected per
`verify-comments.md` (D11 AGREE for the wire_motion_verb_shim.cpp
changelog delete).

**Scope decision for new files**: `tests/host/` gained several files
after the audit ran — `encoder_glitch_armor_shim.cpp`,
`encoder_glitch_armor_syntax_check.cpp`,
`encoder_pose_source_syntax_check.cpp`, `heading_wrap_shim.cpp`,
`heading_wrap_syntax_check.cpp`, `golden_telemetry.py`,
`test_pxt_manifest_completeness.py`. These are **out of the 135-item
work order** — the audit never saw them, so there is nothing in it to
"apply." Spot-check them against the five anti-patterns ticket 011
documents (ticket-archaeology headers, reviewer-justification essays,
stale cross-layer claims, diff restatement, orphaned comments); fix
only unambiguous instances (e.g. a stray "sprint 006 ticket NNN" tag)
without opening a second full audit. Record the spot-check's outcome
(clean, or what was fixed) in this ticket's completion notes.

## Acceptance Criteria

- [ ] `tests/host/README.md`'s "What's here" section is extended or
      cut per the audit (either list the current file inventory one
      line each, or cut to "one shim + one test file per subsystem;
      see the file headers").
- [ ] `tests/host/README.md`'s "What this does NOT cover yet" section
      — **confirmed the known-stale one**: it claims
      `wire_handler`/`wire_adapter`/`motion_engine` "none of which
      exist yet," which is false (they exist, are covered by
      `test_wire_grammar.py`/`test_wire_reliability.py`/
      `test_motion_engine_*.py`) — is replaced with what is genuinely
      uncovered: `shims.cpp`/`protocol.cpp`'s CODAL-bound settle loop
      and watchdog and transports, plus PXT/simulator behavior.
- [ ] `tests/host/README.md`'s intro drops "This repo's first test
      suite" and the "later sprint 003 tickets" framing.
- [ ] `fake_pose_source.h`'s header (1-11, light) drops the "sprint 003
      ticket 010's own AC" reference, keeping the test-double contract.
- [ ] `wire_mock_adapter.h`'s header (1-18) is rewritten — drops the
      "(sprint 003 ticket 003, widened ticket 004)" ticket-archaeology
      and the stale "production adapter... answers the other five
      kUnknown" claim (all six dispatch in production); the
      motion-verb canned-result comment (46-51) drops the same stale
      claim.
- [ ] `motion_engine_shim.cpp`'s four light items (1-17, 35-38, 79-87,
      147-148/163) drop ticket-number tags, keeping the
      handle-shape/extend-don't-fork instruction and the
      measured/velocity-vs-duty distinction.
- [ ] `wire_grammar_shim.cpp`'s header (1-13, light) drops the "(ticket
      002, widened by ticket 003)" tag, keeping the one-shim-several-
      files pattern and RecordingSink/borrowed-pointer notes.
- [ ] `wire_motion_verb_shim.cpp`'s header (1-65) is rewritten:
      **delete** the "Sprint 003 ticket 012 extends the WaHandle
      surface three ways" changelog (8-27, confirmed pure diff
      narration by verify-comments.md D11 — every fact in it is
      restated at the definitions, which stay); keep the two-
      handles/two-jobs table, the WaHandle-supplies-shims.cpp-
      definitions safety constraint, and the `countsPerLength=1.0`
      convention. The six light items (110-118, 127-141, 162-166,
      183-184, 555-560, 579-580) drop ticket tags only.
- [ ] The new-files spot-check (Description above) is performed and
      its outcome recorded in this ticket's completion notes.
- [ ] All KEEP blocks (`fake_ports.h` ×10, `kernel_shim.cpp` ×8,
      `wire_mock_adapter.h` ×9, `wire_grammar_shim.cpp` ×10,
      `wire_motion_verb_shim.cpp` ×12) are confirmed present and
      untouched.

## C++11 gate coverage

**Not applicable to most of this ticket's C++ files** — they are
host-only test infrastructure (`tests/host/*_shim.cpp`,
`wire_mock_adapter.h`, `fake_pose_source.h`), compiled only at C++20
for the host test harness and never compiled for the target;
`test_cxx11_syntax_gate.py` deliberately does not cover them.
`README.md` is documentation. No build gate risk from this ticket's
edits.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite — these are
  shared shims/mocks/README referenced across the whole host suite;
  scoping to a subset risks missing a shim-signature regression).
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest`
