---
id: '031'
title: Drivetrain tuning and gate acceptance on tovez
status: roadmap
branch: sprint/031-drivetrain-tuning-and-gate-acceptance-on-tovez
use-cases: []
issues:
- tovez-drivetrain-tuning-and-restated-acceptance-bars.md
- segment-moves-end-early-just-after-boot.md
- wire-done-reason-is-resolved-lazily.md
- parallax-k-and-registered-mount-z-correct-twice.md
- pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 031: Drivetrain tuning and gate acceptance on tovez

## Goals

Take the hardware findings of sprint 029's acceptance session
(`reports/bench-acceptance-029-20260904d.md` §7-§9) from "measured and
explained" to "tuned and passing" on tovez, and restate the two gate
bars the overhead camera cannot resolve. Concretely: cancel the
per-direction leg yaw (about −5 deg forward / +5 deg reverse on a
600 mm leg) so a leg holds heading within 1 deg both ways; retune the
kernel's FF/I gains so a 200 mm/s step peaks under 210 mm/s and
measured acceleration stays under 1.5×`accel` (today: 226-256 mm/s
and up to 2.5×); find and fix why segment moves end early in the first
minutes after a boot; fix the kernel's stale-velocity PID sample after
an encoder fault; and land the two host-side measurement defects that
distort every one of those numbers (the parallax factor applied twice
on a registered tag; the wire's `done= reason=` resolved lazily).
Finish with G1-G6 rerun against restated bars and a 500 mm square that
closes under the 10.8 mm baseline.

## Problem

Sprint 029 confirmed its motion profile on hardware — one shaper,
predictive arrival, no end bump, the K1 servo stable, tovez's motor
mapping baked, the pre-flight dance passing outright — and left four
things that are not the profile:

1. **Leg yaw by direction.** `g3-run-north.log`: forward legs −6.0 /
   −1.0 / −5.6 deg, reverse +4.3 / +1.7 / +5.0 deg. One wheel runs
   faster than the other at the same command and the twist hold at
   gain 2 does not cancel it. It is most of the 44 mm closure on a
   500 mm square (`g6-run-500.log`, heading residual −7…−12 deg/lap).
2. **Kernel tracking overshoot.** Wheels reach 226-256 mm/s on a
   200 mm/s command; measured acceleration up to 993 mm/s² on a
   400-limited command (`g3-run*.log`, `lag-trials.json`). The shaper's
   command obeys the limits (host tests); the kernel's gains (`ki` 6,
   `kp` 0) overshoot it. This fails the G3-peak, G4 and G5 bars.
3. **Early-ending segments after a boot.** Four `MOVE_X` moves in the
   first minutes after a boot ended early (a +180 pivot at −1.4 deg, a
   −40 cm drive at 13.4 cm, a −50 mm move that never started, a +200
   mm move stopped at 11 mm) while `WHEELS_V` holds were fine; the
   wrong-way counter explains two, nothing in the frames explains the
   other two; 15 later moves were clean
   (`segment-moves-end-early-just-after-boot.md`).
4. **Bars below the instrument.** Camera heading noise at rest is sd
   1.03 deg per sample (0.65 on a difference of 5-sample means) and
   position repeatability several mm; G1's 0.4 deg sd and G2's 5 mm
   bars cannot be resolved as measured (G1: mean|err| 2.07, sd 2.29,
   no bias; G2: endpoint mean 10 mm).

Two host-side defects sit under all of it: `field_dance.py` divides
by `parallax_k` on a tag whose registered `mount_z` the daemon already
corrects (every dance drive read 12 % short until tovez's k was forced
to 1.0), and `WireAdapter::resolvePendingReason()` labels an early
arrival `timeout` unless something polls STATUS before the lease
elapses. Plus the review's kernel finding that the PID error can use a
stale velocity sample after an encoder fault.

Sprint 030 must land first: its bus-ownership guard removes one source
of destroyed encoder samples that would otherwise muddy the gain
tuning.

## Solution

Order of work, each step measured on tovez over zilch's serial daemon
with the camera as truth and every number citing its capture:

1. Host fixes first: one owner for parallax (register `mount_z` for
   every robot and delete `parallax_k` from the tools, or the reverse —
   not both), latch the wire's done reason when the engine goes
   inactive, fix the stale PID sample; host tests for all three.
2. Per-wheel forward/reverse gain: `WHEELS_V ±v` per wheel, encoder vs
   camera; bake a per-wheel `travel_calib` or retune the twist hold
   until a 600 mm leg holds heading within 1 deg both ways.
3. Kernel FF/I retune on the lagged host model
   (`tests/host/test_profile_probe.py`), then `lag-trials`-style step
   responses on the robot: peak ≤ 210 on a 200 command, measured accel
   ≤ 1.5×`accel`.
4. Cold-boot early-end hunt: STATUS at 8 Hz from the send on the first
   moves after a boot; gate the stall detector on the shaper having
   commanded above the floor for longer than the lag, or defer the
   wrong-way check until a minimum progress; host test with a lagged,
   skewed wheel model.
5. Restate G1 (mean|err| ≤ 1.0 deg with ≥ 20-sample fixes, sd ≤ 1.0)
   and G2 (endpoint ≤ 10 mm) at the instrument's resolution — or
   improve the fix (larger tag, two tags) and keep the originals; keep
   G3 length, G4 first tick, G5 tracking, G6 closure vs baseline.
6. Rerun G1-G6 with `lag_s 0.13` baked (radio-robot-lib eafccd2) and a
   500 mm square; fold the sprint 029 acceptance scripts into
   `tests/playfield/turn_calibration.py` as modes so there is one
   calibration program.

## Success Criteria

- A 600 mm leg changes heading by ≤ 1 deg in either direction, six of six.
- A 200 mm/s step peaks ≤ 210 mm/s; measured acceleration ≤ 600 mm/s².
- No early-ending segment in the first ten moves after three cold boots.
- G1-G6 pass against the restated bars; a 500 mm square closes under
  10.8 mm on three laps.
- Every constant that changes is baked in radio-robot-lib's tovez.json
  with a capture cited.

## Scope

### In Scope

Kernel gains and their bake, per-wheel calibration, the two host-side
measurement defects, the cold-boot early end, the bar restatement, the
gate rerun, the calibration-program consolidation.

### Out of Scope

Bus/fiber safety (sprint 030), the odometry object (sprint 033),
tool consolidation beyond the calibration program (sprint 034), other
robots' tuning (same method, later).

## Test Strategy

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

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
