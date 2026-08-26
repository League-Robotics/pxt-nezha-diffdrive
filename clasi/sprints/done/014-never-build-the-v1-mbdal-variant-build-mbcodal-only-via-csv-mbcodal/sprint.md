---
id: '014'
title: "Never build the V1 (mbdal) variant \u2014 build mbcodal only via csv-mbcodal"
status: done
branch: sprint/014-never-build-the-v1-mbdal-variant-build-mbcodal-only-via-csv-mbcodal
use-cases:
- SUC-001
issues:
- never-build-the-v1-mbdal-variant.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 014: Never build the V1 (mbdal) variant — build mbcodal only via csv-mbcodal

## Goals

Stop building the V1 (`mbdal`) micro:bit variant entirely. The fleet is
nRF52833 (micro:bit V2) only; nothing we ship runs on V1. Today `pxt
build` always compiles `mbdal` first and discards its hex — and under
`PXT_FORCE_LOCAL=1` (local Docker C++ compile) that wasted V1 build
doesn't just waste time, it **aborts the whole build**: V1's own
hex-merge step exits nonzero, which the cloud tolerates but a local
subprocess treats as a fatal `INTERNAL ERROR`, so `mbcodal-binary.hex`
is never produced. See
`clasi/issues/never-build-the-v1-mbdal-variant.md` for the full
mechanism, the measured evidence, and the exact pxt-core code path
(`PXT_COMPILE_SWITCHES=csv-mbcodal` selects `appTargetVariant` up
front, which is a different — and correct — mechanism from
`disablesVariants`, which the issue explains must NOT be used here).

## Problem

`pxt-microbit` declares `alwaysMultiVariant: true`, so every build
compiles both `mbdal` and `mbcodal` regardless of `disablesVariants`.
This is harmless-but-wasteful in the MakeCode cloud (V1's benign
hex-merge warning is swallowed and `pxt` moves on to `mbcodal`), but
fatal locally: a subprocess exit code aborts `pxt build` before
`mbcodal` is ever attempted, so `PXT_FORCE_LOCAL=1` currently cannot
produce a hex at all. Additionally, once single-variant builds are
in use, the output filename changes shape (`built/binary.hex` instead
of `built/mbcodal-binary.hex`, with no `:0400000A` block markers), and
nothing today asserts which kind of hex was produced — a stale/wrong
hex flashed to the robot is exactly the class of bug that has already
cost hours on this project.

## Solution

Set `PXT_COMPILE_SWITCHES=csv-mbcodal` (alongside the existing
`PXT_FORCE_LOCAL=1`) in the build subprocess environment inside
`tools/make_deploy.py`, so `pxt-core` selects `appTargetVariant=mbcodal`
up front and never builds `mbdal` at all — this is the mechanism the
issue confirms is measured-correct, not the `disablesVariants` trap
that silently strips the extension from the V1 half of a universal
hex. Update `make_deploy.py`'s output-path handling
(`HEX`/`HEX_TESTRIG`) to point at the resulting single-variant
artifact (`built/binary.hex`) instead of the old
`built/mbcodal-binary.hex`, and add an assertion that the produced hex
is a plain V2 hex (0 `:0400000A` markers) rather than a universal
V1+V2 hex, so a mismatched build fails loudly instead of getting
flashed. Decide deliberately what happens to the now-unreachable
V1-specific triage in `classify_attempt()` (the `_V1_HEXMERGE_RE`
pattern and the V1 half of the TS9283 note) — delete it or keep it as
a tripwire — and rewrite the module docstring, `tools/DESIGN.md`, and
any deploy notes that still describe the multi-variant world or tell
someone to flash `built/mbcodal-binary.hex`.

## Success Criteria

- `uv run python tools/make_deploy.py` (with `PXT_FORCE_LOCAL=1`)
  completes cleanly with no `mbdal`/`built/dockeryt/` build attempted,
  no `srec_cat` hex-merge step, and no `INTERNAL ERROR` abort.
- The produced hex is asserted to be a single-variant V2 hex (not a
  universal hex) before it's treated as flashable.
- The resulting hex boots on vevov and answers `STATUS`.
- `tests/tools/test_make_deploy_triage.py` is updated to match the new
  triage behavior and passes.
- Docs (`tools/DESIGN.md`, deploy notes, the module docstring) describe
  the single-variant build, not the old universal-hex world.

## Scope

### In Scope

