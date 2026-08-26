---
status: done
sprint: '021'
tickets:
- 021-002
---

# Simulator's `_setWheels()` turn-rate divisor is 4.3% off hardware's `effectiveTrackWidth()` — and off the simulator's own `_driveTwist()`

## Summary

`blocks/sim.ts:99`'s `_setWheels()` computes yaw rate as
`(right - left) / 115`. Hardware's equivalent path (`setWheels()` ->
`MotionEngine::wheelsV()`) divides by `effectiveTrackWidth()`, which is
`trackWidth / rotationalSlip = 114.2 / 0.952 = 119.96` mm — not
`trackWidth` alone. The comment at `sim.ts:92-95` says `115` stands in
for the caliper-measured `trackWidth_` (114.2 mm), which is correct as
far as it goes, but hardware does not divide by `trackWidth` alone —
sprint 007 (ticket 004, `R-12`) fixed a 10x error in this same divisor
and picked `trackWidth` when it should have picked
`effectiveTrackWidth()` (`trackWidth / rotationalSlip`). The result is
a genuine ~4.3% VALUE discrepancy between simulated and real turn rate
for any program that calls `setWheels()`/`_setWheels()` directly.

This is not merely a sim-vs-hardware gap: `_driveTwist()`'s own sim
body (`sim.ts`, a few lines below `_setWheels()`) computes
`simYawRate = (yawRate / 100) * Math.PI / 180`, which reproduces
hardware's round trip through `effectiveTrackWidth()` exactly (no
`115`/`119.96` divisor appears in that path at all — it works in
already-converted rad/s). So today, in the simulator alone,
`_setWheels()`-driven turns and `_driveTwist()`-driven turns disagree
with EACH OTHER by the same 4.3%, before even comparing either one to
hardware.

## Where

- `src/blocks/sim.ts:99` — `simYawRate = (right - left) / 115  // [rad/s]`
  (the value to change, if the fix is "divide by the right number")
- `src/blocks/sim.ts:92-95` — the comment justifying `115`, which
  correctly cites `trackWidth_` (114.2 mm) but incorrectly implies that
  is the full divisor hardware uses
- `src/motion/motion_engine.h:225` —
  `float effectiveTrackWidth() const { return trackWidth_ / rotationalSlip_; }`,
  the real hardware divisor (114.2 / 0.952 = 119.96 mm)
- `src/blocks/sim.ts` `_driveTwist()` — the sim's OTHER turn path,
  which already gets this right and is the reference for what
  `_setWheels()` should reproduce

## Why this is a correctness issue, not a mirrored-constant hygiene item

Sprint 019 ticket 006's constant-mirroring sweep (`duplicated-
constants-across-the-shim-boundary.md`) found this while enumerating
mirrored values, but it is out of that ticket's scope on purpose: the
two numbers do not represent an unguarded-but-currently-agreeing
duplicate (the pattern that ticket's drift tests fix) — they actively
disagree today. Adding a drift test asserting `115 == 119.96` would be
asserting something false; changing `sim.ts`'s divisor to fix a real
4.3% VALUE discrepancy is a simulator physics/behavior change, which
deserves review on its own terms (does the simulator's contract
promise exact parity? does `_setWheels()` even need the same fix that
was already applied correctly to `_driveTwist()`?) rather than folding
into a hygiene ticket.

## Suggested direction (not a decision — for whoever picks this up)

- `_driveTwist()`'s sim body already shows the right shape: express the
  simulator's turn-rate divisor in terms of the same
  `trackWidth / rotationalSlip` relationship hardware uses (119.96, or
  the two constituent constants), rather than a single fixed-in-time
  stand-in number, so a future `trackWidth`/`rotationalSlip` bake
  update doesn't silently re-open this same 4.3% gap.
- `setGeometry()`/`_setGeometry()` is currently a no-op in the
  simulator (`sim.ts`), which is why `115` has to be a hard-coded
  stand-in in the first place — worth deciding, as part of any real
  fix, whether the simulator should track a settable geometry the way
  hardware does, or continue with a fixed constant (just the *correct*
  one).

## Source

Code review 2026-08-26, finding C-14
(`docs/code-review/2026-08-26/raw/correctness-wire-blocks.md`).
