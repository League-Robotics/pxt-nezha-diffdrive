---
id: '020'
title: Playfield accuracy campaigns on corrected motion
status: roadmap
branch: sprint/020-playfield-accuracy-campaigns-on-corrected-motion
use-cases: []
issues:
- gotoworld-overshoots-by-fixed-stopping-distance.md
- rotation-error-is-injected-by-the-legs-not-the-pivots.md
- finish-the-vevov-calibration-verification.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 020: Playfield accuracy campaigns on corrected motion

> **Split out of sprint 018 on 2026-08-26.** 018's two camera-truthed campaigns
> could not run: no relay was up, so there was no untethered radio and USB
> reaches only the bench stand; the room lights were off. Rather than hold 018
> open on external resource availability, its bench-runnable work closed and the
> playfield work moved here. The ready-to-run bench procedures and evidence
> templates written for 018 tickets 004/005 carry over — see
> `clasi/sprints/done/018-*/tickets/`.

## Goals

Re-measure this robot's absolute accuracy against camera ground truth, on
firmware whose motion paths have been corrected, and settle two open questions
that have resisted diagnosis since sprint 011.

## Problem

Sprints 015 and 016 changed the arc reduction, the phase handoff, the timeout
budget and stop delivery. **Every accuracy number on record predates them**, so
every one describes firmware that no longer exists. Two campaigns in particular
are owed a re-run:

- **`goToWorld` overshoots by a fixed ~48 mm** regardless of leg length — median
  48.1 mm over n=10 camera-scored runs, 0 of 10 inside the 20 mm target. Fixed
  distance rather than proportional, so a stopping-distance effect rather than a
  scale error. Sprint 015 rewrote the leg planning entirely (`goToWorld` now
  routes through `goToR` and its 25 deg curvature cap is gone), so this number
  may have changed character completely.
- **Rotation error is injected by the legs, not the pivots.** Isolated pivots
  *under*-rotate (camera/commanded 0.9852) while a whole tour *over*-rotates by
  +3.3 deg. That inference is now WEAKER than when it was filed: sprint 018's
  bench work showed a split move's heading loss was at the pivot→leg handoff,
  not in the leg, and the leg itself contributed only +0.3–0.4 deg. With that
  handoff fixed and confirmed, a tour whose corners no longer unwind may simply
  not have a leg problem.

Also outstanding: **`travelCalib` 0.7878 has never been checked against ground
truth.** It was measured and flashed; the verification run was never done.

## Solution

Verify the constant everything else is measured in terms of, then re-run the two
campaigns and see which findings survive.

The order matters. `travelCalib` first — it scales both distance and, through
`effectiveTrackWidth()`, rotation, so every other number is expressed in it.
Then `goToWorld` absolute arrival, then the leg-vs-pivot split.

Sprint 018 already landed the two things that make these measurements
trustworthy: every `RUN:` handler now sets one named shaping profile on entry
and records it in the capture (so a run's conditions no longer depend on what
preceded it), and `tools/field.py` carries the field limits with a pre-flight
path check.

## Success Criteria

- [ ] `travelCalib` verified against camera truth over the same twelve-leg
      protocol that produced it (three distances, both directions, camera fixes
      at rest); cam/enc within ~0.5% of 1.0.
- [ ] `goToWorld` absolute arrival re-measured, n >= 10, camera-scored, on
      firmware matching a named commit, with an explicit verdict on whether the
      fixed ~48 mm overshoot survives.
- [ ] The leg-vs-pivot rotation split re-measured with **per-boundary camera
      fixes at rest** — not a continuous recording segmented afterwards. With
      only two fixes there is no way to split the residual between leg-length
      and rotation error.
- [ ] Each campaign's capture records the shaping profile it ran under.
- [ ] Findings that did not survive are closed with the evidence; findings that
      did are restated against current firmware.

## Scope

### In Scope

Bench procedures, campaign scripts under `tools/`, and the resulting evidence.
Firmware changes only if a campaign finds something and the fix is small;
otherwise findings become issues.

### Out of Scope

- The **~5.5 deg pivot overshoot** measured on the bench (peak +187.3 deg on a
  180 deg command, sprint 018 ticket 003). Real and still unexplained, but it is
  an encoder-domain question answerable on the bench and does not need the
  playfield — it should not consume field time.
- `cleartext-run-hangs-the-link-under-active-telemetry.md`. It will bite any
  campaign that wants telemetry and a `RUN:` trigger together; sprint 018 worked
  around it by sampling on-robot and dumping afterwards, and these campaigns
  should do the same rather than waiting on a fix.

## Test Strategy

Hardware, camera-truthed, under this project's standing discipline:

- The camera is a **diagnostic, never a control input**.
- Confirm bench-vs-playfield **from the data**, never from memory of the setup —
  the OTOS `ox`/`oy` columns are the cheapest discriminator (~112 cm of travel
  across a tour on the floor, ~1 mm on the stand).
- Room lights are a Shelly at `192.168.1.122` and turn themselves off. Confirm
  `output: true` before arming a run; a dark field looks exactly like a broken
  camera.
- Verify the camera against **AprilTag 1** (the fixed field-centre marker, must
  read world (0,0)) — `camlink.py --check` looks for AprilTags 10/11 and will
  report NOT VISIBLE on a healthy camera now that the field carries ArUco.
- Compute the full projected path from a **measured** start pose before
  commanding any motion, and confirm every waypoint clears the 12 cm margin.
  `tools/field.py`'s `check_path()` now does this.

## Architecture

N/A — measurement sprint. No structural change anticipated.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] Architecture review passed or skipped
- [ ] Stakeholder has approved the sprint plan
- [ ] **vevov on the playfield** (the OTOS is vevov-only; tovez cannot serve these)
- [ ] **A relay up** — zavaz, channel 4. Never retune getez's channel 3.
- [ ] **Room lights on**, confirmed via `Switch.GetStatus`
- [ ] **Camera verified** against AprilTag 1 reading world (0, 0)

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Verify `travelCalib` 0.7878 against camera truth, twelve legs at three distances | — |
| 002 | Re-measure `goToWorld` absolute arrival on corrected firmware, n >= 10 | 001 |
| 003 | Re-measure the leg-vs-pivot rotation split, per-boundary camera fixes at rest | 001 |
| 004 | Reconcile surviving vs retired findings; close or restate each issue | 002, 003 |
| 005 | **Build checkpoint** (standing convention, always last) | 001–004 |

Tickets execute serially in the order listed.
