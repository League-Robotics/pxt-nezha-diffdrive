---
id: 008
title: src/DESIGN.md truth pass, re-measure and tighten both ratchets
status: done
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

- [x] `src/DESIGN.md` states `kMaxPayloadBytes = 240` consistently; the
      §6/§10 contradiction is gone.
- [x] The dangling `captures/tovez-wifi-20260902/` path is gone and the
      tracked `docs/knowledge/2026-09-02-wifi-transport-tovez.md`
      citation remains.
- [x] `src/DESIGN.md` no longer describes a MessageBus RUN bridge, and
      its wording matches what tickets 004/005 wrote in the source.
- [x] §6 and §8 re-verified against the post-cleanup source; every
      correction listed in the completion notes with its anchor.
- [x] The §2 upstream provenance references are unchanged and recorded
      as a verified no-op.
- [x] Findings reported by tickets 002-007 have each been acted on or
      explicitly recorded as out of scope.
- [x] `_RATIO_BASELINE` re-seeded from a post-cleanup measurement; no
      entry raised above ticket 001's seed without a written reason.
- [x] `_BUDGET` lowered to the measured post-cleanup marker count, with
      the change justified in its own comment.
- [x] `sprint.md`'s "Verification pass" table shows baseline vs
      achieved per file, plus the aggregate before/after.
- [x] Both ratchet tests pass.
- [x] No source file under `src/`, `test/` or `tools/` is modified by
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

## Completion notes

Three files changed: `src/DESIGN.md`, the ratchet test, and this
sprint's `sprint.md`. **No file under `src/` other than `src/DESIGN.md`,
and no file under `test/` or `tools/`** — `git diff --stat` before the
commit lists exactly `clasi/sprints/035-…/sprint.md`, `src/DESIGN.md`,
`tests/host/test_archaeology_marker_budget.py` (plus `.clasi/.clasi.db`,
which the MCP server maintains). The tree is clean after the commit;
the desk firmware build is the team-lead's step and nothing here needed
it (`src/DESIGN.md` is not a translation unit).

### Part A — `src/DESIGN.md` corrections, anchor → change

