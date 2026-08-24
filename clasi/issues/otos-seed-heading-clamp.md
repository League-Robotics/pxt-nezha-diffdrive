---
status: pending
sprint: '006'
---

# OTOS pose seed clamps heading beyond ±180° instead of wrapping

Priority: **Medium** — code review 2026-08-23, R-05 (KERN-05; CONFIRMED —
clamp located at `otos_port.cpp:61-66`).

`writePoseMm` clamps the heading register to ±32767 LSB ≡ ±179.89°. Seeding
with a heading outside ±180° — a 0–360° camera convention value, or the
deliberately-unwrapped odometry heading echoed back through
`r.heading`/`poseHeading()` — silently clamps: a 350° seed lands at
+179.89° instead of −10°, up to ~170° of error. The two pose sources then
start disagreed, which poisons exactly the drift measurement `seedPose`
exists to make (aprilcam world-frame reseeding, `RUN:seedxy`).

## What to do

Wrap the heading to ±180° before the register write (one modulo). Add a
host test seeding 350°/−350°/720°. Note the related Minor (KERN-08): the
OTOS PoseSource reports wrapped heading against `motion_engine.h:139`'s
"(unwrapped)" contract — fix or re-document the contract while in there.
