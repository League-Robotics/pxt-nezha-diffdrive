# src/blocks — shim + student-facing blocks

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The composition root and the student-facing MakeCode API:
`shims.cpp` (top level, composes the `Rig` — motor ports, kernel,
motion engine — and owns the starvation watchdog fiber) plus the
TypeScript block modules: `sim.ts`, `run.ts`, `pose.ts`, `stop.ts`,
`world.ts`, `motion.ts`, and the robot-setup layer `report.ts` (packed
JSON report lines), `calibration.ts` (calibration stored in flash) and
`program.ts` (button menu, cancel, `setupRobot()`).

One part of `motion.ts` is **generated, not written**: the
`ConfigField` enum comes from `src/comms/config_fields.h` via
`tools/gen_config_field_enum.py`. Edit the header and re-run the
generator (`uv run python tools/gen_config_field_enum.py`), then commit
both; do not hand-edit the enum. See [`src/DESIGN.md`](../DESIGN.md) §5.

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §9. This file does not
duplicate that content — it exists so `ls src/blocks/` points
somewhere.

## Stop paths and the watchdog under position moves

The starvation watchdog keeps its invariant: the robot moves only while
something ticks. A live position move counts as driving
(`commandLooksActive()`), so a stalled host gets `hardStop()` on both
wheels 100 to 150 ms after the last tick, not a move that finishes
unattended. `Rig::softStop()` hard-stops live moves first. The `nudge()`
block and `beginNudgeWheels()` take hundredths of a millimetre.

## The stored radio address

`setupRobot()` resolves the radio address in one order: the program's own
`setupRadio(ch, grp)`, then the address stored in flash, then the one
derived from the micro:bit's name. The boot line and `_radioshow` say which
one won (`program`, `stored` or `name`).

The stored address is two numbers under `#`-prefixed `settings` keys (so it
survives flashing a different program), channel 0-83 and group 0-255.
`_radioset <channel> <group>` writes it, `_radioclear` removes it,
`_radioshow` reports it. A set answers with the stored values; an invalid
value answers with a fail report and stores nothing. A stored address takes
effect at the next boot: the radio is never retuned while a program runs
(see `clasi/issues/low/changing-the-radio-group-mid-run-is-unverified.md`),
so the console follows a set with `_reboot`. `_radioshow` also reports the
name-derived default, so a caller that keeps the group name-derived (the
fleet policy of 2026-11-14) can read it back.

`_reboot` is the console's remote reset: it refuses while a program is
running, otherwise it stops the motors, reports, and calls `control.reset()`.
