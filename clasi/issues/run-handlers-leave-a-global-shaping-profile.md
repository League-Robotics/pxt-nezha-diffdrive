---
status: pending
sprint: 018
---

# `RUN:` handlers mutate a global shaping profile and never restore it, so bench results depend on command order

Priority: **Medium** -- a reproducibility hole on a rig whose three open
questions are all about a few degrees of rotation error.

| Handler | taper windows | taper floors | ramp | default speed | default yaw rate |
|---|---|---|---|---|---|
| `openLoopProfile()` (tours, `straight`) | 400, 180 | 25, 12 | 400 | 20 | 90 |
| `RUN:goto` | 120, 80 | 45, 35 | 180 | **40** | 120 |
| `RUN:face` | -- | -- | -- | -- | 90 |
| `RUN:pivot` | 400, 180 | 25, 12 | 400 | -- | `pivotYawRate` |

`RUN:face` sets only the yaw rate. Run after `RUN:goto`, it closes its heading
loop under the **fast closed-loop** profile (taper 120/80, floors 45/35, ramp
180) instead of the accuracy profile. Same command, different physical
behaviour, determined entirely by which command preceded it -- and nothing in
the emitted transcript records which profile was in force.

`RUN:pivot` after `RUN:goto` inherits `defaultSpeed = 40` (harmless for a pure
pivot) but correctly re-sets everything that matters, which shows the intended
discipline. `RUN:face` is the one that does not follow it.

## What to change

Every handler calls one named profile function on entry -- `openLoopProfile()`
or a new `closedLoopProfile()` -- with no partial sets. If a handler genuinely
needs a one-off value, it sets it *after* the named profile so the deviation is
visible in one place.

Optionally: emit the profile name in the handler's own `DBG:` line, so a capture
records the conditions it was taken under.
