---
id: '011'
title: Comment-standards section in docs/code-review/guidelines.md
status: done
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
- 008
- 009
- '010'
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

- [x] `docs/code-review/guidelines.md`'s existing "6. Comment hygiene"
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
- [x] The section names `comment-audit.md` §4's "counterexamples worth
      imitating" (nezha_port.cpp's measured wedge/glitch comments,
      diffdrive.cpp's `kMaxCycleGapUs` block, wire_adapter.cpp's
      `mradToRad`, main.ts's no-initialiser trap, shims.cpp's
      vevov-wiring forensics and watchdog section) as what "Keep" looks
      like in practice, alongside the section's existing Keep bullets.
- [x] The addition is a genuine extension of the existing "6. Comment
      hygiene" dimension — same voice, same list style as the
      surrounding Delete/Keep bullets — not a disconnected new section.

## Completion notes

Read all ten completion notes (tickets 001-010) before writing, per the
dispatch instruction — they are far better evidence than the audit
itself, since they applied it to real code and found where it was
wrong. `docs/code-review/guidelines.md`'s existing "6. Comment hygiene"
section (### 6, under "## Review dimensions") was extended with four
new pieces, all nested as `####` subsections under it (not sibling `###`
sections — an earlier draft used `###` and was corrected to nest
properly):

1. A short "What 'keep' looks like in practice, concretely" bullet list
   appended directly after the existing Keep bullets (AC2) — the five
   named counterexamples, each with a one-line reason it's exemplary,
   verified live against current source before citing (grepped
   `mradToRad`, `kMaxCycleGapUs`, the wedge/glitch comments, the
   no-initialiser trap, and the vevov/watchdog sections in `shims.cpp`
   — all present and matching the audit's description).
2. "Recurring anti-patterns (delete or rewrite on sight)" — the five
   anti-patterns from `comment-audit.md` §4, numbered, each with its
   named example class and rule (AC1).
3. "Applying a comment audit or cleanup work order safely" — new
   content beyond the literal ACs, requested by the dispatcher: how to
   apply a batch cleanup pass without reintroducing what it was meant to
   remove (content-match re-anchoring, treat every item as a possible
   no-op, load-bearing-check every REWRITE even a previously-verified
   one, and check a proposed replacement against the same audit's own
   KEEP list for the same file). Grounded in real near-misses from
   tickets 002, 004, and 005 (the `rotationalSlip_` derivation, the
   `kMaxPayloadBytes`/`goToWorld` no-ops, the radio TX-only
   contradiction).
4. "Standards that came from getting this wrong once" — six durable
   rules from the dispatcher's list (derivation reproducibility,
   platform-ceiling constants, deliberate asymmetry, what a test does
   NOT prove, no hardcoded counts, provenance in one place), each tied
   to a concrete, currently-live example (`encoder_glitch_armor.h`'s
   `kMaxDeltaCounts`, `serial_transport.h`'s `kRingBytes{255}`,
   `radio_transport.h`/`serial_transport.h`'s retry asymmetry,
   `test_cxx11_syntax_gate.py`, `wire_adapter.cpp`'s `kFields`,
   `src/DESIGN.md` §2).

No source or test file touched. `uv run pytest` re-run after the edit:
528 passed, matching the stated baseline exactly (unaffected, as
expected for a markdown-only change).

**Note for the team-lead**: the issue this ticket completes lives at
`clasi/sprints/009-hygiene-comment-cleanup-and-upstream-re-diff/issues/
comment-cleanup-work-order.md`, not top-level `clasi/issues/` — the
dispatch brief's path was off by the sprint-issues subdirectory.

**Known gap surfaced, not fixed here (out of scope for a docs-only
ticket)**: `radio_transport.h:8` and `radio_transport.cpp:7` still say
`radio-robot-elite` as of this ticket — both ticket 007 (which swept
this name) and ticket 005 (which owns these two files) explicitly left
it for the other to fix, and neither ultimately did. Worth a follow-up
ticket if a zero-`radio-robot-elite`-occurrences state matters.

## C++11 gate coverage

Not applicable — pure markdown, no build gate.

## Testing

- **Existing tests to run**: none — this ticket touches only
  `docs/code-review/guidelines.md`.
- **New tests to write**: none.
- **Verification command**: `uv run pytest` — re-run to confirm the
  528-test baseline is unaffected; 528 passed.
