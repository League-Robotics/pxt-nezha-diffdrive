---
id: 009
title: 'Hygiene: comment cleanup and upstream re-diff'
status: executing
branch: sprint/009-hygiene-comment-cleanup-and-upstream-re-diff
use-cases:
- SUC-001
- SUC-002
issues:
- comment-cleanup-work-order.md
- vendored-kernel-upstream-rediff.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 009: Hygiene: comment cleanup and upstream re-diff

> **Arc position.** Fifth and closing sprint out of the 2026-08-23 code
> review (`docs/code-review/2026-08-23/review.md`), after sprint 004
> (radio/wire transport, ticketing), sprint 005 (bench tooling, roadmap,
> blocked on 004's hardware checkpoint), sprint 006 (motion correctness,
> roadmap), sprint 007 (student API, roadmap), and sprint 008 (wire
> hardening, roadmap). It runs **deliberately last, not by triage order but
> by necessity**: sprints 006-008 rewrite many of the same regions this
> sprint's comment audit covers (`shims.cpp`, `wire_handler.*`,
> `wire_adapter.*`, `protocol.*`, the settle-tick loop). Comment cleanup
> against pre-fix code would be thrown away or re-diffed the moment any of
> those three sprints lands; running it last means the audited work order
> applies once, to the code as it actually ends up, with no rework. This
> is also why the sprint is behavior-neutral by design — a hygiene pass
> that changes behavior would need to be re-validated against whatever
> 006-008 changed underneath it, defeating the point of going last.

## Goals

Theme: **comments say only what's true and load-bearing, and the vendored
kernel's relationship to its upstream is documented and current.** Two
issues, one theme (the codebase's *written record* — comments and
provenance — catches up to what the code actually does), zero behavior
change:

- Apply the audited 135-item comment work order (11 DELETE, 123 REWRITE,
  1 ADD out of ~854 blocks across 59 files) from
  `docs/code-review/2026-08-23/raw/comment-audit.md`, corrected by
  `docs/code-review/2026-08-23/raw/verify-comments.md` wherever the two
  disagree. Spot-verification already found 8 of 16 sampled rewrites would
  have lost load-bearing content (worst case: a wrong calibration constant
  baked into the rotationalSlip derivation), so the correction pass is not
  optional cleanup — it is the difference between a hygiene sprint and a
  silent regression sprint.
- Restore the five truncated `diffdrive.h` comments (lines 81, 84, 90, 91,
  125) from the upstream text already recovered in verify-comments.md, and
  re-diff `src/diffdrive.h/.cpp` against current upstream
  `League-Robotics/radio-robot` `src/firm/diffdrive/` to catalogue every
  remaining divergence as deliberate (documented) or accidental (fixed or
  backported) — closing the possibility that a lossy vendoring step lost
  code deltas along with comment text, the way it lost the
  `fullDutyVelocity = 0` "uncalibrated -> VELOCITY refused" contract that
  the cruise-sentinel bug later tripped over.
- Fix the provenance pointers themselves: `src/DESIGN.md` and
  `overview.md` §Provenance both still name an old upstream path; the
  upstream kernel has moved to `src/firm/diffdrive/`
  (`differential_drive.h`), and two places name a repo variant that
  doesn't exist. State the maintenance boundary (what may be edited here
  vs. upstream) alongside the corrected path.
- Distill the audit's five recurring comment anti-patterns
  (ticket-archaeology headers, reviewer-justification essays, stale
  cross-layer claims, diff restatement, orphaned comments) into a short
  comment-standards section of `docs/code-review/guidelines.md`, so the
  next round of work doesn't regenerate the same noise this sprint
  deletes.

## Problem

Two related but independent gaps, both filed as LOW-priority findings
from the 2026-08-23 review's comment-hygiene dimension (R-28 and the
comment work order in `review.md` §"Comment hygiene (work order)"):

