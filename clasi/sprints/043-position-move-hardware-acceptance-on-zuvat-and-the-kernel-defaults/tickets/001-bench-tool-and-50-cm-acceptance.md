---
id: '001'
title: Bench tool and 50 cm acceptance
status: open
use-cases: [SUC-002]
depends-on: []
github-issue: ''
issue: position-move-hardware-acceptance-and-the-zuvat-square.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench tool and 50 cm acceptance

## Description
Port `/Volumes/Proj/proj/robot-projects/nezha-esp32/tools/mb50.py` (Wire class, run_line, STATUS parsing; read-only source) into this repo's `tools/` and add `--mode position`: set `SET position_mode 1 #n`, drive `MOVE_X` for 500 mm, read `posmove` from `STATUS` mid-move to confirm the built-in path, then read the final travel. Keep the existing brick mode working for now (ticket 008 moves it onto real verbs). Protocol: `nezha-esp32/docs/fifty-cm.md`. Rig: one motor on M1, 83 mm wheel, micro:bit on local USB; flash the 042 hex using the recipe in memory (`nezha-microbit-bench-harness`: cloud compile with blank `PXT_FORCE_LOCAL`, copy hex to /Volumes/MICROBIT). Run 50 cm at 30/60/100 %, four trials each direction (24 trials). Record `v_floor 40`, `decel` <= 1000, `stop_distance 0.3` kernel runs (`--mode position` off, `position_mode 0`) as the comparison set; ticket 007 uses them.

## Acceptance Criteria
- [ ] `tools/mb50.py` in this repo supports `--mode position`; a host test of its STATUS/posmove parsing passes (`uv run pytest`).
- [ ] 24 position-mode trials: every trial stops within 0.5 mm of 500 mm; time at 100 % under 1.2 s. (If not met: record, per rules.)
- [ ] `posmove=1` seen mid-move in every trial (and `0` after), cited per trial in the CSV.
- [ ] Kernel-mode comparison set (same 30/60/100 %, 4 trials each direction) captured with the same tool.
- [ ] `captures/bench-position-<date>/` holds hex, CSVs, summary table, `notes.md`.

## Testing
- Existing: `uv run pytest tests/tools`. New: parser test for the new mode. Hardware: the runs above.

## Implementation notes
Files: `tools/mb50.py` (new), `tests/tools/test_mb50.py` (new), `tools/DESIGN.md` mention is covered by the sprint overlay.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
