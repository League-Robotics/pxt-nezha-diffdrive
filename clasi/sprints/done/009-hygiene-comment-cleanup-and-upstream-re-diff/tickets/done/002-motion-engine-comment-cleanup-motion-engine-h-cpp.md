---
id: '002'
title: Motion engine comment cleanup (motion_engine.h/.cpp)
status: done
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

- [x] `motion_engine.h`'s 113-line-header REWRITE (audit item 1-113)
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
- [x] `rotationalSlip_`'s comment is verified to already carry the
      full 0.915→120.0mm→0.952 derivation chain and the "do not set to
      0.915" caution (per sprint 007 ticket 005) and is **left
      unchanged** — this is the ticket's explicit non-edit; state so
      in the ticket's completion notes.
- [x] `PoseSource` comment (122-132), constructor comment (144-157),
      `wheelsV` doc (191-198), section banners (214-215, 265-267), and
      the `348-349` parenthetical are re-anchored and rewritten per the
      audit (all AGREE per verify-comments.md — no correction needed,
      only re-anchoring).
- [x] `motion_engine.cpp`'s section-banner REWRITE (drop the ticket
      reference) is applied, re-anchored to its current location.
- [x] Every REWRITE not explicitly named above (this file had 8 total,
      3 are covered by name; the remainder — PoseSource, constructor,
      wheelsV, banners) is checked against the "preserves every
      invariant, unit, measured value, and derivation" test before
      applying, per the sprint's mandatory protocol.
- [x] All ×20 KEEP blocks (geometry method docs, primitive/move-engine
      contracts, `kTurnFirstAngleRad`, `MoveState`, `startSegment`/
      `cancelMove`, `travelCalib_`/`trackWidth_` measured provenance,
      shaping-default trade-off block) are confirmed still present and
      untouched.

## Completion notes

**`rotationalSlip_` (motion_engine.h:436-461, current line numbers):
confirmed non-edit, left byte-for-byte untouched.** Read before
touching anything else in the file. It already carries the full
sprint-007-ticket-005 derivation chain: "CAMERA-MEASURED 2026-08-20
... six steady-state 180 deg pivots turned 164-166 deg physical, ratio
0.915. / 0.915 is NOT the slip -- do not set rotationalSlip_ to 0.915
... trackWidth_ (114.2 ...) divided by the 1.040 rotationalSlip_ this
entry replaces, i.e. 114.2/1.040 = 109.8 mm ... the TRUE
effectiveTrackWidth must be LARGER ... specifically 109.8/0.915 =
120.0 mm ... Only then: slip = trackWidth_/effectiveTrackWidth =
114.2/120.0 = 0.952." Both the audit's 3-line replacement and
verify-comments.md's R9-corrected replacement would have shortened
this and were declined as no-ops, per the ticket's explicit
instruction.

**Header (AC1):** the top-of-file block comment has grown from the
audit's 113 lines to 131 (pre-edit) via sprints 006/007/008 —
`goToR`'s KERN-02/03/04 pivot-vs-blend/short-arc-normalization/
arrive-as-no-op-gate rationale and `goToW`'s PoseSource-pluggability
rationale did not exist when the audit ran, and both are pointed at
by their method docs via "see header comment for why" — so both were
kept in full, not compressed. Also declined the audit's literal
"arrive is accepted but unused" wording for invariant (b): that was
true pre-sprint-006, but sprint 006 ticket 001 made `arrive` an
honored radial no-op gate (`hypot(x,y) <= arrive`) — the header
already states this correctly (KERN-04) and that current, accurate
text was preserved rather than reverting to the stale pre-sprint-006
phrasing. What *was* cut, because it is genuinely restated verbatim at
each method's own doc comment with no "see header" back-reference:
the "TWO PRIMITIVES" section's per-method restatement of
`wheelsX`/`wheelsV` (replaced with a short pointer), and the
"sprint.md Design Rationale" quotation about the two call paths
"meant to eventually share" the implementation — verified via grep
that `shims.cpp` and `wire_adapter.cpp` both already dispatch through
`MotionEngine engine{kernel, clock}` via the `engine*` forwards, so
this is now stated as accomplished fact, not aspiration. Dropped
"sprint 003 ticket 006/007/010" tags throughout, per the audit's
explicit anti-pattern guidance.

**PoseSource comment, constructor comment, wheelsV doc, both section
banners, and the move-engine-state parenthetical (AC3):** none of
these were in verify-comments.md's 27-item sample, so each got the
same load-bearing check as an unsampled REWRITE, per the sprint's
mandatory protocol.
- `wheelsV` doc, both banners, and the parenthetical: audit's
  suggested cuts (a "byte-for-byte the math ... already perform"
  historical aside, two ticket-tag parentheticals, and one
  call-graph-narration sentence naming `shims.cpp`'s taper setters)
  carry no unit, invariant, or derivation — applied as specified.
- PoseSource and the constructor comment: applied a **lighter**
  compression than the audit's literal targets (PoseSource to ~3
  lines; constructor to ~3 lines). Both still carry a "why this shape"
  design rationale (PoseSource: why a future no-OTOS robot needs this
  minimal an interface, and why it's host-testable; constructor: why
  the engine needs its own `Clock` reference separate from the
  kernel's private one) that the audit's shorter replacement text
  would have dropped — kept those, cut only the pattern-analogy aside
  (PoseSource) and the "new in ticket 007"/"extracted from shims.cpp's
  former Rig fields" archaeology (constructor).

**motion_engine.cpp (AC4):** the one REWRITE item — the move-engine
section banner at (now) line 86 — had the "sprint 003 ticket 007" tag
dropped, re-anchored by content match (original audit line 62). Left
`settleToRest()`'s own "Sprint 008 ticket 004" comment untouched: it
postdates the audit (sprint 008), is not one of the audit's items, and
touching un-audited content is out of this ticket's scope.

**KEEP blocks (AC6):** spot-confirmed present and untouched — the
yaw-taper-double-count block (measured vevov 2026-08-22), the
rolling-lease reissue rationale, the wrong-way SIGNED-progress
comment, and the phase-transition abort rules in `.cpp`; and in `.h`
the geometry section, sign-convention section, `kTurnFirstAngleRad`,
`MoveState`, `startSegment`/`cancelMove` docs, `travelCalib_`/
`trackWidth_` field comments, and the shaping-default trade-off block.

**Gate coverage:** `motion_engine.cpp` is one of the four translation
units `tests/host/test_cxx11_syntax_gate.py` syntax-checks; no new
registration needed (comment-only change). Ran
`tests/host/test_motion_engine_primitives.py`,
`test_motion_engine_reductions.py`, `test_motion_engine_gotow.py`,
`test_motion_engine_settle.py`, and `test_cxx11_syntax_gate.py` in the
foreground: 69 passed.

**Nothing in the audit turned out to be wrong against current code**
beyond what verify-comments.md already flagged (R8/R9) — the header's
growth since sprint 006 simply means more of it is load-bearing than
either document anticipated.

## C++11 gate coverage

`motion_engine.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `motion_engine.h` is included by it and is covered
indirectly. No new gate registration needed.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_motion_engine_primitives.py tests/host/test_motion_engine_reductions.py tests/host/test_motion_engine_gotow.py tests/host/test_motion_engine_settle.py tests/host/test_cxx11_syntax_gate.py`
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_motion_engine_primitives.py tests/host/test_motion_engine_reductions.py tests/host/test_motion_engine_gotow.py tests/host/test_motion_engine_settle.py tests/host/test_cxx11_syntax_gate.py`
