---
id: '006'
title: speed_path A/B on WHEELS_V and a kernel leg
status: done
use-cases:
- SUC-004
depends-on:
- '001'
- '002'
github-issue: ''
issue: fine-velocity-actuator-behind-a-speed-path-switch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# speed_path A/B on WHEELS_V and a kernel leg

## Description
Hardware half of the fine-velocity issue (host half shipped in 042). `speed_path 0` (0x60 integer percent) against `1` (0x77 + 0x70 mode 3, 11.5 deg/s per %, bare 0x70 refresh every 400 ms) on `WHEELS_V` at several speeds (include low speeds near the floor) and on a 600 mm kernel leg (`position_mode 0`), bench rig first, then zuvat. Measure speed hold (mean and spread of wheel speed from telemetry) and heading error on the leg. Verify the 400 ms refresh keeps the motor running (no stalls/stutter).

## Acceptance Criteria
- [x] For each of paths 0 and 1: speed-hold error and spread at >= 4 speeds (5 speeds x 2 directions, 40/70/120/200/250 mm/s) on zuvat (the one-wheel bench rig no longer exists, so per-path on zuvat only), table in `captures/zuvat-position-2026-10-27/notes.md` section "Ticket 006", CSVs in `.../speedpath/`.
- [x] 600 mm leg heading error and final distance error, >= 4 runs per path on zuvat.
- [x] A decision line for the `speed_path` default; the default stays 0 unless 1 is clearly better and stall-free (this ticket does not change it; ticket 009 does).

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.

## Result (2026-10-27, zuvat, ENCODER truth)
Scope: the one-wheel bench rig is gone (its micro:bit is zuvat), so the per-rig table became a per-path table on zuvat. Full tables: `captures/zuvat-position-2026-10-27/notes.md` (section "Ticket 006"), data in `captures/zuvat-position-2026-10-27/speedpath/`.
- WHEELS_V hold: path 0 within 0.2..3.6 mm/s of command at 70..250 (sd 5..10), but 40 mm/s does not run (and i2cf +80 per run); path 1 runs 40 mm/s (mean 33..41) with no stall frame anywhere, but sd 14..88 and 10..14 percent low at 200/250.
- 600 mm legs (6 per path): distance error the same (L +3.9 / R 0 mm); heading about 2 deg both; lateral 17.4 mm (path 1) vs 11.8 mm (path 0); path 1 270 ms slower.
- Refresh check (path 1, 120 mm/s, 3 s): never zero, min 49..61 mm/s, +-50 percent ripple.
- Decision: `speed_path` default stays 0 (path 1 not clearly better); path 1 only wins below v_floor (40 mm/s). Nothing tuned; ticket 009 owns the default.
