---
id: '003'
title: Zuvat pivots and two-wheel start skew
status: in-progress
use-cases:
- SUC-001
depends-on:
- '002'
github-issue: ''
issue: position-move-hardware-acceptance-and-the-zuvat-square.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Zuvat pivots and two-wheel start skew

## Description
On zuvat at `position_mode 1`: 90 deg and 180 deg pivots (both directions, several repeats each) and 600 mm straight legs; derive the two-wheel start skew (time between left and right wheel first motion) from v6 telemetry. Also record mid-leg twist (heading drift over a 600 mm leg) against the kernel's twist hold (`position_mode 0`, same leg) to decide whether straights need a correction. Use `tools/pivot_truth.py` / `tools/tour_capture.py` as suitable.

## Acceptance Criteria
- [ ] Encoder-side pivot error within 0.5 deg for 90 and 180 deg, at least 5 repeats per angle and direction; no lurch (no wheel-speed spike > the commanded speed in the speed panel).
- [ ] Two-wheel start skew under 10 ms from telemetry (give the median and worst).
- [ ] 600 mm leg heading drift at mode 1 vs mode 0 recorded with a stated conclusion on whether a straight correction is needed.
- [ ] Charts + CSVs + `notes.md` in the captures dir, labelled encoder truth.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