| # | § | anchor (quoted content) | change |
|---|---|---|---|
| A1 | 6 | `the comment now states the true relationship: kMaxPayloadBytes is deliberately the **tighter** … The *value* is unchanged — still 200` | Rewritten. The sprint-008 history is kept **as history** (the doc comment did once claim "sized the same as SerialTransport's bound"; radio's cap WAS the tighter one at that time; sprint 008 single-sourced the name, not the value). The present-tense claims are now true: `kMaxPayloadBytes` **is 240**, raised by sprint 010, EQUAL to `SerialTransport::kMaxLineBytes`, `Wire::WireHandler::kMaxLineBytes` and `RadioTransport`'s own private RX capacity — all four the same number — with `tests/host/test_wire_constants_drift.py` naming as the pin. The trailing "still-open finding that a legal `FULL`-mode frame can reach 239 bytes, above this same cap" was a second falsehood in the same sentence and is now "fits under 240, with one byte of headroom (§10)", matching §10's own resolved entry. |
| A2 | 8 | `this constant is deliberately the **tighter** of the two transports' caps (radio's, not serial's 240)` | Same defect, second site — review §5's table listed only the §6 one. Recast as history plus the current equality. The sprint-008 rationale (a clipped line must not depend on which transport carries it; the bare literal was numerically right but disconnected from that rationale) is kept verbatim in substance. |
| A3 | 6 | `Verified on tovez 2026-09-02: \`captures/tovez-wifi-20260902/\`` | Dangling path dropped; the parenthetical description of what was verified is kept inline and the sentence now reads "…recorded in `docs/knowledge/2026-09-02-wifi-transport-tovez.md`". That doc is tracked (`git ls-files --error-unmatch` succeeds), so the citation still names a reachable artifact per `.claude/rules/measurement-citations.md`. This closes ticket 007's outstanding row **A4**. |
| A4 | 5 | `by-name test trigger is protocol.cpp's MessageBus RUN bridge, a CODAL` | Rewritten to match what ticket 005 wrote in `comms/wire_adapter.h`'s `onRun()` comment: "no registration table here … the real by-name test trigger is protocol.cpp's cleartext `RUN:` bridge, `RunBridge` plus `dispatchJob()` running the job on the protocol fiber itself (§8), a CODAL-side mechanism this host-portable class must never touch." Verified against `protocol.h` (`RunBridge runBridge_; void dispatchJob();`) and `protocol.cpp` (`runBridge_.offer(...)`, `dispatchOne()`). |
| A5 | 6 | `bring-up stays lazy-on-first-use (group 10 by default, channel 4 — vevov's fleet assignment — power 7) … Group is the one field a student program can change … Channel and power stay fixed constexpr values with no settable surface.` | **Two falsehoods, found by the §6 re-verification, same class as the ones tickets 004/006 fixed in the source.** (a) 4/10 is not "vevov's fleet assignment" — it is the un-baked placeholder pair `tools/make_deploy.py::_inject_radio_channel()` rewrites per robot in the deploy scratch copy (`radio_transport.h`'s own DO-NOT-REFORMAT block says so, and vevov migrated off 4/10 on 2026-08-30). (b) Channel is **not** fixed with no settable surface: `RadioTransport::setChannel()` exists, `channel_` is mutable, and the student path is the "setup radio channel %channel group %group" block (`run.ts::setupRadio()` → `Protocol::setupRadio()`). Rewritten to state both, with `kTransmitPower` = 7 named as the one radio constant that really has no settable surface, and the UNVERIFIED already-armed re-apply now citing the open issue by its real path `clasi/issues/low/changing-the-radio-group-mid-run-is-unverified.md` (verified present and tracked; ticket 004 corrected the same path in the source). |
| A6 | 8 | `then **two** \`Wire::WireHandler\` instances — \`wireHandler_\` (serial) and \`wireHandlerRadio_\` (radio…) … not two adapters` | Now **three**, naming `wireHandlerWifi_`. The paragraph contradicted its own section: the Fiber-loop paragraph three lines below already names all three, and `protocol.h:459` declares `wireHandlerWifi_`. |
| A7 | 5 | `the real reader is \`diagValue()\`'s ordinal 28, ordinal 30 does not exist in \`diagValue()\` at all` | Present-tense falsehood inside a dated narrative: sprint 033 gave `diagValue()` an ordinal 30 (the RUN bridge's sanitizer-refusal count). Recast as "at that point ordinal 30 did not exist", with a parenthetical noting both namespaces now carry a 30 meaning unrelated things. Found by the diag-ordinal check below. |

### §6 and §8 re-verified against the post-cleanup source

Everything the ticket asked to confirm, plus an identifier sweep:

- **Same-text dedupe window: 400 ms — correct, and it stayed.**
  `src/DESIGN.md` §8 says "A **400 ms** same-text dedupe (at arrival,
  not at handling)"; `run_bridge.h:41` is
  `static constexpr int32_t kDedupe = 400;  // [ms]`. The "was 3000 ms
  until it was cut" sentence beside it is dated history and stays.
- **Single-writer model: correct, no two-fiber claim survives in §6 or
  §8.** §6's "**Single writer: the protocol fiber.** … The `sending_`
  bool and its bounded `kMaxSendAttempts` retry … are **deleted**"
  matches `radio_transport.h`'s own "writer: the protocol fiber" note
  and ticket 004's finding that the retired claim is gone from
  `src/comms/`. The surviving `sending_` / `kMaxSendAttempts` /
  `Protocol::radioEnabled_` / `rxFrames_` / `rxAccepted_` mentions are
  all inside explicit "are **deleted**" / "used to be" clauses — dated
  history, left alone.
- **Diag ordinals: correct against `shims.cpp`'s `diagValue()`.**
  Checked case by case: `case 26` `protocolSerialDropCount()` (§6's
  "diag ordinal 26"), `case 28` `protocolRunDropCount()` (§8's "diag
  ordinal 28" and the diagram's `dropped 28`), `case 30`
  `protocolRunMalformedCount()` (§8's "surfaced at diag ordinal
  **30**"), `case 31..34` the four `protocolRadioRx*Count()` in that
  order (§6's "diag ordinals **31–34**" and the diagram's
  `rx frames/accepted/overrun/oversize 31-34`). The one mismatch found
  anywhere was A7, in §5.
- **Other §6/§8 constants spot-checked and correct**: `kRxDrainPerPass`
  = 4 (`protocol.h:269`); the RUN ring's "8 x 48 slot" (`RunBridge`
  `kSlots = 8`, `kTextBytes = 48`); serial `kRingBytes{255}` and the
  480→224 truncation story (`serial_transport.h`); `kMaxLineBytes` =
  240 "kept equal to `WireHandler::kMaxLineBytes`".
- **Identifier sweep.** Every backticked identifier in §6 and §8 was
  matched against the whole of `src/`. The only ones with no match are
  `Protocol::radioEnabled_`, `kMaxSendAttempts`, `rxFrames_`,
  `rxAccepted_`, `sending_`, `RUN_EVENT_SOURCE`, `emitReliability`,
  `jobOwnsMotion_` — all named in explicitly deleted/retired contexts —
  plus `BOOT_RADIO_LINK` and `tourWorld` (both live in `test/test.ts`,
  which the sweep did not read). No stale live reference remained.

### Verified no-op (as the ticket instructed)

**§2's upstream provenance is CORRECT and unchanged.** The invariant
reads "vendored from
`radio-robot-elite/src/firm/diffdrive/differential_drive.{h,cpp}`" —
the **upstream** path, which is where the kernel really lives; ticket
002 fixed only the two vendored files' *self*-names
(`diffdrive.{h,cpp}`). Not touched. One observation recorded, **not**
acted on: `src/core/diffdrive.h`'s own header names the upstream repo
`League-Robotics/radio-robot` while `src/DESIGN.md` §2 says
`radio-robot-elite`. Which repo name is right is an upstream question,
not a claim this ticket can settle, and the ticket explicitly forbids
"fixing" the provenance statement.

### Reconciliation of tickets 002-007's reported findings

| from | finding | disposition |
|---|---|---|
| 002 | `motion/motion_engine.cpp` still carries dangling `this ticket:` clauses (anti-pattern 4) | **Recorded, out of scope.** They are in `src/motion/`, which this ticket may not touch, and the file's ratio (0.73) is nowhere near its ceiling. Nothing in `src/DESIGN.md` repeats the claim. Worth a row in a later comment pass. |
| 002 | `motion/segment.h`, `motion_limits.h`, `odometry.h` deliberately unchanged | **Recorded.** All three appear in the re-seeded baseline at their unchanged values (1.38 / 1.26 / 1.33), and the sprint.md table shows `cmt before → after` identical for them. |
| 002 | `vMaxMmS_`/`brakeFrac_` "not consulted yet" and `goToWorld` "capped-curvature" already moot | **Confirmed no-op.** Neither phrase occurs in `src/DESIGN.md`. |
| 003 | `vfp_guard.h` / `platform_ports.h` `MEASURED` claims now cite `docs/knowledge/2026-09-01-codal-does-not-save-fpu-registers-across-fibers.md` | **Acknowledged, no doc change needed.** `src/DESIGN.md` does not restate either measurement, so there is nothing to repoint. |
| 003 | `nezha_port.cpp`'s two citations repointed to `captures/tigez-cal-20260830/notes.md`, dependent on 007's `git add -f` | **Closed.** 007's Part A tracked that file (`captures/tigez-cal-20260830/` 4 files); its citation-resolution check shows `tracked=4`. |
| 004 | five further stale claims fixed in `comms/` (`enableRadio()`'s "group 10", a closed issue cited as live, a wrong issue path, a `serialDropCount()` back-reference, a "sprint.md Open Question 1" that resolves to nothing) | **Reconciled against the document.** The "group 10" defect has a twin in `src/DESIGN.md` §6 — fixed as **A5(a)** above, with the same wording ticket 004 used (both constants are deploy-injected). The issue-path correction has a twin too: §6 now cites `clasi/issues/low/changing-the-radio-group-mid-run-is-unverified.md`, the same corrected path. The other three have no counterpart in the document. |
| 004 | `emitLine`'s "deliberately the TIGHTER of the two transports' caps" is now FALSE — the four caps are equal at 240 since sprint 010 | **Acted on, and it overrides this ticket's own Part A item 1.** The ticket text says the tighter-of-two *relationship* "is still true and worth keeping"; ticket 004 proved otherwise from the source, and `test_wire_constants_drift.py::test_radio_transport_doc_comment_states_equality_not_tighter` requires the word "equal" and forbids "tighter" in that comment. So A1 and A2 state the **equality** and keep "tighter" only inside the dated sprint-008 clause where it was true. Recording the override explicitly rather than silently following the stale instruction. |
| 004 | `formatDiag()` and the two-fiber writer model already resolved | **Confirmed no-op** in the document (see the §6/§8 verification above). |
| 005 | two `MEASURED`/`Measured` claims in `wire_handler.cpp` (`emitHelp()`, `execGet()`) name a board and date but **no artifact**, and disagree with each other and with `emitReminderIfStalled()` — 66-75% vs 66-83% per-line delivery | **Recorded as an open follow-up finding; nothing invented, nothing edited.** Out of this ticket's file scope in any case (`src/comms/`). `src/DESIGN.md` does not repeat either figure, so the document needs no change. Recommend an issue: locate the 2026-08-27 tovez torture-relay capture, repoint all three claims at it and reconcile the two ranges, or mark them UNVERIFIED. |
| 005 | `gapOutstanding_` is LIVE, not deleted — no follow-up needed | **Confirmed.** `src/DESIGN.md` makes no claim about the field either way; nothing to correct. |
| 005 | `wire_adapter.h`'s `onRun()` comment rewritten (no MessageBus, no `runSlots_`) | **This is the source text A4 was matched to.** The document and the code now say the same thing. `runSlots_` occurs nowhere in `src/DESIGN.md`. |
| 006 | the `run.ts` JSDoc "group 10" claim was blocked (JSDoc out of scope) and deferred to `clasi/issues/run-ts-jsdoc-still-says-radio-group-10.md` | **Recorded; still open, and the document no longer shares the defect** — A5(a) removes `src/DESIGN.md`'s own version of it. The deferred issue is `src/blocks/run.ts`'s student-facing JSDoc and needs a ticket with JSDoc explicitly in scope. |
| 006 | two `MEASURED` claims in `test/test.ts` (lines ~320 and ~941) name no artifact | **Recorded, out of scope.** `test/` may not be modified by this ticket, neither claim was introduced or stripped by this sprint, and inventing a citation is forbidden. Same recommended disposition as 005's pair. |
| 006 | BT-08 (`motion.ts` `goTo` / `defaultYawRate`) resolved by sprint 032 | **Confirmed no-op.** No counterpart claim in `src/DESIGN.md`. |
| 007 | **A4 outstanding for ticket 008**: `src/DESIGN.md`'s dangling `captures/tovez-wifi-20260902/` | **Closed by A3.** With that path gone, every `captures/` citation from `src/` (including `src/DESIGN.md`) resolves in a fresh clone — the sprint's second success criterion. |
| 007 | three capture citations **outside** `src/` still do not resolve (`captures/vevov-cal-20260902`, `captures/vevov-line-20260902/deskew-clean.jpeg` untracked; `captures/consolidation-acceptance-tigez-20260906` absent from disk) | **Recorded, out of scope** — the sprint's acceptance is scoped to citations from `src/`, and none of the three is cited from `src/DESIGN.md` (checked). Worth an issue, especially the third: an absent directory cannot be tracked, only repointed or produced. |
| 007 | `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` now itself carries the stale "camlink says mount registrations are NOT persisted" description, and its "tag 57 missing from `MOUNTS`" item is doubly moot | **Recorded, deliberately not edited** — `.claude/` is outside this ticket's scope and the dispatch forbids touching it. The rules file's §"Why this kept happening" items (2) and (3) both describe a `tools/camlink.py` that ticket 007 has since corrected; item (3)'s `MOUNTS` table no longer exists at all. Needs its own edit. |
| 002-006 | a `src/` file introduced with no `_RATIO_BASELINE` entry | **None.** `test_comment_volume_ratio_is_within_per_file_baseline` reports unbaselined files rather than failing on them; it reported none. The file set is the same 46 as ticket 001's seed — no additions, no deletions, no stale entries. |

Sprint 033/034 removals also re-checked in `src/DESIGN.md`, per the
dispatch: `EncoderPoseSource` (4 mentions, every one dated or
explicitly "RETIRED in sprint 033" — historical narrative, left),
`deliverStopNow()` (2 mentions, both "…then; `Rig::softStop()` since
sprint 033 folded that free function into it" — left), `kFields` (2
mentions, both "is gone" / "Before this consolidation there were" —
left), `camproc`, `pendingGoToDeadlineMs_` and `place()` (**zero**
occurrences). No present-tense falsehood among them.

### Part B — re-measurement

Counting rule re-derived from the module docstring, not re-invented:
a line is a COMMENT line iff, stripped of leading whitespace, it begins
with `//` and NOT `//%`; every other non-blank line is CODE; blanks are
neither. Measured by importing `_comment_ratio_by_file()` and
`_marker_line_count()` from the test module itself, so the numbers below
are by construction the ones the ratchet compares against.

`src/DESIGN.md` is a `.md` file and no suffix in `_SOURCE_SUFFIXES`
matches it, so Part A moved neither ratchet; the measurement was
nonetheless taken after Part A landed.

**`_BUDGET`: 388 → 173.** (356 at detail-planning time; tickets 002-006
took it to 173, with ticket 005's four `comms/wire_*` files alone
accounting for 110 of the reduction.) The change is justified in the
constant's own comment, in the existing comment's format — what the old
number was and why it differed from the audit's 363, what the new one
measures against, and why 173 is not a floor to drive to zero (the
remaining 103 markers in the four biggest files are dominated by live
spec citations the regex deliberately does not distinguish).

**Aggregate: 7866 / 6987 = 1.126 before → 6585 / 6987 = 0.943 after.**
The 6987 code-line total is byte-identical before and after — the whole
sprint deleted comment lines and nothing else.

**`_RATIO_BASELINE`: re-seeded to the achieved values, all 46 entries.**
No entry was raised above ticket 001's seed and none was given invented
headroom, per the ticket's judgement call: a baseline below what the
tree achieves fails the next unrelated sprint for no reason, and one
above it gives back ground this sprint paid for. Three files
(`core/encoder_glitch_armor.h`, `motion/segment.h`, `blocks/motion.ts`)
now sit within `_RATIO_TOLERANCE`'s slack of their ceiling; that is
stated in the constant's comment so the next author reads it as
"raise this entry deliberately", which is what the failure message
already tells them to do. The tolerance comment's worked example was
re-derived too: 25 of 46 files (not 20) now sit fractionally above their
printed two-decimal baseline, and the example file is
`blocks/motion.ts` at 0.174941 printed 0.17 (`shims.cpp` now rounds up,
so it no longer illustrates the point).

| file | code | cmt before → after | baseline → achieved |
|---|---|---|---|
| `comms/wire_adapter.h` | 70 | 382 → 262 | **5.46** → **3.74** |
| `comms/radio_transport.h` | 70 | 370 → 258 | **5.29** → **3.69** |
| `comms/serial_transport.h` | 18 | 93 → 70 | **5.17** → **3.89** |
| `motion/motion_engine.h` | 107 | 508 → 396 | **4.75** → **3.70** |
| `comms/protocol.h` | 98 | 434 → 351 | **4.43** → **3.58** |
| `core/fiber_identity.h` | 7 | 29 → 28 | **4.14** → **4.00** |
| `core/bus_guard.h` | 18 | 72 → 48 | **4.00** → **2.67** |
| `core/heading_wrap.h` | 11 | 44 → 31 | **4.00** → **2.82** |
| `platform/vfp_guard.h` | 13 | 50 → 46 | **3.85** → **3.54** |
| `core/motion_owner.h` | 18 | 66 → 64 | **3.67** → **3.56** |
| `core/encoder_glitch_armor.h` | 44 | 125 → 108 | **2.84** → **2.45** |
| `comms/wire_handler.h` | 220 | 580 → 455 | **2.64** → **2.07** |
| `comms/run_bridge.h` | 34 | 84 → 79 | **2.47** → **2.32** |
| `comms/transport_sink.h` | 24 | 54 → 46 | **2.25** → **1.92** |
| `motion/velocity_shaper.h` | 20 | 43 → 38 | **2.15** → **1.90** |
| `comms/config_fields.h` | 59 | 101 → 95 | 1.71 → 1.61 |
| `shims.cpp` | 710 | 1215 → 1007 | 1.71 → 1.42 |
| `comms/wifi_uart.h` | 19 | 30 → 30 | 1.58 → 1.58 |
| `motion/segment.h` | 65 | 90 → 90 | 1.38 → 1.38 |
| `motion/odometry.h` | 57 | 76 → 76 | 1.33 → 1.33 |
| `comms/wire_adapter.cpp` | 397 | 522 → 474 | 1.31 → 1.19 |
| `comms/protocol.cpp` | 338 | 431 → 389 | 1.28 → 1.15 |
| `motion/motion_limits.h` | 58 | 73 → 73 | 1.26 → 1.26 |
| `motion/velocity_shaper.cpp` | 54 | 65 → 65 | 1.20 → 1.20 |
| `comms/emit_queue.h` | 49 | 50 → 39 | 1.02 → 0.80 |
| `platform/platform_ports.h` | 27 | 27 → 20 | 1.00 → 0.74 |
| `platform/nezha_port.cpp` | 255 | 244 → 189 | 0.96 → 0.74 |
| `comms/wire_handler.cpp` | 834 | 717 → 565 | 0.86 → 0.68 |
| `comms/serial_transport.cpp` | 52 | 43 → 43 | 0.83 → 0.83 |
| `platform/nezha_port.h` | 74 | 59 → 58 | 0.80 → 0.78 |
| `motion/motion_engine.cpp` | 299 | 224 → 218 | 0.75 → 0.73 |
| `platform/otos_port.h` | 69 | 52 → 52 | 0.75 → 0.75 |
| `comms/run_queue.h` | 61 | 39 → 36 | 0.64 → 0.59 |
| `comms/wifi_link.h` | 226 | 145 → 145 | 0.64 → 0.64 |
| `blocks/sim.ts` | 379 | 236 → 165 | 0.62 → 0.44 |
| `comms/radio_transport.cpp` | 112 | 65 → 64 | 0.58 → 0.57 |
| `platform/vfp_guard.cpp` | 12 | 7 → 7 | 0.58 → 0.58 |
| `comms/run_bridge.cpp` | 61 | 34 → 34 | 0.56 → 0.56 |
| `blocks/world.ts` | 157 | 70 → 71 | 0.45 → 0.45 |
| `comms/wifi_uart.cpp` | 31 | 11 → 11 | 0.35 → 0.35 |
| `platform/otos_port.cpp` | 163 | 44 → 44 | 0.27 → 0.27 |
| `blocks/run.ts` | 243 | 61 → 56 | 0.25 → 0.23 |
| `blocks/motion.ts` | 423 | 81 → 74 | 0.19 → 0.17 |
| `comms/wifi_link.cpp` | 844 | 113 → 113 | 0.13 → 0.13 |
| `blocks/stop.ts` | 49 | 6 → 1 | 0.12 → 0.02 |
| `blocks/pose.ts` | 38 | 1 → 1 | 0.03 → 0.03 |
| *(vendored, excluded)* `core/diffdrive.h` | 303 | 71 → 71 | 0.23 → 0.23 |
| *(vendored, excluded)* `core/diffdrive.cpp` | 851 | 100 → 100 | 0.12 → 0.12 |
| *(not in `src/`)* `test/test.ts` | 482 | 645 → 619 | 1.34 → 1.28 |

`blocks/world.ts` is the one file whose comment count went **up**, by a
single line: ticket 006's factual fix 5 split one wrong statement
("every read here is a live I2C burst") into the two true ones. Its
ratio still rounds to 0.45 and its baseline is unchanged.

Marker count 173, by file: `shims.cpp` 33, `comms/wire_handler.cpp` 24,
`motion/motion_engine.h` 24, `comms/wire_handler.h` 22,
`motion/motion_engine.cpp` 12, `comms/wire_adapter.cpp` 11,
`comms/wire_adapter.h` 6, `core/encoder_glitch_armor.h` 5,
`platform/nezha_port.cpp` 5, `comms/radio_transport.h` 4,
`platform/otos_port.h` 4, `blocks/sim.ts` 3, `motion/motion_limits.h` 3,
`motion/segment.h` 3, `blocks/motion.ts` 2, `motion/odometry.h` 2, and
one each in `blocks/world.ts`, `comms/protocol.cpp`,
`comms/radio_transport.cpp`, `comms/transport_sink.h`,
`core/heading_wrap.h`, `motion/velocity_shaper.cpp`,
`motion/velocity_shaper.h`, `platform/nezha_port.h`,
`platform/otos_port.cpp`, `platform/vfp_guard.h`.

`sprint.md`'s "Verification pass" table now carries the
`cmt before → after` and `baseline → achieved` columns above, the
aggregate before/after line, and the marker line updated to
"**356** at detail-planning time … **173** after tickets 002-006;
ticket 008 lowered `_BUDGET` 388 → 173". Nothing else in `sprint.md`
was touched.

### Tests (foreground, this turn)

    uv run pytest tests/host/test_archaeology_marker_budget.py -v
    tests/host/test_archaeology_marker_budget.py::test_archaeology_marker_count_is_within_budget PASSED [ 33%]
    tests/host/test_archaeology_marker_budget.py::test_comment_counting_rule_matches_its_specification PASSED [ 66%]
    tests/host/test_archaeology_marker_budget.py::test_comment_volume_ratio_is_within_per_file_baseline PASSED [100%]
    ============================== 3 passed in 0.10s ===============================

    uv run pytest tests/host -q    -> 1167 passed in 31.64s
    uv run pytest tests/tools -q   ->  608 passed in 28.59s

Both `tests/host` and `tests/tools` were run in full because several
`tests/host/` tests read `src/DESIGN.md` as text
(`test_no_stale_src_paths.py`, `test_pxt_bound_exclusion_is_current.py`,
`test_soft_stop_source_pin.py`, `test_otos_product_id_single_source.py`
and others), so a scoped run would not have covered this ticket's own
diff. The per-file numbers are not printed by a passing `-v` run — the
ratchet only emits them in its failure message — so the table above was
produced by calling the module's own `_comment_ratio_by_file()` and
`_marker_line_count()` directly.

No version bump (sprint cadence: `close_sprint` bumps once).
