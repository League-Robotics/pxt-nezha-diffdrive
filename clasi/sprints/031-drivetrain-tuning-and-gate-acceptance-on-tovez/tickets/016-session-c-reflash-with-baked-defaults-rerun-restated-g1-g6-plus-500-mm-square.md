---
id: '016'
title: 'Session C: reflash with baked defaults; rerun restated G1-G6 plus 500 mm square'
status: open
use-cases: [SUC-001, SUC-002, SUC-005, SUC-007]
depends-on: ['007', '014', '015']
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session C: reflash with baked defaults; rerun restated G1-G6 plus 500 mm square

**Type: (a) hardware/playfield — team-lead executes personally. Final
session; closes out the sprint's Success Criteria.**

## Description

Flash ticket 015's baked-defaults build (confirmed to be the plain
build, not the canary variant — see ticket 014's reflash-back).
Pre-flight as usual (lights, camera, AprilTag 1, tag 52). Using ticket
007's consolidated `tests/playfield/turn_calibration.py`, run:

1. G1-G6 against the restated bars (G1 mean|err| ≤ 1.0°/sd ≤ 1.0° with
   ≥ 20-sample fixes; G2 ≤ 10 mm endpoint; G3-G6 unchanged).
2. A 500 mm square, three laps, confirming closure under the 10.8 mm
   baseline.
3. A repeat of the 600 mm leg heading check (six legs, both
   directions) as a final confirmation of ticket 012's twist-hold/
   `travel_calib` bake, now running on the REBUILT firmware rather than
   the live-`SET` values from Session B.

This is the sprint's closing measurement — every Success Criteria bullet
in `sprint.md` should be answered, pass or `UNVERIFIED`, by this
ticket's closing note.

## Acceptance Criteria

- [ ] tovez confirmed running ticket 015's baked-defaults build before
      any gate is run.
- [ ] G1-G6 all pass against the restated bars, capture cited per gate,
      using the consolidated `turn_calibration.py` program.
- [ ] 500 mm square, three laps, closes under 10.8 mm.
- [ ] Six of six 600 mm legs (both directions) hold heading within 1°
      on the REBUILT firmware (confirms the bake, not just the live
      `SET` value from Session B).
- [ ] Every constant that changed this sprint is confirmed baked in
      `shims.cpp` and/or `radio-robot-lib/config/robots/tovez.json`
      with its capture cited — this sprint's own Success Criteria,
      quoted verbatim.
- [ ] Any bar not met is recorded as such, with what was tried — not
      silently rounded up to a pass.

## Testing

- **Existing tests to run**: N/A — final hardware acceptance session.
- **New tests to write**: none.
- **Verification command**: N/A (hardware ticket).
