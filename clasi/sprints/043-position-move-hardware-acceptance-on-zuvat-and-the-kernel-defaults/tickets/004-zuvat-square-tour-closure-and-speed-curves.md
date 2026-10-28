---
id: '004'
title: Zuvat square tour closure and speed curves
status: done
use-cases:
- SUC-001
depends-on:
- '002'
- '003'
github-issue: ''
issue: position-move-hardware-acceptance-and-the-zuvat-square.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Zuvat square tour closure and speed curves

## Description
THE stakeholder deliverable (2026-10-27): "run a square tour with two motors and show me the square completion: the metric on how closely you complete the square, and the speed curves for the motors during the square tour."

On zuvat run the square tour (`RUN:tour:square:<side>` from `test/test.ts` `squareTour`, 4 x tickedMove(side,0) + tickedMove(0,90); sides 50 or 60 cm) at `position_mode 0` and `position_mode 1`, at least 5 laps each (reset pose at the start of each lap or capture start/end per lap), captured with `tools/tour_capture.py --wifi 127.0.0.1`, charted with `tools/tour_chart.py` (`uv run --with numpy --with matplotlib`; x-y path with start-to-end closure and the wheel-speed panel). Copy the layout of `captures/vevov-square-20260829/`. Add a small helper (e.g. `tools/square_closure.py`, with a host test on a synthetic CSV) that computes, per lap: start-to-end distance (mm) and heading residual (deg), plus mean/worst across laps, and writes a comparison table (markdown + CSV). Run `position_mode 2` too if arcs are exercised in the same session (otherwise ticket 005).

## Acceptance Criteria
- [x] Per lap, per mode: closure distance (mm) and heading residual (deg), >= 5 laps per mode, in a CSV and a table in `notes.md`.
- [x] Comparison table mode 0 vs mode 1 (mean, worst) with a target line: closure better than 11 mm (the sprint 031 figure); state met / not met.
- [x] tour_chart PNGs for each mode showing the x-y path with closure and the left/right wheel-speed curves.
- [x] Every figure labelled ENCODER truth (no camera); a short note on what the encoders cannot see (wheel slip, trackwidth error).
- [x] Summary paragraph ready to paste into the sprint postmortem (ticket 009).
- [x] Helper has a passing host test.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
