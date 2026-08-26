<!-- Bench procedure written for sprint 018 ticket 004, which could not run:
     no relay was up (so no untethered radio, and USB reaches only the bench
     stand) and the room lights were off. Sprint 018 closed on its
     bench-runnable work; this campaign moved to sprint 020. Preserved
     verbatim below -- the procedure and evidence template are ready to run
     once vevov is on the playfield with a relay up and the lights on. -->

---
id: '004'
title: 'DEFERRED: goToWorld absolute-arrival re-measurement on corrected firmware'
status: exception
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: gotoworld-overshoots-by-fixed-stopping-distance.md
completes_issue: true
exception:
  thrown_by: sprint-planner
  thrown_at: '2026-08-26T12:41:13.736241+00:00'
  attempted: Wrote a full, ready-to-run camera-truthed bench procedure and evidence
    template for re-measuring goToWorld absolute-arrival error on corrected (post
    sprints 015/016) firmware, per the original single-hop protocol that measured
    a median 48.1 mm systematic overshoot. No measurement was attempted.
  conflict: 'This is a vevov- and OTOS-dependent campaign: goToWorld''s world-frame
    arrival requires vevov''s OTOS for pose seeding/tracking, and camera scoring requires
    room lights and a verified camera. Measured at sprint execution time (mbdeploy
    probe): vevov CONN=no, getez CONN=no, zavaz CONN=no; room lights (Shelly 192.168.1.122)
    output:false. No relay means no untethered radio, and USB reaches only the bench
    stand (wheels off the ground), where goToWorld cannot be meaningfully exercised
    at all. This is an external resource blocker, not a defect or implementation gap
    -- the stakeholder''s own standing overnight approval explicitly anticipated it
    ("if you can''t, then go ahead and defer"), recorded on this sprint''s stakeholder_approval
    gate.'
  surface: user-visible
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# DEFERRED: goToWorld absolute-arrival re-measurement on corrected firmware

## Description

`goToWorld` was measured (vevov, 2026-08-25, camera-truthed) to
overshoot its target by a fixed ~48 mm regardless of leg length --
median 48.1 mm across n=10 camera-scored runs, 0 of 10 inside a 20 mm
target. This is systematic (fixed distance, not proportional -- legs
of 100 cm and 60 cm both show it) and specific to `goToWorld`'s
arc-planning path (`tickedMove`/`legToward`): a plain
`RUN:straight:20` on the same robot, same session, showed no
meaningful overshoot (19.55 cm vs 20 cm commanded).

This sprint's sequencing exists precisely so this number gets
re-measured AFTER, not before, sprints 015/016's motion-path
corrections (arc consolidation, the phase-handoff fix ticket 003
verifies, the stop-delivery fix) -- every prior `goToWorld` number
describes firmware that no longer exists. Some or all of the 48 mm
bias may not survive; that is the question this ticket answers.

## Bench procedure (ready to run once unblocked)

Single-hop protocol, camera-truthed, isolating one `goToWorld` call
from tour accumulation -- the same shape as the original measurement:

1. Recalibrate the overhead camera immediately before the campaign.
   Require 10/10 ArUco ids visible and reprojection error in the same
   range as the original measurement (1.83 mm) before proceeding --
   do not run against a stale or degraded calibration.
2. Confirm the world-sensor lever arm is applied (`worldReady()`'s
   fix, already merged) -- this measurement is meaningless without it.
3. Confirm room lights are on (`GET http://192.168.1.122/rpc/Switch.GetStatus?id=0`
   shows `output: true`) before arming any run.
4. For each of n >= 10 hops:
   a. Get a camera fix on the robot's actual pose; seed the robot's
      world pose from it (`RUN:seedxy:<x>:<y>:<h>`).
   b. Command `RUN:goto:<x>:<y>` to a point roughly matching the
      original campaign's leg lengths (the tour's own 100 cm / 60 cm
      legs, not a 10 cm hop -- the original 48 mm bias was measured at
      tour-leg scale).
   c. Record the robot's own reported arrival position (`GOTO:end`'s
      preceding `OCAL:arrived` fix) AND an independent camera fix
      taken immediately after the robot reports arrival.
   d. Compute position error (camera vs commanded target) and heading
      error (camera vs robot-believed).
5. Compute closure separately (|end - start| over a full
   `RUN:tour:world` run) for contrast -- the original campaign found
   closure flatters this defect (median 15.3 mm) while absolute
   arrival exposes it (median 48.1 mm), because a fixed overshoot at
   every corner largely cancels around a closed loop. Both numbers are
   needed; closure alone would not answer this ticket's question.
6. Before concluding a fix is needed, check whether
   `tools/leg_analysis.py`'s existing `straight-overrun` classifier
   (sprint 011 ticket 002) already explains the shape of whatever is
   measured -- it was built for exactly this kind of stopping-distance
   defect.

## Evidence template

| run # | seed (cam) | commanded target | robot-reported arrival | camera fix after | position err (mm) | heading err (deg) |
|---|---|---|---|---|---:|---:|
| 1 | | | | | | |
| ... | | | | | | |
| 10 | | | | | | |

Summary: median / p90 position error; count within 20 mm / 50 mm;
closure median/p90 for contrast; **stated verdict**: does the fixed
~48 mm systematic overshoot survive sprints 015/016's corrections,
survive but change magnitude, or disappear? If it survives, this
ticket's own diagnostic step (ramp-down/taper stopping distance not
subtracted from the planned segment, vs. late `serviceMove()`
completion) narrows where a follow-up fix ticket should look, but
actually fixing it is OUT OF SCOPE here per `sprint.md`'s own Out of
Scope section -- a changed-character result becomes a fresh issue with
this run's evidence, not a speculative fix carried forward from
pre-correction data.

## Acceptance Criteria

- [ ] Camera recalibrated and verified (10/10 tags, reprojection error
      recorded) immediately before the campaign.
- [ ] n >= 10 single-hop, camera-scored `goToWorld` runs at tour-leg
      scale (not 10 cm), each with an independent camera fix
      immediately after the robot's own reported arrival.
- [ ] Position error and heading error computed per run; median, p90,
      and within-tolerance counts reported.
- [ ] Closure computed separately for contrast, per the original
      campaign's own finding that closure flatters this defect.
- [ ] A stated verdict on whether the fixed ~48 mm bias survives
      sprints 015/016's corrected firmware.
- [ ] If the bias survives, evidence is left in a form (or a fresh
      issue) a follow-up ticket can act on -- not a fix attempted here.

## Testing

- **Existing tests to run**: none -- this is a hardware measurement
  campaign, not a code change.
- **New tests to write**: none.
- **Verification command**: N/A -- see bench procedure above.

## Exception

See this ticket's `exception:` frontmatter block, written via
`throw_ticket_exception`. Blocked on external hardware availability
(no vevov, no OTOS, no relay, no lights), not a defect or
implementation gap. The procedure above is ready to run as soon as the
blocker clears.
