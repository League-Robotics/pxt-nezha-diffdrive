---
status: pending
---

# The Nezha brick's opcode map and the measured tables belong in this repo

Everything the simulator and the new port code will be written against
was measured on 2026-10-27 and lives in another repo
(`nezha-esp32/docs/motor-protocol.md` §7-8, `microbit-comparison.md` §7,
`fifty-cm.md`, and the CSVs under `nezha-esp32/docs/data/`). This repo's
tests must cite something in-tree (`.claude/rules/measurement-citations.md`).

## Change (`change-plan.md` C11)

A knowledge doc `docs/knowledge/2026-10-27-nezha-brick-opcodes.md`:

- The opcode map: `0x60` (→ `03 6E pct×10`, integer percent), `0x77`
  (per-port speed store, verbatim speed field of `03 67`/`03 70`),
  `0x70` modes 0/1 turns, 2 degrees (×10), 3 seconds (time 10n − 3 in
  100 ms units), `0x5F` (→ `03 5A 01` + zero relative move at 900 =
  hard stop/hold), `0x5D` absolute (as far as decoded), the `0x46/0x47`
  reads, the `FE: 03 64 00/02` mode brackets, the 400 ms `45 46` ping,
  the constant `CC` checksum the motor accepts as a wildcard.
- The measured tables: stop travel ramp vs hard (§7a), fine velocity
  (§7b), kernel with `pid_ki 0` (§7c), the 50 cm table, with the board,
  date and file for each.
- The three CSVs behind the tables copied to
  `docs/code-review/2026-10-27/data/` (`mb_probe_stops1.csv`,
  `mb_probe_fine1.csv`, the `mb50_ffcmp2_*` per-run summaries).

## Acceptance

`tests/host/test_sim_nezha_bus_brick_opcodes.py` (from the position-move
issue) and `src/platform/DESIGN.md` cite the doc; every number in the
doc names its file.
