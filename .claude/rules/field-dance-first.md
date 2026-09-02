---
paths:
  - "tools/**"
  - "tests/system/**"
  - "reports/**"
---

# Run the dance before you drive the field

**Before ANY commanded motion on the playfield, run:**

```
uv run tools/field_dance.py
```

Ask the operator to put the robot in the **middle of the field** first.
That is the entire safety argument — the dance never leaves a 25 cm
circle, so there is no path to project, no geofence to compute, and no
reason to spend time on either. It takes **under a minute**. Run it,
read the verdict, move on.

It turns +90, +180, +90, then drives 20 cm forward, 40 cm back, 20 cm
forward, checking the camera at every step, and it must come home.

## Why this exists

Twice now a field session has ended with a robot in a rail because a
convention was **inherited instead of measured**:

- 2026-08-31: the camera's yaw convention had changed between sessions.
- 2026-09-02: the snake tour advances PERPENDICULAR to the start
  heading. It was staged assuming it advanced along +x when it advances
  along -x, drove a metre with 17 cm of field, and pushed into the west
  rail. Then the recovery made it worse: the robot was read as "facing
  north" when it was facing **west**, and the correcting drive put it
  into the northwest corner.

Neither would have survived this check.

## Read the verdict correctly

**The gate is CONVENTION, not accuracy.** Left must be left, forward
must be forward, and it must come home. A robot whose pivots run 2 deg
long still passes — that is a tuning number, printed separately. Gating
on accuracy would train you to ignore a failing check, which is worse
than having none.

## The failure that looks like a broken convention but is not

**Zero motion on every step** means the robot refused, not that the
geometry is wrong. A latched e-stop does exactly this. The dance clears
the e-stop and asserts `ready=1` before it starts, and labels a
motionless step `NO MOTION` rather than reporting it as a heading error
— because three tours were once recorded as "closure 1 mm" when the
robot had simply never moved.

MEASURED vevov 2026-09-02, dance passing: turns +90.2 / -177.8 / +93.3
against commanded +90 / +180 / +90; drives 20.0, 40.0, 20.0 cm against
commanded, bearings within 2 deg; home to 1.0 cm.