1. **Signal-to-noise in comments.** The audit classified ~854 comment
   blocks across 59 files and found ~16% pure noise, concentrated in the
   wire-layer headers (`serial_transport.h` 83%, `wire_adapter.h` 71%,
   `tests/host/README.md` 60%): ticket archaeology, restated diffs,
   reviewer-justification essays, and cross-layer claims that no longer
   match the code. Left alone, this noise compounds — every future editor
   reads it, half-trusts it, and sometimes copies the pattern forward.
2. **Unverified vendoring boundary.** The kernel (`src/diffdrive.h/.cpp`)
   was vendored from `League-Robotics/radio-robot` at some point in the
   past, but the copy is known-lossy: five comments are truncated
   mid-sentence, and one of the lost halves encoded a real behavioral
   contract, not just prose. If comment text was truncated during
   vendoring, code deltas may have been dropped too, and nobody has
   re-diffed against upstream to check. The provenance pointers that are
   supposed to document this boundary (`src/DESIGN.md`,
   `overview.md` §Provenance) also point at a path upstream no longer
   uses.

## Solution

Two issues, worked together because they share a "read the written
record, correct it against ground truth, don't change behavior" shape,
and because both touch `src/diffdrive.h` (the re-diff restores the same
five comments the work order's item list also names — doing this once,
not twice):

- **`comment-cleanup-work-order.md`**: apply `comment-audit.md`'s
  delete/rewrite/add work order, with every item — sampled or not —
  checked against `verify-comments.md`'s corrections and, for anything
  outside the 27 already spot-checked, against the same test
  spot-verification applied: does the replacement preserve every
  invariant, unit, measured value, and derivation the original comment
  carried? Restore (not paraphrase) the five upstream-truncated
  `diffdrive.h` comments per item 3 of the issue. Fix
  `tests/host/README.md`'s stale "does NOT cover yet" section per the
  audit. Fold the five anti-patterns into `docs/code-review/guidelines.md`
  as a follow-up in the same work, so the standard is written down once
  the noise it targets has actually been removed.
