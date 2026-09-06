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

## Closing note (team-lead, 2026-09-05)

Session run personally over zilch's serial socket
(`192.168.4.52:46011`), camera-truthed throughout. Full record and every
MEASURED citation: `captures/session-b-20260905/notes.md`; per-gate
captures under `captures/session-b-20260905/ticket016/`.

**Every gate was run. Every gate FAILED.** Recording that plainly rather
than rounding anything up, per this ticket's last acceptance criterion.

| gate | bar | measured | verdict |
|---|---|---|---|
| G1 | mean\|err\| <= 1.0 deg, sd <= 1.0 deg | 1.531 / 1.775 deg | FAIL |
| G2 | mean endpoint <= 10 mm | 54.78 mm (1/6 within) | FAIL |
| G3 | length err +-3.0 mm; peak <= cruise x1.05 | -4.7 mm; 121 on a 100 command | FAIL |
| G4 | first-tick <= v_floor; accel <= 1.5x; decel <= 2.0x | 36.0 PASS; 787.9 FAIL; 490.7 PASS | FAIL |
| G5 | peak <= 210; rise <= 600 | 226; 784.6 | FAIL |
| G6 | closure <= 10.8 mm | 48 / 15 / 103 mm | FAIL |
| AC #4 | 6/6 legs within 1 deg | 0 of 6; mean 3.19 deg | FAIL |

**The sprint's Success Criteria are NOT met.** That is the headline and
it should not be softened.

### What the session did establish

1. **tovez had no turn calibration at all.** `stop_distance` 0 and a
   slip that left every pivot 5.1% short. Correcting `rotational_slip`
   to a VERIFIED 0.962 cut G1's mean\|err\| 3x, 4.604 -> 1.531 deg.
   **Recommended bake: `rotational_slip = 0.962`** (tigez's
   independently measured value is 0.9617).
2. **The real defect is that tovez's wheels are not matched** -- left
   step lag 0.168 s vs right 0.096 s, corroborated by four independent
   gates. Filed as
   `clasi/issues/tovez-wheels-are-not-matched-and-lag-is-chassis-wide.md`.
   No per-wheel config field exists, so this sprint could not have
   fixed it with the knobs it had. This is the most valuable output of
   the session and it reframes the next one.
3. **`wire_get()` returns stale readings**, so every gate banner's
   "(live)" config values may be wrong. Filed as
   `clasi/issues/wire-get-returns-a-stale-reading.md`. Worked around
   here by verifying the slip with a raw read before driving.
4. **G5's fail-closed fix is confirmed on hardware** -- all 8 trials
   travelled 20.8-23.1 cm where the pre-fix gate passed on 0.02 cm.

### Deviations from this ticket as written, stated explicitly

- **Ticket 014 (its dependency) was never run**, so the canary-vs-plain
  reflash-back it was meant to confirm did not happen. Instead the
  board carries commit 38808e1 = ticket 015's bake PLUS ticket 017's
  ownership fix, which is a strict superset of what AC #1 asks for. No
  canary build was ever flashed to this board, so AC #1's real concern
  (that a canary build is not left on the robot) is satisfied by
  construction, not by 014's procedure.
- **AC #5 (every constant that changed this sprint confirmed baked) is
  NOT verified.** `twist_hold_gain` 4.0 is confirmed in `shims.cpp` and
  resident; `rotational_slip` 0.962 was set LIVE this session and is
  **not baked anywhere** -- it is lost on the next power cycle. Baking
  it is a source edit and belongs in a ticket.
- **G6 needed `--margin 14`.** Its 25 cm default cannot admit a 500 mm
  square on an 89.3 cm field (50 + 2x25 = 100 cm needed). The worst
  corner still cleared the rail by 17.6 cm.
- **G2's arc 1 hit the 9000 ms timeout.** Whether that is a stall or
  simply too short a budget is UNVERIFIED; the discriminating re-run at
  a longer timeout was not done.

### Recommendation

Do not close sprint 031 as successful. The measurement work is
complete and the findings are strong, but no acceptance bar was met.
The per-wheel asymmetry issue should drive the next sprint, and
`rotational_slip = 0.962` should be baked before any further tuning so
the next session does not start from an unknown value again.
