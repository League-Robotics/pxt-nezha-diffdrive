---
status: pending
---

# `i2cf` counts stuck wheels, not I2C faults; tovez's left wheel breaks away late

Measured 2026-10-29 on tovez with `tovez-017-i2cf.hex`, which splits `i2cf`
into TLM FULL `busf` (NAK'd encoder select or read), `stl` (acked read
unchanged while the wheel is driven) and `glt` (glitch rejects plus
re-anchors), summed over both wheels. Logs in
`captures/sprint044-acceptance-20261028/` (`tovez-drift9-017`, `tovez-i2cf-*`).

10.2 m drift run, 21 GO_TO_W legs, 6604 cycles: `i2cf` 371, `busf` 0,
`stl` 380, `glt` 14. The bus never failed.

One streamed GO_TO_W (`tovez-i2cf-gotow.jsonl`): all 40 `stl` are the left
wheel sitting still under drive. At the pivot start the right wheel turns
at duty 300-600 while the left needs ~1900 and 0.4 s; in the pivot-closure
trims the left holds at duty 400-600 without moving while the right turns;
the straight starts with the left lagging again. Plain MOVE_X moves the
same session started both wheels within 0.06 s, so it is worst at the low
duties of trims and pivot starts.

## Decide

- `i2cf` is a misleading name for what it counts. Either make it count
  `busf` only, or rename it; dashboards and the zuvat issue
  (`zuvat-i2c-fault-count-grows-during-position-moves.md`) read it as bus health.
- Eric (2026-10-29): no visible difference between tovez's two wheels;
  motors differing in stiction is long known across the fleet. Not a
  defect to chase here. Lubrication is the only mechanical idea so far; a
  per-wheel breakaway feedforward is the firmware one, not planned.

## Decision (2026-10-29)

Eric left it to us. `i2cf` (STATUS and TLM) becomes what its name says:
NAK'd encoder transfers only, today's `busf`, and the `busf` column goes.
The old "cycle where a wheel's sample did not advance" total is dropped;
`stl` and `glt` carry its parts. Tools reading `i2cf` as bus health then
read the truth.
