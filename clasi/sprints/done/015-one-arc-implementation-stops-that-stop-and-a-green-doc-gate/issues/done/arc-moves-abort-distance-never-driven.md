---
status: done
sprint: '015'
split_into:
- pivot-stops-11-degrees-short-of-commanded.md
tickets:
- 015-004
---

# `move(distance, yaw)` over 50 deg runs out of budget mid-pivot — the timeout is computed for a blended move but the split path runs sequentially

Priority: **High** — it is a student-facing block, every `move(d, 180)` at the
default yaw rate is over budget regardless of distance, and the failure reports
itself as a clean completion.

**Provenance.** Surfaced by the `blocks-local-codeserver-test` session measuring
on tovez (blocktest firmware, encoder pose over `TLM POSE`); the mechanism was
proposed by its sprint planner and confirmed here against the real firmware C++.
That session holds the hardware repro (`RUN:arc:<deg>` verbs in
`projects/blocktest`) and should fold it into this file rather than authoring a
parallel one — see "Open question" below for the one reading that still needs
hardware to settle.

**This is NOT the arc-geometry defect** in `block-go-to-misses-its-target.md`.
Same split path, different fault, and it survives every remedy proposed there:
those consolidate the `goTo` family onto `goToR`, and `move(distance, yaw)` ->
`startMove()` -> `moveX()` is a separate entry point that keeps using the split.

## The rule

`shims.cpp:420-437 startMove()` budgets the move as:

```cpp
duration = max(dist_duration, yaw_duration);   // correct for a BLENDED move
timeout  = (uint32_t)(duration * 1000.0f) + 1500u;
```

