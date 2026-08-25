---
id: '001'
title: Kernel re-diff and provenance restoration (diffdrive.h/.cpp, src/DESIGN.md,
  overview.md, specification.md)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue:
- comment-cleanup-work-order.md
- vendored-kernel-upstream-rediff.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Kernel re-diff and provenance restoration (diffdrive.h/.cpp, src/DESIGN.md, overview.md, specification.md)

## Description

Runs first because both linked issues converge on the same two files.
`diffdrive.h` has five comments truncated mid-sentence during a lossy
vendoring step (lines 81, 84, 90, 91, 125); the vendoring provenance
comment names `radio-robot-elite`, which does not resolve on GitHub.
Real upstream is `League-Robotics/radio-robot`, and the kernel has
moved within it to `src/firm/diffdrive/` (`src/firm/control/` is now a
thin forwarding-adapter header, not the kernel itself). This ticket
re-diffs the vendored pair against that current upstream location,
restores the five comments verbatim, catalogues any other divergence,
and writes the one authoritative provenance statement other tickets'
files will point at instead of each restating a path that goes stale.

Do this **before** editing any other file's provenance reference —
ticket 007 depends on this ticket's `src/DESIGN.md` statement existing
first.

## Acceptance Criteria

- [x] Fetched (WebFetch or equivalent) the current upstream
      `https://github.com/League-Robotics/radio-robot` tree at
      `src/firm/diffdrive/differential_drive.{h,cpp}` and diffed it
      against this repo's `src/diffdrive.{h,cpp}`, beyond just the five
      known-truncated comments — confirm no other comment or code
      divergence exists that the original vendoring step silently
      dropped alongside the truncated text.
- [x] `diffdrive.h` lines 81, 84, 90, 91, and 125 read the complete
      upstream sentences (not paraphrases), using the text already
      quoted in `docs/code-review/2026-08-23/raw/verify-comments.md`
      §3:
      - 81: `// command before begin(). NOT before start(): the host
        harness commands and step()s WITHOUT ever launching the fiber,
        so readiness is begin()'s to grant, not start()'s`
      - 84: `// post-begin setConfig with a differing cyclePeriod:
        block applied, frozen cadence kept`
      - 90-91 (`maxDuty`): `// [%] authority rail (lambda scales to
        this); 0 = ALL modes refused` — use this text, **not** the
        audit's raw completion, which drops the `0 = ALL modes
        refused` sentinel (verify-comments.md R4).
      - 91 (`fullDutyVelocity`, the truncation the audit itself
        missed): `// [counts/s] wheel rate at 100% duty; 0 =
        uncalibrated → VELOCITY refused`
      - 125: `// cycles that missed their absolute deadline` (upstream
        also has a "lesson 17" clause the audit correctly drops as
        upstream-repo lore, per verify-comments.md R5 — do not
        restore that part).
- [x] `diffdrive.h`'s file-header REWRITE (audit item 1-26) and
      `diffdrive.cpp`'s file-header REWRITE (audit item 1-6) are
      applied using `verify-comments.md`'s R1/R6-corrected text (the
      resolvable repo name and current path), never the audit's raw
      "radio-robot-elite" replacement text — apply the load-bearing
      check to the rest of the audit's proposed compression before
      landing it (both R1/R6 CHALLENGE only the repo-name/path
      portion; the rest of the compression is otherwise sound per
      verify-comments.md).
- [x] `src/DESIGN.md` §2 (Kernel) — the "Vendored, synced copy"
      invariant currently says "extracted from the radio-robot
      firmware (`src/firm/control/`)" — this is the stale path.
      Rewrite it to state, as one authoritative statement: upstream
      repo `League-Robotics/radio-robot`; kernel currently lives at
      `src/firm/diffdrive/differential_drive.{h,cpp}`;
      `src/firm/control/differential_drive.h` is now a thin
      forwarding-adapter header, not the kernel; fix kernel bugs in
      both trees until the firmware consumes this package directly.
      Add a one-line maintenance-boundary note (kernel files are a
      synced copy — edit both trees; port/shim files are this repo's
      own and are edited here only) if §2 doesn't already carry one
      clearly.
- [x] `docs/design/overview.md` §Provenance and
      `docs/design/specification.md` §12 are updated to **resolve**,
      not merely flag, the README/source path discrepancy
      specification.md §12 currently defers ("flagged here rather
      than silently resolved"): both should state the current path
      matter-of-factly and point at `src/DESIGN.md` §2 as the one
      place the path details live, rather than each independently
      restating it.
- [x] Any divergence the re-diff finds beyond the five comments is
      recorded: deliberate divergences get a one-line note in place
      (in `diffdrive.{h,cpp}` or `src/DESIGN.md` §2, whichever is the
      more natural home); an **accidental** divergence gets fixed
      narrowly in `diffdrive.{h,cpp}` — this is the sprint's one
      permitted code change, not a general kernel refactor — and is
      called out explicitly in this ticket's completion notes with
      the specific upstream contract it restores.
- [x] No file in `src/` states `radio-robot-elite` as the vendored
      kernel's upstream repository (the broader sweep of
      `radio-robot-elite` in other, non-kernel files — `otos_port.*`,
      `radio_transport.*`, `nezha_port.cpp` — is ticket 007's job, not
      this one; this criterion is scoped to `diffdrive.{h,cpp}` and
      the design docs this ticket touches).

## Completion notes

