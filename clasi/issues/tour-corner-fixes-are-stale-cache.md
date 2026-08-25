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

---

## CORRECTION (2026-08-25, team-lead) — the stale-cache mechanism is REFUTED

The "What to do" list above is built on a hypothesis this issue's own data
rules out. Read this section before acting on anything above it.

### 1. `logFix()` does not read a cache. It forces a live I2C burst.

```
test/test.ts:79   function logFix(tag) {
                      if (!diffDrive.readWorld()) emitLine("OERR:read-failed:"+tag)
                      ... worldX() / worldY() / worldHeading()
```

`readWorld()` -> `otosRead()` (`src/main.ts:478`, `src/shims.cpp:1088`) ->
`OtosPort::read()` (`src/otos_port.cpp:114`), which writes `kRegPositionXl`
and reads 12 bytes off the wire every call. `worldX/Y/Heading` then read the
members that `read()` just overwrote.

So the premise "the tour never takes a boundary fix, therefore `logFix()`
returns the seeded value" is wrong at the first step: `logFix()` takes its own
fix, unconditionally, on the spot. The cache-refresh contract cited from
`otos-on-vevov-move-goto-world-pose-square-tours.md` governs the *motion
layer's* pose source, not this diagnostic path.

Corollary: no `OERR:read-failed` lines appeared in the capture, so all five
reads returned `true` — the I2C transactions succeeded.

### 2. The recorded fixes are not identical, and a stale cache would be.

```
c0 5000:3000:17989
c1 5000:2998:17982
c2 5000:2998:17980
c3 5000:2998:17974
c4 5000:2998:17970
```

Heading walks 17989 -> 17970 monotonically; y moves 3000 -> 2998. A cache
returning a stored value returns the *same bytes* every time. Monotonic creep
of ~0.19 deg over ~30 s is the signature of live reads from a sensor that is
genuinely powered, tracking, and very slightly drifting — i.e. a sensor
watching a chassis that is sitting still.

Note also that `c0` reads 17989, not the seeded 18000. `otos_port.cpp:99`
documents exactly this: a seed of (50, 30, 180) read back a few seconds later
as 49.97, 29.97, 179.89. The `c0` value is the *drifted readback* of the seed,
not the seed itself — further evidence the read path is live.

### 3. The likely real mechanism: the chassis never moved.

The capture script (`tour3.py`, preserved in this session's scratchpad) opened
`/dev/cu.usbmodem212402` — **tovez over the USB cable**. On this bench the USB
cable reaches the bench stand, where the wheels are off the ground. Every
observation then falls out consistently:

| observation | on a stand |
|---|---|
| `posl/posr` +34834/+44306 counts | wheels spin freely ✓ |
| peak duty 2500/2900 | motors driven ✓ |
| encoder odometry integrates ~52 mm | phantom trajectory from free-spinning wheels ✓ |
| OTOS reports ~0.6 mm | **correct** — the chassis did not translate ✓ |

On this reading the OTOS was the only honest instrument in the run, and the
encoder odometry was the fiction. That inverts the issue title.

### 4. What is NOT yet established

Floor-vs-stand placement during that run is not recorded anywhere, and tovez
dropped off the USB bus during the follow-up attempt (2026-08-25 — its port
disappeared mid-test), so the confirming experiment has not run. The
alternative — chassis on the floor, OTOS powered but not optically tracking —
remains formally open, though it does not explain the monotonic drift as
naturally.

**Decisive experiment, when tovez is back:** place it on the floor, seed a
pose, drive `RUN:straight:20`, and compare the OTOS delta against the encoder
delta. Agreement => sensor fine, earlier run was on a stand. OTOS flat while
encoders advance on a *floor* run => the sensor really is not tracking.

### 5. The finding that survives, and it is a real one

Regardless of which way the experiment lands, this stands:

> Nothing in the firmware, the tooling, or the tour distinguishes "robot
> driving on the floor" from "robot on a stand with its wheels in the air."
> Both produce a complete, well-formed, plausible-looking tour record.

That is a genuine gap and it is worth fixing: a wheels-vs-OTOS divergence
check at each corner would catch a robot on a stand, a stalled wheel, a
slipping surface, and a dead sensor — all with one comparison. Item 3 of the
original "What to do" list ("make a stale fix detectable") is still the right
instinct; the correct implementation is a *cross-source disagreement* check,
not a cache-freshness flag, because there is no cache to check.

### Impact on this sprint

Tickets 005 and 006 (the OTOS and residual-leg campaigns) are **not** blocked
by a firmware defect, because no firmware defect has been demonstrated. They
ARE blocked by a methodology requirement: **every campaign procedure they
produce must state the robot's placement (floor vs stand) and must include the
wheels-vs-OTOS divergence check as a validity precondition.** A campaign that
cannot tell those two situations apart will confirm whatever it hoped to see —
which is the one true thing the original issue text got exactly right.
