---
id: '002'
title: Motion engine comment cleanup (motion_engine.h/.cpp)
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Motion engine comment cleanup (motion_engine.h/.cpp)

## Description

Apply `comment-audit.md`'s `motion_engine.h` (8 REWRITE) and
`motion_engine.cpp` (1 REWRITE) items, corrected per
`verify-comments.md`. **This file has grown substantially since the
audit ran** (sprints 006/007 added the `goToR`/`goToW` split-geometry
doctrine, the `PoseSource` heading-wrap-convention paragraph, and
`rotationalSlip`'s setter) — locate every audited item by content
match against the current file, not by the audit's line numbers, which
no longer point at the same text.

**The highest-risk item in this ticket is a non-edit.** The audit's
item for `rotationalSlip_` (original lines 335-346) proposes
compressing the comment to a 3-line version whose own numbers are
internally inconsistent (164-166/180 ≈ 0.915, not 0.952) —
`verify-comments.md`'s R9 correction fixes the arithmetic but is
**still stale**: sprint 007 ticket 005 already rewrote this comment
with the full measurement-to-constant derivation chain (0.915 measured
ratio → 120.0 mm effective track → 0.952 slip) and an explicit "do not
set `rotationalSlip_` to 0.915" caution, specifically to prevent a
future re-measurer from "correcting" the constant back to the wrong
value. Read the current comment before touching this item: if it
already carries the full derivation chain and the caution, **leave it
untouched** — do not apply the audit's or even verify-comments.md's
version, both of which would shorten it. Only touch this comment if
the current text has since regressed (i.e., no longer carries the
chain), in which case restore the derivation chain, not either
proposed replacement.

## Acceptance Criteria

- [ ] `motion_engine.h`'s 113-line-header REWRITE (audit item 1-113)
      is applied per `verify-comments.md`'s R8 correction: the
      audit's own ~20-line exclusive keep-list is short two
      invariants that live *only* in this header, with surviving
      method docs elsewhere pointing back at it via "see header
      comment" — (a) odometry stays out of this class; callers must
      update it themselves around `serviceMove()`, and (b)
      `goToR`/`goToW` are single-shot reductions and `arrive` is
      accepted but unused. Both must survive the compression (either
      in the compressed header or folded into the method docs that
      currently defer to it) so no "see header comment" pointer is
      left dangling. Re-anchor against the file's current, larger
      content — the compression target is "keep only what's
      load-bearing," not a literal line count.
- [ ] `rotationalSlip_`'s comment is verified to already carry the
      full 0.915→120.0mm→0.952 derivation chain and the "do not set to
      0.915" caution (per sprint 007 ticket 005) and is **left
      unchanged** — this is the ticket's explicit non-edit; state so
      in the ticket's completion notes.
- [ ] `PoseSource` comment (122-132), constructor comment (144-157),
      `wheelsV` doc (191-198), section banners (214-215, 265-267), and
      the `348-349` parenthetical are re-anchored and rewritten per the
      audit (all AGREE per verify-comments.md — no correction needed,
      only re-anchoring).
- [ ] `motion_engine.cpp`'s section-banner REWRITE (drop the ticket
      reference) is applied, re-anchored to its current location.
- [ ] Every REWRITE not explicitly named above (this file had 8 total,
      3 are covered by name; the remainder — PoseSource, constructor,
      wheelsV, banners) is checked against the "preserves every
      invariant, unit, measured value, and derivation" test before
      applying, per the sprint's mandatory protocol.
- [ ] All ×20 KEEP blocks (geometry method docs, primitive/move-engine
      contracts, `kTurnFirstAngleRad`, `MoveState`, `startSegment`/
      `cancelMove`, `travelCalib_`/`trackWidth_` measured provenance,
      shaping-default trade-off block) are confirmed still present and
      untouched.

## C++11 gate coverage

`motion_engine.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `motion_engine.h` is included by it and is covered
indirectly. No new gate registration needed.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_motion_engine_primitives.py tests/host/test_motion_engine_reductions.py tests/host/test_motion_engine_gotow.py tests/host/test_motion_engine_settle.py tests/host/test_cxx11_syntax_gate.py`
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_motion_engine_primitives.py tests/host/test_motion_engine_reductions.py tests/host/test_motion_engine_gotow.py tests/host/test_motion_engine_settle.py tests/host/test_cxx11_syntax_gate.py`
