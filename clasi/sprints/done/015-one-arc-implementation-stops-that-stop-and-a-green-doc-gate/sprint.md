---
id: '015'
title: One arc implementation
status: done
branch: sprint/015-one-arc-implementation-stops-that-stop-and-a-green-doc-gate
use-cases: []
issues:
- block-go-to-misses-its-target.md
- tour-legs-share-the-arc-split-defect.md
- arc-moves-abort-distance-never-driven.md
- pivot-stops-11-degrees-short-of-commanded.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 015: One arc implementation

> **Rescoped 2026-08-26.** This sprint originally carried the stop paths and the
> doc gate too. Those moved to sprints 016 and 017 when the whole issue pool was
> roadmapped; what remains is one tight theme. The directory slug still carries
> the old title.

## Goals

Every path in this repo that turns "a target" into a move computes its own arc.
There are four, and the fix sprint 006 applied reached exactly one. Consolidate
them onto that one, and fix the two faults that ride the same split path.

## Problem

`theta = 2*atan2(y,x)` with arc length `s = R*theta` is self-consistent only
when executed as **one blended segment**. `MotionEngine::moveX()` splits any
`|rotation| >= 50 deg` into pivot-then-straight and drives `s` — the arc
*length* — as a straight line. Sprint 006 gave `goToR()` its own correct split
(pivot to the line-of-sight bearing, drive the chord) plus a short-arc wrap;
three callers still hand `moveX` the raw pair.

Measured against the real firmware C++
([`raw/goto_probe.cpp`](../../../docs/code-review/2026-08-26/raw/goto_probe.cpp)):

```
block goTo(10,10)   ends 112.5 mm off a 141.4 mm hop   (wire GO_TO_R: 2.9 mm)
block goTo(-10,1)   drives a 3.07 m arc to a point 10 cm away, ends 3.17 m out
```

Two further faults on the same split, both found on hardware after the review:

- **The timeout budget is computed for a blended move.** `startMove()` budgets
  `max(dist, yaw) + 1500 ms`; the split runs the axes sequentially, needing
  their sum. `margin = 1500 ms - min(dist, yaw)`, so **every `move(d, 180)` at
  the default yaw rate is over budget regardless of distance**. Marginal in
  practice — one night the straight leg never ran, the next it always did.
- **Every pivot stops ~11 deg short and reports complete.** Deterministic,
  floor-insensitive, identical across nights: 10.3–11.8 deg over five arcs at
  two taper settings. Every shortfall lands inside the 13.55 deg yaw taper
  window while the completion margin is 0.30 deg.

## Solution

Consolidation, not rewrite. `goToR()` is already correct, host-portable,
host-tested, and already reachable from `shims.cpp` via `engineGoToR()` — which
merely lacks a `//%` annotation. Expose it to the block layer and route the
three remaining callers through it: that removes the duplication *and* the
defect in one move, and makes `world.ts`'s 25 deg curvature cap unnecessary,
retiring its numeric collision with `kTurnFirstAngleRad` as a side effect.

The budget and shortfall faults are separate, smaller changes in the same two
files.

## Success Criteria

- [ ] `goto_probe.cpp`, re-run unmodified, puts the block path within **5 mm**
      of target for both cases (currently 112.5 mm and 3172.4 mm).
- [ ] A host test exercises the arc path **above** the 50 deg split threshold
      and fails against today's code. Its absence is why this survived six
      sprints.
- [ ] A host test fails today for `move(30, 180)` — the smallest nominal-rate
      case unambiguously over budget — asserting the move reaches its commanded
      heading *and* drives its commanded distance.
- [ ] Commanded-vs-believed pivot error under 1 deg on hardware, at both taper
      floor settings.
- [ ] Full suite green, flashable hex from this sprint's final state.

## Scope

### In Scope

`src/shims.cpp` (a `//%` `goToR` entry point; `startMove()`'s budget),
`src/blocks/motion.ts` (`startGoTo`, plus the two wrong doc comments the review
found), `src/blocks/world.ts` (`goToWorld`'s legs, the 25 deg cap),
`test/test.ts` (`legToward`), `src/motion/motion_engine.cpp` (the taper fix, if
the experiment confirms it), `tests/host/` (the regression tests each needs).

### Out of Scope

Stop paths (sprint 016), doc and lint gates (017), hardware accuracy campaigns
(018), wire/shim minors (019).

## Test Strategy

Every fault here is invisible to the current green suite, so the bar per ticket
is *a test that fails against today's code and passes after* — not "tests pass".
The specific gap: existing `goTo` host tests deliberately stay **below** the
50 deg threshold, and the threshold is the bug.

## Architecture

Compact. One change of shape: four independent implementations of
"target -> (distance, rotation)" become one, `MotionEngine::goToR()`, with three
thin callers doing unit conversion only. No new dependency direction —
`blocks/` and `test/` already reach `shims.cpp`, which already holds a
`MotionEngine`. `src/DESIGN.md` S1's layering table is unchanged.

## Use Cases

### SUC-001: A student drives to a point beside the robot
Parent: UC-002
- **Acceptance**: `goTo(10, 10)` lands within 5 mm; a target behind the robot
  does not drive the long way around; both covered by a host test that fails
  today.

### SUC-002: A commanded turn actually turns that far
Parent: UC-002
- **Acceptance**: `move(20, 180)` reaches 180 deg believed (within 1 deg) and
  drives its 20 cm, on hardware, at both taper floor settings.

## Definition of Ready

- [x] Sprint planning document complete
- [ ] Architecture review passed
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Expose `MotionEngine::goToR()` to the block layer; host regression tests **above** the 50 deg split threshold | — |
| 002 | Route `startGoTo`/`goTo`/`whileGoingTo` through it; fix the two wrong doc comments in `motion.ts` | 001 |
| 003 | Route `world.ts goToWorld` and `test.ts legToward` through it; retire the 25 deg cap and its collision with `kTurnFirstAngleRad` | 001 |
| 004 | `startMove()` budgets the **sequential** need when the split will fire, not the blended `max()` | — |
| 005 | Phase-1 -> phase-2 handoff issues `kernel_.neutral()` so the kernel's twist-hold reference re-arms; host test | — |
| 006 | **Build checkpoint** (standing convention, always last) | 001-005 |

Tickets execute serially in the order listed.

> **Ticket 005 added 2026-08-26, mechanism confirmed in code.** A split move
> unwinds its own pivot at the phase handoff. `twistRef_` (`diffdrive.cpp:585`)
> arms once and is disarmed only by `kModeNeutral`/`kModeRawDuty`; a split move
> goes phase 1 -> phase 2 via `startSegment()` with **no `neutral()` between**,
> so the kernel keeps a pre-pivot origin and an accumulated pivot reference,
> then actively trims the pivot back out when phase 2 commands twist = 0.
> Measured on tovez: pivot peaks at +185.5 deg, unwinds 17.2 deg with the robot
> in place, leg contributes +0.4 deg. A two-command control (`turn` then `go`,
> which *does* pass through neutral) holds heading to +0.3 deg — that contrast
> is the proof. Fix is in project-owned code; `diffdrive.cpp` stays byte-stable.
> Hardware re-confirmation deferred to the morning per stakeholder instruction.
> See `pivot-stops-11-degrees-short-of-commanded.md`.
