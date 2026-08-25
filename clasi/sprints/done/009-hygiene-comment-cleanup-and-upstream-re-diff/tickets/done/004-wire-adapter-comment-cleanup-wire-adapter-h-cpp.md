---
id: '004'
title: Wire adapter comment cleanup (wire_adapter.h/.cpp)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire adapter comment cleanup (wire_adapter.h/.cpp)

## Description

Apply `comment-audit.md`'s `wire_adapter.h` (12 REWRITE) and
`wire_adapter.cpp` (8 REWRITE, 4 DELETE, 1 ADD) items — the largest
single file cluster in the work order (25 items), all corrected per
`verify-comments.md` where sampled (R10, R11 both AGREE as specified;
the "verified in passing" list at the bottom of verify-comments.md
also confirms several `wire_adapter.cpp` stale-claim items — 1-4,
195-211, 228-231, 74-82, the 422-436 ADD item — as accurate). Every
item not covered by those confirmations still gets the load-bearing
check before landing.

Re-anchor by content match — this file changed materially in sprints
006-008 (`engineDefaultCruiseMmS()`'s split from `fullDutyVelocity`,
sprint 007's config-field additions, sprint 008's obligation-tracking
note about the decode-time clamp).

## Acceptance Criteria

- [x] `wire_adapter.h`'s 108-line header REWRITE (1-108) is applied
      per the audit's ~12-line replacement — AGREE per
      verify-comments.md's R10 (every stated invariant preserved; the
      dropped "unserviced move dies to the watchdog in ~100-150 ms"
      narrative survives verbatim in `shims.cpp`'s kept "Move-completion
      stop delivery" comment, per ticket 008 — confirm that comment is
      still present there before treating this as satisfied).
      **DONE** — confirmed `shims.cpp:623-629` still carries the
      "Move-completion stop delivery" comment with the "~100-150 ms"
      narrative verbatim; lines 1-108 replaced with the ~17-line
      contract summary (content-identical to the audit's ~12-line
      text; line-wrapped a little longer). The re-anchor held: current
      file's paragraphs 1-108 matched the audit's original 108-line
      span almost exactly by line count, with the sprint 004 telemetry
      paragraph (110-131) appended afterward, untouched.
