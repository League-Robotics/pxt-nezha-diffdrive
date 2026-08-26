---
id: '005'
title: 'DEFERRED: leg-vs-pivot rotation split, per-boundary camera fixes at rest'
status: exception
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: rotation-error-is-injected-by-the-legs-not-the-pivots.md
completes_issue: true
exception:
  thrown_by: sprint-planner
  thrown_at: '2026-08-26T12:41:18.320952+00:00'
  attempted: Wrote a full, ready-to-run camera-truthed bench procedure and evidence
    template for the leg-vs-pivot rotation split, using per-boundary camera fixes
    at rest across a nine-pose tour:wheels-shaped lap (start + 4 legs + 4 pivots),
    per the playfield rule's own decomposition. No measurement was attempted.
  conflict: 'This campaign requires overhead-camera ground truth at every one of nine
    rest poses around a lap, which requires room lights on and a camera verified against
    AprilTag 1 reading world (0,0). Measured at sprint execution time (mbdeploy probe):
    vevov CONN=no, getez CONN=no, zavaz CONN=no; room lights (Shelly 192.168.1.122)
    output:false. No relay means no untethered radio, and USB reaches only the bench
    stand, where a full tour lap cannot be driven at all (wheels off the ground).
    This is an external resource blocker, not a defect or implementation gap -- the
    stakeholder''s own standing overnight approval explicitly anticipated it ("if
    you can''t, then go ahead and defer"), recorded on this sprint''s stakeholder_approval
    gate.'
  surface: user-visible
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# DEFERRED: leg-vs-pivot rotation split, per-boundary camera fixes at rest

## Description

A contradiction, camera-truthed on vevov 2026-08-25: six isolated
`RUN:pivot:90` commands UNDER-rotate (camera/commanded 0.9852, mean,
consistent across all six), yet a full four-pivot `tour:wheels` run
OVER-rotates end to end (encoder 360.4 deg vs camera 363.7 deg, +3.3
deg net). If each of the tour's four pivots under-rotates like the
isolated ones, the pivots cannot be the source of the tour's net
over-rotation -- the remaining ~+7 deg must be injected during the
four STRAIGHT LEGS, physical heading change the wheel odometry never
sees. Travel distance is accurate to 0.5% over 320 cm, so the legs
appear to be right about how far they went while being wrong about
which way they were pointing.

**Consequence already established, do not re-litigate it in this
ticket**: do not "fix" the pivots -- they under-rotate slightly, and
correcting them would move the tour's closure the wrong way. This
ticket's job is confirming the leg/pivot split, not tuning
`rotationalSlip_` or any other constant. This project has changed its
rotation constant three times from small samples, each time wrongly at
least once; six pivots is not enough to justify touching it again, and
neither is this campaign's data on its own -- it exists to establish
WHERE the residual is injected, which is a precondition for any future
constant change, not the change itself.

The existing per-segment pass that produced the "-0.94 deg per pivot"
figure has known boundary contamination -- it was a continuous
recording segmented after the fact, not fixes taken at rest. This
ticket exists to replace that with a trustworthy measurement.

## Bench procedure (ready to run once unblocked)

Per-boundary camera fixes AT REST, not a continuous recording
segmented afterward -- the playfield rule's own nine-pose
decomposition (`.claude/rules/playfield-testing.md`): start + 4 legs +
4 pivots = 9 rest poses around one `tour:wheels`-shaped lap (100, 60,
100, 60 cm legs with 90 deg left pivots between, matching
`test.ts`'s own `LEG_CM`/tour geometry).

1. Confirm room lights on, camera recalibrated and verified against
   AprilTag 1 reading world (0, 0), before arming any run.
2. At the start pose and after EVERY leg and EVERY pivot (9 total
   boundaries), bring the robot to a full stop and take an independent
   camera fix -- do not rely on a fix taken mid-motion or inferred from
   a continuous recording. `RUN:pivot`/`RUN:straight` (or equivalent
   single-leg/single-pivot commands) issued one at a time, with the
   tick loop run to completion and the robot at rest, before each
   camera fix, satisfies this.
3. Unwrap camera yaw across each pivot -- a single before/after pair
   cannot resolve a ~90 deg turn without landing on the wrap branch
   cut. Track cumulative unwrapped heading across the whole lap, not
   per-boundary wrapped values.
4. At each boundary, record: encoder-believed heading, camera
   (unwrapped) heading, and which kind of boundary it was (leg or
   pivot).
5. Note that `RUN:pivot` does NOT call `worldReady()`, so if pivots
   are issued via that verb the OTOS/`oh` telemetry column reads a
   flat 0.00 throughout -- this is expected and not a fault; the
   camera, not the OTOS, is the ground truth for this campaign
   regardless.

## Evidence template

| boundary # | type | commanded delta | encoder delta | camera delta (unwrapped) | residual (camera - encoder) |
|---|---|---:|---:|---:|---:|
| 0 (start) | -- | -- | -- | -- | -- |
| 1 | leg | | | | |
| 2 | pivot | 90 | | | |
| 3 | leg | | | | |
| 4 | pivot | 90 | | | |
| 5 | leg | | | | |
| 6 | pivot | 90 | | | |
| 7 | leg | | | | |
| 8 | pivot | 90 | | | |

Summary: total residual attributed to legs vs. total attributed to
pivots; whether the per-pivot residual matches the previously-measured
isolated-pivot ratio (cam/cmd 0.9852) now that it is measured at rest
rather than inferred; **stated verdict**: is the leg-injected
component confirmed, and roughly how large is it per leg? This is the
number the issue's own "consequences" section says is "currently
unattributed" -- this ticket's whole job is attributing it.

## Acceptance Criteria

- [ ] All 9 boundary poses (start + 4 legs + 4 pivots) measured with
      an independent camera fix taken AT REST, not inferred from a
      continuous recording.
- [ ] Camera yaw unwrapped across the full lap.
- [ ] Per-boundary table filled in with commanded/encoder/camera
      deltas and residuals, split by boundary type (leg vs. pivot).
- [ ] Stated verdict on how much of the tour's net +3.3 deg
      over-rotation is attributable to legs vs. pivots, with the
      isolated-pivot result (cam/cmd 0.9852) checked for consistency
      against this campaign's own pivot residuals.
- [ ] No change made to `rotationalSlip_` or any other rotation
      constant as part of this ticket -- confirming the split is the
      deliverable, not tuning a constant from it.

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
