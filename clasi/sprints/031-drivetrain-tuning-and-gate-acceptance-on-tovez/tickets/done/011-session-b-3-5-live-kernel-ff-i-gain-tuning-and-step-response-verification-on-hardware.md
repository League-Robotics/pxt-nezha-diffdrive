---
id: '011'
title: 'Session B (3/5): live kernel FF/I gain tuning and step-response verification
  on hardware'
status: done
use-cases:
- SUC-002
depends-on:
- '006'
- 009
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

- [x] Each candidate gain set is tried and its measured peak/acceleration
      recorded, camera- and encoder-truthed, capture cited.
- [ ] A converged gain set is identified that peaks ≤ 210 mm/s on a
      200 mm/s command with measured acceleration ≤ 1.5×`accel`
      (target ≤ 600 mm/s²) — this sprint's Success Criteria bar.
      **NOT MET** — no candidate from ticket 006's list converges on
      hardware. See Closing Note.
- [x] If no candidate converges within budget, the closing note states
      the best achieved result and flags the gap for ticket 015/016
      rather than silently accepting a value that doesn't meet the bar.
- [x] The converged values are written into the closing note in a form
      ticket 015 can bake directly (exact `kp`/`ki`/`kaff`).
      **N/A** — there are no converged values; the closing note states
      the best-achieved (non-converged) result instead and is explicit
      that ticket 015 must not bake it as a pass.

## Closing Note

This ticket was executed under a CLASI OOP bypass; this note reconciles
the ticket record with work already committed on this branch. The
ticket is closed as done because the required deliverable — try every
candidate, measure honestly, and flag a non-convergent result rather
than hide it — was produced. **The tuning itself did not converge.**
Do not read this closure as a tuning success.

MEASURED tovez 2026-09-05, firmware 1.20260904.5, four `WHEELS_V 200
200 1500` steps per gain set (alternating sign), gains applied live via
`SET pid_kp` / `SET pid_ki` / `SET accel_kaff` and restored to firmware
defaults afterwards, camera travel 22-26 cm on every trial. Captures
under `captures/session-b-20260905/g5-{today,cand1,cand2,cand3}/`:

| set | kp | ki | kaff | peak (mm/s) | max rise (mm/s^2) | peak bar | rise bar |
|---|---|---|---|---|---|---|---|
| today (sprint 029 defaults) | 0 | 6 | 0 | 227 | 864 | FAIL | FAIL |
| candidate 1 | 0 | 0.5 | 0.10 | 230 | 631 | FAIL | FAIL |
| candidate 2 | 0.075 | 0.5 | 0.05 | 220 | 1394 | FAIL | FAIL |
| candidate 3 | 0.10 | 0 | 0 | 220 | 652 | FAIL | FAIL |

Bars: peak ≤ 210 mm/s (cruise × 1.05), rise ≤ 600 mm/s² (1.5 × accel 400).

Two facts anchor this result:

1. "today" at 227 mm/s reproduces sprint 029's own measured 226-256
   mm/s, which is the evidence that this sweep measured the real thing.
2. Ticket 006's host model asserts all three candidates hold BOTH
   bars; on hardware none holds EITHER. The model's `LaggedRig` carries
   a HYPOTHESIZED per-wheel residual (0.97/1.02, its own comment says
   "NOT measured") and an unfitted breakaway constant, so its absolute
   numbers do not transfer. Ticket 006's own docstring anticipated this
   and says re-running with the measured residual is the right
   extension.

**BEST ACHIEVED, for ticket 015**: candidate 3 (kp=0.10, ki=0, kaff=0)
— peak 220 mm/s (over the bar by 4.8%), rise 652 mm/s² (over by 8.7%),
and the only set whose per-trial peaks reach 204-210 mm/s. **TICKET 015
MUST NOT BAKE THIS AS IF IT CONVERGED.** The recommended next search is
a grid extension around candidate 3 (kp 0.10-0.20 with a small kaff),
ideally after re-running ticket 006's model with tovez's measured
per-wheel residual.

Also recorded, because it invalidates prior results: this sweep was
only possible after fixing two defects in
`tests/playfield/turn_calibration.py`'s `--mode g5`, present since
ticket 007 consolidated it. (a) `WHEELS_V` was sent unsequenced via
`link.send()`; it is a SEQUENCED verb, so the v6 handler silently
declined it and the robot never moved — MEASURED A/B seconds apart:
unsequenced moved 0.04 cm, sequenced `#1` moved 20.84 cm. (b) The gate
then reported `passed: true`, because zero motion trivially clears
"peak ≤ 210" and yields no acceleration samples to fail the rise bar.
Both fixed and pinned by three tests; the false-pass output is kept
deliberately at
`captures/session-b-20260905/g5-today-FALSEPASS-unsequenced/`. **ANY
G5 RESULT TAKEN FROM THAT MODE BEFORE COMMIT b26bd64 IS VOID.**

Commits: b26bd64 (the fix plus this sweep), cd8eb61.

Note `captures/` is gitignored; the paths above are committed and
readable via `git show`.

## Testing

- **Existing tests to run**: N/A — hardware tuning session.
- **New tests to write**: none here; ticket 015's bake is what gets a
  regression-pinning host test (the new default values).
- **Verification command**: N/A (hardware ticket).