- **`vendored-kernel-upstream-rediff.md`**: diff `src/diffdrive.h/.cpp`
  against `League-Robotics/radio-robot`'s current `src/firm/diffdrive/`.
  Every divergence gets catalogued as deliberate (documented in place) or
  accidental (fixed or backported — but only where the divergence proves
  accidental; see Scope). Correct the provenance path and repo-variant
  references in `src/DESIGN.md` and `overview.md` §Provenance, and add
  the maintenance-boundary statement (what's edited here vs. upstream)
  that both currently lack.

Because both issues touch the same file (`diffdrive.h`'s five truncated
comments), Detail Mode should sequence the re-diff's comment restoration
and the work order's `diffdrive.h` items as one coordinated ticket-level
edit, not two independent passes that could each partially clobber the
other's changes to the same lines.

## Success Criteria

- All 135 audited comment items applied, with every REWRITE (sampled and
  unsampled) checked against `verify-comments.md` and against the "does
  this preserve every invariant, unit, measured value, and derivation"
  test — zero load-bearing content lost.
- The five `diffdrive.h` truncated comments (lines 81, 84, 90, 91, 125)
  read the full upstream text, not a paraphrase.
- `src/diffdrive.h/.cpp` has been diffed against current upstream
  `League-Robotics/radio-robot src/firm/diffdrive/`; every divergence is
  either documented as deliberate or fixed/backported as accidental.
- `src/DESIGN.md` and `overview.md` §Provenance name the correct upstream
  path (`src/firm/diffdrive/`, `differential_drive.h`) and no longer
  reference a nonexistent repo variant; both state the maintenance
  boundary.
- `docs/code-review/guidelines.md` has a comment-standards section
  covering the audit's five anti-patterns.
- `tests/host/README.md`'s stale coverage section is corrected.
- The scoped test suites for every touched module pass unchanged —
  proving the sprint is behavior-neutral (comments/docs-only, plus any
  accidental-divergence fixes in `diffdrive.*` that the re-diff surfaces).

## Scope

### In Scope

- Comment and doc-text edits across `src/`, `tests/host/`, `tools/`, and
  `test/`, per the audited work order and its corrections.
- `src/diffdrive.h/.cpp`: comment restoration (the five truncated
  comments) plus code changes **only where the upstream re-diff proves a
  divergence is accidental** (e.g., a dropped guard or constant upstream
  still carries) — not a general refactor of the kernel.
- Provenance-pointer corrections in `src/DESIGN.md` and
  `overview.md` §Provenance, including the maintenance-boundary statement.
- A new comment-standards section in `docs/code-review/guidelines.md`.

### Out of Scope

- Any behavior change to `diffdrive.h/.cpp` beyond fixing divergences the
  re-diff shows to be accidental — this is not a place to opportunistically
  "improve" the kernel logic.
- Anything owned by sprints 006, 007, or 008 (motion correctness, student
  API, wire hardening) — this sprint runs after them specifically to avoid
  overlapping their code changes.
- Renumbering, restructuring, or otherwise reorganizing files beyond
  comment/doc-text content.
- New tests beyond what's needed to confirm the scoped modules are
  unchanged in behavior (this is a comment/doc sprint, not a
  test-coverage sprint).

## Test Strategy

Behavior-neutral by construction, so the bar is regression, not new
coverage: run the existing scoped test suites (host tests plus whatever
`test/`/`tools/` coverage exists) for every module touched by the comment
work order and the `diffdrive.*` re-diff, before and after, and confirm
no output changes. Any accidental-divergence fix the re-diff surfaces in
`diffdrive.*` gets its own targeted verification against the specific
behavior upstream defines (e.g., the `fullDutyVelocity = 0` refusal
semantics), since that one class of change is not purely cosmetic. No new
test infrastructure is anticipated; Detail Mode should confirm this
against actual coverage gaps once tickets are scoped.

## Architecture

**Sizing: Substantial** — by module count alone: this sprint's comment
work order and upstream re-diff touch every layer of `src/DESIGN.md`'s
layer map (kernel, motion engine, wire grammar, wire adapter,
transports, hardware ports, protocol composition, shim + blocks) plus
`test/`, `tests/host/`, and `tools/` — 59 files audited, ~20 more
touched incidentally by the provenance sweep and guidelines update.
That clears the "3+ modules touched" substantial-tier signal by a wide
margin. But — mirroring sprint 020's own precedent — **no component,
ERD, or dependency-graph diagram is included**: this sprint introduces
no new module, no new or changed cross-module dependency, no
dependency-direction change, and no data-model change. It rewrites and
deletes comments (behavior-neutral by construction) and, in one
narrowly-scoped exception, fixes only those `diffdrive.{h,cpp}`
divergences the upstream re-diff proves accidental. A diagram would
show the same layer map `src/DESIGN.md` §1 already draws, unchanged;
it would clarify nothing this sprint actually does.

### Architecture Overview

**What changed.** Two coordinated efforts, both landing in
`src/diffdrive.h`/`.cpp` first because they share those two files:

1. **Vendored-kernel re-diff and restoration**
   (`vendored-kernel-upstream-rediff.md`). `diffdrive.h`'s five
   comments truncated mid-sentence during a lossy vendoring step are
   restored verbatim from the upstream text `verify-comments.md` §3
   already fetched and confirmed against `League-Robotics/radio-robot`'s
   current tree (kernel now at `src/firm/diffdrive/`, not the stale
   `src/firm/control/` path several local comments and both design
   docs still name). The full pair is re-diffed against that upstream
   location; any divergence beyond comments is catalogued as
   deliberate or fixed if proven accidental. `src/DESIGN.md` gains one
   authoritative provenance statement (current repo, current path,
   maintenance boundary) that per-file headers point at instead of
   each restating a path that goes stale — closing the exact failure
   mode that let `src/firm/control/` survive as long as it did.
   `overview.md` §Provenance and `specification.md` §12 — which
   already *flag* the README/source discrepancy without resolving it —
   get resolved, pointing at `src/DESIGN.md` as the one place path
   details live.

2. **Comment-hygiene work order** (`comment-cleanup-work-order.md`).
   `comment-audit.md`'s 135-item work order (11 DELETE, 123 REWRITE, 1
   ADD) applies across 59 files, corrected wherever
   `verify-comments.md`'s adversarial spot-check overrides it — 8 of
   16 sampled REWRITEs would otherwise have destroyed load-bearing
   content, so every REWRITE not among the 16 sampled gets the same
   "does the replacement preserve every invariant, unit, measured
   value, and derivation" check before landing, not just the sampled
   ones. `docs/code-review/guidelines.md`'s existing comment-hygiene
   dimension gains a short section distilling the audit's five
   recurring anti-patterns, written after the cleanup lands so it can
   point at what was actually removed.

