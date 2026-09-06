---
id: '031'
title: Drivetrain tuning and gate acceptance on tovez
status: done
branch: sprint/031-drivetrain-tuning-and-gate-acceptance-on-tovez
use-cases: []
issues:
- tovez-drivetrain-tuning-and-restated-acceptance-bars.md
- segment-moves-end-early-just-after-boot.md
- wire-done-reason-is-resolved-lazily.md
- parallax-k-and-registered-mount-z-correct-twice.md
- pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md
- sprint-030-hardware-acceptance-needs-one-bench-session.md
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

This is a hardware sprint: the "test strategy" is the bench session plan
below, plus the host tests each code fix carries. Every measured claim
follows `measurement-citations.md` — a named capture path, board, and
date, or `UNVERIFIED` with what would settle it. No claim is written
before the capture exists.

**Physical sessions.** tovez needs two reflashes across this sprint (a
consolidated build after the wire/motion code fixes; a second after
gains are baked as new defaults), which naturally partitions the work
into three contiguous robot-powered blocks — never interleaved with
desk work mid-block:

1. **Session A — pre-reflash baseline** (current firmware
   `1.20260903.1`, pre-sprint-030). Three cold boots: capture the
   raw-zero teleport check's PRE-FIX baseline (sprint-030 item 3 needs
   this to mean anything) and the cold-boot early-end diagnostic
   (STATUS polled at 8 Hz from send on the first ~10 `MOVE_X` segments
   after each boot). One session, two purposes, same power cycles.
