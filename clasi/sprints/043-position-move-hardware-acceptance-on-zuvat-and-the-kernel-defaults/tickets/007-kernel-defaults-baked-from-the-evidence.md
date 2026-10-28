---
id: '007'
title: Kernel defaults baked from the evidence
status: in-progress
use-cases:
- SUC-004
depends-on:
- '001'
- '004'
- '006'
github-issue: ''
issue: kernel-defaults-from-the-fifty-cm-evidence.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Kernel defaults baked from the evidence

## Description
Bake kernel defaults per robot from the evidence (issue and change-plan C18): `v_floor 40`, `decel` <= 1000, `stop_distance 0.3`, `omega_floor` above stiction (about 45 deg/s body rate), `v_max` <= 0.9 x full-duty velocity, `pid_ki` kept or dropped on the two-wheel evidence. Use the bench kernel set from ticket 001 and zuvat kernel legs from tickets 003/004/006; where evidence is missing for a constant, run a short zuvat kernel leg to get it. Edit `src/comms/config_fields.h` and `radio-robot-lib/config/robots/*.json` as appropriate (zuvat at least; other robots only if the evidence is robot-independent and you say so). Put a capture path in the comment beside each changed constant. Update host default-pinning tests in the same commit.

## Acceptance Criteria
- [ ] Each changed constant has a capture path in its comment; none changed without one.
- [ ] Zuvat 600 mm kernel leg after the change: final distance error and heading error recorded vs before (>= 4 runs each).
- [ ] Host suite (`uv run pytest` and the project's host test target) green with pinning tests updated.
- [ ] Constants not supported by evidence are left unchanged and listed as such in `notes.md`.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
