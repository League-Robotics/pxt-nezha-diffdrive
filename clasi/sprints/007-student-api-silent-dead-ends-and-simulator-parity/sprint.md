---
id: '007'
title: 'Student API: silent dead-ends and simulator parity'
status: roadmap
branch: sprint/007-student-api-silent-dead-ends-and-simulator-parity
use-cases: []
issues:
- stall-latch-invisible-dead-end.md
- drivetick-contract-broken-idiom.md
- cruise-zero-sentinel-full-duty-lunge.md
- simulator-parity-turn-rate-and-estop.md
- rotational-slip-not-tunable.md
- runargcount-guard-and-shim-minors.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 007: Student API: silent dead-ends and simulator parity

## Goals

Theme: **when the robot won't move, the student can find out why; the
simulator tells the truth; documented idioms work.**

- Every silent refusal becomes observable. The stall latch gets a clear
  path (block + wire verb) and a readback (STATUS bit + DIAG ordinal +
  student-visible reporter) — framed, where it doesn't blow the sprint's
  scope, against the review's broader design note: e-stop, stall latch,
  watchdog, and lease expiry are four invisible "robot is off" states that
  a single unified "why won't it move" surface could retire as one class.
  At minimum the stall latch itself stops being invisible; the unified
  surface is a stretch goal, not a gate.
- The `driveTick()` continuous-drive contract is *decided*, not
  patched around: either it returns "keep ticking" while a velocity
  command is live, or a separate documented idiom (e.g. `driveHold()`)
  replaces the broken one. Code, all four doc sites (README ×2,
  specification.md §4.2, usecases.md UC-002), and a regression host test
  move together so they cannot diverge silently again.
- The wire's `cruise == 0` "configured default" sentinel resolves to a
  safe speed instead of the full-duty ~875 mm/s rail, and becomes an
  actual config field (`default_cruise`) instead of an unconfigurable
  constant.
- The browser simulator matches hardware on the two axes students
  actually feel: turn rate (kill the stray `/10` in `set wheel speeds`)
  and e-stop latching (the sim currently refuses nothing post-e-stop,
  making UC-011's "forgot to clear emergency stop" trap invisible exactly
  where students develop).
- `rotationalSlip` becomes a calibratable field (Setup group /
  `ConfigField` / `MotionEngine` setter with the same `setGeometry`-style
  validation) instead of a hard-coded, recompile-only constant, so a
  non-vevov chassis can be turn-calibrated without touching source. The
  load-bearing derivation comment for 0.952 moves with the field.
- The `runArgCount` null-guard and its batched one-to-five-line Minors
  land together as one low-risk cleanup pass.

## Problem

The 2026-08-23 code review's second major theme (after goTo geometry,
which sprint 006 owns) is that the student-facing API is full of silent
dead ends: a robot can stop responding to a program for five different
reasons, and none of them are visible to the student or the host. On top
of that, one of the four documented ways to drive the robot (the
`while (driveTick())` idiom) doesn't work as documented, the wire's "use
the default speed" sentinel instead commands maximum speed, and the
simulator disagrees with hardware on both turn rate and e-stop behavior —
so a student's simulator-tuned program does not transfer to the real
robot. `rotationalSlip` being unconfigurable is the same class of problem
one level down: a documented calibration path (`set track width`) exists
but is explicitly the wrong knob, and the right knob doesn't exist yet.

## Solution

Treat these as one sprint because they share a boundary: everything here
is student-observable API surface (blocks, wire verbs a student's program
or a host test can hit, docs, and the simulator), not transport plumbing
(sprints 004/005) or motion-geometry math (sprint 006). Detail planning
will size each issue individually — the stall-latch/driveTick/cruise
work touches `motion_engine`/`shims.cpp`/wire decode together and may
warrant more than a "compact" architecture treatment; the slip setter and
the Minors batch are likely compact or trivial on their own.

## Success Criteria

- A student (or host) can discover, after a stall latch trips, that it
  tripped and how to clear it — without a power cycle.
- The documented `driveTick()` continuous-drive idiom, as written in the
  README/spec/usecases, actually keeps the robot moving; a host test
  proves it.
- Sending `cruise 0` (or the equivalent wire field) on any of the four
  motion verbs produces a safe, documented speed — never the duty
  ceiling.
- Simulator turns match hardware turns for the same `set wheel speeds`
  call, and a simulated `emergency stop` refuses further motion until
  cleared, matching hardware's two-layer refusal.
- `rotationalSlip` has a setter reachable from a block or `ConfigField`,
  validated like other geometry fields, with its derivation comment
  intact.
- `runArgCount` no longer panics on an unguarded pre-RUN call, and the
  batched Minors (dead `microphone` dep, tsconfig gap, dead `maxNudges`,
  stale `goToWorld` JSDoc, spliced DIAG case 25, float→int cast UB at the
  wire boundary, under-sized verb tables) are resolved.

## Scope

### In Scope

- `src/main.ts` — block-level surface for stall clear/readback, the
  `driveTick()`/continuous-drive contract, the two simulator parity
  fixes (turn-rate `/10`, e-stop latch), the `runArgCount` guard, and the
  batched Minors that live in this file (dead `maxNudges`, stale
  `goToWorld` JSDoc, dead `microphone` dep in `pxt.json`, tsconfig gap).
- `src/shims.cpp` — wire-verb-facing surface for stall clear/readback and
  for the cruise==0 sentinel resolution; DIAG case-25 reordering.
