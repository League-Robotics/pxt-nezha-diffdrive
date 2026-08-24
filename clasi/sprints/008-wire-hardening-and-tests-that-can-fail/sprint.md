---
id: 008
title: Wire hardening and tests that can fail
status: roadmap
branch: sprint/008-wire-hardening-and-tests-that-can-fail
use-cases: []
issues:
- wire-timeout-hardening.md
- wire-constants-single-source.md
- host-harness-double-drift.md
- settle-tick-loop-is-not-host-testable.md
- tlm-auto-buffer-column-set-undefined.md
- host-tests-compile-newer-standard-than-target.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 008: Wire hardening and tests that can fail

> **Arc position.** Fourth planned sprint out of the 2026-08-23 code review
> (`docs/code-review/2026-08-23/review.md`), after sprint 004 (radio/wire
> transport, currently in `ticketing`), sprint 005 (bench tooling, roadmap,
> blocked on 004's hardware checkpoint), sprint 006 (motion correctness,
> roadmap), and sprint 007 (student API, roadmap). It is placed after 006/007
> in sequence but has only one soft dependency on either: this sprint's
> settle-loop extraction
> (`settle-tick-loop-is-not-host-testable.md`) touches the same
> `shims.cpp::Rig::tickDrive()` neighborhood as sprint 006's stop-timing fix
> (`cross-fiber-stop-settle-window-race.md`, R-08) — both sprints
> read/modify code around the settle tick, and 006's own sprint.md already
> flags the one-ticker-per-move constraint this sprint must not violate.
> Running 006 first (or at minimum landing its settle-window fix before this
> sprint touches the same loop) avoids two independent rewrites of the same
> few lines. Sprint 007 has no code-path overlap with this sprint at all —
> it is sequenced after only because it was triaged before this one, not
> because it blocks anything here. This sprint's wire-layer scope
> (`wire_handler.*`, `wire_adapter.*`, `protocol.*`) also overlaps files
> sprint 004 is actively ticketing; if 004 lands first, this sprint's detail
> plan should re-check those files against 004's changes before ticketing.

## Goals

Theme: **mirrored constants can't drift silently, timeouts have edges, and
the host suite can actually catch the regressions it claims to.** Four
issues, none large enough alone to be its own sprint, share this thread —
every one of them is a place where the wire protocol or the test harness
can be silently wrong and nothing turns red:

- **Timeout edges** (`wire-timeout-hardening.md`, HIGH, R-06 + R-18):
  reject or clamp `timeout 0` at decode instead of letting the motion
  obligation die at `now+0` while a ~10 s kernel lease stays armed; define
  one meaning for 0 across all X verbs (`WHEELS_X` vs `MOVE_X` currently
  disagree); cap timeouts at decode (e.g. ≤ 2^31−1) so values above 2^31 ms
  stop wrapping the deadline arithmetic negative and killing an acked move
  at ~150 ms. Add the boundary values (0, 2^31−1, 2^31, uint32-max) to the
  existing host-test parametrize, which currently maxes at 5000 ms.
- **Constants single-sourced** (`wire-constants-single-source.md`, MED,
  R-17 + R-21): stop hand-mirroring `kVersion` against `pxt.json` (currently
  `1.0.0` vs `1.0.10` — ten bumps drifted) — generate it or drift-test it.
  Give `emitLine`'s line cap and the transports' `kMaxLineBytes` one shared
  constant instead of two (`200` vs `240`, silently truncating long bench
  result lines) and fix the radio transport's now-false "equals
  SerialTransport's cap" comment. Pin the smaller duplicated pairs (radio
  group `0x2001` in `main.ts` vs `protocol.cpp`; `kDiag*` ordinals
  re-declared across files) with drift tests of the same shape.
- **Harness doubles re-synced** (`host-harness-double-drift.md`, MED,
  R-25): fix the three confirmed drifts between the `WaHandle` test doubles
  and production — wedge field pairs (`wedgeLeft/Right` vs
  `wedgeSuspectLeft/Right`), `setWheelsTimed` skipping
  `MotionEngine::wheelsV()`'s `cancelMove()` call, and truncation vs
  `std::lround` in config rounding — then add a drift test that fails when
  either side changes alone, so "mirrors field-for-field" stops being a
  comment nobody checks.