`max()` is right for a simultaneous blended arc, where both axes finish
together. But `moveX` splits at `|rotation| >= kTurnFirstAngleRad` (50 deg) into
pivot-then-straight, which runs the axes **sequentially** — needing
`dist_duration + yaw_duration` — and `motion_engine.h` is explicit that one
deadline spans both phases ("`deadline` is fixed for the whole moveX() call ...
NOT reset across a pivot-to-straight phase transition"). So:

```
margin = 1500 ms - min(dist_duration, yaw_duration)
```

Negative whenever the **shorter** axis exceeds 1.5 s. At block defaults
(15 cm/s, 90 deg/s):

| call | budget | sequential need | margin |
|---|---:|---:|---:|
| `move(20, 90)` | 2833 ms | 2333 ms | +500 ms |
| `move(20, 180)` | 3500 ms | 3333 ms | +167 ms |
| `move(30, 180)` | 3500 ms | 4000 ms | **−500 ms** |
| `move(50, 180)` | 4833 ms | 5333 ms | **−500 ms** |
| `move(100, 180)` | 8167 ms | 8667 ms | **−500 ms** |

**Every `move(d, 180)` at 90 deg/s is over budget regardless of distance**
(`yaw_duration` = 2.0 s > 1.5 s). Every `move(d, 90)` sits at a constant
+500 ms.

Those are *nominal* rates, before the 400 ms acceleration ramp and before the
end-of-move taper — which `shims.cpp`'s own comment sizes at "up to ~1 s". The
split path is hit hardest, and for a reason worth stating: phase 1 has
`distance == 0`, so `pureTurn` is **true** and the *yaw* taper applies with
`turnFloor` 0.12. The last ~180 counts (~13.5 deg) of the pivot crawl at 12%
rate — roughly 1.25 s on its own, which consumes the +500 ms margin by itself.

## Measured

Real `MotionEngine` + real kernel + ideal wheels, `startMove()`'s budget math
transcribed verbatim, `openLoopProfile()` shaping. Probe:
[`docs/code-review/2026-08-26/raw/movex_budget_probe.cpp`](../../docs/code-review/2026-08-26/raw/movex_budget_probe.cpp).

```
move(0,180)   ran 2496 ms / 3500 budget   ends h=179.82 deg           correct
move(20,0)    ran 1848 ms / 2833 budget   ends x=199.5 mm             correct
move(20,90)   ran 1944 ms / 2833 budget   ends x=33.8  y=196.5  h=80.31 deg
move(20,180)  ran 2952 ms / 3500 budget   ends x=-200.2 y=3.6   h=179.25 deg
```

Both working cases have `|rotation| < 50 deg`; both failing cases are on the
split path. The heading shortfall reproduces: **80.31 deg against 90
commanded** here, 77.3 deg measured on tovez.

### The ideal-wheels replay UNDERSTATES this — hardware is worse

On tovez, `move(20, 90)` ended at **(x = −5, y = 19 mm)** — total displacement
~20 mm. The straight leg genuinely never ran. The ideal-wheels replay above
drove 196.5 mm of it, because ideal wheels finish the pivot fast enough to leave
budget for the leg; real ones do not. So on hardware the deadline bites *during
the pivot*, and "distance never driven" is literally true.

That is the discriminator: **timing**, not geometry. The 400 ms ramp plus the
`turnFloor` 0.12 taper crawl consume the +500 ms margin before the pivot even
finishes, so the second phase is never reached.

One caveat for interpreting runs where the leg *does* drive (as the replay
does): the travel lands along the **post-pivot** heading, so on a 90 deg move it
goes into `+y` and start-frame `x` reads near zero even when the leg ran in
full. Distinguish the two cases by total displacement, not by `x`. In the replay
the blended arc actually requested ends at (127.3, 127.3) with h=90 while the
split puts it at ~(34, 197) with h=80 — a **116 mm miss**, the same family as
`block-go-to-misses-its-target.md` at a different entry point. Both faults ride
the same split, which is why they are easy to conflate.

## HARDWARE RESULT (2026-08-26, tovez) — both latch candidates REFUTED

Full amended protocol run: clean baselines, stall latch cleared and confirmed 0
between every arc, five arcs at two floor settings.

**`probe(2) = 0` and `probe(25) = 0` at baseline and after every arc.** No stall
latch, no wrong-way abort, at either floor setting. Both candidates above are
dead, and the 2.56 deg event did not reproduce.

The straight leg **ran every time** (198–209 mm), matching the host replay's
geometry. So the leg-cut is *marginal*, not deterministic — consistent with the
budget arithmetic sitting right on the edge, where battery and load move phase
durations across the deadline. Last night the leg never ran; tonight it always
did; same kernel, same commands.

### A second, deterministic defect fell out — the ~11 deg pivot shortfall

| run | floors | Δ heading vs commanded |
|---|---|---:|
| arc:180 #1 | 25/12 | −11.8 deg |
| arc:180 #2 | 25/12 | −10.6 deg |
| arc:90 | 25/12 | −11.2 deg |
| arc:90 | 45/35 | −11.1 deg |
| arc:180 | 45/35 | −10.3 deg |

**Constant, and floor-insensitive.** Tripling the crawl rate (12% → 35%) moved
it by 0.1 deg. It is also identical across nights (77.3 deg last night vs
78.8 deg tonight on arc:90) while the leg behaviour flipped entirely — so the
shortfall is deterministic and the leg-cut is environmental. **Two different
mechanisms; keep them separate tickets.**

Note this is the *odometry-believed* heading, not camera truth: the controller
is stopping short by its own measurement, which is a different fault from the
physical/believed scrub in
`rotation-error-is-injected-by-the-legs-not-the-pivots.md`.

**Leading hypothesis: the yaw taper crawls below breakaway.** The numbers
bracket it exactly:

```
yawTaper_             = 180 counts = 13.55 deg      <- the taper window
yawMargin (pure turn) =   4 counts =  0.30 deg      <- the completion margin
measured shortfalls   = 10.3 .. 11.8 deg           <- every one INSIDE the window
```

The completion margin is 0.30 deg, nowhere near 11 — so this is not an early
handoff. But every shortfall lands inside the 13.55 deg taper window. If the
taper crawls the commanded rate below the wheels' breakaway, the pivot stops
advancing ~11 deg short and the move ends on its deadline — dying at the same
*angle* rather than the same *time*, which is what makes it look like a fixed
margin. Floor-insensitivity follows: 12% and 35% of the pivot cruise are both
below breakaway, and tripling a rate too small to move the wheel changes nothing.

It also explains the flat probes: a gentle sub-breakaway crawl keeps raw demand
under `stallDemand` (510.4 counts/s), so `demanding` is false and the stall
detector never trips even though the wheel is stationary.

**Decisive experiment** — shrink the taper *window* rather than raising its
floor, which is the knob that actually removes the crawl:

```
setTaperWindows(400, 1)     // yaw taper effectively off
arc:180
setTaperWindows(400, 180)   // restore
```

Shortfall collapsing toward 0.30 deg confirms the taper. Staying at ~11 deg
refutes it, and the hunt moves to whatever else is 11–13 deg wide.

**Still outstanding**: whether the arcs ended on the deadline or on completion.
Elapsed wall time from command to end-of-move against the 3500 ms budget for
`move(20, 180)` settles it and needs no hardware — the existing telemetry
timestamps carry it.

## What to change

Two candidates, smallest first:

1. **`shims.cpp startMove()`**: when `|rotation| >= kTurnFirstAngleRad` **and**
   `distance != 0`, budget `dist_duration + yaw_duration` instead of `max()` —
   because that is the path `moveX` will actually take. Keeps one deadline per
   call, matches the existing contract, smallest diff. **Preferred.**
2. **`motion_engine.cpp`**: give each phase its own deadline slice rather than
   sharing one across a sequential pair. Cleaner separation, but it changes the
   documented "one `timeout` bounds the whole call" contract in
   `motion_engine.h`, so the doc has to move with it.

Either way, the flat `+1500u` needs a comment saying what it now covers — it was
sized as taper headroom for a *single* segment and is currently the only thing
paying for an entire second phase.

**Acceptance**: a host test that fails against today's code for
`move(30, 180)` — the smallest nominal-rate case that is unambiguously over
budget — asserting the move reaches its commanded heading *and* drives its
commanded distance rather than ending on the deadline.
