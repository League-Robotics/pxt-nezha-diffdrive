---
id: 018
title: 'Bench truth: re-measure accuracy on corrected motion'
status: done
branch: sprint/018-bench-truth-re-measure-accuracy-on-corrected-motion
use-cases: []
issues:
- gotoworld-overshoots-by-fixed-stopping-distance.md
- rotation-error-is-injected-by-the-legs-not-the-pivots.md
- finish-the-vevov-calibration-verification.md
- i2c-fault-count-climbs-on-idle-bus.md
- geofence-described-in-rules-does-not-exist.md
- run-handlers-leave-a-global-shaping-profile.md
- pivot-stops-11-degrees-short-of-commanded.md
- confirm-the-handoff-fix-on-hardware.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 018: Bench truth — re-measure accuracy on corrected motion

## Goals

Re-establish what this robot's accuracy actually is, on firmware whose motion
paths have been corrected, and close the open hardware questions that have been
accumulating since sprint 011.

## Problem

Five open hardware issues, and a sequencing problem that affects all of them.

- **`goToWorld` overshoots by a fixed ~48 mm** regardless of leg length — median
  48.1 mm across n=10 camera-scored runs, 0 of 10 inside the 20 mm target. Fixed
  distance, not proportional, so it is a stopping-distance effect rather than a
  scale error.
- **Rotation error is injected by the legs, not the pivots.** Isolated pivots
  *under*-rotate (camera/commanded 0.9852) while a whole tour *over*-rotates by
  +3.3 deg. The residual must enter during the straight legs, on legs whose
  distance is accurate to 0.5%.
- **`travelCalib` 0.7878 has never been checked against ground truth.** It was
  measured and flashed; the verification run was never done. Until it is, the
  robot runs an unverified calibration constant.
- **`i2cf` climbs on a largely idle bus** — an error counter increasing while
  the robot does nothing.
- **The geofence the operating rules rely on does not exist.**
  `.claude/rules/playfield-testing.md` says "the geofence is what catches
  unexpected drift"; a repo-wide search finds those field limits only in that
  rule file. No tool, block or test program knows them.
- **`RUN:` handlers leave a global shaping profile behind**, so the same command
  produces different physical behaviour depending on what preceded it — which
  undermines every measurement in this sprint if not fixed first.

## Solution

**Sequencing is the substance of this sprint.** Sprints 015 and 016 change the
motion paths these campaigns measure — the arc consolidation, the pivot
shortfall, the timeout budget, the stop delivery. Every accuracy number taken
before those land describes firmware that no longer exists. This sprint
therefore runs **after** them, and its first tickets are the ones that make
measurement trustworthy:

1. Fix the profile leakage, so a run's conditions are determined by the run.
2. Build the geofence, so a campaign cannot drive off the field while chasing a
   number.
3. Verify `travelCalib` against camera truth — the constant everything else is
   measured in terms of.

Only then re-measure `goToWorld` overshoot and the leg-injected rotation error,
on corrected firmware, and see which survive. Some may not: an 11 deg
per-pivot shortfall and a 116 mm arc miss are large enough to have been
contaminating these campaigns.

The `i2cf` question gets its answer from sprint 016 rather than a fresh
investigation — the motion-obligation fix has a concrete mechanism to test
against.

## Success Criteria

- [ ] Every `RUN:` handler sets one named shaping profile on entry; a capture
      records which profile was in force.
- [ ] `tools/field.py` knows the field limits and the margin, and a projected
      path can be checked before a run is armed — or the rule is corrected to
      say the pre-flight check is the only guard.
- [ ] `travelCalib` verified against camera truth over the same twelve-leg
      protocol that produced it; cam/enc within ~0.5% of 1.0.
- [ ] `goToWorld` absolute arrival error re-measured on corrected firmware,
      n >= 10, camera-scored, with a stated verdict on whether the fixed ~48 mm
      overshoot survives.
- [ ] The leg-vs-pivot rotation split re-measured with **per-boundary camera
      fixes at rest**, not a continuous recording segmented afterwards.
