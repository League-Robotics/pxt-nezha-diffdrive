---
id: 009
title: Host test harness comment cleanup (tests/host/*.h/.cpp, README.md)
status: done
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

- [x] `tests/host/README.md`'s "What's here" section is extended or
      cut per the audit (either list the current file inventory one
      line each, or cut to "one shim + one test file per subsystem;
      see the file headers").
- [x] `tests/host/README.md`'s "What this does NOT cover yet" section
      — **confirmed the known-stale one**: it claims
      `wire_handler`/`wire_adapter`/`motion_engine` "none of which
      exist yet," which is false (they exist, are covered by
      `test_wire_grammar.py`/`test_wire_reliability.py`/
      `test_motion_engine_*.py`) — is replaced with what is genuinely
      uncovered: `shims.cpp`/`protocol.cpp`'s CODAL-bound settle loop
      and watchdog and transports, plus PXT/simulator behavior.
- [x] `tests/host/README.md`'s intro drops "This repo's first test
      suite" and the "later sprint 003 tickets" framing.
- [x] `fake_pose_source.h`'s header (1-11, light) drops the "sprint 003
      ticket 010's own AC" reference, keeping the test-double contract.
- [x] `wire_mock_adapter.h`'s header (1-18) is rewritten — drops the
      "(sprint 003 ticket 003, widened ticket 004)" ticket-archaeology
      and the stale "production adapter... answers the other five
      kUnknown" claim (all six dispatch in production); the
      motion-verb canned-result comment (46-51) drops the same stale
      claim.
- [x] `motion_engine_shim.cpp`'s four light items (1-17, 35-38, 79-87,
      147-148/163) drop ticket-number tags, keeping the
      handle-shape/extend-don't-fork instruction and the
      measured/velocity-vs-duty distinction.
- [x] `wire_grammar_shim.cpp`'s header (1-13, light) drops the "(ticket
      002, widened by ticket 003)" tag, keeping the one-shim-several-
      files pattern and RecordingSink/borrowed-pointer notes.
- [x] `wire_motion_verb_shim.cpp`'s header (1-65) is rewritten:
      **delete** the "Sprint 003 ticket 012 extends the WaHandle
      surface three ways" changelog (8-27, confirmed pure diff
      narration by verify-comments.md D11 — every fact in it is
      restated at the definitions, which stay); keep the two-
      handles/two-jobs table, the WaHandle-supplies-shims.cpp-
      definitions safety constraint, and the `countsPerLength=1.0`
      convention. The six light items (110-118, 127-141, 162-166,
      183-184, 555-560, 579-580) drop ticket tags only.
- [x] The new-files spot-check (Description above) is performed and
      its outcome recorded in this ticket's completion notes.
- [x] All KEEP blocks (`fake_ports.h` ×10, `kernel_shim.cpp` ×8,
      `wire_mock_adapter.h` ×9, `wire_grammar_shim.cpp` ×10,
      `wire_motion_verb_shim.cpp` ×12) are confirmed present and
      untouched.

## Completion notes

Re-anchored every item by content match (not the audit's original line
numbers — this directory has grown substantially since the audit ran).
None turned out to be a no-op; every listed item had live, matching
text to rewrite.

**README.md**: "What's here" cut to the short form (one shim + one test
file per subsystem, see file headers) rather than a 30+-file inventory
that would go stale again; added a pointer to the sibling `tests/tools/`
suite (plain-Python, no compiler/subprocess/network) per the task's
scope note. "What this does NOT cover yet" replaced the false
`wire_handler`/`wire_adapter`/`motion_engine` "don't exist yet" claim
with the real gap: `shims.cpp`'s `tickDrive()` (fiber-concurrency guard,
Rig-local `odomUpdate()`, starvation watchdog), `protocol.cpp`'s CODAL
fiber, and the transport layer — all `pxt.h`-bound and uncompilable
here. **Correction beyond the audit's own wording**: the audit's
suggested replacement (from `verify-comments.md`'s R16 write-up)
describes the settle loop itself as a live gap. It is not, as of
sprint 008 ticket 004: the settle-then-neutral DECISION was extracted
into `MotionEngine::settleToRest()`, which is host-portable and *is*
covered by `test_motion_engine_settle.py` (confirmed live: the shim
exports `meSettleToRest()`/`meArmSettleProfile()`, and
`shims.cpp::tickDrive()`'s own current comment says exactly this — "the
settle-tick decision... is now a real MotionEngine method this file
already links"). README now says so explicitly rather than repeating a
now-superseded gap. Also folded in the task's C++11-gate-vs-manifest-
vs-real-build honesty note (`test_cxx11_syntax_gate.py` closes the
language-standard half, `test_pxt_manifest_completeness.py` the
manifest half, neither proves target buildability).

**fake_pose_source.h**, **wire_mock_adapter.h**, **wire_grammar_shim.cpp**:
ticket-archaeology tags dropped per the audit; substance kept verbatim.
`wire_mock_adapter.h`'s "answers the other five kUnknown" claim and
`wire_grammar_shim.cpp`'s "reused by BOTH test_wire_grammar.py and
test_wire_reliability.py" claim were both stale in a way the audit
didn't call out (grep-confirmed `wire_grammar_shim.cpp` is now also
reused by `test_wire_telemetry_frame.py` and
`test_wire_per_transport_isolation.py`) — corrected while already
rewriting that exact text, per the ticket's "re-anchor by content, not
line numbers" instruction.

**motion_engine_shim.cpp**: the four items re-anchored to (a) the file
header, (b) the goToW PoseSource member comment, (c) the post-move
regression comment (also fixed `Rig::tickDrive()` → `tickDrive()`,
since `tickDrive()` is a free function, not a `Rig` method — confirmed
via `grep` on `src/shims.cpp`), (d) the `rotationalSlip_` setter comment
plus the adjacent "move engine" section banner (the two items the audit
grouped as "147-148/163"). Left untouched: several *newer* ticket-
tagged banners this file gained after the audit ran (EncoderPoseSource
section, settle-tick-decision section, the `sprint 006 ticket 002`
FakeSleeper reference) — out of this ticket's explicit four-item list,
same "don't reopen a second audit" principle as the new-files
spot-check. Flagging for a future pass, not fixed here.

**wire_motion_verb_shim.cpp**: deleted exactly the 20-line "Sprint 003
ticket 012 extends the WaHandle surface three ways" changelog (D11
AGREE), leaving the surrounding kept text (two-handles/two-jobs table,
safety constraint, countsPerLength=1.0 convention) byte-for-byte
unchanged, including its own residual ticket tags (e.g. "Sprint 008
ticket 003") — the AC says "keep" those sections, not further-trim
them. The six light items were re-anchored by grepping every remaining
`ticket 011`/`ticket 012` occurrence and matching them in file order to
the audit's six original ranges: the `waNowMs` forward-declaration
comment, the adjacent `engine`+`pose` member comments (merged, as the
audit's own range spanning both suggests), the `waNowMs()` definition
comment, the `engineWheelsX`/`engineMoveX`/`engineDefaultCruiseMmS`
comment, the `engineMoveV`/`engineGoToR`/`engineGoToW` comment, and the
"real nowMs + motion-obligation tracking" section banner. All confirmed
KEEP content (RecordingSink, `g_activeWaHandle` contract, mirrors-
production field-for-field notes, `waCreate` borrowed-pointer comment,
`waSetNowMs`) is present and untouched (grep-verified against the six
`mirrors shims.cpp's real` occurrences plus the borrowed-pointer note).

**New-files spot-check** (Description's scope decision): of the seven
files named, five are `.cpp` (in this ticket's scope) and all five
carried the exact stray-tag anti-pattern the description names as an
example ("sprint 006 ticket NNN", split across a line-wrap in three of
the five, which is why an initial single-line grep missed them —
caught on retry with a wrapped pattern): `encoder_glitch_armor_shim.cpp`,
`encoder_glitch_armor_syntax_check.cpp`,
`encoder_pose_source_syntax_check.cpp`, `heading_wrap_shim.cpp`,
`heading_wrap_syntax_check.cpp`. Fixed all five (tag dropped, substance
kept) as an unambiguous instance of the named anti-pattern. The other
two named files are `.py` (`golden_telemetry.py`,
`test_pxt_manifest_completeness.py`) and out of this ticket's edit
scope (only `.h`/`.cpp`/`README.md`); read-only spot-check found
`golden_telemetry.py` carries one similar stray "sprint 004 ticket
004's shared" tag in its module docstring (not fixed — out of scope,
flagged for ticket 010 or a follow-up) and
`test_pxt_manifest_completeness.py` clean (its one "Sprint 007 ticket
006 found..." sentence is load-bearing — it names the specific defect
the test guards against, the same pattern the audit explicitly keeps
for regression tests).

**Gate coverage**: every file this ticket touched is either compiled by
the host suite itself (`*.h`/`*_shim.cpp`/`*_syntax_check.cpp` — a
comment-only edit that breaks a brace or an include is a compile
failure on the very next `uv run pytest`) or is `README.md`
(documentation, no build gate). Ran the full `tests/host/` suite in the
foreground per the ticket's own testing note (shared shims/mocks
touched across the whole harness): 425 passed. Also ran the full `uv
run pytest` (host + `tests/tools/`): 528 passed, matching the stated
baseline exactly.

**DESIGN.md**: not edited (out of scope per the ticket). No content
change in this ticket's diff requires a DESIGN.md update — the shim
naming/shape conventions DESIGN.md documents were not altered, only
their comments' historical framing.

**Audit accuracy note**: comment-audit.md's own suggested replacement
text for the README's "What this does NOT cover yet" section (and
verify-comments.md's R16 discussion of the settle loop) both predate
sprint 008 ticket 004's extraction of the settle-tick decision into
`MotionEngine::settleToRest()` — neither is wrong for what it audited,
but applying either verbatim today would reintroduce a stale claim.
Handled by writing the current, correct state instead of the audit's
literal wording (see README notes above).

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
