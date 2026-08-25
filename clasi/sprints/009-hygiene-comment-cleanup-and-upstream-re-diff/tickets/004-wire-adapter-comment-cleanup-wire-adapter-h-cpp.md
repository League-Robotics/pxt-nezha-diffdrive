---
id: '004'
title: Wire adapter comment cleanup (wire_adapter.h/.cpp)
status: open
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

- [ ] `wire_adapter.h`'s 108-line header REWRITE (1-108) is applied
      per the audit's ~12-line replacement — AGREE per
      verify-comments.md's R10 (every stated invariant preserved; the
      dropped "unserviced move dies to the watchdog in ~100-150 ms"
      narrative survives verbatim in `shims.cpp`'s kept "Move-completion
      stop delivery" comment, per ticket 008 — confirm that comment is
      still present there before treating this as satisfied).
- [ ] `kWheelsVDurationCeiling`, `setIdentity`, `onWheelsV`/`onWheelsX`/
      `onMoveX`/`onMoveV`/`onGoToR`/`onGoToW` doc comments, the config
      section banner, `hasLiveMotionObligation` banner, the private
      banner, and the 23-line `lastDone()` DECISION essay (→ 3 lines,
      per verify-comments.md's R11 AGREE) are re-anchored and rewritten
      per the audit.
- [ ] `wire_adapter.cpp`'s file comment (1-4, "why five motion verbs
      answer kUnknown" — confirmed stale, all six dispatch), the three
      forward-decl blocks (12-21, 29-48, 50-70 — fold into one
      comment per the audit), `kFields` comment (74-82), `status()`
      preamble (195-211 — see below), the "active" comment (228-231 —
      confirmed stale "WHEELS_V-only" claim), the `onWheelsV`/
      `onWheelsX` obligation comments (259-261, 286-293), and the
      `onEstop`/`onStop` obligation comments (392-396/409) are
      re-anchored and rewritten per the audit.
- [ ] The four DELETE items (313, 331-332, 351, 377-378 — repeated
      "see identical comment above" ticket cross-refs on
      `onMoveX`/`onMoveV`/`onGoToR`/`onGoToW`) are removed; confirm
      each referenced comment they point to survives as the REWRITE
      the audit specifies (D3-D6 in verify-comments.md — all AGREE).
- [ ] The ADD item (422-436, onGet/onSet) is applied verbatim per the
      audit — confirmed correct by verify-comments.md: `// config
      values cross the shim boundary as x1000-scaled ints (shims.cpp
      convention).`
- [ ] `status()`'s 17-line "flagged here for whoever picks this up
      next" essay (195-211) is compressed to the audit's 3-line
      replacement, and the DIAG-has-no-v6-equivalent narrowing is
      **noted in this ticket's completion notes as a filing request
      for the team-lead** (the audit itself says "file it as an
      issue") — do not create a new CLASI issue mid-ticket.
- [ ] All ×5 (header) and ×12 (cpp) KEEP blocks are confirmed present
      and untouched, in particular `mradToRad` (159-173 — keep
      verbatim per the audit's explicit callout) and the
      `hasLiveMotionObligation` wraparound idiom.

## C++11 gate coverage

`wire_adapter.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `wire_adapter.h` is included by it and is covered
indirectly. No new gate registration needed.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_telemetry_projection.py tests/host/test_wire_telemetry_frame.py tests/host/test_wire_per_transport_isolation.py tests/host/test_cxx11_syntax_gate.py`
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_telemetry_projection.py tests/host/test_cxx11_syntax_gate.py`
