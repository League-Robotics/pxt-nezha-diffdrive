---
status: pending
sprint: 039
---

# vevov: encoders read 0 while `i2cf` faults on ~99% of cycles

Priority: **High** — but see the correction immediately below: the I2C framing
in this title and in the original text is WRONG.

## CORRECTION 2026-09-16, same session

**The cause was the Nezha brick being unpowered, not an I2C bus fault.** The
stakeholder reported the robot had been switched off, powered it back on, and
every symptom cleared at once:

```
posl=144 posr=161            (were 0 and 0)
i2cf=17 while cyc 37 -> 45   (ZERO new faults across a commanded nudge)
connL=1 connR=1
```

against the failure's 1246 new faults in 1251 cycles with both encoders at 0.

The trap is worth recording, because every artifact looked like a live robot:
**the micro:bit is powered from the host Raspberry Pi over USB, so it keeps
answering HELLO, serving STATUS, and accepting flashes while the Nezha brick's
own battery is off.** `connL`/`connR` read 0, `posl`/`posr` read 0, and `i2cf`
climbs on every cycle — which is simply what I2C to an unpowered peripheral
looks like, and is easy to read as a failing bus on a healthy robot.

What remains true and worth keeping from the original report:

- The **inert distance guard** is real and independent of the cause. A drive
  bounded by a comparison against `poseX()` cannot terminate when `poseX()` is
  frozen, whatever froze it. `sweep 10` ran 111 cm. The guard added in
  nezha-robot-template (`CALJ_DEAD_TICKS`) stands on its own merits: it does not
  care whether the odometry died from a flat battery or a broken bus.
- The remaining exposure list (`caljHome`, `calt`'s pivots, `sweep`) is
  unchanged.

What is retracted: the claim that this is an I2C hardware or bus-integrity
fault, and the comparison drawn against
`i2c-fault-count-climbs-on-idle-bus.md`. That issue documents faults on a
*powered* idle bus and is untouched by this. A power-state check belongs
*before* any I2C fault is diagnosed.

Original report follows, retained unedited for the record.

## Original report

Priority as filed: **High** — the robot drives, cannot measure that it is
driving, and every distance limit built on odometry is silently inert. It drove
111 cm on a 10 cm command.

## What was observed

vevov, 2026-09-16, on the eye field, running the calibration image
(nezha-robot-template profile `vevovwire`, flashed over `_mbflash._tcp`).

`TLM FULL`, robot stationary and estopped:

```
thdr seq now flags x y h ox oy oh vl vr i2cf cyc posl posr dutl dutr lexc wrng cycovr
t 1 866627 31 0 0 0 0 0 0 0 0 1252 1264 0 0 0 0 0 0 0
```

- **`posl = 0`, `posr = 0`** — both encoders exactly zero, after the robot had
  physically crossed the field.
- **`i2cf = 1252` against `cyc = 1264`** — about 99% of control cycles faulting.
- `connL = 1`, `connR = 1`, `ready = 1`: the brick reports both motors present.

The fault rate climbed with commanded motion, not at rest:

| moment | i2cf | cyc |
|---|---|---|
| pre-flash, navigation image | 70 | 699 |
| fresh boot after flash | 0 | 0 |
| after an 8-tick nudge | 6 | 13 |
| after one `sweep` | 1252 | 1264 |

## Why it matters: the distance guards are inert, not conservative

`sweep`'s termination is `if (Math.abs(x) >= Math.abs(cm))` where `x` is
`poseX()`. With the encoders dead `poseX()` never leaves 0, so that condition
can never become true. The 10 cm bound did nothing. The drive ran to
`CALL_MAX_SECS` (30 s) at `CALL_CREEP` (4 cm/s) = 120 cm; the camera measured
111 cm of displacement, from x=41.15,y=3.15 to x=-64.26,y=40.28, off the paper
and into the north-west corner.

This is a general hazard, not a `sweep` bug. `calj`, `calt` and `caljHome` all
bound their drives with comparisons against `poseX()`, and all fall back to a
seconds budget. `CALJ_MAX_SECS` is 60 s at 8 cm/s — **480 cm on a 134 cm
field.** A time budget sized for "a stalled robot stops its pose too" is not a
backstop for "the robot moves but the pose is frozen."

The earlier symptom was misread: two `nudge` commands moved the robot 0.8 mm
while reporting `x=0cm heading=0deg`, and `cyc` advanced by exactly the
requested tick count. That was dead encoders, and it was diagnosed as a
breakaway/speed-floor problem (sprint 039's own subject), which is why the next
command sent was a longer sustained drive.

## Relationship to `i2c-fault-count-climbs-on-idle-bus.md`

That issue records a slow idle climb on this same robot (60 → 107 over ten
minutes, priority Medium, "not blocking anything today"). **This is not that.**
That one advances at rest and absorbs faults invisibly; this one faults on
essentially every cycle under motion and takes the encoder path down with it.
They may share a root cause in the Nezha I2C path, but the older issue's own
"What is NOT known" section says there is no baseline — this is now a data
point at the opposite extreme, and should not be folded in without evidence.

## What is NOT known

- Whether this is vevov-specific hardware (cable, brick, connector) or the
  build. A like-for-like fleet baseline was attempted and failed: tovez and
  gopiv both answered `i2cf=0 cyc=0 ready=0`, the cold-boot state, so there is
  no comparable fault rate from a *driving* robot on another chassis.
- Whether the motor-drive path and the encoder-read path fail independently.
  Motor commands demonstrably got through while encoder reads did not.
- Whether a power cycle clears it. Not tried — the robot was left estopped and
  untouched for the stakeholder.

## Suggested first steps

1. Add a **dead-odometry guard** anywhere a drive is bounded by `poseX()`:
   if motion is commanded for N consecutive ticks and the pose does not move at
   all, stop. Done for `runCalibrateJ` in nezha-robot-template
   (`CALJ_DEAD_TICKS`); `caljHome`, `calt`'s pivots and `sweep` still need it.
2. Surface `i2cf` relative to `cyc`. A near-equal pair means the bus is
   failing; today it is a raw counter in a telemetry column that nothing
   asserts a bound on, which is exactly the complaint in the older issue.
3. Power-cycle vevov and re-read `posl`/`posr` under a short commanded move,
   to separate a transient bus wedge from a hardware fault.
