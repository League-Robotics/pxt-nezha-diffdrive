# Moves glide to a stop — vevov, 2026-09-02

Stakeholder observation: *"a lot of crawling... they're going back and
forth. It's like they're overshooting and then trying to correct. I
prefer they just glide into a stop."*

Fixed. Same robot, same session, three repeats per figure.

| tour | legacy closure | **glide closure** | |
|---|---|---|---|
| square | 52.3 ± 15.3 mm | **3.9 ± 3.9 mm** | 13.4× |
| diamond | 28.6 ± 7.2 mm | **2.2 ± 1.4 mm** | 13.0× |
| circle | 25.6 ± 15.9 mm | **7.8 ± 4.8 mm** | 3.3× |
| infinity | 85.6 ± 4.9 mm | **27.8 ± 5.4 mm** | 3.1× |
| snake | advance 1066.3 mm | 1056.6 mm | *(open path)* |

Net rotation error against ideal:

| tour | legacy | glide |
|---|---|---|
| square | −6.64° | **+0.22°** |
| diamond | −7.10° | **−0.93°** |
| circle | −5.21° | −1.23° |
| infinity | +7.10° | +1.32° |

Best individual runs: square **1.0 mm**, diamond **1.0 mm**, circle
**2.2 mm**.

## Why it was crawling

Two halves of one design, and only one of them had been built.

The **profile** — sprint 025's constant-acceleration work — answers *how
fast should I be going right now*: `v_allow = √(2a·remain)`, decaying to
zero exactly at the target. That existed and worked.

The **exit test** answers *is the move over*, and it was untouched:

```cpp
distDone = remain <= 10 counts;                  // 0.79 mm
yawDone  = remain <= (pureTurn ? 4 : 10) counts; // 0.16 deg on a pivot
if (!(distDone && yawDone)) kernel_.drive(...);
```

Purely positional. So the profile decayed toward zero and the exit test
said *not there yet, keep driving* — which is exactly what the taper
floor (`distFloor_` 0.25, `turnFloor_` 0.12) exists for: it holds the
command at 25% of cruise so the move can still close that last fraction
of a millimetre. The floor and the positional exit are two halves of one
mechanism, and the profile was overridden precisely where it was
supposed to land.

That margin is also in **encoder counts, not the world**. Legs run
0.3–0.7% long, so a 600 mm leg is 2–4 mm out however precisely the
counts land. The crawl bought precision in *believed* position only, and
paid for it with a hunt at every move boundary.

## The three changes

1. **The yaw axis got the kinematic braking gate.** The distance axis
   had `v²/(2a)`; the yaw axis still gated on the fixed `yawTaper_`
   window even in shaped mode, so one tuning constant — not the physics
   — decided when a pivot braked. Pivot scatter went sd 1.14 → 0.18 at
   unchanged bias.

2. **Profile-completion exit** (`profile_exit`, [mm/s], default 0 =
   legacy). When armed the taper floor is bypassed so the command
   genuinely decays, and the move ends once the dominant axis's
   commanded speed falls to that value. The residual is accepted rather
   than chased.

3. **The exit's shortfall is compensated at the target.** Ending at
   `v_exit` leaves `v_exit²/(2a)` still to travel — 4.5 mm here. That is
   deterministic, so `startSegment()` extends each axis's target by
   exactly it. Without this the shortfall is charged to *every* move and
   figures made of many moves accumulate it: an 8-arc circle lost 12° of
   rotation and the 16-arc figure-8's closure went 85.6 → 128.9 mm.
   With it, infinity came back to 27.8 mm.

## Configuration

```
SET accel 400          SET decel 400         SET profile_exit 60
SET pivot_overrun 3.7  SET yaw_taper 800     SET twist_hold_gain 8
SET speed_floor 512    SET dist_floor 0.25   SET turn_floor 0.12
```

**`pivot_overrun` must be retuned whenever `profile_exit` changes** —
they are both yaw-axis bias terms and they compose. Measured at
`profile_exit 60`: overrun 2.0 → +2.49°, 3.0 → +1.21°, **3.7 → +0.53°
sd 0.27**, 4.5 → +0.69° sd 1.07.

`profile_exit` trades residual for glide, and the trade is real:

| `profile_exit` | pivot hunts | pivot excess | leg travel (600 cmd) |
|---|---|---|---|
| 0 (legacy) | 7 | +1.57° sd 2.21 | 601.0 mm |
| 45 mm/s | 7 | −0.06° sd 0.80 | 599.4 mm |
| **60 mm/s** | **3** | −1.43° sd 0.31 | 597.5 mm |
| 80 mm/s | 1 | −5.59° sd 0.66 | 595.3 mm |

60 is the knee: most of the glide, a bias small enough for
`pivot_overrun` to cancel. 80 glides best but needs more correction than
that knob can give.

## Charts

![square](vevov-glide-final-20260902/square.png)
![diamond](vevov-glide-final-20260902/diamond.png)
![circle](vevov-glide-final-20260902/circle.png)
![infinity](vevov-glide-final-20260902/infinity.png)
![snake](vevov-glide-final-20260902/snake.png)

## Still open

- **Defaults are still 0** — `accel`, `decel` and `profile_exit` all
  select legacy mode unless a host sets them, so no robot changes
  behaviour until asked. Baking these belongs in its own change, with
  per-robot `pivot_overrun` re-measured, since the two compose.
- **The arcs still trail the pivot figures** (circle 7.8 mm, infinity
  27.8 mm vs square 3.9 mm). Arc segments accumulate more moves; whether
  the residual is the exit, the arc geometry, or slip is not yet
  separated.
- These are bench numbers, wheels up, pure odometry.
