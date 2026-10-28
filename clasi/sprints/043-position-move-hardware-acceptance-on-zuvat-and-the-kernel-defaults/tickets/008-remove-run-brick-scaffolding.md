---
id: 008
title: Remove RUN brick scaffolding
status: done
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
- [x] `grep -n "pins.i2c" test/test.ts` finds nothing outside the `BusGuard` path (state the exact grep and its output in the ticket).
- [x] Test build compiles (`make_deploy.py --robot zuvat --no-otos` or the project's test build) and FUNCS no longer lists `brick*`.
- [x] `tools/mb50.py` has no brick-mode raw-I2C path; a quick bench 50 cm confirms it still drives the real verbs (one run per mode, captured).
- [x] Host suite green; `clasi design validate` passes for `test/DESIGN.md` if it mentions the probes.

## Hardware rules (apply to every run in this ticket)

- Keep runs short. Send `STOP` between runs. Never send brick opcode 0x1D (motor reset; it bricked a motor until replugged).
- Evidence lands under `captures/zuvat-position-<date>/` (bench: `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`. Every number quoted anywhere is cited to a file there (`.claude/rules/measurement-citations.md`).
- Zuvat has no camera and no OTOS: all closure/pose numbers are ENCODER truth and must be labelled so. Camera steps in `.claude/rules/field-dance-first.md` / `playfield-testing.md` do not apply; follow the rest (clear floor, short legs, hand on the robot).
- If the robot does not meet a bar: record the number and capture, state "bar not met" in `notes.md` and the ticket, and tell the team-lead. Do NOT tune constants silently to pass.
- Zuvat wire access: `open_link(wifi='127.0.0.1')` or `tools/tour_capture.py --wifi 127.0.0.1` through the ssh tunnel to the loki serial bridge (127.0.0.1:7654 -> /dev/ttyACM1). If the bridge dies: `ssh loki.local 'nohup /home/eric/mbtools-venv/bin/python /home/eric/serial_bridge.py /dev/ttyACM1 7654 > /home/eric/serial_bridge.log 2>&1 &'`; kill an old one only with `pkill -f "^/home/eric/mbtools-venv/bin/python /home/eric/serial_bridge"`.

## Result

- Removed from `test/test.ts`: `brickCmd`, `brickAngle`, and the `brick`, `brickx`, `brickraw`, `brickread`, `brickstop` handlers with their `runSignature` registrations (169 lines).
- Check: `grep -n "pins.i2c" test/test.ts` prints nothing (exit 1). `grep -n "brick" test/test.ts` leaves only two comment words ("the brick's RAW counter" at the `spin` probe, "once bricked two robots").
- Build: `make_deploy.py --robot zuvat --no-otos` ends with the expected "not all translation units compiled" message (zero 'Building CXX object' lines); hex produced at `.tmp/deploy-head/built/binary.hex`, copy `.tmp/binary-zuvat-043-008.hex` (includes ticket 007's `decel`/`stop_distance_mm` bake). There is no binary.js; the artefacts are `binary.hex` and `binary.asm`. Decoding the hex data records: no string matching `brick\w*` is present (the `nudgel` and `setwire` handler names are), and `(deg:number,pct:number)` is absent; `grep -c brick binary.asm` is 0. The on-robot FUNCS check is deferred to ticket 009's reflash.
- `tools/mb50.py` (this repo) had no brick-mode or raw-I2C path left: the port already used only MOVE_X via `--mode kernel|position`. The sibling repo's tools were not touched.
- Real-verb runs on zuvat, 150 mm/s, 500 mm there and back, ENCODER truth, 2026-10-27, `captures/zuvat-position-2026-10-27/mb50_check/` (`kernel*.csv`, `position*.csv`): kernel err L/R +3.31/-0.18 mm fwd, +3.95/+1.57 mm rev, posmove mid 0; position err -0.26/-0.42 mm fwd, -0.49/-0.42 mm rev, posmove mid 1, after 0. Restored `position_mode 0`, `TLM OFF`; STATUS posmove=0.
- `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` gains a note that the handlers were removed and the surviving probe path is `nezha-esp32/tools`. `test/DESIGN.md` does not mention the brick probes.
- Tests: tests/tools/test_mb50.py, test_run_tour_programs, run-abort pin, no-units pin, manifest completeness, archaeology budget, sim brick opcodes: green; ruff clean; `clasi design validate` valid.