- [ ] `i2cf` behaviour reported against sprint 016's obligation fix.

## Scope

### In Scope

`test/test.ts` (`RUN:` handler profiles), `tools/field.py` (geofence),
`tools/` campaign scripts as needed, and the bench procedures/evidence templates
this project's hardware sprints produce. Firmware changes only if a campaign
finds something and the fix is small; otherwise findings become issues.

### Out of Scope

Chasing `goToWorld`'s overshoot to a fix if the re-measurement shows it changed
character — that becomes a new issue with fresh evidence rather than a
speculative fix carried forward from pre-correction data.

## Test Strategy

Hardware, camera-truthed, with this project's standing discipline:

- The camera is a **diagnostic, never a control input**.
- Confirm bench-vs-playfield **from the data**, not from memory of what was set
  up — the OTOS `ox`/`oy` columns are the cheapest discriminator.
- Per-boundary fixes at rest beat start-and-end: with only two fixes there is no
  way to split the residual between leg-length and rotation error.
- Room lights are a Shelly at `192.168.1.122` and turn themselves off; confirm
  `output: true` before arming a run.

Every campaign ticket carries a bench procedure and an evidence template, as
sprints 010 and 011 established.

## Architecture

N/A — measurement sprint. `tools/field.py` gains the field limits and a path
check, which is additive to a module every tour tool already imports.

## Use Cases

### SUC-001: A tour's accuracy number means something
Parent: UC-012
- **Acceptance**: camera-scored, n >= 10, on firmware matching a named commit,
  with the shaping profile recorded in the capture.

### SUC-002: A campaign cannot drive off the field
Parent: UC-012
- **Acceptance**: a projected path that would breach the margin is refused
  before the run is armed.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] **Sprints 015 and 016 merged and flashed** — this sprint measures their output
- [ ] Hardware available: vevov connected, relays up, room lights confirmed on
- [ ] Camera calibrated and verified against AprilTag 1 reading world (0, 0)

## Tickets

| # | Title | Status |
|---|-------|--------|
| 001 | One named shaping profile per `RUN:` handler, recorded in the capture | done |
| 002 | Field limits and a pre-flight path check in `tools/field.py` | done |
| 003 | Split-move verb + phase-handoff fix **confirmed on hardware** | done |
| 006 | Build checkpoint | done |

> **Scope reduced during execution, 2026-08-26.** Tickets 004 and 005 — the two
> camera-truthed playfield campaigns — could not run: no relay was up, so there
> was no untethered radio and USB reaches only the bench stand, and the room
> lights were off. They moved to **sprint 020**, with their ready-to-run bench
> procedures and evidence templates preserved verbatim at
> `clasi/sprints/020-playfield-accuracy-campaigns-on-corrected-motion/bench-procedures/`.
> This sprint closed on the work that was genuinely done rather than being held
> open on external resource availability.

## Outcome

The sprint's headline result is ticket 003: **sprint 015's phase-handoff fix is
confirmed on hardware.** Three trials on vevov (bench, USB, wheels-up — valid
here because heading integrates from the encoder differential and needs no
floor):

| measure | before the fix | this run (mean of 3) |
|---|---:|---:|
| peak heading | +185.5 deg | +187.3 deg |
| **peak -> leg-start (the unwind)** | **-17.2 deg** | **-0.49 deg** |
| final heading | +168.7 deg | +183.2 deg |

The unwind — the fix's own signature — collapsed to noise. The stale twist-hold
reference across the pivot->leg handoff was the mechanism, and deferring
`startSegment()` by one `serviceMove()` call resolves it.

Two findings remain open and are recorded rather than closed:

- The **~5.5 deg pivot overshoot** (+187.3 on a 180 deg command) is a separate,
  still-unexplained mechanism that survives this fix. It is encoder-domain and
  answerable on the bench.
- `cleartext-run-hangs-the-link-under-active-telemetry.md`, discovered by this
  sprint. Ticket 003 worked around it by sampling on-robot and dumping after the
  move — this project's own documented pattern (`shims.cpp`'s `probe()` comment)
  — rather than waiting on a firmware fix.