- **Settle loop made host-testable** (`settle-tick-loop-is-not-host-testable.md`,
  pre-review, filed after sprint 003 ticket 009): extract the settle
  loop's logic (bounded iteration count, break-on-rest, never re-energize)
  out of `shims.cpp::Rig::tickDrive()` into a host-portable helper in
  `motion_engine`, leaving only CODAL platform glue behind the
  `pxt.h`/`shims.cpp` boundary. Preserve the one-fiber-ticks-a-move
  constraint — protocol co-ticking caused heisenbugs before. Grouped into
  this sprint because it is the same "tests must be able to fail" disease
  as the harness-double issue: a passing test suite currently proves
  nothing about whether this loop still exists.

## Problem

All four issues are places where the test suite — or the wire protocol
itself — cannot detect its own drift or its own edge cases:

- A `timeout 0` on `WHEELS_X` acks and appears to succeed while leaving a
  stale ~10 s kernel lease armed, and `MOVE_X`'s `timeout 0` means
  something different (instant no-op) — the same input means two things
  depending on verb. A timeout above 2^31 ms wraps the deadline arithmetic
  negative and re-triggers the ticket-011 starvation bug (an acked move
  dying at ~150 ms) for an input class no existing test reaches.
- `kVersion` has drifted ten version bumps from the value it claims to
  mirror, defeating the deploy-verification flow (`mbdeploy` → `VER`
  check) — the build a host thinks it's talking to may not be the build
  actually flashed. `emitLine`'s line cap silently truncates long bench
  result lines below what the transports can actually carry, and the
  comment claiming the radio transport's cap "equals SerialTransport's" is
  false since ticket 005 raised the serial cap alone.
- The `WaHandle` host-test doubles diverge from production in three
  load-bearing ways, and the comments asserting fidelity are worse than no
  comment — they tell the next reader not to check. Wedge state, command
  supersession via `cancelMove()`, and config rounding are all effectively
  untested as wired, because the double being exercised isn't the code
  that ships.