**Why this shape.** The audit and its corrections are both roughly
five months stale relative to `src/`'s current state — sprints
006/007/008 rewrote large parts of exactly the files this work order
targets (`shims.cpp`, `wire_handler.*`, `wire_adapter.*`, `protocol.*`,
the settle-tick loop) after the audit ran. Two consequences drive every
ticket's plan, not just a general caution:

- **Line numbers are stale.** Every ticket re-anchors its items by
  content match against current source, not by the audit's line
  numbers, which have shifted or no longer exist.
- **Some audited comments have been superseded by better ones.** Six
  confirmed instances — three named in the sprint charter, three more
  found while cross-referencing `src/DESIGN.md`'s own sprint 006-008
  change-summary sections during planning:
  - `motion_engine.h`'s `rotationalSlip_` comment (audit lines
    335-346) — sprint 007 ticket 005 already expanded it with the
    full measurement-to-constant derivation chain and an explicit
    "do not set `rotationalSlip_` to 0.915" caution. The audit's own
    REWRITE (and even `verify-comments.md`'s R9 correction) predates
    that expansion and would shorten it back. **Ticket 002 verifies
    this item is already satisfied — it does not overwrite it.**
  - `shims.cpp`'s `tickDrive()` banner and the settle-loop essay
    (audit lines 427-447, 501-519) — sprint 008 replaced the inline
    settle loop with a call into a new `MotionEngine` helper and
    rewrote this region; the audit's proposed text describes the
    *pre-008* inline loop. **Ticket 008 re-derives this comment from
    current code**, keeping the audit's anti-pattern guidance (drop
    ticket refs, state the KNOWN GAP crisply) without pasting stale
    prose over a newer, correct one.
  - `wire_handler.cpp`'s motion-verb decode region (audit lines
    433-437, 741-749) — sprint 008 added the shared decode-time
    `duration`/`timeout` clamp (WIRE-02/KERN-06/WIRE-10) in this exact
    area. **Ticket 003 confirms the current comment already documents
    the clamp before applying any audit text.**
  - `radio_transport.h`'s `kMaxPayloadBytes` comment (audit lines
    118-125; `verify-comments.md`'s R14 correction) — both the audit
    and R14 assume the comment still claims equality with
    `SerialTransport`'s cap. Sprint 008 already rewrote this exact
    comment to state the true (tighter-cap) relationship as part of
    its own WIRE-05/R-21 single-sourcing fix. **Ticket 005 reads the
    live comment first**; if sprint 008's fix already meets the
    dimension-6 bar, this item is a no-op.
  - `protocol.cpp`'s identity-constants essay (audit lines 30-63)
    describes `kVersion` as "a manually-synced mirror... the sync is
    currently broken (1.0.0 vs 1.0.10)" — sprint 008 fixed that exact
    drift (`kVersion` is now single-sourced or drift-tested against
    `pxt.json`). **Ticket 006 must not reintroduce the "currently
    broken" claim.**
  - `protocol.h`'s retired-TLM note (audit lines 47-61) describes v6
    as having "no data-bearing telemetry frame yet" — sprint 004
    built that frame. **Ticket 006 corrects this to reflect the
    shipped telemetry projection**, leaving only the `tools/` retrofit
    gap (still real, still sprint 005's scope) as the KNOWN GAP.
- **New files the audit never saw**: `heading_wrap.h`,
  `encoder_glitch_armor.h`, `encoder_pose_source.h` (sprint 006), and
  the sprint 006-008 `tests/host/test_*.py`/shim files. **Decision:
  out of the 135-item work order** — nothing in the audit names them,
  so there is nothing to "apply" — but tickets 009/010 spot-check them
  against the new comment-standards section for the same five
  anti-patterns, fixing only unambiguous instances (a stray ticket
  tag) rather than opening a second full audit. These files were
  written after dimension-6 review became routine and read clean in
  the sampling done during planning.

**Provenance-name sweep beyond `diffdrive.*`.** The re-diff issue's
problem statement is broader than its own "What to do" list: "both
this repo's vendoring comments **and** two of the comment audit's
proposed replacements name the unresolvable repo." Reading current
source during planning confirms this: `otos_port.h` (×2),
`otos_port.cpp`, `radio_transport.h`, `radio_transport.cpp`, and
`nezha_port.cpp` (×2) all currently say `radio-robot-elite` in live,
unaudited, KEEP-tagged comments — not just the audit's proposed
`diffdrive.{h,cpp}` rewrites. `nezha_port.h`'s own header already says
the correct `radio-robot`, so the tree is internally inconsistent
about its own upstream's name. Ticket 007 sweeps all of these to point
at `src/DESIGN.md`'s new authoritative statement, consistent with the
issue's stated goal even though its own numbered action list names
only `diffdrive.*` explicitly.

**Behavior-neutral, proven two ways.** No ticket changes wire grammar,
motion math, or hardware timing, with one narrow exception (ticket
001's accidental-divergence fix, if the re-diff finds one — verified
against the specific upstream contract it restores, e.g. the
`fullDutyVelocity == 0` refusal). Every ticket scopes its test run to
the modules it touches; ticket 012 is the mandatory final
build-checkpoint (per `src/DESIGN.md` §11's standing convention since
sprint 008) that runs the full host suite and produces a flashable hex
via `make_deploy.py` — the host suite proves no host-visible output
changed, the checkpoint proves the files `test_cxx11_syntax_gate.py`
doesn't cover (`protocol.*`, `*_transport.*`, the hardware ports,
`shims.cpp`) still link for the real target. Neither alone is
sufficient; both run.

