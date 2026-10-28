---
id: '005'
title: 'Arcs: position_mode 2 vs kernel'
status: in-progress
use-cases:
- SUC-001
depends-on:
- '004'
github-issue: ''
issue: position-move-hardware-acceptance-and-the-zuvat-square.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# 'Arcs: position_mode 2 vs kernel'

## Description
Arcs: `position_mode 2` against the kernel's arcs on zuvat, using a circle (e.g. `tools/arc_capture.py`) and/or a diamond/square-of-arcs, same laps/metric/chart machinery as ticket 004 (encoder truth). Decides whether the default becomes 1 or 2.

## Acceptance Criteria
- [ ] At least 5 laps per mode (0 and 2) of the same arc path: closure distance and heading residual per lap, mean/worst.
- [ ] Speed-curve charts for both modes.
- [ ] A written decision line: mode 2 default for arcs yes/no, with the cited numbers; if equal within noise, say so and keep the lower-risk mode.
- [ ] Captures and `notes.md` in the captures dir.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
