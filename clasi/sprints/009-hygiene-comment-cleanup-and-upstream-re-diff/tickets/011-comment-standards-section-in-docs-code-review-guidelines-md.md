---
id: '011'
title: Comment-standards section in docs/code-review/guidelines.md
status: open
use-cases: []
depends-on: ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Comment-standards section in docs/code-review/guidelines.md

## Description

Runs after every comment-cleanup ticket (002-010; ticket 001 too, for
consistency) — both issues ask for this explicitly: the
comment-cleanup issue's own text says "Fold the five anti-patterns...
as a follow-up in the same work, so the standard is written down once
the noise it targets has actually been removed." Writing it first
would describe noise that hasn't been demonstrated removed yet;
writing it last lets it cite this sprint's own concrete before/after
examples.

`docs/code-review/guidelines.md` already has a "6. Comment hygiene"
dimension (Delete/Keep bullet lists) — **extend it**, don't create a
new top-level section, with `comment-audit.md` §4's five recurring
anti-patterns and their concrete counterexamples.

## Acceptance Criteria

- [ ] `docs/code-review/guidelines.md`'s existing "6. Comment hygiene"
      section gains a subsection naming all five anti-patterns from
      `comment-audit.md` §4, each with the concrete example class
      named there:
      1. **Sprint/ticket archaeology as file headers** —
         `wire_adapter.h`'s pre-cleanup 108-line ticket chronicle as
         the extreme case.
      2. **Justification-to-reviewer essays around decisions** —
         `wire_adapter.h`'s `lastDone()` essay and `shims.cpp`'s
         settle-loop essay as examples; the rule: keep the decision +
         one-line reason, put the defense in the ticket/PR.
      3. **Stale cross-layer claims after a refactor** — "the other
         five answer kUnknown," "for the Protocol v5 wire link / COBS
         keyed on 0x0A," dangling `readLine()` references, as
         examples; the rule: describe the contract at *this* seam,
         point elsewhere by name, never by restating behavior.
      4. **Diff restatement / caller-history comments** — "fields
         formerly here moved to X (ticket N)," "now thin forwards...
         the math is unchanged," as examples; the rule: the code below
         already says it.
      5. **Orphaned/misplaced comments surviving code motion** —
         `shims.cpp`'s dangling first-pivots fragment, `probe()`'s doc
         sitting 48 lines from `probe()`, `main.ts`'s
         `_startProtocol()` doc parked over unrelated variables, as
         examples; the rule: a comment moves (or dies) with its code.
- [ ] The section names `comment-audit.md` §4's "counterexamples worth
      imitating" (nezha_port.cpp's measured wedge/glitch comments,
      diffdrive.cpp's `kMaxCycleGapUs` block, wire_adapter.cpp's
      `mradToRad`, main.ts's no-initialiser trap, shims.cpp's
      vevov-wiring forensics and watchdog section) as what "Keep" looks
      like in practice, alongside the section's existing Keep bullets.
- [ ] The addition is a genuine extension of the existing "6. Comment
      hygiene" dimension — same voice, same list style as the
      surrounding Delete/Keep bullets — not a disconnected new section.

## C++11 gate coverage

Not applicable — pure markdown, no build gate.

## Testing

- **Existing tests to run**: none — this ticket touches only
  `docs/code-review/guidelines.md`.
- **New tests to write**: none.
- **Verification command**: N/A (documentation-only ticket; confirm
  with a read-through, not a test run).
