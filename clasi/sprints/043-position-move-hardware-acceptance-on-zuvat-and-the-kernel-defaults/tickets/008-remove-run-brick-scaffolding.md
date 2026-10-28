---
id: 008
title: Remove RUN brick scaffolding
status: in-progress
use-cases:
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue: remove-the-run-brick-scaffolding.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Remove RUN brick scaffolding

## Description
Delete `RUN brick`, `brickx`, `brickraw`, `brickread`, `brickstop` from `test/test.ts` (and from FUNCS and docs mentioning them). Move `tools/mb50.py`'s brick mode onto the real verbs (`MOVE_X` / `WHEELS_X` / `STOP`), keeping `--mode position` and the kernel mode. Do this after tickets 001/002 so the evidence runs that needed the probes are finished.

## Acceptance Criteria
- [ ] `grep -n "pins.i2c" test/test.ts` finds nothing outside the `BusGuard` path (state the exact grep and its output in the ticket).
- [ ] Test build compiles (`make_deploy.py --robot zuvat --no-otos` or the project's test build) and FUNCS no longer lists `brick*`.
- [ ] `tools/mb50.py` has no brick-mode raw-I2C path; a quick bench 50 cm confirms it still drives the real verbs (one run per mode, captured).
- [ ] Host suite green; `clasi design validate` passes for `test/DESIGN.md` if it mentions the probes.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
