# src/blocks — shim + student-facing blocks

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The composition root and the student-facing MakeCode API:
`shims.cpp` (top level, composes the `Rig` — motor ports, kernel,
motion engine — and owns the starvation watchdog fiber) plus the six
TypeScript block modules split out of the former `main.ts`:
`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts`.

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §9. This file does not
duplicate that content — it exists so `ls src/blocks/` points
somewhere.