**Deliberately out of scope, with the disposition stated so it isn't
silently dropped:**
- `tools/otos_levercal.py` still sends `RUN:8`/`RUN:14`, which current
  firmware doesn't answer (the real trigger is
  `RUN:cal`/`RUN:cal:1`). The audit calls this a code bug, not a
  comment problem; fixing it would violate this sprint's
  behavior-neutral constraint (bench tooling is still project
  behavior, just not robot firmware). Ticket 010 corrects the
  *comment* to state the mismatch honestly and leaves the call in
  place, noting the audit's broader "handoff-2" class (several tools
  speak a retired wire vocabulary) in its completion notes for the
  team-lead to file as a follow-up issue.
- `wire_adapter.cpp`'s DIAG-has-no-v6-equivalent note (the audit's own
  "file it as an issue" instruction) — ticket 004 keeps the compressed
  comment the audit specifies and notes the filing request in its
  completion notes rather than creating a new issue mid-execution.

### Design Rationale

**Decision: partition tickets by `src/DESIGN.md`'s own layer map,
kernel first.** *Context*: 135 items need to land in units small
enough to review but few enough to plan. *Alternatives*: one ticket
per audited file (59 — too fine-grained, most files are a handful of
lines); one ticket per DELETE/REWRITE/ADD risk class (3 — too coarse,
mixes unrelated files with wildly different superseded-content risk).
*Why this choice*: the codebase's own layer map already groups files
by "changes for the same reason" — the cohesion test this process
applies to architecture — so reusing it for ticket boundaries means
each ticket's reviewer only needs one layer's mental model loaded, and
the kernel (highest stakes: the re-diff, the 0.952/0.915 near-miss
precedent) goes first so the riskiest work isn't discovered last.
*Consequences*: 12 tickets rather than a smaller number — acceptable
per this sprint's own "135 items is a lot for one ticket" instruction;
ticket 007 (hardware ports) is the one ticket that depends on ticket
001, since it points several files' provenance comments at the
authoritative statement ticket 001 writes.

