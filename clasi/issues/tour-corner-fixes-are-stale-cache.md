---
status: pending
sprint: '011'
---

# The square tour records the SEEDED OTOS pose at every corner, so its closure number is fiction

Priority: **High** — found on hardware (tovez, 2026-08-25) by actually running
the square tour, which no sprint in the 004-008 arc had done. A tour that
"passes" with a fabricated closure is worse than one that fails.

## What was observed

`RUN:tour:wheels` on tovez, firmware from master. The tour ran to completion
(`TOUR:end`, ~30 s) and emitted five corner fixes:

```
OCAL:c0:5000:3000:17989      x=500.0mm  y=300.0mm  h=179.89deg
OCAL:c1:5000:2998:17982
OCAL:c2:5000:2998:17980
OCAL:c3:5000:2998:17974
OCAL:c4:5000:2998:17970      x=500.0mm  y=299.8mm  h=179.70deg
```

Computing closure from those gives **0.6 mm** — an implausibly perfect result
that would sail past any 50 mm or 20 mm acceptance gate.

**It is fiction.** Simultaneous `TLM FULL` capture over the same run proves the
robot really did drive:

```
cyc  47 -> 1102              (1055 kernel cycles)
posl 1233 -> 36067           (+34834 counts)
posr 1272 -> 45578           (+44306 counts)
peak |dutl|=2500  |dutr|=2900
odom pose  x 101 -> 455      y -3 -> 376      h 151 -> 54655
i2cf 0 -> 11
```

Encoders turned, duty was applied, and the **encoder odometry tracked it**
(ending ~35 mm x / ~38 mm y from the start, ≈52 mm by odometry — right in the
band this project's own history reports for encoder-only tours, 9-54 mm). Only
the OTOS-derived corner fixes stood still.

## The OTOS is NOT the problem — it is present and healthy

```
RUN:probe -> OPROBE:95:1
```

95 is `0x5F`, the SparkFun OTOS product id; `otosGet(7)` = 1 = connected.
`STATUS` reports `otos=1` after the probe. (Note: `STATUS` reports `otos=0`
before anything initialises the chip — the same lazy-init ambiguity recorded in
`unpowered-nezha-brick-wedges-program-at-boot.md`.)

## Probable mechanism — read before fixing

This project's architecture deliberately has the protocol fiber report a
**cached** OTOS pose, never a live read: an OTOS I2C transaction interposed in
the Nezha encoder's select->read window destroys the encoder sample (the
"Phase F" hazard recorded in
`otos-on-vevov-move-goto-world-pose-square-tours.md`). The cache is documented
to refresh **only when the motion layer takes a boundary fix on the tick
fiber**.

The tour's legs run through `tickedMove()`, which appears never to take such a
boundary fix — so `logFix()` reads the value left by the initial
`seedPose(START_X, START_Y, START_H)` and reports it at all five corners. That
also explains why `c0` reads exactly the seeded `(500.0, 300.0)` and why the
heading only creeps 0.19 deg across four 90 deg turns.

**Verify this before fixing.** The alternative reading — that the OTOS is
connected but not tracking motion — is not excluded by the evidence above, and
the two have completely different fixes.

## Why this matters more than one bad number

1. **`worldReady()` returned true and the tour ran** on fixes that were never
   refreshed. Nothing anywhere reported a problem.
2. Any bench campaign built on `logFix()` — including sprint 011's planned OTOS
   and residual-leg-fault campaigns — would record fiction and "confirm"
   whatever it hoped to see.
3. A closure gate fed from these fixes would pass a robot that drove into a
   wall. The tighter the gate, the more convincing the lie.

## What to do

1. Establish which mechanism is real (stale cache vs. non-tracking sensor).
2. Make the tour take a genuine boundary fix at each corner, or read live where
   it is safe to do so on the tick fiber.
3. **Make a stale fix detectable**: if the cache has not refreshed since the
   last corner, `logFix()` must say so rather than emit the previous value. A
   fix that cannot be distinguished from its predecessor is not evidence.
4. Only then is a closure acceptance gate meaningful.

## Related

- `otos-on-vevov-move-goto-world-pose-square-tours.md` — the Phase F hazard and
  the cache-refresh contract this issue says is not being honoured.
- `intermittent-cw-pivot-abort-wheel-reversal.md` — its campaign measures tour
  closure; it must not be run until this is fixed.
- `unpowered-nezha-brick-wedges-program-at-boot.md` — same lazy-init class of
  ambiguity in `STATUS`.