- `src/diffdrive.*` / `motion_engine.h` — the stall latch's clear/readback
  plumbing, and the `rotationalSlip` setter (with its derivation comment
  carried along).
- `src/wire_adapter.cpp` — cruise==0 sentinel resolution, `default_cruise`
  config field, float→int cast clamp at the wire boundary, verb-table
  sizing (WIRE-09).
- Docs — README (both `driveTick()` examples), `specification.md` §4.2
  (driveTick contract) and §5 (simulator gaps, currently omits e-stop),
  `usecases.md` UC-002 (driveTick idiom) and UC-013 (chassis calibration,
  to include `rotationalSlip`).
- `tests/host` — regression tests for the driveTick idiom, the cruise
  sentinel across all four motion verbs, stall latch clear+readback, and
  the `rotationalSlip` setter.

### Out of Scope

- `goTo` geometry, pivot-split behavior, arrival tolerance, OTOS heading
  wrap, and odometry chord integration — sprint 006 (motion correctness).
- Radio/serial transport work (RX capacity, TX serialization, RX ring
  sizing, wire version drift) — sprints 004/005.
- Bench-tool/camera link-layer consolidation (stale venv, copied `Cam`
  scaffolds, numeric `RUN:<n>` vocabulary) and the comment-cleanup work
  order — separate proposed issues/sprints, unrelated to the student API
  surface this sprint targets.
- Brick-reset odometry teleport, cross-fiber stop/settle race — filed as
  their own issues, not claimed here.

## Test Strategy

(Sized in Detail Mode, per issue. Expect host-test additions in
`tests/host` for: the driveTick continuous-drive idiom end-to-end, the
cruise==0 sentinel on all four motion verbs, stall latch
clear-then-readback, and the `rotationalSlip` setter's validation. Sim
parity fixes are checked by comparing sim math against the hardware
conversion it's meant to mirror, not by a new test harness.)

## Architecture

N/A — roadmap phase. Architecture is written and sized (trivial /
compact / substantial, per issue) during Detail Mode planning.

### Architecture Overview

(Deferred to Detail Mode.)

### Design Rationale

(Deferred to Detail Mode.)

### Migration Concerns

(Deferred to Detail Mode.)

## Use Cases

N/A — roadmap phase. Use cases (new or updated UC-002, UC-011, UC-013)
are written during Detail Mode planning.

## GitHub Issues

(None linked yet — this is a roadmap-phase sprint.)

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

Tickets execute serially in the order listed. (None yet — roadmap
phase.)

## Issues Claimed

All filed under `clasi/issues/`, from the 2026-08-23 code review
(`docs/code-review/2026-08-23/review.md`). Not yet linked via
`link_sprint_issues` — that step is left to whoever runs Detail Mode on
this sprint.

| Issue file | Priority | Review IDs | Covers |
|---|---|---|---|
| `stall-latch-invisible-dead-end.md` | High | R-01 | No clear path or readback for the stall latch; includes the review's "unify the invisible robot-is-off states" design note |
| `drivetick-contract-broken-idiom.md` | High | R-10 | Documented `while (driveTick())` idiom stops the robot in ~150 ms; every doc site prescribes it |
| `cruise-zero-sentinel-full-duty-lunge.md` | High | R-11 | Wire `cruise == 0` resolves to full-duty ~875 mm/s instead of a safe default |
| `simulator-parity-turn-rate-and-estop.md` | Med | R-12, R-13 | Simulator `/10` turn-rate bug; simulator never latches e-stop |
| `rotational-slip-not-tunable.md` | Low | R-14 | `rotationalSlip` hard-coded 0.952, no setter on any surface |
| `runargcount-guard-and-shim-minors.md` | Low | R-15 + Minors | `runArgCount` null-guard one-liner, batched with small shim/build Minors |

## Ordering Rationale

This sprint is the third track in the post-review arc, after:

- **004** (`Radio full v6 transport + telemetry frame`, firmware) and
  **005** (`Retrofit bench tooling onto the v6 telemetry stream`) — the
  transport/telemetry track, already executing/roadmapped.
- **006** (`Motion correctness: goTo geometry and odometry truth`) — the
  motion-geometry track, just roadmapped.

007 is sequenced *after* 006 specifically (not just "later in the
backlog") because both sprints touch `motion_engine.h`/`shims.cpp`:
006 rewrites the `goTo` arc-encoding and pivot-split logic there, and 007
adds the stall-latch clear/readback surface and the `driveTick`/cruise-
sentinel contract in the same files. Landing 006's geometry fix first
avoids two detail-planned sprints editing the same motion-engine methods
concurrently on divergent branches. Within 007 itself, no further
internal ordering is fixed yet — that's a Detail Mode ticketing decision
— but the natural dependency shape is: stall-latch surface and
driveTick-contract and cruise-sentinel resolution first (they share
files and the "invisible dead end" theme), simulator parity next (touches
`main.ts` sim bodies, independent of the wire-side fixes), then the
`rotationalSlip` setter and the Minors/guard batch last (lowest risk,
least coupled to the rest).

007 is ordered ahead of the tooling-consolidation work implied by the
review's proposed issues #13/#14 (bench-tool venv/`Cam`-scaffold/numeric-
`RUN` cleanup) because that tooling should be built and tested against
the *fixed* stall-latch/driveTick/cruise-sentinel wire behavior, not
patched twice.