**Decision: treat the new sprint-006/007/008 files as out of the
135-item work order, not silently folded into it.** *Context*:
sprint.md requires an explicit in/out decision for files the audit
never saw. *Alternatives*: fold them into the nearest layer ticket and
audit them fresh; ignore them entirely. *Why this choice*: the
135-item count is a specific, sized, reviewed work order; silently
expanding it either invents unaudited work with no `verify-comments.md`
coverage to check it against, or silently drops newer files from a
sprint whose whole theme is "the written record catches up to the
code." A bounded spot-check against the same five anti-patterns
threads that needle without opening a second full audit.
*Consequences*: tickets 009/010 carry a small, explicitly-bounded
extra task; a spot-check finding real noise gets fixed only where
unambiguous, with anything larger noted for a future sprint rather
than expanding scope mid-execution.

**Decision: no diagram.** *Context*: substantial tier by module count
normally warrants one. *Alternatives*: draw the layer map anyway for
completeness. *Why this choice*: sprint 020's own precedent — a
diagram earns its place by clarifying composition, and this sprint
composes nothing new; `src/DESIGN.md` §1's existing layer-map table
already is that diagram, unchanged. *Consequences*: none — the
existing table remains the reference; this sprint touches §2's prose
only, to correct the kernel's provenance path.

### Migration Concerns

None. No data migration, no wire-format change, no deployment
sequencing beyond the ordinary flash cycle ticket 012's checkpoint
exercises. The one class of change with any runtime effect — an
accidental-divergence fix in `diffdrive.{h,cpp}` the re-diff might
surface — is scoped narrowly (ticket 001) and gets its own targeted
verification against the specific upstream contract it restores, per
the Test Strategy above.

## Use Cases

No student-facing or robot-behavior use case is added or changed —
this sprint is comment- and documentation-only by construction (one
narrow, re-diff-justified exception scoped to ticket 001). The two
sprint-level use cases below describe the *maintainer's* experience,
which is what this sprint actually changes; neither parents a UC-XXX
from `docs/design/usecases.md`, since none of those describe reading
or trusting source comments.

### SUC-001: A contributor reads a vendored kernel comment and trusts it
Parent: N/A — maintainability, not a functional use case

- **Actor**: A future contributor re-syncing or debugging the vendored
  kernel.
- **Preconditions**: `diffdrive.h`/`.cpp` carry comments truncated
  during a past lossy vendoring step, and the provenance comment names
  a repository that does not resolve.
- **Main Flow**:
  1. The contributor opens `diffdrive.h` to check a config field's
     contract (e.g., `maxDuty`, `fullDutyVelocity`).
  2. The comment states the complete contract, including sentinel
     meanings, without needing to cross-reference `checkCommandable()`
     to guess what a truncated comment might have meant.
  3. The contributor follows the provenance comment to
     `src/DESIGN.md`'s one authoritative statement of the current
     upstream repo and path, instead of hitting a dead repository
     name or a path upstream no longer uses.
- **Postconditions**: The five truncated comments read complete
  upstream text; `src/diffdrive.h`/`.cpp` have been diffed against
  current upstream with every divergence catalogued; the provenance
  statement resolves, not merely flags, the README/source discrepancy
  `specification.md` §12 previously left open.
