---
id: '041'
title: Cutebot Pro bring-up, calibration and the PWM/onboard handoff
status: roadmap
branch: sprint/041-cutebot-pro-bring-up-calibration-and-the-pwm-onboard-handoff
use-cases: []
issues:
- cutebot-pro-bring-up-and-handoff.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 041: Cutebot Pro bring-up, calibration and the PWM/onboard handoff

## Goals

**Depends on Sprint 040** (the Cutebot Pro board seam, port, and hybrid
actuation policy must already build and pass host tests). This sprint
puts that code on the real board for the first time. Per
`clasi/issues/cutebot-pro-bring-up-and-handoff.md`'s Proposed
resolution and `docs/design/cutebot-pro-support.md` §8's bench order
and §9's Sprint 041 paragraph, every step below produces a MEASURED
capture under `captures/cutebot-bringup-<date>/` (see
`.claude/rules/measurement-citations.md` — no capture artifact, no
claim):

1. Identity (`HELLO`), the v2 revision probe, firmware version
   (`0xA0 [0]`), a raw-pulse probe (`0x16`, whether v2 still answers
   it), and encoder sign/resolution by hand-spinning a wheel.
2. Caliper geometry (wheel diameter, track width) and pulses-per-
   revolution against the ELECFREAKS wiki's 1428 figure.
3. First Cutebot firmware build over USB: `PING`, `STATUS`, the
   `WHEELS_V` sign bake, `fullDutyVelocity`, the kernel bake for the
   3.3 V / 0.2 A motors; `MOVE_X` vs. tape for `travelCalib`; pivots
   for `rotationalSlip`.
4. The handoff probes from §3.D: the onboard loop's floor at 100 and
   150 mm/s; setpoint accuracy against our own encoder at 200/300/400
   mm/s; an up-handoff trace from a running PWM; whether a `0x10`
   write cancels a running `0x80` loop; which zero (PWM or setpoint)
   actually stops a wheel under onboard control.
5. A three-way square-tour A/B/C at `onboard_pid 0 / 1 / 2`, scored on
   closure and per-leg heading exactly like every other tour in
   `reports/`. The winner becomes this board's fleet-JSON default.
6. Close the encoder-resolution decision (§3.A: raw pulses vs. a
   longer velocity window vs. accept the quantization), answer the
   WiFi pin question (§5: is P8 exposed, or do P1/P2 become the
   per-board UART pins), and wire the servo verb (`0x40`) for the
   gripper.

Open board-identity question carried into this sprint's scope, not
resolved ahead of it: the stakeholder named **zeguz on mangi**; the
farm (2026-09-21 22:29) advertised **zetuv on magni** and no zeguz, and
zetuv refused a connect as `busy`. Step 1's `HELLO` is what resolves
which board this sprint actually runs against, and whether it is v1 or
v2 hardware.

## Problem

Nothing about the Cutebot Pro has been measured. The ELECFREAKS wiki
gives no wheel diameter, track width, gear ratio, or v2 encoder
resolution; it is unknown whether a v2 board still answers the v1
raw-pulse read, whether the 200 mm/s onboard-loop floor is enforced by
the MCU or only by the ELECFREAKS TypeScript extension, whether a
`0x10` PWM write cancels a running `0x80` onboard loop, or which zero
actually stops a wheel under onboard control. Sprint 040 lands a port
and a hybrid-actuation policy that only the host simulator has
exercised; none of its assumptions about the real hardware are yet
confirmed.

## Solution

Run the doc's §8 bench order end to end on whichever board `HELLO`
resolves to, capturing a MEASURED artifact at every step so the
handoff hazards in §3.D (up-handoff bump, down-handoff cancellation,
setpoint accuracy, per-wheel eligibility, which zero stops the wheel)
are answered by data rather than assumption, then score the three
`onboard_pid` policies against each other on a real square tour and
bake the winner as this board's fleet-JSON default.

## Success Criteria

- Every numbered step in Goals has a capture file under
  `captures/cutebot-bringup-<date>/` and a MEASURED citation naming it.
- `travelCalib`, `rotationalSlip`, `fullDutyVelocity`, and the wheel
  sign bake are all measured and baked into the board's fleet JSON.
- The four §3.D handoff hazards each have a measured answer (not an
  assumption carried over from the design doc).
- The three-way `onboard_pid` A/B/C tour comparison is scored on
  closure and per-leg heading, and the winning policy is set as the
  board's fleet-JSON default.
- The board-identity question is resolved by `HELLO` and recorded,
  before any of the other steps run.

## Scope

### In Scope

- Bench bring-up in the doc's §8 order, on the real board.
- Fleet JSON bake for the assigned board (geometry, calibration,
  `onboard_pid` default).
- The four §3.D handoff-hazard probes.
- The three-way `onboard_pid` tour A/B/C and picking the winner.
- The encoder-resolution decision, the WiFi pin answer, and the
  gripper servo verb.
- Resolving which physical board (zeguz vs. zetuv, v1 vs. v2) this
  sprint runs against.

### Out of Scope

- Any change to the board-seam architecture, the port implementation,
  or the actuation-policy logic itself — that is Sprint 040's output,
  consumed here as-is unless a bench measurement proves it wrong, in
  which case a fix is scoped as a ticket against the measured defect,
  not a redesign.
- §6 peripherals beyond the servo verb (headlights, line sensor,
  ultrasonic, IR) — later issues.
- §3.C (onboard distance/angle moves as a student fast path).

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