**Upstream fetch.** `gh api repos/League-Robotics/radio-robot/contents/...`
(default branch `master`) pulled the live
`src/firm/diffdrive/differential_drive.{h,cpp}` (556 + 1101 lines,
heavily commented) and, for cross-checking the historical framing, the
old-path forwarding-adapter header now at
`src/firm/control/differential_drive.h`. Comparing comment-stripped
upstream against this repo's `src/diffdrive.{h,cpp}` (Python
regex-strip of `//`/`/* */`, blank-line collapse, then `diff -u`) found
**exactly one code-level difference** in each file: the
`cycleGapCount`/`cycleGapCount_` field and its `kMaxCycleGapUs` guard in
`step()`/`publishOutput()`, present only in this repo's copy. This is
the known, closed, deliberate fix from
`clasi/issues/done/first-move-after-idle-runs-at-full-duty.md` (commit
704c40d) — not accidental, so it was **recorded, not reconciled**, per
the ticket's own instruction. No other code divergence exists anywhere
in either file; every other diff line was upstream's own additional
commentary (this repo's copy has comments "stripped for size" per
`specification.md`, confirmed accurate) or the expected
`differential_drive.h`→`diffdrive.h` include-filename rename.

**Restored comments (before → after), verbatim from upstream:**
- `81` `kRefusedNotBegun`: `// command before begin(). NOT before
  start(): the` → `...the host harness commands and step()s WITHOUT
  ever launching the fiber, so readiness is begin()'s to grant, not
  start()'s`
- `84` `kCadencePreserved`: `// post-begin setConfig with a differing
  cyclePeriod:` → `...cyclePeriod: block applied, frozen cadence kept`
- `90` `maxDuty`: `// [%] authority rail (lambda scales to` →
  `...scales to this); 0 = ALL modes refused` (audit's own completion
  would have dropped the sentinel — used verify-comments.md R4's
  corrected text instead)
- `91` `fullDutyVelocity` (the fifth truncation, missed by the audit
  entirely): `// [counts/s] wheel rate at 100% duty;` → `...100%
  duty; 0 = uncalibrated → VELOCITY refused`
- `125` `cycleOverrunCount`: `// cycles that missed their absolute` →
  `...their absolute deadline` (upstream's trailing "— the
  observability half of lesson 17" deliberately dropped as
  upstream-repo lore, per R5)

**Audit items verified against current, post-sprint-004/005/006/007/008
code (not the audit's line numbers) — no no-ops or wrong calls found
among this ticket's items.** `radio_transport.h`'s `kMaxPayloadBytes`
comment (sprint 008), `protocol.cpp`'s `kVersion` drift note (sprint
008), and `protocol.h`'s telemetry-frame gap note (sprint 004) — the
three staleness traps flagged in the dispatch brief — are all outside
this ticket's file set (`diffdrive.{h,cpp}`, `src/DESIGN.md`,
`overview.md`, `specification.md`) and were left untouched, confirmed
already correct by earlier sprints.

**Unsampled REWRITE load-bearing check.** Both REWRITE items this
ticket applies (`diffdrive.h` 1-26, `diffdrive.cpp` 1-6) **were**
sampled and CHALLENGE-corrected by `verify-comments.md` (R1/R6) — there
was no unsampled REWRITE item in this ticket's scope, so there was
nothing additional to load-bearing-check beyond applying R1/R6's
corrections and re-verifying the "otherwise fine" remainder against the
live file (confirmed: the ports summary and both-trees invariant they
describe still match the current class surface exactly).

**Authoritative provenance statement (for ticket 007 to point at):**
`src/DESIGN.md` §2, "Vendored, synced copy" invariant — upstream repo
`League-Robotics/radio-robot`; kernel currently at
`src/firm/diffdrive/differential_drive.{h,cpp}`;
`src/firm/control/differential_drive.h` is a thin forwarding-adapter
header in the upstream repo, not the kernel; fix kernel bugs in both
trees until the firmware depends on this package directly; one
documented exception (`cycleGapCount`, not yet ported upstream);
maintenance boundary (kernel files synced-copy/edit-both-trees vs.
port/shim files ported/edit-here-only) stated explicitly. This overlay
edit needs its `.diff.md` `source_hash` regenerated by the team-lead
(see report).

## C++11 gate coverage

`diffdrive.cpp` is one of the four translation units
`tests/host/test_cxx11_syntax_gate.py` syntax-checks at `-std=c++11
-fsyntax-only`; `diffdrive.h` is included by it and is therefore
covered indirectly. Any edit here is gate-checked automatically by the
existing host suite — no new gate registration needed. `src/DESIGN.md`,
`overview.md`, and `specification.md` are documentation; no build gate
applies to them.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` scoped to the
  kernel — `tests/host/test_kernel_harness.py` and
  `tests/host/test_cxx11_syntax_gate.py` at minimum; run the full `uv
  run pytest` if an accidental-divergence fix touches shared behavior
  reachable from other test files.
- **New tests to write**: none expected for comment-only changes. If
  the re-diff surfaces and fixes an accidental code divergence, add a
  targeted test proving the specific upstream contract restored (e.g.,
  a `fullDutyVelocity == 0 → kRefusedUnconfigured` case if that path
  is what's found accidentally broken).
- **Verification command**: `uv run pytest tests/host/test_kernel_harness.py tests/host/test_cxx11_syntax_gate.py`