- [x] `kWheelsVDurationCeiling`, `setIdentity`, `onWheelsV`/`onWheelsX`/
      `onMoveX`/`onMoveV`/`onGoToR`/`onGoToW` doc comments, the config
      section banner, `hasLiveMotionObligation` banner, the private
      banner, and the 23-line `lastDone()` DECISION essay (→ 3 lines,
      per verify-comments.md's R11 AGREE) are re-anchored and rewritten
      per the audit.
      **DONE with corrections** — `kWheelsVDurationCeiling`, `setIdentity`,
      `onWheelsX`, `onMoveX`, `onMoveV`, `onGoToR`, the config banner
      (partial), and `hasLiveMotionObligation` banner applied per audit.
      `onWheelsV`'s doc and the config banner needed the audit's text
      corrected in place to keep post-audit WIRE-08 cast-ceiling facts
      (see completion notes). `onGoToW`'s doc was declined verbatim
      (stale — describes the pre-sprint-006-ticket-007 no-fallback
      behavior) and replaced with an accurate compression instead. The
      `lastDone()` "23-line essay" no longer exists in that form — it
      was superseded by sprint 005 ticket 004's real implementation (a
      43-line essay covering the actual completion-signal design, not
      a "no completion channel yet" decision) — left untouched
      (post-audit load-bearing content, out of this item's scope). The
      "private banner" (the short "real clock + motion-obligation
      state" banner) was found and compressed per audit.
- [x] `wire_adapter.cpp`'s file comment (1-4, "why five motion verbs
      answer kUnknown" — confirmed stale, all six dispatch), the three
      forward-decl blocks (12-21, 29-48, 50-70 — fold into one
      comment per the audit), `kFields` comment (74-82), `status()`
      preamble (195-211 — see below), the "active" comment (228-231 —
      confirmed stale "WHEELS_V-only" claim), the `onWheelsV`/
      `onWheelsX` obligation comments (259-261, 286-293), and the
      `onEstop`/`onStop` obligation comments (392-396/409) are
      re-anchored and rewritten per the audit.
      **DONE with corrections/no-ops** — file comment, three
      forward-decl blocks (folded into one, corrected to keep the
      post-audit engineGoToW fallback fact), `kFields` comment
      (corrected — stale "15 wire names" count dropped, now 18 entries
      per sprint 007 tickets 003/005), "active" comment, and the
      onWheelsV/onWheelsX obligation comments all applied per audit.
      `status()`'s preamble (195-211 old numbering) is a NO-OP — see
      below. `onEstop`'s obligation comment is a NO-OP — see below.
      `onStop`'s small residual cross-ref ("see onEstop()'s identical
      comment above") had its ticket tag dropped, matching the audit's
      "onStop's may say 'see onEstop'" instruction.
- [x] The four DELETE items (313, 331-332, 351, 377-378 — repeated
      "see identical comment above" ticket cross-refs on
      `onMoveX`/`onMoveV`/`onGoToR`/`onGoToW`) are removed; confirm
      each referenced comment they point to survives as the REWRITE
      the audit specifies (D3-D6 in verify-comments.md — all AGREE).
      **DONE** — onMoveX's and onGoToR's cross-refs deleted outright
      (D3, D5); onMoveV's and onGoToW's cross-refs reduced to their
      one load-bearing clause each ("duration IS the lease already,
      same as onWheelsV()" / "only armed on the path that actually
      dispatched a move") per D4/D6. The referenced onWheelsX comment
      they all pointed to survives as the "timeout is a backstop..."
      REWRITE.
- [x] The ADD item (422-436, onGet/onSet) is applied verbatim per the
      audit — confirmed correct by verify-comments.md: `// config
      values cross the shim boundary as x1000-scaled ints (shims.cpp
      convention).`
      **DONE** — added above `onGet`'s `out = ... * 0.001f` line,
      verbatim per the audit.
- [x] `status()`'s 17-line "flagged here for whoever picks this up
      next" essay (195-211) is compressed to the audit's 3-line
      replacement, and the DIAG-has-no-v6-equivalent narrowing is
      **noted in this ticket's completion notes as a filing request
      for the team-lead** (the audit itself says "file it as an
      issue") — do not create a new CLASI issue mid-ticket.
      **NO-OP — filing request already moot.** The audited essay no
      longer exists: sprint 004 ticket 004 (R-22/WIRE-06) already
      rewrote this exact preamble while fixing `out.otos` and closing
      the numeric `i2cf` half of the gap, replacing the "flagged here
      for whoever picks this up next" essay with an accurate ~12-line
      description of what's fixed (i2cf) vs. still gapped (the other 7
      FULL numeric columns). The filing request the audit asked for is
      **already satisfied**: `clasi/sprints/004-.../issues/status-lost-diag-numeric-surface.md`
      already exists and is referenced by name in the current comment,
      and part of the gap it names is already closed. Applying the
      audit's 3-line replacement verbatim would have reintroduced a
      **false** claim ("v6 has no DIAG-equivalent... i2cf" — i2cf now
      has one) — declined per the ticket's load-bearing-check
      instruction. Left untouched. No new issue created.
- [x] All ×5 (header) and ×12 (cpp) KEEP blocks are confirmed present
      and untouched, in particular `mradToRad` (159-173 — keep
      verbatim per the audit's explicit callout) and the
      `hasLiveMotionObligation` wraparound idiom.
      **CONFIRMED** — all header KEEP ×5 (NowMsFn rationale,
      constructor borrowed-pointer contract, onEstop/onStop `->`
      tags, onRun no-registration-table comment,
      motionObligationDeadlineMs_ unit tag) and cpp KEEP ×12 (flags
      layout, kDiag ordinals, tlmModeWireName kNow note, mradToRad
      verbatim, now() comment, exact-narrowing-cast note,
      hasLiveMotionObligation wraparound idiom, onTlm kNow note, onRun
      comment) present and untouched by grep/read verification.

## C++11 gate coverage

`wire_adapter.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `wire_adapter.h` is included by it and is covered
indirectly. No new gate registration needed.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_telemetry_projection.py tests/host/test_wire_telemetry_frame.py tests/host/test_wire_per_transport_isolation.py tests/host/test_cxx11_syntax_gate.py`
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_telemetry_projection.py tests/host/test_cxx11_syntax_gate.py`
