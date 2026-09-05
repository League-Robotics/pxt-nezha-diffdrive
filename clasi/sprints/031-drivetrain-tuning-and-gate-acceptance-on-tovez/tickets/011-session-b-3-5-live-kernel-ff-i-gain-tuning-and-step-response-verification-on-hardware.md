---
id: '011'
title: 'Session B (3/5): live kernel FF/I gain tuning and step-response verification
  on hardware'
status: open
use-cases: [SUC-002]
depends-on: ['006', '009']
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (3/5): live kernel FF/I gain tuning and step-response verification on hardware

**Type: (a) hardware/playfield — team-lead executes personally. Live
`SET` iteration, no reflash needed mid-ticket.**

## Description

Try ticket 006's candidate `(kp, ki, kaff)` gain sets on tovez via `SET`
commands (no rebuild needed — these are runtime-settable, per
`shims.cpp`'s SET dispatch cases 2/3). For each candidate, run a
`lag-trials`-style 200 mm/s step response and measure peak wheel speed
(camera + encoder) and acceleration. Converge on the set that best
holds the bars; if none of ticket 006's candidates hold, feed the
measured discrepancy back into the host model (informally — a full
re-run of ticket 006 is only needed if the gap is large).

Record the FINAL converged `(kp, ki, kaff)` values for ticket 015 to
bake — this ticket does not touch `shims.cpp`.

## Acceptance Criteria

- [ ] Each candidate gain set is tried and its measured peak/acceleration
      recorded, camera- and encoder-truthed, capture cited.
- [ ] A converged gain set is identified that peaks ≤ 210 mm/s on a
      200 mm/s command with measured acceleration ≤ 1.5×`accel`
      (target ≤ 600 mm/s²) — this sprint's Success Criteria bar.
- [ ] If no candidate converges within budget, the closing note states
      the best achieved result and flags the gap for ticket 015/016
      rather than silently accepting a value that doesn't meet the bar.
- [ ] The converged values are written into the closing note in a form
      ticket 015 can bake directly (exact `kp`/`ki`/`kaff`).

## Testing

- **Existing tests to run**: N/A — hardware tuning session.
- **New tests to write**: none here; ticket 015's bake is what gets a
  regression-pinning host test (the new default values).
- **Verification command**: N/A (hardware ticket).
