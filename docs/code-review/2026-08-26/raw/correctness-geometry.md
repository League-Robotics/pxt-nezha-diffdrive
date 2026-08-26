# Annex — Correctness: the go-to geometry family (2026-08-26)

Consolidated as **C-01, C-02, C-03** and **Q-01** in [`../review.md`](../review.md).

Every finding here was executed against the real firmware C++, not derived on
paper. The probe is archived as [`goto_probe.cpp`](goto_probe.cpp); it links
`src/core/diffdrive.cpp` and `src/motion/motion_engine.cpp` against
`tests/host/fake_ports.h`, applies `shims.cpp`'s own kernel `Config` bake and
its own `odomUpdate()` integration, and advances the fake wheels at exactly the
applied duty each 24 ms tick.

```
/usr/bin/c++ -std=c++20 -O1 -w -I src -I tests/host -o /tmp/probe \
    docs/code-review/2026-08-26/raw/goto_probe.cpp \
    src/core/diffdrive.cpp src/motion/motion_engine.cpp && /tmp/probe
```

---

## The shared mechanism

Four call paths in this repo turn "drive to a point" into a move. All four use
the same encoding:

```
theta = 2 * atan2(y, x)              // arc turn angle
R     = (x² + y²) / (2y)             // signed radius
s     = R * theta                    // arc LENGTH
```

`(s, theta)` describes a constant-curvature arc, and it is self-consistent
**only when executed as one blended segment** — velocity and twist held in a
fixed ratio so the wheels sweep the arc together.

`MotionEngine::moveX()` does not always do that:

```cpp
// motion_engine.cpp:161
if (distance != 0.0f && std::fabs(rotation) >= kTurnFirstAngleRad) {
    queuePivotThenStraight(rotation, distance, cruise);
} else {
    startSegment(distance, rotation, cruise);
}
```

`kTurnFirstAngleRad` = 0.8726646 rad = **50°**. Above it, `moveX` pivots by
`theta` and then drives `distance` — which is `s`, the *arc length* — **as a
straight line**. Arc length is not chord length except in the limit, so the
robot ends somewhere else entirely, having also over-rotated by `theta − bearing`.

This is not a defect in `moveX`. Pivot-then-straight is `moveX`'s documented,
intended reduction (motion-api.md §3.3, a measured `turn_first_angle`). The
defect is in handing it an `(arc-length, arc-angle)` pair, which only one of the
four callers knows not to do.

### Sprint 006 fixed exactly this — in one place

`MotionEngine::goToR()` (KERN-02/KERN-03) owns its own split:

```cpp
// motion_engine.cpp:196-224
const float bearingRaw = std::atan2(y, x);   // |.| <= pi
const float thetaRaw   = 2.0f * bearingRaw;  // |.| < 2*pi
const float theta      = wrapToPi(thetaRaw); // short arc

if (std::fabs(theta) >= kTurnFirstAngleRad) {
    move_.deadline = nowMs() + timeoutMs;
    const float chord = std::hypot(x, y);
    queuePivotThenStraight(bearingRaw, chord, speed);   // bearing + CHORD
} else { ... plain arc ... }
```

Pivot to the **line-of-sight bearing**, drive the **straight-line chord** —
reaches `(x, y)` exactly, by construction. Plus `wrapToPi()`, so a target behind
the robot takes the short way round.

**Q-01 — the four copies:**

| Site | Reached by | Short-arc wrap | Split correct | Status |
|---|---|---|---|---|
| `motion/motion_engine.cpp:186` `goToR` | wire `GO_TO_R` / `GO_TO_W` | yes | yes (bearing + chord) | **correct** — sprint 006 |
| `blocks/motion.ts:183` `startGoTo` | blocks `go to`, `start go to`, `while going to` | no | no | **C-01** |
| `test/test.ts:161` `legToward` | `RUN:tour:robot` | n/a (pivots ≥50°) | no | **C-02** |
| `blocks/world.ts:224` `goToWorld` | `RUN:goto`, `RUN:tour:world` | n/a (capped 25°) | boundary collision | **C-03** |

---

## C-01 — CRITICAL: the student `go to` block misses its target

**Path**: `blocks/motion.ts:151 goTo()` → `blocks/motion.ts:183 startGoTo()` →
`blocks/motion.ts:170 startMove()` → `_startMove` shim →
`shims.cpp:380 startMove()` → `MotionEngine::moveX()`.

```ts
// blocks/motion.ts:183
export function startGoTo(x: number, y: number): void {
    if (x == 0 && y == 0) return
    const theta = 2 * Math.atan2(y, x)   // [rad] signed — NOT wrapped
    let s: number
    if (Math.abs(y) < 0.01) {
        s = x
    } else {
        const radius = (x * x + y * y) / (2 * y)
        s = radius * theta               // arc LENGTH
    }
    startMove(s, theta * 180 / Math.PI)  // -> moveX(s, theta)
}
```