- `tools/make_deploy.py`: set `PXT_COMPILE_SWITCHES=csv-mbcodal` in the
  build subprocess env (not relying on ambient environment); update
  `HEX`/`HEX_TESTRIG` to the single-variant artifact path; add an
  assertion guarding against a universal hex being mistaken for a V2
  one.
- `classify_attempt()`'s V1-specific triage (`_V1_HEXMERGE_RE`, V1 half
  of the TS9283 note): deliberately delete or convert to a tripwire —
  decided during detail planning, not left ambiguous.
- Module docstring in `tools/make_deploy.py` and `tools/DESIGN.md`:
  rewrite the documented traps for the single-variant build.
- `tests/tools/test_make_deploy_triage.py`: update to pin the new
  triage behavior.
- Deploy docs/notes that currently say "flash
  `built/mbcodal-binary.hex`".

### Out of Scope

- `src/` — the C++/TS extension itself is unchanged; this is
  build-tooling only.
- Any change to the MakeCode cloud build path (unaffected by this —
  the cloud already tolerates the V1 benign-abort; this sprint is
  about the local Docker path, though the switch applies to both).
- Broader rotation/travel-calibration issues tracked separately
  (`rotation-error-is-injected-by-the-legs-not-the-pivots.md`,
  `travel-calib-is-2.8-percent-too-large.md`, etc.) — unrelated to
  build tooling.

## Test Strategy

Primarily tool-level: `tests/tools/test_make_deploy_triage.py` pins
`classify_attempt()` behavior and must be updated in lockstep with the
triage change. The acceptance test is an actual local build —
`uv run python tools/make_deploy.py` under `PXT_FORCE_LOCAL=1`
producing a hex, plus a real hardware flash-and-`STATUS` check on
vevov per `.claude/rules/playfield-testing.md` /
`.claude/rules/hardware-bench-testing.md` conventions. No new unit
tests are anticipated beyond updating the existing triage test, since
this sprint changes build orchestration and environment plumbing, not
application logic.

## Architecture

**Sizing: Compact.** One module changed — `tools/make_deploy.py`'s build
orchestration (plus its direct test companion,
`tests/tools/test_make_deploy_triage.py`, and its subsystem doc,
`tools/DESIGN.md`) — with no new cross-module dependency (the script
already shells out to `pxt`/`mbdeploy`; it gains no new dependency on
any other module in this repo), no dependency-direction change, and no
data-model change (no wire field, no protocol shape, no `src/` change
at all — `src/` is explicitly out of scope per the issue). Diagrams are
omitted per the compact variant: a one-file build-tooling change has
nothing a component diagram would clarify beyond the prose below.

### What Changed

