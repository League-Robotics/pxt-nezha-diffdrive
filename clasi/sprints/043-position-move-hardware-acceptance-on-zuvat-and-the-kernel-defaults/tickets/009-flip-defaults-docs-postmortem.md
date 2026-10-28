---
id: 009
title: Flip defaults, docs, postmortem
status: open
use-cases: [SUC-004]
depends-on: ["004","005","006","007","008"]
github-issue: ''
issue: position-mode-default-and-docs-after-acceptance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Flip defaults, docs, postmortem

## Description
Flip the defaults on the evidence and close out. `position_mode` default = the accepted mode (1, or 2 if ticket 005 says so; 0 if the bars were not met, with the reason). `speed_path` default per ticket 006. Update student-facing block docs and README's tick contract to describe the built-in move and decision D1; update `src/comms/DESIGN.md` (via the sprint overlay) and `src/DESIGN.md` where they say "default 0"; update the host default-pinning tests in the same commit; rebuild and flash zuvat with the new defaults and run one short smoke (a square lap, a STOP). Copy/consolidate captures beside `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` as needed. Write `docs/postmortem/` (or the project's sprint postmortem location) for sprint 043: what the encoders said on zuvat, a table of the closure metric per mode, the speed-curve PNGs, stop timing, arcs and speed_path decisions, and every unmet bar. Every number cites a capture file.

## Acceptance Criteria
- [ ] `position_mode` and `speed_path` defaults match the accepted modes; pinning tests updated and green.
- [ ] Docs and README updated; `clasi design validate` passes.
- [ ] Postmortem contains the square-tour closure comparison table and chart links; every number names a capture path.
- [ ] Zuvat re-flashed with the new defaults and smoke-tested (capture cited).

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.
