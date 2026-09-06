---
id: 008
title: src/DESIGN.md truth pass, re-measure and tighten both ratchets
status: in-progress
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
github-issue: ''
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# src/DESIGN.md truth pass, re-measure and tighten both ratchets

## Description

The closing ticket. Two jobs, in this order: fix `src/DESIGN.md`'s
surviving false claims, then re-measure the tree and tighten both
ratchets to what the sprint actually achieved.

**No behaviour change.** This ticket edits one design document and one
test file's constants.

Runs last because the ratchet tightening must be seeded from the
post-cleanup tree, and because `src/DESIGN.md` describes files that
tickets 002-006 are still editing.

### Design overlay

`src/DESIGN.md` is a canonical design doc and this sprint's overlay was
seeded from it at planning time
(`clasi/sprints/035-…/design/DESIGN.md`). **Edit the canonical
`src/DESIGN.md` directly** — the team-lead syncs the overlay at close.
Do not edit the overlay copy.

The co-located subsystem docs (`src/comms/DESIGN.md`,
`src/motion/DESIGN.md`, `src/platform/DESIGN.md`,
`src/blocks/DESIGN.md`, `src/core/DESIGN.md`) were checked at planning
time: all are 19-35 line stubs and none carries any of the stale
claims. They are **out of scope**; leave them alone.

### Part A — `src/DESIGN.md` truth pass

`src/DESIGN.md` is 2440 lines. Fix the specific false claims below; do
**not** attempt a general rewrite.