`tools/make_deploy.py`'s `_run_pxt_build()` now sets
`PXT_COMPILE_SWITCHES=csv-mbcodal` unconditionally in the `pxt build`
subprocess's environment, and defaults `PXT_FORCE_LOCAL=1` (honoring an
ambient override if the caller has already set it) instead of relying
on the caller's shell to have exported either — this is what makes
`uv run python tools/make_deploy.py` alone reproduce the sprint's own
acceptance criterion, with no env-var prefix required. `HEX` and
`HEX_TESTRIG` move from `built/mbcodal-binary.hex` to `built/binary.hex`
(the single-variant output path `pxt-core` produces once
`appTargetVariant` is set — see the linked issue's mechanism section).
Because `built/binary.hex` is ambiguous by name alone — a universal
(V1+V2) hex under the old multi-variant build and a plain V2 hex under
`csv-mbcodal` are byte-for-byte different artifacts sharing one
filename — `build()` gains a new check: it counts `:0400000A`
universal-hex block-start markers in the produced hex and hard-fails,
loudly, before ever reporting the hex as ready, if the count is not
exactly 0. Two markers (a universal hex) means the switch silently
failed to take effect; the build must not be treated as flashable in
that case. `classify_attempt()`'s V1-specific triage
(`_V1_HEXMERGE_RE`) is removed — see Design Rationale.

### Why

The linked issue (`clasi/issues/never-build-the-v1-mbdal-variant.md`)
measured that `PXT_FORCE_LOCAL=1` builds abort entirely before
`mbcodal` is ever attempted, because V1's own hex-merge step exits
nonzero and a local subprocess treats that as fatal where the
MakeCode cloud tolerates it. `PXT_COMPILE_SWITCHES=csv-mbcodal` sets
`appTargetVariant` up front, which selects only `mbcodal` before any
variant-dependency filtering runs — a different, measured-correct
mechanism from `disablesVariants`, which the issue shows does *not*
remove `mbdal` from the build list under this target's
`alwaysMultiVariant: true` (it only strips the extension from
`mbdal`'s dependencies, producing a wasted, dead-on-device V1 hex,
which is exactly the trap the module docstring already warns about and
must continue to warn about — see Migration Concerns).

### Impact on Existing Components

Additive/corrective within one file and its direct companions — no
other module is touched. `flash()`, `sync()`/`sync_testrig()`, and the
CLI (`main()`) are unaffected; they already reference `HEX`/
`HEX_TESTRIG` by name, not by literal path, so the constant rename
propagates through them with no call-site change. `_sync_scratch()`'s
existing `manifest.pop('disablesVariants', None)` line is unchanged —
see Design Rationale for why it still matters even though `mbdal` no
longer builds regardless.

### Migration Concerns

None for runtime behavior — this is build tooling, not shipped
firmware, and `src/` is untouched. The one thing worth stating
plainly: the `disablesVariants: ["mbdal"]` dead-hex warning **must
survive** this sprint's doc rewrite, not be deleted as obsolete —
`csv-mbcodal` is a different mechanism, and the trap remains real for
anyone who reaches for `disablesVariants` in a top-level project
(this repo's own `pxt.json` still declares it, correctly, for
extension consumers). Any developer note or muscle-memory habit of
typing `.tmp/deploy-head/built/mbcodal-binary.hex` by hand (rather than
through `make_deploy.py`'s own `HEX` constant or `--flash`) will find
that path gone after this sprint — the module docstring and
`tools/DESIGN.md` are updated so nothing in the living docs still
points there. Historical ticket records under `clasi/sprints/done/`
that quote the old filename are left alone; they are dated records of
past builds, not standing instructions, and are out of scope.

### Design Rationale

**Decision: delete `_V1_HEXMERGE_RE`'s `BENIGN` classification rather
than keep it as a tripwire in `classify_attempt()`, but repurpose its
existing test into a regression pin for the new expected verdict.**
- **Context**: under the old multi-variant build, V1's hex-merge
  failure was an expected, harmless, retry-worthy shape — it happened
  on effectively every build regardless of outcome. Under
  `csv-mbcodal`, V1 never builds at all, so this shape becomes
  structurally impossible in normal operation; its only remaining
  meaning is "the env var silently failed to take effect."
- **Alternatives considered**: (a) delete the pattern, its branch, and
  its test outright; (b) keep the `BENIGN` classification and retry as
  before, purely as a tripwire, unchanged.
- **Why this choice**: (b) is wrong on its own terms — retrying a
  shape that is now a configuration regression, not a transient flake,
  wastes an attempt and, worse, frames it as "benign" when it is not;
  `classify_attempt()`'s own stated philosophy is to fail closed on
  anything that isn't a genuinely transient, known shape. Deleting the
  `BENIGN` branch means this log shape now falls through to `UNKNOWN`
  — reported as a hard failure with no retry, which is the correct,
  more conservative response to what "V1 built" now implies. Deleting
  the *test* too (option a) would lose the one place that pins what
  happens if this shape ever reappears; repurposing
  `test_v1_hexmerge_failure_is_benign` into a test asserting `UNKNOWN`
  keeps that tripwire at the test level without carrying dead
  benign-retry logic in the shipped script.
- **Consequences**: if `PXT_COMPILE_SWITCHES` ever silently stops
  taking effect (a pxt-core upgrade, a subprocess-env regression, a
  future call site that bypasses `_run_pxt_build()`), the very first
  build reports a hard failure instead of quietly retrying and
  eventually succeeding with a V1 build still baked into a universal
  hex nobody asked for. The block-marker assertion (What Changed,
  above) is the actual backstop for that scenario; failing fast here
  means the ordinary case never gets that far.

**Decision: `PXT_COMPILE_SWITCHES` is forced unconditionally;
`PXT_FORCE_LOCAL` defaults to `'1'` but honors an ambient override.**
- **Context**: the issue's Scope asks for both to be set "in the build
  subprocess env rather than relying on ambient environment," and the
  Acceptance criterion requires a bare `uv run python
  tools/make_deploy.py` (no env-var prefix) to work with the local
  Docker compiler.
- **Alternatives considered**: force both unconditionally, always
  overriding any ambient value; or leave both ambient-only (today's
  behavior, which is what makes the bug reachable in the first place).
- **Why this choice**: `PXT_COMPILE_SWITCHES=csv-mbcodal` has no
  legitimate reason to ever be anything else for this project — V1 is
  categorically unsupported hardware — so forcing it unconditionally
  removes a footgun with no corresponding loss of flexibility.
  `PXT_FORCE_LOCAL` is different: it selects *which compiler* runs
  (local Docker vs. MakeCode cloud), and the issue's own Out-of-Scope
  note says the cloud path is unaffected and still valid — defaulting
  it to `'1'` (satisfying the bare-invocation acceptance criterion)
  while still honoring an ambient override preserves a way back to the
  cloud compiler (e.g. `PXT_FORCE_LOCAL=0 uv run python
  tools/make_deploy.py`) without a new CLI flag or any change to the
  cloud path itself.
- **Consequences**: the script's default behavior changes (local
  Docker instead of whatever the ambient shell happened to have) —
  worth a one-line callout in `tools/DESIGN.md` so a future reader
  isn't surprised that a bare invocation now compiles locally.

### Open Questions

None. The issue's own measured evidence (mechanism, exact env vars,
before/after byte counts, block-marker counts) leaves no ambiguity the
sprint needs stakeholder input to resolve — the two decisions above are
made explicitly in this document rather than left to ticket-time
judgment.

