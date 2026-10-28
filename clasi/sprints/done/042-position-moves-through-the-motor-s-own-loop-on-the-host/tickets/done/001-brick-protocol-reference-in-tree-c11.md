---
id: '001'
title: Brick protocol reference in-tree (C11)
status: done
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: nezha-brick-opcode-reference-in-tree.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Brick protocol reference in-tree (C11)

## Description

C11. The measured brick facts live in the other repo (`nezha-esp32`). This repo's simulator and tests must cite something in-tree. Write the knowledge doc and copy the data behind it. This ticket is the spec every later ticket's frame bytes and numbers cite, so it lands first.

Sources to read (outside this repo, read-only):
- `/Volumes/Proj/proj/robot-projects/nezha-esp32/docs/motor-protocol.md` sections 7 and 8
- `/Volumes/Proj/proj/robot-projects/nezha-esp32/docs/microbit-comparison.md` section 7 (7a stop travel, 7b fine velocity, 7c kernel with `pid_ki 0`)
- `/Volumes/Proj/proj/robot-projects/nezha-esp32/docs/fifty-cm.md` (the 50 cm table)
- CSVs in `/Volumes/Proj/proj/robot-projects/nezha-esp32/docs/data/`: `mb_probe_stops1.csv`, `mb_probe_fine1.csv`, `mb50_ffcmp2_stock.csv`, `mb50_ffcmp2_ffonly.csv`

## Files

- Create `docs/knowledge/2026-10-27-nezha-brick-opcodes.md`
- Create `docs/code-review/2026-10-27/data/` and copy the four CSVs there unchanged (verify with `cmp`)

## Content of the knowledge doc

- Opcode map, each with the UART frame it becomes: `0x60` (to `03 6E pct*10`, integer percent); `0x77` per-port speed store (verbatim speed field used by the next `03 67`/`03 70`; a `0x77` alone does not retarget; value in degrees per second, one frame per port, port byte 1..4, 0 = all); `0x70` modes 0/1 (turns), 2 (integer degrees, times 10 counts), 3 (timed run, time `(10n - 3) x 100 ms`); `0x5F` (to `03 5A 01` plus a zero relative move at 900: hard stop, hold within 5 degrees); `0x5D` absolute (as far as decoded); the `0x46`/`0x47` reads; the `FE: 03 64 00/02` mode brackets; the 400 ms `45 46` ping; the constant `CC` checksum the motor accepts as a wildcard.
- Behaviour rules a simulator must reproduce: `0x60 0` during a move ramps at v^2/2a and drops the target; nonzero `0x60` takes over; a second `0x70` supersedes from the current position; `0x5F` stops within 5 degrees and drops the target.
- A frame table giving exact I2C bytes for the three frames this sprint emits: `0x77` per-port speed, `0x70` dir mode 2, `0x5F`. Take the layout from `motor-protocol.md` and `test/test.ts` (`RUN brick`, `RUN brickx`); the issue text `nezha-brick-opcode-reference-in-tree.md` and `position-moves-through-the-motors-own-position-loop.md` quote `FF F9 <port> <dir> 70 <hi> 02 <lo>` and `FF F9 <port> 00 77 <hi> 00 <lo>`. Where those quote percent x 9 for 0x77 and the plan says degrees per second, reconcile against `motor-protocol.md` and state the unit and scaling once, explicitly. If the sources conflict, write UNVERIFIED and what would settle it; do not guess.
- Measured tables, each row naming board, date and file: 7a stop travel ramp vs hard (0.6/0.6 mm at 8%, 2.8/1.4 at 15%, 11.1/2.2 at 30%, 41.7/4.9 at 60%, 101.9/8.6 at 100%, `mb_probe_stops1.csv`); 7b fine velocity (60 to 60.5, 300 to 302, 905 to 909.5 deg/s, saturating near 980, `mb_probe_fine1.csv`); 7c kernel with `pid_ki 0`; the 50 cm table (`mb50_ffcmp2_stock.csv`, `mb50_ffcmp2_ffonly.csv`, `fifty-cm.md`).
- A section "Never send" naming `0x1D` / `03 1D 01` (motor reset) and why.

## Acceptance Criteria

- [x] `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` exists with the opcode map, the three-frame byte table, the behaviour rules and the 7a/7b/7c/50 cm tables
- [x] every number in the doc names its board, date and a file under `docs/code-review/2026-10-27/data/` (or is marked UNVERIFIED)
- [x] the four CSVs are in `docs/code-review/2026-10-27/data/`, byte-identical to the originals (`cmp` clean)
- [x] the doc says `0x1D` is never sent
- [x] `grep -n "measured" docs/knowledge/2026-10-27-nezha-brick-opcodes.md` shows no claim without an adjacent file path

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/tools -q` (docs inventory guards, if any pick up `docs/knowledge/`)
- **New tests to write**: none (documentation ticket); later tickets cite this doc
- **Verification command**: `for f in mb_probe_stops1 mb_probe_fine1 mb50_ffcmp2_stock mb50_ffcmp2_ffonly; do cmp /Volumes/Proj/proj/robot-projects/nezha-esp32/docs/data/$f.csv docs/code-review/2026-10-27/data/$f.csv; done`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