No short-arc normalization, no split correction.

### Measured

```
blocks/motion.ts startGoTo(10,10) -> startMove(s=15.708 cm, theta=90.000 deg)
  block `go to`  : ends at (3.0, 156.9) mm, heading 89.1 deg   -> MISS 112.5 mm on a 141.4 mm hop
  wire GO_TO_R   : ends at (101.5, 97.5) mm, heading 43.8 deg   -> miss 2.9 mm

blocks/motion.ts startGoTo(-10,1) -> startMove(s=307.2 cm, theta=348.6 deg)  [target is 10.0 cm away]
  block `go to`  : ends at (3009.8, -617.1) mm  -> MISS 3172.4 mm; drove 3.07 m of arc
  wire GO_TO_R   : ends at (-99.5, 10.1) mm     -> miss 0.5 mm
```

**Case 1** — `goTo(10, 10)` cm. θ = 90°, R = 10 cm, s = 15.708 cm. `moveX` sees
|90°| ≥ 50°, so: pivot 90°, then drive 157.08 mm straight. Endpoint ≈ (0, 157),
target (100, 100). **112.5 mm off a 141.4 mm hop — a 79% error.**

**Case 2** — `goTo(-10, 1)` cm, a point 10 cm behind and 1 cm left. `atan2` gives
174.3°, doubled to 348.6° — no wrap. R = 50.5 cm, s = 307 cm. The robot pivots
almost a full turn and drives **three metres** to reach a point ten centimetres
away, ending 3.17 m from it. This is R-03 (2026-08-23) verbatim, on the block
path.

Both cases are within the field's ±67.15 / ±44.65 cm limits at their start and
outside them at their end. Case 2 leaves the playfield.

### Blast radius

Three of the six Move-palette blocks: `go to`, `start go to`, `while going to`.
Any student target more than 25° off the bow (θ = 2·bearing, so bearing ≥ 25°
gives θ ≥ 50°). Below that the block is fine, which is why it looks like it
works.

### Why nothing caught it

- Host tests exercise `MotionEngine` directly and deliberately stay **below**
  the split threshold — the threshold is the bug.
- No TypeScript in this repo is executed by any test. `tsconfig.json` maintains
  a hand-edited `files` array, but `typescript` is absent from `package.json`
  and `node_modules/`, so nothing can run it (see
  [`cohesion-and-tooling.md`](cohesion-and-tooling.md) Q-07).
- The 2026-08-23 review *did* name this path — R-02 explicitly says the defect
  "affects the **block** `go to`/`start go to` path (main.ts→shims.cpp:411→moveX)
  as well as GO_TO_R". Sprint 006 fixed the C++ half. `motion_engine.h:70` even
  records the two paths as deliberately separate — "two paths sharing one
  primitive, not one implementation" — without noting that one of them is wrong.

### Remedy

`startGoTo` should not compute an arc at all. Add a `//%` shim onto
`MotionEngine::goToR()` — the machinery is already there
(`engineGoToR()` exists in `shims.cpp:1004` for the wire, un-annotated) — and
have `startGoTo` call it with the cm→mm conversion. One implementation, the
fixed one, for both callers, and `whileGoingTo`/`goTo` inherit it.

If that is too large for one ticket, port `wrapToPi()` and the bearing/chord
split into `startGoTo`. Either way this needs a regression test **above** the
50° threshold; its absence is the whole reason the finding exists.

---

## C-02 — MAJOR: `legToward()` has the same defect, in the accuracy campaign's own tour

```ts
// test/test.ts:144
function legToward(tx: number, ty: number) {
    for (let attempt = 0; attempt < 3; attempt++) {
        diffDrive.readWorld()
        const h = diffDrive.worldHeading() * Math.PI / 180
        const dx = tx - diffDrive.poseX(), dy = ty - diffDrive.poseY()
        if (Math.sqrt(dx*dx + dy*dy) < 2) return
        const bx =  Math.cos(h)*dx + Math.sin(h)*dy
        const by = -Math.sin(h)*dx + Math.cos(h)*dy
        const bearing = Math.atan2(by, bx)
        if (Math.abs(bearing) >= 50 * Math.PI / 180) {
            tickedMove(0, bearing * 180 / Math.PI)
            continue                      // re-measure, then curve out the rest
        }
        const theta = 2 * bearing         // <-- up to 100 deg
        if (Math.abs(by) < 0.01) tickedMove(bx, 0)
        else tickedMove((bx*bx + by*by) / (2*by) * theta, theta * 180 / Math.PI)
        return
    }
}
```

The pivot branch fires at |bearing| ≥ 50°. Below it, `theta = 2·bearing` runs up
to 100° — so for any residual bearing in **[25°, 50°)**, `moveX` splits.

