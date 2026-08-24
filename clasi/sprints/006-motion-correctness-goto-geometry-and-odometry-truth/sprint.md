---
id: '006'
title: 'Motion correctness: goTo geometry and odometry truth'
status: roadmap
branch: sprint/006-motion-correctness-goto-geometry-and-odometry-truth
use-cases: []
issues:
- goto-geometry-pivot-split-miss.md
- cross-fiber-stop-settle-window-race.md
- continuous-mode-odometry-chord-error.md
- otos-seed-heading-clamp.md
- brick-reset-odometry-teleport.md
- no-encoder-odometry-posesource-fallback.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 006: Motion correctness: goTo geometry and odometry truth

> **Arc position.** This sprint is the third planned out of the
> 2026-08-23 code review (`docs/code-review/2026-08-23/review.md`), after
> sprint 004 (`004-radio-full-v6-transport-telemetry-frame-firmware`,
> ticketed — the radio/wire-grammar arc) and sprint 005
> (`005-retrofit-bench-tooling-onto-the-v6-telemetry-stream`, roadmap —
> the bench-tooling arc). The three sprints partition the same review's
> findings by theme, not by dependency: 004/005 are a transport-and-tooling
> pair that must run in that internal order (005 waits on 004's hardware
> checkpoint), while this sprint is independent of both — it touches
> `motion_engine`/`diffdrive`/`otos_port`/`shims` tick paths, not the wire
> layer or the bench scripts. It comes after 004/005 in sprint numbering
> because the review's transport-and-telemetry gaps were triaged as the
> more urgent arc first; nothing here blocks on or is blocked by 004/005
> landing, so this sprint could in principle be pulled forward or run
> interleaved without harm.

## Goals

Group the code review's motion-correctness cluster — five findings whose
common thread is "the robot goes where it is told, and the pose it
reports is the truth" — into one sprint, fixed together because they
share that theme, not because they share a code path:

- **goTo geometry** (`goto-geometry-pivot-split-miss.md`, HIGH): fix the
  pivot-split miss, the long-way-around degeneracy, and the dead `arrive`
  tolerance in the `goTo`/`moveX` path. Add host tests **above** the 50°
  pivot-split threshold and for behind-the-robot targets — the specific
  gap that let all three ship green.
- **Stop timing** (`cross-fiber-stop-settle-window-race.md`, HIGH):
  deliver a cross-fiber/watchdog-triggered stop inside the kernel's
  settle window every time, not ~1/3 of the time, without adding a second
  ticker.
- **Continuous-mode odometry** (`continuous-mode-odometry-chord-error.md`,
  MED): fold `odomUpdate()` into the velocity-mode tick path so pose stays
  correct during continuous driving instead of integrating one long chord
  at the next read.
- **Heading seed wrap** (`otos-seed-heading-clamp.md`, MED): wrap seeded
  headings to ±180° instead of clamping, so a 0–360°-convention or
  unwrapped-odometry seed doesn't silently poison the OTOS pose source.
- **Brick reset discontinuity** (`brick-reset-odometry-teleport.md`,
  MED): run the decisive bench experiment (power-cycle the brick
  mid-drive, watch DIAG ordinals 10/11 and pose) to confirm or rule out
  the ~4 m teleport, then — if confirmed — rebaseline odometry on an
  impossible-delta discontinuity instead of integrating it.

## Problem

All five defects come from the 2026-08-23 code review's kernel/odometry
findings (R-02/03/04, R-08, R-09, R-05, R-07), each independently
CONFIRMED — four by static re-derivation (arithmetic in
`verify-kernel.md`/`verify-blocks.md`), one (`brick-reset-odometry-teleport`)
with the code path statically certain but the hardware premise
unverifiable without a bench run. Left as-is:

- A `goTo` call can miss its target by over 100 mm on any split above 50°,
  or spin nearly 360° for a target behind the robot, and the host test
  suite stays green because it never exercises either case.
- A stop issued from another fiber, or a watchdog-timed stop, has roughly
  a 1-in-3 chance of landing in the kernel's settle window and being held
  for another 100-150 ms — reintroducing the per-turn overshoot the
  settle logic exists to remove.
- Continuous velocity-mode driving silently decouples from odometry:
  pose is only ever right immediately after a discrete move, never during
  or after sustained twist-driven motion.
