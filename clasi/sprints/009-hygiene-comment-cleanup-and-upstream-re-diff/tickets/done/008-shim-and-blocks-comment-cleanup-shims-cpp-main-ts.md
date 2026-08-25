---
id: 008
title: Shim and blocks comment cleanup (shims.cpp, main.ts)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: comment-cleanup-work-order.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Shim and blocks comment cleanup (shims.cpp, main.ts)

## Description

Apply `comment-audit.md`'s `shims.cpp` (3 DELETE, 12 REWRITE) and
`main.ts` (1 DELETE, 5 REWRITE) items, corrected per
`verify-comments.md`, plus `verify-comments.md`'s N6 addition (a
stale `main.ts` JSDoc the audit's own "Public-API bar check" missed).

**`shims.cpp`'s `tickDrive()` banner and settle-loop essay are the
highest-risk items in this ticket — re-derive from current code, don't
paste the audit's text.** Sprint 008 replaced the inline post-move
settle loop with a call into a new `MotionEngine` settle helper
(audit's items at 427-447 and 501-519 describe the *pre-008* inline
loop and its "KNOWN GAP, hardware-only" framing). The audit's proposed
3-line KNOWN GAP replacement for 501-519 (`verify-comments.md`'s R16,
AGREE) may still be substantially accurate — the extraction narrowed
but did not eliminate the hardware-only gap (`src/DESIGN.md`'s Open
Questions §10 still lists `odomUpdate(r)` and the loop's actual
`kernel.step()` calls as hardware-only) — but read the **current**
`tickDrive()` and settle-related comments first and write from what's
actually there, applying the audit's anti-pattern guidance (drop
ticket refs, state the gap crisply) to the current text rather than
overwriting it with pre-008 prose.

## Acceptance Criteria

- [x] `shims.cpp` header (1-27) is compressed per the audit, keeping
      the four-bullet composition summary and the integer-boundary
      convention (load-bearing).
- [x] The three DELETE items — the orphaned first-pivots fragment
      (77-85; **confirmed safe to delete**, per `verify-comments.md`
      D8 — its defect is filed and closed in
      `clasi/issues/done/first-move-after-idle-runs-at-full-duty.md`),
      the moved-state diff narration (130-137), and the thin-forwards
      narration (237-244) — are removed.
  - [x] "Second/Third/Fourth caller" narration (29-53) is replaced with
      the audit's 3-line same-package-forward-declaration summary.
- [x] The watchdog-launch comment (201-205), `setWheelsTimed` banner
      (264-279), `engineWheelsX` banner (299-317), `updateMove` comment
      (415/418-421), and `diagValue` comment (674-678 — confirmed
      still-stale per `verify-comments.md`'s "verified in passing":
      DIAG retired, `probe()` and `wire_adapter.cpp` both call
      `diagValue`, only duty is ×100) are rewritten per the audit.
- [x] The `tickDrive()` banner and settle-loop essay are re-derived
      from current code per the Description above — not pasted from
      the audit's pre-008 text.
- [x] The watchdog section (570-603, essentially KEEP — only "this
      sprint" phrases and the sprint.md citation drop), `getConfigValue`
      essay (788-809, confirmed stale per verify-comments.md), and
      `engineMoveV`/`engineGoToW` banners (850-863, 875-888) are
      rewritten per the audit. (`engineGoToW`'s comment had itself gone
      further stale than the audit knew — sprint 006 t007 replaced its
      "honest kUnimplemented refusal" behavior with an encoder-odometry
      PoseSource fallback after the audit was written — so this one was
      re-derived from current code rather than pasted from the audit's
      now-inapplicable text; see report.)
- [x] The `700-712` case-reordering item (move the "23/24" comment so
      it sits above what it describes, confirmed by verify-comments.md)
      is applied. **Already done** — sprint 007 t007 (commit
      `6f4b21e`) reordered case 25 before this ticket started; verified
      current code already has the comment correctly placed. No-op.
- [x] The fused `898-912` comment (probe()'s doc + setTaperWindows's
      doc + the PXT TS9200 shim-failure trap, confirmed fused by
      verify-comments.md) is split: probe()'s doc moves to sit above
      `probe()` (line ~946); setTaperWindows's doc and the TS9200 trap
      stay as their own block.
- [x] `main.ts`'s jumbled triple comment (52-72) is split and moved: the
      `_startProtocol()` doc relocates to sit above that statement
      (line ~86); the `runParts` semantics and no-initialiser
      PXT-init-order-trap comments stay in place.
- [x] The RUN comment (143-153), `startMove` doc (266-276), sim tick
      comment (740-748), and `simIntegrate` clip comment (756-767) are
      rewritten per the audit.
- [x] `maxNudges` (546) — the dead variable and its comment — is
      **deleted together** (confirmed dead by verify-comments.md's D7:
      grepped whole file, `goToWorld` is confirmed one-pass). **Already
      done** — sprint 007 t006 (commit `be7e289`) deleted it before
      this ticket started; verified current code has no `maxNudges`
      reference at all. No-op.
- [x] **N6**: `goToWorld`'s exported JSDoc (≈558-562, "Repeats until
      inside the arrival tolerance") is corrected in the same edit as
      the `maxNudges` deletion — it contradicts the function's own
      one-pass body comment; this is a real doc bug the audit's own
      "Public-API bar check" missed, not an optional extra. **Already
      done** — same sprint 007 t006 commit (`be7e289`) fixed the JSDoc
      to "ONE PASS: drives the leg and stops..."; verified current text
      already matches. No-op.
- [x] All KEEP blocks (`shims.cpp` ×25: vevov wiring block, init-order,
      tovez defaults, TICK MODEL block, move-completion stop delivery,
      settle ticks, `startMove` dual-rate algebra, watchdog constants;
      `main.ts` ×49: file header, all student-facing JSDoc, world-pose
      doctrine, `goToWorld` one-pass/curvature-cap blocks, `turnFirstDeg`
      rationale, `emitLine`'s PXT-radio trap, `otosGet` unit table) are
      confirmed present and untouched.

## C++11 gate coverage

**`shims.cpp` is not covered by `test_cxx11_syntax_gate.py`** — it
includes `pxt.h` (CODAL). `main.ts` is TypeScript and is governed by
the PXT/MakeCode compile, not the C++11 gate at all. C++11/PXT
buildability for this ticket's edits is proven only by ticket 012's
flashable-hex build checkpoint.

## Testing

- **Existing tests to run**: no host-portable tests exercise
  `shims.cpp`/`main.ts` directly; run the full `uv run pytest` to
  confirm no unrelated regression (the host suite compiles this
  package's *portable* C++ only — neither of these files is in that
  set).
- **New tests to write**: none — comment-only change.
- **Verification command**: `uv run pytest`
