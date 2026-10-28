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
