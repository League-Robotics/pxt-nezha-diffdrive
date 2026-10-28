---
id: '006'
title: speed_path A/B on WHEELS_V and a kernel leg
status: open
use-cases: [SUC-004]
depends-on: ["001","002"]
github-issue: ''
issue: fine-velocity-actuator-behind-a-speed-path-switch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# speed_path A/B on WHEELS_V and a kernel leg

## Description
Hardware half of the fine-velocity issue (host half shipped in 042). `speed_path 0` (0x60 integer percent) against `1` (0x77 + 0x70 mode 3, 11.5 deg/s per %, bare 0x70 refresh every 400 ms) on `WHEELS_V` at several speeds (include low speeds near the floor) and on a 600 mm kernel leg (`position_mode 0`), bench rig first, then zuvat. Measure speed hold (mean and spread of wheel speed from telemetry) and heading error on the leg. Verify the 400 ms refresh keeps the motor running (no stalls/stutter).

## Acceptance Criteria
- [ ] For each of paths 0 and 1: speed-hold error and spread at >= 4 speeds on both rigs, as a table with capture paths.
- [ ] 600 mm leg heading error and final distance error, >= 4 runs per path on zuvat.
- [ ] A decision line for the `speed_path` default; the default stays 0 unless 1 is clearly better and stall-free (this ticket does not change it; ticket 009 does).

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