- A heading seed outside ±180° (any 0-360°-convention source, or the
  project's own unwrapped odometry heading echoed back) clamps instead of
  wrapping, disagreeing with the odometry pose source by up to ~170° —
  poisoning exactly the drift measurement the reseed exists to make.
- If a brick MCU reset actually zeroes the encoder registers mid-session,
  the two-strike glitch armor accepts the resulting counter jump as truth,
  teleporting pose by ~4 m with no rebaseline and no diagnostic signal.

## Solution

Per-issue, at a level of detail the "What to do" section of each issue
file already states in full (read `clasi/issues/<file>` at detail-planning
time for the exact approach) :

1. `goto-geometry-pivot-split-miss.md` — recompute the post-pivot leg
   toward the actual target (or split the arc geometrically rather than
   kinematically); normalize theta to ±180° and take the short arc;
   implement the arrival-tolerance check that is already parsed but
   unimplemented.
2. `cross-fiber-stop-settle-window-race.md` — deliver staged neutral
   inside `step()`'s settle path, or push duty directly through the
   anti-latch pipeline, honoring the one-ticker-per-move constraint from
   `settle-tick-loop-is-not-host-testable.md`.
3. `continuous-mode-odometry-chord-error.md` — call `odomUpdate()` from
   `tickDrive`'s velocity-mode branch, preserving the same one-ticker
   constraint.
4. `otos-seed-heading-clamp.md` — wrap the heading (one modulo) before
   the `writePoseMm` register write; while in there, resolve or
   re-document the wrapped-vs-unwrapped heading contract mismatch noted
   against `motion_engine.h:139` (KERN-08).
5. `brick-reset-odometry-teleport.md` — run the bench experiment first
   (prove the DIAG-capture instrument is watching, per this project's
   measurement doctrine); only design the rebaseline fix once the
   hardware premise is confirmed.

## Success Criteria

- `GO_TO_R`/`goTo` hits its target within tolerance for splits above and
  below the 50° pivot threshold, and for targets behind the robot; new
  host tests cover both cases and fail on the pre-fix behavior.
- A stop issued mid-settle-window is delivered within that same tick,
  every time — not probabilistically — with no added ticker.
- A host test drives a full circle under continuous velocity-mode
  driving and reads pose back near the origin.
- A host test seeds heading at 350°/-350°/720° and reads back the
  correctly wrapped equivalent; the OTOS pose source's wrapped-vs-
  unwrapped contract is consistent with `motion_engine.h`.
- The brick-reset bench experiment has been run and its result (confirmed
  or ruled out) is recorded in `brick-reset-odometry-teleport.md`; if
  confirmed, a rebaseline-on-discontinuity fix ships with a DIAG counter
  surfacing when it fires.
- All new/changed host tests pass; no regression in existing
  `tests/host` coverage.

## Scope

### In Scope

- `src/motion_engine.*` — goTo/moveX geometry: pivot-split leg
  recomputation, theta normalization, arrival-tolerance check.
- `src/diffdrive.*` stop path — settle-window-safe stop delivery.
- `src/shims.cpp` tick paths — continuous-mode `odomUpdate()` folding;
  no change to the one-ticker-per-move constraint.
- `src/otos_port.*` — heading wrap on seed; brick-reset detection and
  rebaseline (contingent on the bench result).
- `tests/host` — new/extended host tests for all five fixes: above-50°
  and behind-robot goTo cases, settle-window stop timing, continuous-mode
  circle-closure, heading-wrap seeding, and (if the bench confirms the
  brick-reset premise) discontinuity-rebaseline coverage.
- The brick-reset bench experiment itself (hardware step, DIAG ordinals
  10/11 + pose capture), recorded back into
  `brick-reset-odometry-teleport.md`.

### Out of Scope

- The wire grammar / protocol (`radio-robot-lib`, `WireHandler`,
  `RadioSink`, frame formats) — sprint 004's domain.
- `tools/` bench scripts and `tools/tlm.py` — sprint 005's domain.
- Any issue not in this sprint's linked set (see the code review annex
  and `clasi/issues/` for the rest of the backlog — notably the other
  R-0x findings not claimed here).
- Detail planning, architecture, use cases, and tickets — this is a
  roadmap-phase sprint; those are produced when this sprint is
  detail-promoted.

## Test Strategy

Host-only (`tests/host`), consistent with this project's existing
practice of catching kernel/geometry defects without hardware wherever
possible:

- New geometry tests for `goTo`/`moveX` deliberately above the 50° split
  threshold and for targets behind the robot — the exact gap the code
  review found the existing suite silent on.
- A settle-window timing test that issues a stop at a point in the tick
  cycle known to fall inside the settle window and asserts the stop is
  delivered within that tick, not on the next watchdog cycle.
- A continuous-mode odometry test: drive a closed circle under constant
  twist in an unconditional tick loop, assert pose returns near origin.
- A heading-wrap test: seed 350°/-350°/720°, assert the register and the
  read-back heading match the wrapped equivalent.
- The brick-reset case is bench-only by nature (hardware MCU reset); its
  host-testable half (rebaseline logic, once the bench confirms the
  premise) gets a host test at detail-planning time, but the reset
  detection itself cannot be simulated host-side.

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