- **Acceptance Criteria**:
  - [ ] Lines 81, 84, 90, 91, and 125 of `diffdrive.h` read complete
        upstream sentences, not paraphrases.
  - [ ] `src/DESIGN.md`, `overview.md` §Provenance, and
        `specification.md` §12 all name `League-Robotics/radio-robot`
        and `src/firm/diffdrive/` and state the maintenance boundary.
  - [ ] No file in `src/` states `radio-robot-elite` as the upstream
        repository.

### SUC-002: A reviewer trusts a kept comment reflects current behavior
Parent: N/A — maintainability, not a functional use case

- **Actor**: A code reviewer or future agent editing wire-layer,
  motion-engine, or shim code.
- **Preconditions**: `comment-audit.md`'s 135-item work order has not
  yet been applied; roughly 16% of audited comment blocks are noise
  (ticket archaeology, stale cross-layer claims, diff restatement,
  reviewer-justification essays, orphaned fragments), concentrated in
  the wire-layer headers.
- **Main Flow**:
  1. The reviewer reads a comment in `wire_adapter.cpp`,
     `wire_handler.h`, `motion_engine.h`, or `shims.cpp`.
  2. The comment states the *current* contract — post sprints
     006-008 — not a claim that predates them (e.g., not "the other
     five verbs answer kUnknown" when all six now dispatch).
  3. The comment carries no ticket-archaeology header, no
     reviewer-justification essay, no stale cross-layer claim, no diff
     restatement, and sits immediately above the code it describes.
- **Postconditions**: All 135 audited items are applied, corrected
  wherever `verify-comments.md` overrides the audit, with every
  unsampled REWRITE checked against the same "preserves every
  invariant, unit, measured value, and derivation" test before
  landing. `docs/code-review/guidelines.md`'s comment-hygiene
  dimension documents the five anti-patterns so future work doesn't
  regenerate them.
- **Acceptance Criteria**:
  - [ ] Zero load-bearing content (invariant, unit, measured value, or
        derivation) is lost across all 135 items.
  - [ ] The `motion_engine.h` `rotationalSlip_` comment still carries
        the full 0.915→120.0mm→0.952 derivation chain and the
        "do not set to 0.915" caution (verified unchanged, not
        rewritten).
  - [ ] `docs/code-review/guidelines.md` names the five anti-patterns
        with the concrete examples this sprint found.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Kernel re-diff and provenance restoration (diffdrive.h/.cpp, src/DESIGN.md, overview.md, specification.md) | — |
| 002 | Motion engine comment cleanup (motion_engine.h/.cpp) | — |
| 003 | Wire grammar comment cleanup (wire_handler.h/.cpp) | — |
| 004 | Wire adapter comment cleanup (wire_adapter.h/.cpp) | — |
| 005 | Transports comment cleanup (serial_transport.*, radio_transport.*) | — |
| 006 | Protocol composition comment cleanup (protocol.h/.cpp) | — |
| 007 | Hardware ports comment cleanup and provenance-name sweep (nezha_port.*, otos_port.*, platform_ports.h) | 001 |
| 008 | Shim and blocks comment cleanup (shims.cpp, main.ts) | — |
| 009 | Host test harness comment cleanup (tests/host/*.h/.cpp, README.md) | — |
| 010 | Test programs, Python test suite, and tooling doc cleanup (test/*.ts, tests/host/test_*.py, tools/*.py) | — |
| 011 | Comment-standards section in docs/code-review/guidelines.md | 001-010 |
| 012 | Final build checkpoint (host suite + flashable hex) | 001-011 |

Tickets execute serially in the order listed. Partitioned by
`src/DESIGN.md`'s own layer map, kernel first (highest stakes: the
re-diff, the 0.952/0.915 near-miss precedent) — see Architecture
§Design Rationale for why. Ticket 007 has a genuine dependency on 001
(it points several files' provenance comments at the authoritative
statement 001 writes); 011 and 012 are written to run after the
cleanup work they describe/verify, per each ticket's own rationale.