That range is precisely the "small residual, curve it out" case the function's
own comment says it is designed for:

> "Only a genuinely large bearing gets a pivot — an arc to a point 90 deg abeam
> is a semicircle bulging off the field. Small residuals fall through to the
> curve below."

### Worked case: bearing 30°, distance *d*

θ = 60°; by = d·sin 30° = 0.5d; R = d²/(2·0.5d) = d; s = R·θ = 1.047d.

`moveX` splits: pivot 60°, drive 1.047d straight.

- Intended endpoint: (d cos 30°, d sin 30°) = (0.866d, 0.500d)
- Actual endpoint:   (1.047d cos 60°, 1.047d sin 60°) = (0.524d, 0.907d)
- **Miss = 0.531 d** — on a 60 cm leg, **32 cm**.

The `for (attempt)` loop does not save it: only the pivot branch `continue`s;
the curve branch `return`s. One bad arc per leg, no retry.

### Why this matters now

`tourRobot()` — reached as `RUN:tour:robot` and one of the three tours — is how
the robot-relative accuracy campaign is run. Two open issues,
`first-camera-scored-tour-fails-closure-gate.md` and
`rotation-error-is-injected-by-the-legs-not-the-pivots.md`, are currently
attributing tour closure error to the drivetrain. This is a **plan-side** error
of the same order, in the same tours, that injects heading error on the legs
(the pivot over-rotates by θ − bearing = bearing) — which is the exact signature
the second issue describes.

That does not refute the drivetrain hypothesis. It does mean the two cannot be
told apart from tour data until this is fixed, and it should be ruled in or out
before more bench time goes into the other explanation.

---

## C-03 — MAJOR: `goToWorld`'s curvature cap lands exactly on the split threshold

```ts
// blocks/world.ts:216
const dist = Math.sqrt(dx * dx + dy * dy)
const kMaxArc = 25 * Math.PI / 180
let b = bearing
if (b >  kMaxArc) b =  kMaxArc
if (b < -kMaxArc) b = -kMaxArc
if (Math.abs(b) < 0.01) {
    tickedMove(dist, 0)
} else {
    const radius = dist / (2 * Math.sin(b))   // chord `dist` subtending 2b
    tickedMove(radius * 2 * b, 2 * b * 180 / Math.PI)
}
```

The cap is 25° of *bearing*, so the rotation handed to `moveX` caps at exactly
**50.000°** — and `kTurnFirstAngleRad` is exactly 50°.

### The float comparison fires

TS computes `2 * b * 180 / Math.PI` = 50.000000000000000, rounds to 5000 cdeg;
`shims.cpp:385` converts `5000 * 0.01f * 3.14159265f / 180.0f`:

```
rot = 0.872664630   thr(kTurnFirstAngleRad) = 0.872664571   rot >= thr -> TRUE
```

So the capped leg — the one the cap exists to make *safe* — is the one leg
converted into pivot-50°-then-drive-the-arc-length. With b = 25°:
R = dist/(2 sin 25°) = 1.183·dist, arc = R·2b = 1.032·dist. The robot pivots 50°
(twice the intended heading change) and drives 3.2% long.

### Severity, stated fairly

