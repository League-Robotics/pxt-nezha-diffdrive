# Sprint 039 ticket 002 hardware repro — vevov, 2026-09-15

Team-lead session. Robot **vevov** on farm node **zilch**, main playfield,
reached over the farm serial link (`mbdeploy connect --remote vevov`).
Playfield lights confirmed ON before the session
(`Switch.GetStatus` -> `output: true`).

## Baseline, BEFORE flashing the sprint build

The board was still running the nezha-robot-template bench build from the
2026-09-15 calibrateL session — the same firmware that produced
`captures/calibratel-vevov-20260915/bench-log.md`.

```
$ mbdeploy connect --remote vevov "ID"
id diffdrive calibrate-l-bench 1.20260912.8 vevov

$ mbdeploy connect --remote vevov "STATUS"
status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=111 cyc=1660 tlm=off next=1 done=0 reason=none

$ mbdeploy connect --remote vevov "STATUS"
status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=111 cyc=1660 tlm=off next=1 done=0 reason=none
```

**MEASURED vevov 2026-09-15 (this file):** on the PRE-FIX build, an idle
robot reports `active=1` with `cyc` frozen at 1660 across two reads. The
robot is stationary and nothing is ticking. This is sprint 039 ticket
002's Defect 1 — `Rig::softStop()` never steps the kernel, so the
published `Output` keeps its last mid-drive velocity and
`WireAdapter::status()`'s `active` bit reads it forever.

It is an independent confirmation of
`captures/calibratel-vevov-20260915/bench-log.md` run 9, on a different
day, by a different session, and it is the control the post-flash run is
compared against: after the fix, an idle robot must read `active=0`.

Note the counters (`i2cf=111 cyc=1660`) are LOWER than run 9's
(`i2cf=2541 cyc=2901`), so the board has been reset or power-cycled
between that session and this one. Expected; it does not affect the
`active` reading.

## Still to run

See `docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-diagnosis.md`,
"Recommended hardware repro". Steps in order: flash the sprint build
(distinguishable firmware pin), confirm `active=0` when idle, then
reproduce the reversal pair with `TLM FULL` streaming and diags 28/29
read before and after each step.