2. **Session B — post-reflash-1** (consolidated build: sprint 030's
   already-merged fixes + this sprint's wire/motion code fixes). Order
   within the session: pre-flight (lights, camera calibration, AprilTag
   1 at world zero, tag 52's registration confirmed), sprint-030's
   bus-guard and fiber-identity checks plus item 4's post-fix
   comparison against Session A's baseline, then the cold-boot
   early-end re-verification, then the live kernel-gain tuning and
   per-wheel asymmetry measurement — all of that on the ONE
   consolidated binary, iterating gains via `SET` with no reflash
   needed mid-block. The stack-canary check (item 5B) is deliberately
   run LAST, as its own bracketed sub-cycle: it needs a distinct
   `DIFFDRIVE_FAULT_SPIN` build (a debug-only scaffold, source-reviewed
   but never toolchain-built before this sprint) that must not be the
   binary any tuning measurement above was taken against. Flash the
   canary build, run the tour-plus-radio-RUN scenario, halt with pyOCD
   and scan the stack, then **reflash back to the plain consolidated
   build** before Session C — Session C's gate rerun must run on
   production firmware, not the debug-instrumented one.
3. **Session C — post-reflash-2** (baked defaults from Session B's
   converged values). Restated G1-G6 rerun plus the 500 mm square,
   three laps, against the restated bars.

**Host coverage.** Every code-touching ticket (wire done-reason latch,
cold-boot early-end gating, kernel gain defaults) lands or extends a
host test in `tests/host/` before it goes anywhere near the robot;
`tests/host/test_profile_probe.py`'s `LaggedRig` is the harness for the
gain retune and the lagged/skewed-wheel early-end model. The parallax
fix gets a host test that a registered tag's distance is used
unscaled. The K2 stale-velocity ticket is verification-only against
tests already in the suite (`test_kernel_reference_handling.py`,
`test_frozen_encoder_hold.py`) — see Design Rationale.

## Architecture

**Substantial** — this sprint touches five existing modules with
independent, already-diagnosed point fixes plus two rounds of constant
retuning: `core/diffdrive`'s gains, `motion/segment`+`motion_engine`'s
early-termination gating, `comms/wire_adapter`'s completion-reason
resolution, the `tools/` parallax-correction ownership, and a
test-tooling consolidation in `tests/playfield/turn_calibration.py`
(`shims.cpp` and radio-robot-lib's `tovez.json` are composition/bake
artifacts of those five, not additional modules in their own right).
That is 3+ modules touched, which puts it in the substantial tier by
the letter of the sizing rule — but, as with sprint 020, **no
component/dependency diagram is included**: nothing new is being
composed, no module gains a new collaborator, no dependency changes
direction, and no data model changes. Each fix is a self-contained
correction to a decision a single existing module already owns
(diagnosed down to the line in the linked issues).

**Full detail lives in this sprint's `design/` overlay**
(`Project.design_docs_opt_in` is `True`):
`clasi/sprints/031-.../design/DESIGN.md` (the edited copy of
`src/DESIGN.md` — §3's `Segment::wrongWay()` narrative gets a new
"Sprint 031" paragraph on the cold-boot minimum-progress gate, and §5's
"Motion-completion resolution" narrative gets a new "Sprint 031"
paragraph on latching the done-reason at the engine's inactive
transition instead of at poll time) and
`clasi/sprints/031-.../design/playfield-DESIGN.md` (the edited copy of
`tests/playfield/DESIGN.md` — the G1-G6 consolidation and the restated
G1/G2 bars, with the full rationale for restating rather than only
improving the fixture). This section summarizes the responsibilities
and modules touched; see the overlay for the full module-level
narrative and design rationale on those two points.

**`tools/DESIGN.md` could not be seeded into the overlay alongside
`src/DESIGN.md`** — both are their own source root's top-level
`DESIGN.md`, and `seed_sprint_design_overlay` derives a bare
"DESIGN.md" overlay slug for each, so seeding both in one call silently
drops one (flagged as a CLASI tooling defect, task_d119bad8). Ticket
002 (the parallax-ownership fix) updates `tools/DESIGN.md` directly as
a normal git-tracked edit instead, documenting the single-owner
parallax convention — see that ticket.

**Responsibilities touched, by module:**

- **`comms/wire_adapter`** — latch the wire's completion reason at the
  engine's own inactive transition, not lazily at the next unrelated
  poll. Independent of every other fix below; pure protocol-layer
  timing bug. Serves SUC-004.
- **`motion/segment.h` + `motion/motion_engine`, `core/diffdrive`'s
  latch windowing** — gate the early-termination checks (wrong-way
  margin, stall latch) against cold-boot startup skew, so the wheels'
  first-move skew after a power cycle can't trip them before real
  motion begins. Serves SUC-003.
- **`core/diffdrive`'s `Config` gains, baked in `shims.cpp`** — retune
  `kp`/`ki`/`kaff` so a 200 mm/s step doesn't overshoot to
  226-256 mm/s. Serves SUC-002. Verification-only alongside this: the
  stale-velocity/position-reference fix (K2) already landed in sprint
  029 — ticket 004 confirms it closes this sprint's linked issue rather
  than re-deriving a fix.
- **`core/diffdrive`'s twist-hold gain, or `motion/motion_engine`'s
  `travelCalib_` baked from radio-robot-lib's `tovez.json`** — cancel
  the per-direction leg-heading asymmetry. Try the twist-hold gain
  first: it's already live-settable over the wire (`setTwistHoldGain`,
  no reflash), strictly cheaper to iterate than a per-wheel
  `travel_calib` bake, which costs a reflash per attempt. Fall back to
  the bake only if the twist-hold sweep plateaus above the 1° bar.
  Serves SUC-001.
- **`tools/`** (`camlink.py`, `field_dance.py`,
  `field_calibration.json`, and the audited siblings `reposition.py`,
  `park.py`, `tour_*.py`, `leg_analysis.py`, `pivot_truth.py`) — one
  owner for camera parallax correction (register `mount_z_cm`, delete
  the tool-side `parallax_k`), chosen because the daemon-side
  correction is already the single source of truth for every OTHER
  registered tag in the fleet — keeping a second, tool-side factor is
  what let this exact class of bug (two layers each believing they own
  a correction) recur after it was already fixed once (`fc5588f`).
  vevov's existing `k = 1.119` entry is explicitly NOT touched by this
  sprint — flagged as a fast-follow re-fit, not silently changed.
  Purely host-side; no firmware impact. Serves SUC-006.
- **`tests/playfield/turn_calibration.py`** — fold sprint 029's ad hoc
  G1-G6 acceptance scripts in as named modes, and restate G1/G2 (see
  the overlay for the full rationale). Serves SUC-005, SUC-007.
- **Sprint-030 verification (`shims.cpp`/`platform/otos_port.cpp`,
  `comms/protocol.cpp`, stack-canary scaffold)** — no new behavior;
  this sprint runs the four hardware acceptance checks sprint 030's own
  code never got on real hardware. Serves SUC-008.

**Impact on Existing Components**: none of these changes alter a
public block-API surface or the wire grammar's shape —
`resolvePendingReason()`'s output values (`stop`/`timeout`) are
unchanged, only their timing; `Segment::wrongWay()`'s check still
exists, only its cold-boot gating changes; the kernel's `Config` fields
are unchanged in name or unit, only their default values move.
Existing callers, tests, and student programs are unaffected.

**Migration Concerns**: tovez needs three flashes — the main
consolidated build (Session B start), a bracketed
`DIFFDRIVE_FAULT_SPIN` canary build for the stack-canary check alone
(Session B end, immediately reflashed back), and the baked-defaults
build (Session C). Until Session B's first flash lands, the robot runs
pre-sprint-030 firmware and none of this sprint's fixes apply — do not
interpret Session A's readings as reflecting any code in this sprint.
No tuning measurement may be taken against the canary build.

**Open questions**: (1) does the twist-hold sweep alone hold both leg
directions inside 1°, or is the `travel_calib` bake actually needed —
resolved by Session B's measurement, not before; (2) is the restated
G1/G2 bar acceptable as a standing gate, or should a fixture
improvement (second tag, more samples) be scheduled instead — this
sprint restates the bar, it does not decide the fixture question;
(3) the K2 fix's upstream (`radio-robot-elite`) paired-PR sync status
is unconfirmed — ticket 004 flags it rather than performing the sync;
(4) if Session A's capture shows the two unexplained straight-line
early-ends are a refused `kernel_.drive()` rather than the stall latch,
ticket 005's fix targets a different code path than currently
diagnosed — its plan names both candidates and defers to the capture.

## Use Cases

Sized to the change: each SUC below restates or hardens an existing
use case's acceptance envelope rather than introducing new robot
behavior. None of these are new blocks or new student-facing surface.

### SUC-001: A commanded straight leg holds heading regardless of direction
Parent: UC-003 (Drive a Straight Distance)

- **Actor**: A program (or calibration script) commanding `MOVE_X` in
  either direction.
- **Preconditions**: tovez calibrated, on the playfield, camera healthy.
- **Main Flow**:
  1. Command a 600 mm leg forward; camera-truth the heading change.
  2. Command a 600 mm leg reverse; camera-truth the heading change.
  3. Compare against the ≤ 1° bar in both directions.
- **Postconditions**: The twist-hold gain (and, if needed, a baked
  per-wheel `travel_calib`) is set such that both directions hold.
- **Acceptance Criteria**:
  - [ ] Six of six 600 mm legs (three forward, three reverse) hold
        heading within 1°, camera-truthed, capture cited.
  - [ ] The chosen fix (twist-hold retune vs. `travel_calib` bake) and
        its final value are recorded with the capture that justified it.

### SUC-002: A velocity step does not overshoot the commanded profile
Parent: UC-002 (Drive at a Constant Speed or Twist)

- **Actor**: The kernel's velocity-tracking control loop.
- **Preconditions**: tovez on the bench or playfield; consolidated
  firmware (post sprint-030 + this sprint's motion/wire fixes) flashed.
- **Main Flow**:
  1. Command a 200 mm/s step; measure peak wheel speed and acceleration
     against encoder and camera.
  2. Compare against the retuned gain defaults' predicted response from
     the host lagged-rig model.
- **Postconditions**: New `kp`/`ki`/`kaff` defaults are baked in
  `shims.cpp` once hardware confirms the host model's prediction.
- **Acceptance Criteria**:
  - [ ] A 200 mm/s step peaks ≤ 210 mm/s, measured acceleration
        ≤ 1.5×`accel` (target ≤ 600 mm/s²), capture cited.
  - [ ] The already-landed K2 stale-velocity/position-reference fix
        (`core/diffdrive.cpp`'s `positionError()`) is confirmed to
        still cover the encoder-fault-recovery transient this sprint's
        linked issue described; existing host test coverage
        (`test_kernel_reference_handling.py`,
        `test_frozen_encoder_hold.py`) is cited or extended if a gap
        is found.

### SUC-003: No commanded segment ends early in the minutes after a cold boot
Parent: UC-003 (Drive a Straight Distance) / UC-004 (Pivot in Place)

- **Actor**: The motion engine's early-termination checks
  (wrong-way abort, stall latch).
- **Preconditions**: A genuinely cold boot (power cycle, not a warm
  reconnect).
- **Main Flow**:
  1. Boot tovez; poll STATUS at 8 Hz from the send of each of the first
     ten `MOVE_X`/pivot segments.
  2. Confirm none end early for a reason other than the commanded
     completion.
  3. Repeat across three independent cold boots.
- **Postconditions**: The wrong-way margin and/or stall latch are
  gated so cold-boot startup skew cannot cross them.
- **Acceptance Criteria**:
  - [ ] Zero early-ending segments across the first ten moves after
        each of three cold boots, capture cited per boot.
  - [ ] A host test with a lagged, skewed wheel model reproduces the
        pre-fix early-end and confirms the fix.

### SUC-004: The wire reports the true completion reason regardless of poll timing
Parent: UC-007 (Start a Move Without Blocking and Poll It)

- **Actor**: Any tool or program reading `done=`/`reason=` off STATUS.
- **Preconditions**: A segment that arrives well inside its lease.
- **Main Flow**:
  1. Command a move that will arrive early.
  2. Poll STATUS at a cadence slow enough that, under the old lazy
     resolution, the lease would appear to have elapsed first.
  3. Confirm `reason=stop`, not `reason=timeout`.
- **Postconditions**: `resolvePendingReason()`'s reason is latched at
  the engine's own inactive transition.
- **Acceptance Criteria**:
  - [ ] Host test: arrive early, advance the clock past the lease,
        STATUS reads `reason=stop`.
  - [ ] On-hardware spot check reproduces a `reason=stop` result on a
        segment shaped like `pivot-gates-gain2.log`'s Phase B case.

### SUC-005: The camera-truthed acceptance bars are resolvable at the instrument's own noise floor
Parent: UC-013 (Calibrate the Chassis for a Non-Reference Kit)

- **Actor**: The stakeholder / acceptance-gate reviewer.
- **Preconditions**: Camera at-rest noise and position repeatability
  measured (already done, sprint 029).
- **Main Flow**:
  1. Restate G1 (mean|err| ≤ 1.0°, sd ≤ 1.0°, ≥ 20-sample averaged
     fixes) and G2 (endpoint ≤ 10 mm) in
     `tests/playfield/turn_calibration.py`.
  2. Keep G3 (length), G4 (first-tick), G5 (tracking), G6 (closure vs.
     baseline) as-is.
- **Postconditions**: The gate suite's bars are all resolvable by the
  instrument that reports them.
- **Acceptance Criteria**:
  - [ ] Restated bars committed with the rationale (this document's
        Design Rationale) cited alongside them.
  - [ ] G1-G6 rerun in Session C passes against the restated bars,
        capture cited per gate.

### SUC-006: A measured camera distance reflects exactly one parallax correction
Parent: UC-013 (Calibrate the Chassis for a Non-Reference Kit)

- **Actor**: Any host tool computing a distance from a registered tag.
- **Preconditions**: A tag registered with a non-zero `mount_z_cm`.
- **Main Flow**:
  1. Drive a known distance.
  2. Compute the distance from the camera's registered-tag reading.
  3. Confirm it matches the commanded distance within travel-calib
     tolerance, not scaled by an extra factor.
- **Postconditions**: `parallax_k` is removed from every tool that
  divided by it, or every tag is registered at `mount_z 0` and the
  tool-side factor is kept — exactly one, recorded in Design Rationale.
- **Acceptance Criteria**:
  - [ ] Host test: a registered tag's distance is used unscaled.
  - [ ] A repeat of `field-dance-refit-run1.log`'s drives reads within
        tolerance of the commanded distance, capture cited.
  - [ ] vevov's existing entry is flagged (not silently changed) for a
        fast-follow re-fit under the chosen convention.

### SUC-007: One program runs the fleet's calibration and acceptance suite
Parent: UC-013 (Calibrate the Chassis for a Non-Reference Kit)

- **Actor**: Whoever runs a calibration or acceptance session on any
  robot in the fleet.
- **Preconditions**: Sprint 029's ad hoc `g1`-`g6` acceptance scripts
  and `tests/playfield/turn_calibration.py` both exist.
- **Main Flow**:
  1. Fold each sprint 029 acceptance script's behavior into
     `turn_calibration.py` as a named mode.
  2. Retire the standalone scripts (or leave them as thin wrappers, if
     retiring outright breaks a still-cited capture path).
- **Postconditions**: One program, multiple modes, covers what used to
  be a family of one-off scripts.
- **Acceptance Criteria**:
  - [ ] Every sprint 029 acceptance behavior (G1-G6) is reachable as a
        `turn_calibration.py` mode.
  - [ ] Session C's G1-G6 rerun uses the consolidated program, not the
        original standalone scripts.

### SUC-008: Sprint 030's safety mechanisms are verified on real hardware, not just in host tests
Parent: N/A — verification of sprint 030's internal safety mechanisms
(bus guard, fiber identity, raw-zero rejection, stack canary), not a
new or changed student-facing use case.

- **Actor**: The team-lead, running the scripted bench session.
- **Preconditions**: Sessions A (pre-fix baseline) and B (post-reflash)
  as scheduled in Test Strategy.
- **Main Flow**:
  1. Session A: cold-power-up baseline for the raw-zero check.
  2. Session B: bus-guard mid-drive OTOS-read scenario; fiber-identity
     button-handler-during-RUN and block-side-startMove-during-wire-
     obligation scenarios; raw-zero post-fix comparison; stack-canary
     scan under a `DIFFDRIVE_FAULT_SPIN` build (sanity-built first,
     since it was source-reviewed only until now).
- **Postconditions**: Each of the four items is recorded as measured
  (with artifact) or `UNVERIFIED` with what was tried — never a
  fabricated pass.
- **Acceptance Criteria**:
  - [ ] Item 1: `i2cf` does not climb across a mid-drive OTOS-read run.
  - [ ] Item 2: both fiber-identity scenarios behave as designed
        (no `lineBuf_` corruption; second `startMove()` refused with
        `kBusy`).
  - [ ] Item 3: Session A's pre-fix baseline and Session B's post-fix
        run both show no odometry position jump in the first ~40 cm —
        compared, not just individually reported.
  - [ ] Item 4: the stack canary's first non-`0xA5` byte is comfortably
        under the fiber's documented 2 KB high-water mark.

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

| # | Title | Type | Depends On |
|---|-------|------|------------|
| 001 | Session A: pre-reflash cold-boot baseline (raw-zero teleport + early-end diagnostic capture) | (a) hardware | — |
| 002 | Fix camera-parallax double correction: one owner for mount_z_cm vs parallax_k | (b) desk | — |
| 003 | Latch wire done-reason at engine-inactive transition (fix lazy resolvePendingReason) | (b) desk | — |
| 004 | Confirm the K2 stale-velocity/position-reference fix closes the issue; flag upstream sync status | (c) analysis | — |
| 005 | Diagnose and fix cold-boot early-ending segments using Session A's capture | (b) desk | 001 |
| 006 | Kernel FF/I gain retune: candidate values from the host lagged-rig model | (b) desk | — |
| 007 | Restate G1/G2 bars and fold sprint 029's acceptance scripts into turn_calibration.py as modes | (b) desk | — |
| 008 | Build consolidated tovez firmware (sprint 030 + this sprint's wire/motion fixes) | (b) desk | 003, 005 |
| 009 | Session B (1/5): reflash consolidated build; pre-flight; sprint-030 bus-guard, fiber-identity, raw-zero post-fix comparison | (a) hardware | 001, 008 |
| 010 | Session B (2/5): re-verify cold-boot early-end fix across three cold boots | (a) hardware | 005, 009 |
| 011 | Session B (3/5): live kernel FF/I gain tuning and step-response verification on hardware | (a) hardware | 006, 009 |
| 012 | Session B (4/5): per-wheel forward/reverse asymmetry measurement and live twist-hold retune | (a) hardware | 009 |
| 013 | Sanity-build the DIFFDRIVE_FAULT_SPIN stack-canary scaffold | (b) desk | 008 |
| 014 | Session B (5/5): stack-canary bracketed cycle — flash, run, scan, reflash back | (a) hardware | 011, 012, 013 |
| 015 | Bake final kernel gains and per-wheel calibration as firmware defaults; rebuild | (b) desk | 011, 012 |
| 016 | Session C: reflash with baked defaults; rerun restated G1-G6 plus 500 mm square | (a) hardware | 007, 014, 015 |

Tickets execute serially in the order listed. Physically, this groups
into three robot-powered blocks: **Session A** (ticket 001, on
pre-sprint-030 firmware), **Session B** (tickets 009-012 and 014, one
reflash, with 014's canary sub-cycle bracketed and reflashed back at
the end), and **Session C** (ticket 016, after the final bake).
Tickets 002-008, 013, and 015 are desk/analysis work done between
sessions.

## Close-out note on the design overlay (team-lead, 2026-09-05)

`close_sprint`'s `design_overlay_apply` step wrote this sprint's
`design/DESIGN.md` and `design/playfield-DESIGN.md` overlays into the
worktree the sprint was PLANNED from (`robot-circular-movement-e0358d`,
recorded as absolute paths in `design/_sources.json`), not into this
branch. That write was reverted there and `_sources.json` repointed at
this worktree. The overlay was NOT merged into this branch's
`src/DESIGN.md` / `tests/playfield/DESIGN.md`: the diff was cut against
that other worktree's older files and would have removed sections
tickets 019 and 020 wrote during the sprint. The sprint's design record
lives intact in `design/`; the branch's DESIGN.md files carry the
per-ticket updates. Reconciling the two is a documentation task for the
next planner, not a silent overwrite at close.