The cap only *binds* when the pre-pivot (fired at bearing ≥ 12°,
`world.ts:129 turnFirstDeg = 12.0`) leaves ≥ 25° of residual — a fault case, not
the common path. `world.ts:207` records it as measured on vevov ("a leg with
55 deg of residual drove a 110 deg arc and finished 23 cm from where it started
while the target was 60 cm away"), so it does happen, and when it does the cap's
mitigation is defeated rather than applied.

The more durable problem is the coupling itself: **two constants, in two
languages, in two files, numerically coincident at a threshold**, with no
comment linking them, no shared source, and no test. Anyone who changes
`kMaxArc` to 26° or `kTurnFirstAngleRad` to 45° silently changes the other's
behavior, and nothing will say so.

### Remedy

Fold into C-01. If `goToWorld`'s legs route through a corrected `goToR`, the
collision disappears entirely — `goToR` handles any bearing correctly and the
cap becomes unnecessary. Failing that, cap at 24°, and add a comment at each end
naming the other constant.

---

## Related, not a finding: `startSegment()` on a stale deadline

`motion_engine.cpp:129-138`:

```cpp
const uint32_t remainingMs =
    static_cast<int32_t>(move_.deadline - now) > 0 ? (move_.deadline - now) : 0u;
kernel_.drive(move_.velCmd * 0.25f, move_.twistCmd * 0.25f, remainingMs);
```

Correct as written: the signed-difference idiom is wrap-safe, and the wire's
`clampMotionTimeout()` ceiling of 2³¹−1 guarantees `deadline − now` never
exceeds the safe half-range. Worth noting that the guarantee is *supplied by
another layer* — `shims.cpp:436`'s block path computes
`static_cast<uint32_t>(duration * 1000.0f) + 1500u` with no such clamp, and is
safe only because `duration` is derived from block-range-limited inputs. If a
future block ever accepts a large duration, this becomes live. `wire_handler.cpp`
already documents the reasoning at `kMaxMotionTimeoutMs`; `startSegment()` does
not restate it, and probably should not — but the block path should get the same
clamp.

---

## Addendum (2026-08-26, post-publication) — the `moveX` split path has a second, independent defect

Surfaced by a peer session measuring on tovez, then confirmed here against the
real firmware C++. **This is not the geometry defect above**; it is a *timeout
budget* defect on the same split path, and it survives every remedy proposed in
C-01/C-02/C-03 because those consolidate the `goTo` family onto `goToR` and
never touch `move(distance, yaw)`.

Probe: [`movex_budget_probe.cpp`](movex_budget_probe.cpp).

### The rule

`shims.cpp:420-437 startMove()` computes the move's timeout as

```
duration = max(dist_duration, yaw_duration)   // correct for a BLENDED move
timeout  = duration * 1000 + 1500             // the flat +1500 ms
```

but `moveX` splits at `|rotation| >= 50 deg` into pivot-then-straight, which
runs the two axes **sequentially** — needing `dist_duration + yaw_duration` —
and `motion_engine.h` is explicit that one deadline spans both phases. So:

```
margin = 1500 ms - min(dist_duration, yaw_duration)
```

Negative whenever the *shorter* axis exceeds 1.5 s. At block defaults
(15 cm/s, 90 deg/s):

| call | budget | sequential need | margin |
|---|---:|---:|---:|
| `move(20, 90)` | 2833 ms | 2333 ms | +500 ms |
| `move(20, 180)` | 3500 ms | 3333 ms | +167 ms |
| `move(30, 180)` | 3500 ms | 4000 ms | **−500 ms** |
| `move(50, 180)` | 4833 ms | 5333 ms | **−500 ms** |

**Every `move(d, 180)` at 90 deg/s is over budget regardless of distance**
(yaw_duration = 2.0 s > 1.5 s). Every `move(d, 90)` sits at a constant +500 ms.

Those are *nominal* rates — before the 400 ms acceleration ramp and before the
end-of-move taper, which `shims.cpp`'s own comment says adds "up to ~1 s". The
split path is hit hardest: phase 1 has `distance == 0`, so `pureTurn` is true
and the **yaw** taper applies with `turnFloor` 0.12 — the last ~180 counts
(~13.5 deg) of the pivot crawl at 12% rate, roughly 1.25 s on its own. That
alone consumes the +500 ms margin.

### Measured, ideal wheels

```
move(0,180)   ran 2496 ms / 3500 budget   ends h=179.82 deg           correct
move(20,0)    ran 1848 ms / 2833 budget   ends x=199.5 mm             correct
move(20,90)   ran 1944 ms / 2833 budget   ends x=33.8  y=196.5  h=80.31 deg
move(20,180)  ran 2952 ms / 3500 budget   ends x=-200.2 y=3.6   h=179.25 deg
```

Two observations worth carrying forward:

1. **"Distance never driven" is a reading artifact of the geometry defect.** On
   `move(20, 90)` the straight leg *does* run — 196.5 mm of it — but `moveX`
   pivots 90 deg first, so it goes into `+y` and start-frame `x` reads ~34 mm.
   The blended arc actually asked for ends at (127.3, 127.3) with h=90; the
   split puts it at ~(34, 197) with h=80. A **116 mm miss**, same family as
   C-01, different entry point.
2. **The heading shortfall reproduces**: 80.31 deg here against 90 commanded;
   the peer measured 77.3 deg on tovez. Ideal wheels vs real slip covers the
   3 deg gap.

Not reproduced: a reported `move(20, 180)` ending at 2.56 deg. Ideal wheels give
179.25 deg. A deadline biting mid-pivot lands *between* 0 and 180, not at 2.5,
so that specific observation likely has a third mechanism — `stallHalted`
(`probe(2)`), the wrong-way abort (`probe(25)`), or a heading-readout scaling
slip. Worth ruling out before treating it as one defect with the 90 deg case.

### Remedy

Two candidates, smallest first:

- `shims.cpp startMove()`: when `|rotation| >= kTurnFirstAngleRad` **and**
  `distance != 0`, budget `dist_duration + yaw_duration` rather than `max()` —
  because that is the path `moveX` will actually take. Keeps one deadline per
  call; smallest diff.
- `motion_engine.cpp`: give each phase its own deadline slice instead of
  sharing one across a sequential pair. Cleaner, but changes the documented
  "one `timeout` bounds the whole call" contract, so the doc moves with it.