- The settle-tick loop that stages the kernel's neutral duty to the motors
  at move end lives entirely inside `shims.cpp`, which the host harness
  never links. A regression that deleted or shortened that loop — leaving
  the wheels coasting at full duty until the ~150 ms watchdog fires —
  would pass the entire host suite. The behavior is pinned by argument
  (sprint 003's regression test proves the *need* for the step), not by
  executing the actual loop.

## Solution

Per-issue, at the level of detail each issue file's "What to do" section
already states in full (read `clasi/issues/<file>` at detail-planning time
for the exact approach):

1. `wire-timeout-hardening.md` — reject/clamp timeout 0 and cap at 2^31−1
   at decode time in the wire layer, unify `WHEELS_X`/`MOVE_X` semantics
   for 0, ensure the kernel lease is capped/cleared alongside the
   obligation, and extend the host-test boundary-value parametrize.
2. `wire-constants-single-source.md` — single-source or drift-test
   `kVersion` against `pxt.json`; introduce one shared line-capacity
   constant for `emitLine` and both transports; drift-test the smaller
   duplicated-constant pairs (radio group ordinal, `kDiag*`).
3. `host-harness-double-drift.md` — re-sync the `WaHandle` doubles'
   wedge-field reads, route `setWheelsTimed` through
   `MotionEngine::wheelsV()` (or an equivalent path that preserves
   `cancelMove()` semantics), match the `std::lround` config-rounding
   behavior, and add a drift test that fails when only one side changes.
4. `settle-tick-loop-is-not-host-testable.md` — extract the settle loop's
   logic into a host-portable helper consumed by both `shims.cpp` and the
   host harness, preserving the single-ticking-fiber constraint; add a
   host test that exercises the extracted loop directly (not just its
   necessity, as the sprint 003 test does).

Detail planning will size each issue individually; the timeout-hardening
and constants-single-source issues are likely compact-or-smaller (each
touches one or two files with no new cross-module dependency), while the
settle-loop extraction may warrant more scrutiny since it moves logic
across the `shims.cpp`/`motion_engine` boundary that sprint 006's
stop-timing fix also touches.

## Success Criteria

- Host tests parametrized at timeout 0, 2^31−1, 2^31, and uint32-max all
  produce the intended (rejected/clamped/consistent) behavior for every
  X verb; none regress to the pre-fix wrap or stale-lease behavior.
- `kVersion` matches `pxt.json` by construction or a host test fails the
  build the moment they diverge; `emitLine` and both transports agree on
  one line-cap constant, and the radio transport's parity comment is
  either true or removed.
- A host test fails when the `WaHandle` doubles' wedge fields, the
  `setWheelsTimed`/`cancelMove()` path, or the config-rounding behavior is
  changed on only one side (double or production).
- The settle loop's bounded-iteration/break-on-rest/never-re-energize
  logic runs under a host test that would fail if the loop were deleted or
  shortened — not merely a test that proves the loop's necessity.
- All new/changed host tests pass; no regression in existing `tests/host`
  coverage; the full suite stays green.

## Scope

### In Scope

- `src/wire_handler.*`, `src/wire_adapter.*`, `src/protocol.*` — timeout
  decode/clamp logic, `kVersion`/line-cap single-sourcing, duplicated
  radio-group and `kDiag*` constant pairs.
- `tests/host` — `WaHandle` test-double re-sync, new boundary-value
  timeout tests, drift tests for constants and for the doubles, and a
  host test for the extracted settle-loop helper.
- `src/motion_engine.*` — only as far as the settle-loop extraction
  requires (a new host-portable helper consuming the loop's logic); no
  other motion_engine change.
- `src/shims.cpp` — reduced to platform glue around the extracted
  settle-loop helper; no behavior change to the loop itself, just where
  its logic lives.

### Out of Scope

- The transports' buffer/RX-ring work (`serial-transport-rx-ring-and-tx-serialization.md`)
  — that amends sprint 004, not this sprint.
- Motion geometry, stop-timing, continuous-mode odometry, heading wrap,
  and brick-reset rebaseline — sprint 006's domain, even where its
  stop-timing fix shares the settle-loop neighborhood with issue 4 here.
- Blocks, simulator parity, stall-latch visibility, `driveTick` contract,
  cruise sentinel, and `rotationalSlip` — sprint 007's domain.
- Any backlog issue not listed above (see the code review annex and
  `clasi/issues/` for the rest — notably the tools/link-layer
  consolidation and vendored-kernel re-diff items, not claimed here).
- Detail planning, architecture, use cases, and tickets — this is a
  roadmap-phase sprint; those are produced when this sprint is
  detail-promoted.

## Test Strategy

Host-only (`tests/host`), consistent with this project's practice of
catching wire/kernel defects without hardware wherever possible:

- Boundary-value parametrize extension for timeout decode: 0, 2^31−1,
  2^31, and uint32-max (4294967295), across every X verb, asserting
  consistent reject/clamp behavior and no stale kernel lease.
- A drift test reading `pxt.json`'s version alongside `protocol.cpp`'s
  `kVersion` (or asserting build-time substitution occurred), and a
  similar text-level drift test for the radio-group ordinal and
  `kDiag*` pairs across `main.ts` and the C++ headers/sources.
  Constants that no longer need mirroring because they were
  single-sourced don't need a drift test — only remaining duplicated
  pairs do.
- A drift test pinning the `WaHandle` doubles against production for the
  three confirmed divergences (wedge fields, `setWheelsTimed`/`cancelMove()`,
  config rounding) — designed so changing only one side fails it.
- A new host test that links against the extracted settle-loop helper
  directly and asserts its bounded-iteration/break-on-rest/never-
  re-energize behavior by execution, not by argument; the existing
  sprint-003 regression test stays as the "why this matters" test, this
  one becomes the "does the loop still do it" test.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

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

Tickets execute serially in the order listed.
