---
id: 009
title: Hardware acceptance on OTOS and encoder-only robots
status: done
use-cases: [SUC-001, SUC-002, SUC-003]
depends-on: ['008', '005', '010', '012']
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware acceptance on OTOS and encoder-only robots

## Description

Camera-truthed acceptance. (a) vevov (OTOS): 100 m random run with tests/dev/otos_drift.py, no camera re-zero, plus stationary 30 min with tests/dev/otos_gyro.py. (b) tigez (encoders only, chosen by the stakeholder 2026-10-28): same leg run, checking no wrong-way stalls and arrival accuracy. Score with otos_drift_report.py; write results to captures/ with date and board; every measured figure cites its capture file per .claude/rules/measurement-citations.md; anything not run is marked UNVERIFIED. Follow the repo rules for connecting to a robot, camera-checked steps, and not driving blind. Requires stakeholder-arranged robot access.

## Acceptance Criteria

- [x] OTOS: pose error <= 15 cm rms, heading <= 3 deg rms (2nd half), zero wrong-way stalls (tovez-drift5; vevov-drift12)
- [ ] OTOS: arrival median < 1 cm, p90 < 2 cm. Met once (tovez-drift5, 0.99 / 1.76), not repeated: tovez-drift11 1.13 / 2.18, vevov-drift12 1.57 / 3.22
- [x] Stationary 30 min: heading change < 2 deg after settling (tovez-rest1)
- [ ] tigez (encoders only): UNVERIFIED, not run; carried to `clasi/issues/sprint-044-close-out-housekeeping.md`
- [x] Disturbance check (ticket 010): bump taken in, heading followed through lift-and-turn; lift corrupts position by ~3 cm (tovez-disturb1; `clasi/issues/lift-corrupts-position-use-the-accelerometer.md`)
- [x] Captures committed under captures/sprint044-acceptance-20261028/ (NOTES.md and the run logs; hex files and the two multi-MB disturb streams stay local)

## Testing

- **Existing tests to run**: `uv run pytest` (host suites unaffected)
- **New tests to write**: Hardware runs described above
- **Verification command**: `uv run pytest`

## Overnight results, 2026-10-28/29 (team lead; stakeholder asleep)

Full log, citations and incident notes: `captures/sprint044-acceptance-20261028/NOTES.md`
(captures/ is gitignored; files are local on gala).

OTOS acceptance ran on **tovez** (tag 52), not vevov: vevov's Pi Zero `zilch` went
unreachable at ~23:05, so vevov could not be re-flashed after the overnight fixes
(tickets 012-015). The final build is sprint branch at 54b5f4d plus
`--bake otos_angular_scale=0.990 --bake otos_linear_scale=1.021`
(`tovez-015-lin.hex`).

100 m random GO_TO_W run, one rebase, never re-zeroed (`tovez-drift5.jsonl`, 273
legs, 82 min):
- pose err, 2nd-half rms 11.5 cm (max 14.0): meets <= 15 cm
- heading err, 2nd-half rms 2.35 deg: meets <= 3 deg. Raw OTOS drifted -87 deg
  (-64 deg/h) over the same run.
- wrong-way stalls 0
- arrival median 0.99 cm, p90 1.76 cm: meets < 1 / < 2

Not yet done (needs the stakeholder):
- encoders-only robot (tigez) leg run
- bump and lift-and-turn disturbance check (ticket 010)
- vevov re-flash with its measured arm (-105.9, 2.9 mm, chip units scaled) and
  linear scale 1.033 (`vevov-015.hex` is built)
- stationary 30 min on the final build: running now (`tovez-rest1.jsonl`)

Findings that became tickets tonight: 012 (motion steps baked encoder slip), 013
(bias blend ignored rest evidence), 014 (per-robot OTOS linear scale bake), 015
(STATUS active dropped inside GO_TO_W). Harness fixes: devlink send_move waits for
`done`; camlink fix() refuses a stalled or tagless stream; otos_drift stops on a
camera/OTOS chord mismatch.

Later the same night (tovez, same final build):
- stationary 30 min (`tovez-rest1.jsonl`): estimator heading change 0.00 deg
  while the raw OTOS drifted -25.9 deg; dist 0. MEETS < 2 deg.
- speed 200, 17.5 m: arrival median 1.07 / p90 1.77 cm, heading rms 0.90 deg.
- speed 300, 15.1 m: arrival median 1.14 / p90 1.66 cm, heading rms 1.60 deg.

## 2026-10-29 results

All in `captures/sprint044-acceptance-20261028/NOTES.md`.

- tovez, OTOS arm from config (`tovez-019-config-arm.hex`, `tovez-drift11-019`): 33 legs,
  17.3 m. Pose 2nd-half rms 4.3 cm, heading rms 1.05 deg, arrival 1.13 / 2.18 cm.
- vevov, built from `radio-robot-lib/config/robots/vevov.json` alone (`vevov-020-config.hex`,
  `vevov-drift12{,b,c,d}-020`): 178 legs, 92.0 m, about an hour in four segments. Ended by
  camera dropouts in the south band and one network move. Pose rms per segment
  1.5-7.0 cm, heading rms 1.29-2.25 deg, arrival median 1.38-1.66 / p90 2.58-3.22 cm,
  wrng 0. Raw OTOS heading drift grew from +16 to +70 deg/h; the fused heading held to
  1-2 deg. Estimator/camera leg distance 1.0139, so vevov's linear scale 1.033 is about
  1.4 % long (candidate 1.023, not changed).