1. **`kMaxPayloadBytes` "still 200" — the document contradicts
   itself.** Anchor: `*value* is unchanged — still 200, still radio's
   real capacity ceiling`. The constant is `240`
   (`src/comms/radio_transport.h`: `static constexpr size_t
   kMaxPayloadBytes = 240;`), and §10 of this same document states 240
   correctly. Fix the §6 passage. Read the surrounding sprint-008
   paragraph before editing — the *relationship* it states
   (`kMaxPayloadBytes` is deliberately the tighter of the two
   transports' caps, single-sourced rather than a bare literal) is
   still true and worth keeping; only the number and the
   "value is unchanged" framing are wrong. (This is CM-10's row (g),
   which review §5's sixteen-row table omitted.)

2. **The dangling `captures/tovez-wifi-20260902/` citation.** Anchor:
   `Verified on tovez 2026-09-02: \`captures/tovez-wifi-20260902/\``.
   That directory does not exist on disk and nothing tracks it. The
   same sentence already cites
   `docs/knowledge/2026-09-02-wifi-transport-tovez.md`, which **is**
   tracked. Drop the `captures/` path; keep the parenthetical
   description of what was verified and the tracked doc. Do **not**
   delete the whole citation — `.claude/rules/measurement-citations.md`
   wants a reachable artifact named, and there is one.

3. **The MessageBus RUN bridge claim.** Anchor:
   `by-name test trigger is protocol.cpp's MessageBus RUN bridge, a CODAL`.
   There is no MessageBus: it is `runQueue_` plus `RunBridge` /
   `dispatchJob()` on the protocol fiber (sprint 033). Rewrite to match
   what tickets 004 and 005 wrote in the source comments — read those
   first so the document and the code say the same thing.

4. **Re-verify §6 and §8 against what tickets 002-006 landed.** Both
   sections describe the transports, the emit ring, the RUN bridge and
   the dedupe window, and 033/034 plus this sprint moved all of them.
   Specifically confirm, and fix if wrong: the same-text dedupe window
   (400 ms — the document was already corrected, verify it stayed);
   the single-writer model (the two-fiber claim is gone from the
   document, verify); and the diag ordinals (the ordinal-30 correction
   is documented; verify it still matches `shims.cpp`'s
   `case 28` / `case 30`).

5. **The `differential_drive.{h,cpp}` references at
   `src/DESIGN.md`'s §2 provenance statement are CORRECT** — they name
   the **upstream** path `radio-robot-elite/src/firm/diffdrive/
   differential_drive.{h,cpp}`. Record as a verified no-op. Ticket 002
   fixed only the two vendored files' *self*-names. Do not "fix" the
   provenance statement.

6. **Any other claim in `src/DESIGN.md` that tickets 002-007 proved
   false while editing the source.** Each of those tickets is asked to
   report such findings in its completion notes; read them and act.
   This is the one ticket in the sprint positioned to reconcile the
   document against the code.

### Part B — re-measure and tighten both ratchets

Run after Part A and after 002-007 are all done.

1. **Re-measure the per-file comment ratios** using ticket 001's
   counting rule (re-derive it from the module docstring; do not
   re-invent it). Produce the same table shape as `sprint.md`'s
   "Verification pass" section.

2. **Tighten `_RATIO_BASELINE`** to the achieved values. Judgement
   call, delegated here deliberately: **do not invent a stretch
   target**. If a file's achieved ratio is barely under its seed,
   record the achieved value, not a rounder smaller one — a baseline
   set below what the tree actually achieves fails the next unrelated
   sprint for no reason. A small amount of headroom on a file that is
   still actively churning is defensible if you say why.

3. **Lower `_BUDGET`** from 388. It measured **356** at planning time
   with 32 lines of slack; tickets 002-006 (especially 005's mechanical
   marker pass over `wire_adapter.cpp` at 49 markers and
   `wire_handler.h` at 48) will have moved it. Set it to the measured
   post-cleanup count. Record the before/after in the constant's own
   comment, following the existing comment's format — that comment is
   the model for how a ratchet change is justified in this repo.

4. **Add a file that is in `src/` but missing from `_RATIO_BASELINE`**
   to the table, if tickets 002-007 or sprints 033/034 introduced one.
   Ticket 001's test reports these rather than failing on them.

5. **Update `sprint.md`'s "Verification pass" table** with the achieved
   numbers alongside the baseline, so the sprint record shows the
   delta. Add a line giving the project-owned aggregate before (1.126)
   and after.

## Acceptance Criteria

- [ ] `src/DESIGN.md` states `kMaxPayloadBytes = 240` consistently; the
      §6/§10 contradiction is gone.
- [ ] The dangling `captures/tovez-wifi-20260902/` path is gone and the
      tracked `docs/knowledge/2026-09-02-wifi-transport-tovez.md`
      citation remains.
- [ ] `src/DESIGN.md` no longer describes a MessageBus RUN bridge, and
      its wording matches what tickets 004/005 wrote in the source.
- [ ] §6 and §8 re-verified against the post-cleanup source; every
      correction listed in the completion notes with its anchor.
- [ ] The §2 upstream provenance references are unchanged and recorded
      as a verified no-op.
- [ ] Findings reported by tickets 002-007 have each been acted on or
      explicitly recorded as out of scope.
- [ ] `_RATIO_BASELINE` re-seeded from a post-cleanup measurement; no
      entry raised above ticket 001's seed without a written reason.
- [ ] `_BUDGET` lowered to the measured post-cleanup marker count, with
      the change justified in its own comment.
- [ ] `sprint.md`'s "Verification pass" table shows baseline vs
      achieved per file, plus the aggregate before/after.
- [ ] Both ratchet tests pass.
- [ ] No source file under `src/`, `test/` or `tools/` is modified by
      this ticket (only `src/DESIGN.md`, the ratchet test, and
      `sprint.md`).

## Testing

Foreground only.

- **Existing tests to run**:

      uv run pytest tests/host/test_archaeology_marker_budget.py -v
      uv run pytest tests/host/ -q
      uv run pytest tests/tools/ -q

  Run the ratchet test with `-v` so the per-file numbers are visible
  and can be pasted into the completion notes.

- **New tests to write**: none — ticket 001 supplied the tests; this
  ticket re-seeds their constants.
- **Verification command**: `uv run pytest tests/host/ tests/tools/ -q`

## Notes for the implementer

- Read every earlier ticket's completion notes before starting Part A.
  This ticket's job is reconciliation, and the findings are in those
  notes.
- Read `sprint.md`'s "Verification pass" section for the baseline
  table and the live/resolved/moot tallies.
- Do not run the full repo suite; `close_sprint` runs it once, after
  this ticket.

## Gate after this ticket

The team-lead runs a **desk firmware build** after this ticket, before
`close_sprint`. That build is this sprint's acceptance for "no
behaviour change": the host suite compiles the portable C++ and the
TypeScript type-check gate covers `blocks/*.ts` and `test/*.ts`, but
neither links the `pxt.h`-bound translation units, and a comment edit
in a `pxt.h`-bound file can still break a real build through a mangled
delimiter or a disturbed `//%` pragma. Nothing in this ticket needs to
run it; leave the tree clean and say so.
