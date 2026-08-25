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

---

## RESOLVED ON HARDWARE (2026-08-25) — both readings above were half right

The stakeholder pointed out the obvious instrument neither the issue nor the
correction had used: **the overhead camera.** vevov carries AprilTag 53 with a
measured mount offset already registered with the daemon, so the camera reports
the robot's centre of rotation directly. That is a chassis-frame ground truth
independent of BOTH the wheels and the OTOS — it settles in one move what the
two previous sections argued about from inference.

### The experiment

vevov, on the playfield, driven over the **zavaz radio relay** (not USB — the
bench/playfield distinction `tools/robotlink.py`'s own docstring insists on).
Two consecutive `RUN:straight:20` legs, camera fix before and after each.

Leg 2, the cleanest of the pair:

| instrument | reported | error vs camera |
|---|---|---|
| camera, tag 53 centre: (18.02, 27.19) -> (1.85, 16.56) cm | **19.34 cm** | ground truth |
| live OTOS fix, `RUN:fix`: `OCAL:now:382:7:0` -> `OCAL:now:2297:2:102` | **19.15 cm** | **2 mm** |
| encoders, `STRAIGHT:end:2010:30:77` | 20.1 cm | +7.6 mm |
| telemetry `ox`/`oy`/`oh` | **0.0 cm** — `(386,345,-16504)` unchanged | total |

### What this establishes

1. **The OTOS sensor is healthy, and it is the most accurate instrument on the
   robot** — 2 mm from camera truth over 19 cm, beating the encoders, which
   overran by 7.6 mm on the same leg. Any plan premised on a broken or
   non-tracking OTOS is chasing nothing.

2. **`logFix()` is live and correct**, as the correction section argued. The
   `OCAL` values moved 382 -> 2297 across the drive. Confirmed.

3. **A stale cache is real, and the original issue was right that one exists** —
   it is just not the path the issue named. The frozen values are the
   **telemetry projection** `ox`/`oy`/`oh`, which stayed byte-identical through
   an entire camera-confirmed 20 cm drive. `logFix()` and the telemetry columns
   are different code paths, and the issue conflated them.

4. Therefore the correction section's conclusion — *"no firmware defect has been
   demonstrated"* — **is withdrawn.** One has now been demonstrated, on
   hardware, in the telemetry projection.

### Scope limit — do not overstate this

vevov is running **older firmware**: it emits the 12-column `POSE` frame
(`thdr seq now flags x y h ox oy oh vl vr i2cf`) and does not answer `STATUS`.
Current master emits the 20-column `FULL` frame. **The freeze is confirmed on at
least one build; it has NOT been tested on master.** Re-running this exact
experiment against a master-flashed board is the next step, and it is cheap.

### Why this is worse than a wrong number

`tools/tlm.py`'s `otos_cm()` reads `ox`/`oy`/`oh` directly (`tlm.py:265`). Every
consumer of that helper — including sprint 011's planned campaign tooling — can
receive a constant while the robot drives a full leg, and nothing in the data
says so. A frozen source and a genuinely stationary robot are byte-identical.

**The only way to tell them apart is cross-source disagreement**, which is why
the divergence check proposed in the correction section is the right fix, and
now has hardware evidence behind it rather than a hypothesis.

### The tovez question is still open

Nothing here explains tovez's tour, where the *live* `OCAL` fixes barely moved
while its encoders reported 52 mm. vevov proves the live path tracks correctly
when the robot really drives, which makes the stand hypothesis for tovez more
likely, not less — but tovez dropped off the bus before it could be tested and
this has NOT been confirmed. Leave it open.

### Actions

- [ ] Re-run this three-instrument test on a **master-flashed** board to
      establish whether the telemetry freeze exists on current firmware.
- [ ] Fix the telemetry projection so `ox`/`oy`/`oh` refresh, or mark them
      explicitly stale in the frame rather than repeating the last value.
- [ ] `leg_analysis.py` (sprint 011 ticket 002) flags any leg whose OTOS delta
      is ~zero while the encoder delta is real, as `otos-stale` — in flight.
- [ ] Campaign procedures (tickets 005/006) bracket every tour with camera
      fixes at start and end — permitted by the standing rule (camera at tour
      start and end only, never during) and the only way to catch this class.

---

## MECHANISM PINNED (2026-08-25) — the refresh trigger is `logFix()`, and only `logFix()`

Follow-up on vevov, stationary, no motion involved:

```
1. telemetry cache, before any live fix
   ox/oy/oh = (229, 0, 102)
2. force a live fix
   RUN:fix -> OCAL:now:6724:397:14490
3. telemetry cache immediately after
   ox/oy/oh = (672, 39, 14490)      <- adopted the live fix exactly
```

The cache took the live fix's value verbatim: `6724` and `397` are OCAL's
0.1 mm units, `672` and `39` are the telemetry columns' mm units, and the
heading `14490` cdeg matches to the digit.

**Therefore:** `ox`/`oy`/`oh` are a write-through cache whose *only* writer is
an explicit `logFix()` / `RUN:fix`. Motion never refreshes them. A move updates
the encoder odometry (`x`/`y`/`h`) and leaves the OTOS columns holding whatever
the last explicit fix wrote — which is precisely the mechanism the original
issue described, applied to the path that actually has it.

This closes the diagnostic question. The remaining work is the fix, not more
measurement:

- Refresh the projection where it is safe to do so on the tick fiber, **or**
- stamp the frame so a consumer can tell a fresh value from a repeated one
  (a sequence number or an age field on the OTOS columns). Repeating the last
  value with nothing marking it as old is what makes this dangerous — a frozen
  source and a stationary robot are byte-identical today.

### Also observed, and probably worth its own issue

`i2cf` climbed **60 -> 107** across a few minutes of light activity on vevov,
including while the robot sat still. That is a steadily accumulating I2C fault
count on an idle bus, not a burst tied to motion. Nothing in this issue depends
on it, but it should not be left unexamined.

### Second consecutive `RUN:fix` does not answer

Two `RUN:fix` commands sent in quick succession: the first returns `OCAL`, the
second returns nothing (observed twice). Consistent with a re-entry guard or the
single-slot RUN dispatch in `test.ts` rather than a sensor problem — noted so a
campaign script does not read the silence as a failed fix and retry into a
different state.