## Use Cases

None of `docs/design/usecases.md`'s UC-001..UC-016 cover build tooling
(they are all student-facing block use cases) — this SUC is
maintainer/build-tooling scope, following sprint 008's own precedent
for this kind of change (`Parent: N/A`). Sized to the compact tier: one
SUC, proportional — not the full multi-SUC treatment a substantial
sprint's use cases get.

### SUC-001: A maintainer runs one command and gets a flashable V2 hex, locally, every time
Parent: N/A (bench/build-tooling use case; closes
`never-build-the-v1-mbdal-variant.md`)

- **Actor**: A firmware maintainer running `tools/make_deploy.py` to
  produce a hex for vevov (or any fleet unit — all are micro:bit V2).
- **Preconditions**: The repo is checked out; Docker is available for
  the local C++ compiler (or the maintainer has explicitly opted back
  into the cloud compiler via `PXT_FORCE_LOCAL=0`).
- **Main Flow**:
  1. Maintainer runs `uv run python tools/make_deploy.py`, no env-var
     prefix required.
  2. `pxt build` runs with `PXT_COMPILE_SWITCHES=csv-mbcodal` and
     `PXT_FORCE_LOCAL=1` set in its subprocess environment; only
     `mbcodal` builds — no `mbdal` compile, no V1 hex-merge step, no
     local `INTERNAL ERROR` abort.
  3. `build()` finds `built/binary.hex`, confirms it has 0
     `:0400000A` block markers (a plain V2 hex, not a universal one),
     and reports it as the flashable artifact.
  4. Maintainer flashes it (`--flash` or the DAPLink fallback) to
     vevov; the robot boots and answers `STATUS`.
- **Postconditions**: A flashable, verified-single-variant hex exists
  at a known path; no V1 build was attempted; the artifact has been
  proven bootable on real hardware, not just produced.
- **Acceptance Criteria**:
  - [ ] `uv run python tools/make_deploy.py` completes with no
        `.tmp/deploy-head/built/dockeryt/` directory produced (V1
        never attempted) and no `srec_cat`/`INTERNAL ERROR`.
  - [ ] The produced hex is asserted to have 0 universal-hex block
        markers before being reported as ready; a synthetic 2-marker
        fixture is confirmed, by test, to hard-fail the same check.
  - [ ] The resulting hex, flashed to vevov, boots and answers
        `STATUS`.

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
| 001 | Single-variant build via csv-mbcodal: env plumbing, V2-hex assertion, retire V1 triage | — |
| 002 | Build checkpoint: local Docker single-variant build, flash vevov, confirm STATUS | 001 |

Tickets execute serially in the order listed. Ticket 002 is this
sprint's mandatory, always-last build-checkpoint ticket (standing
per-sprint convention since sprint 008) and also carries the sprint's
hardware-validation acceptance criterion (boots on vevov, answers
`STATUS`) — it depends on 001 by design, since it validates 001's
combined final state against a real `pxt`/Docker build and real
hardware, not synthetic fixtures.
