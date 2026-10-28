---
id: '002'
title: Zuvat bring-up, wire smoke, stop timing
status: in-progress
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: position-move-hardware-acceptance-and-the-zuvat-square.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Zuvat bring-up, wire smoke, stop timing

## Description
Bring zuvat up on the sprint 042 firmware and test stop timing. Stop the loki serial bridge first (a flash kills whoever holds the port), flash `.tmp/binary-zuvat-042.hex` (or rebuild: `env -u VIRTUAL_ENV PXT_FORCE_LOCAL= uv run python tools/make_deploy.py --robot zuvat --no-otos` -> `.tmp/deploy-head/built/binary.hex`) with `mbdeploy deploy --hex <hex> zuvat`, then restart the bridge. Copy the hex into the captures dir. Wire smoke: `PING`, `STATUS`, `SET position_mode 1 #n` round trip and read-back, `posmove` flips to 1 during a short `MOVE_X` and back to 0 after. Then stop timing during a live 600 mm move at `position_mode 1`: `STOP`, `ESTOP`, and the host-link watchdog (stop sending), each at 30 % and 100 %; measure time to wheels at rest and travel after the command from v6 telemetry/encoders, compare with the sec 7a table in `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` / motor-path-review.

## Acceptance Criteria
- [x] zuvat runs the 042 build; smoke checklist passes and is logged.
- [ ] `STOP`, `ESTOP`, watchdog during a live move: wheels at rest within 200 ms; travel after the command within the sec 7a table (cite the table row per case).
  - NOT FULLY MET: STOP met (125-128 ms, 2.9/8.7 mm); ESTOP time to rest UNVERIFIED (kernel latches, telemetry frozen with stale vl/vr), travel 3.0/7.8 mm; a host-silence watchdog is not reachable on the wire (the move completes), deadline/lease analogues measured. See captures notes.md findings 1-2.
- [ ] The fault stop covers M1 and M2 (both wheels stop).
  - Met for STOP/deadline/lease (vl and vr zero in the same frame); ESTOP inferred only from post-clear x/h, UNVERIFIED without eyes on the robot.
- [x] Captures under `captures/zuvat-position-<date>/` with `notes.md` (encoder truth).

## Testing
Hardware only; no host code changes expected. If a tool needs a fix, add a test beside it.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
