---
status: pending
sprint: ''
---

# `i2cf` climbs steadily on a largely idle I2C bus

Priority: **Medium** — not blocking anything today, but it is an error counter
that increases while the robot does nothing, which is never benign and is
currently unexplained.

## What was observed

vevov, 2026-08-25, driven over the zavaz radio relay with the robot on the mat.
The `i2cf` column of the telemetry frame (`thdr seq now flags x y h ox oy oh vl
vr i2cf`) over roughly ten minutes of light use:

```
t = 0 min    i2cf = 60     (already 60 at first contact this session)
during a commanded 20 cm drive      60 -> 62     (+2)
t = ~10 min  i2cf = 107    (+45 more, much of it while parked)
```

The robot was stationary for the majority of that window. Two commanded
`RUN:straight:20` legs and a handful of `RUN:fix` / `RUN:probe` calls account
for only a small part of the increase.

## Why it matters

1. **It is monotonic and untriggered.** A fault counter that only advances
   during motion would point at the known Phase-F select/read interposition
   hazard (an OTOS transaction landing inside the Nezha encoder's select->read
   window). Advancing at rest does not fit that story.
2. **Nothing surfaces it.** `i2cf` is a telemetry column; no banner, no
   `STATUS` flag, and no test asserts a bound on it. A robot could accumulate
   thousands of I2C faults across a session and every artifact would look
   normal.
3. **It muddies every campaign** that runs on this hardware. If faults are
   being absorbed silently, "the sensor answered" and "the sensor answered
   correctly" are not the same claim, and no current tooling separates them.

## What is NOT known

- Whether the count is per-transaction retries (benign, bus noise absorbed by
  a retry layer) or genuinely dropped transactions (not benign).
- Whether the rate is normal for this hardware. **There is no baseline.** No
  prior session recorded `i2cf` over time, so "60 at first contact" cannot be
  compared to anything.
- Whether it is specific to vevov, to its older firmware build, or general.
  vevov runs the 12-column `POSE` build and does not answer `STATUS`; this has
  not been checked against master.
- Whether it correlates with the stale telemetry projection recorded in
  `tour-corner-fixes-are-stale-cache.md`. Both involve the OTOS I2C path and
  both were seen in the same session, but no causal link has been shown and
  they should not be assumed related.

## Suggested first steps

1. Find where `i2cf` is incremented in `src/` and establish what one count
   actually means — a retry, or a lost transaction. That single fact decides
   whether this is noise or a real defect, and it is a source read, not a
   bench session.
2. Record `i2cf` at the start and end of every run in the sprint 011 campaign
   procedures (already required there) so a baseline finally exists.
3. Only then decide whether a rate bound is worth asserting anywhere.

## Related

- `tour-corner-fixes-are-stale-cache.md` — same OTOS I2C path, same session.
- `unpowered-nezha-brick-wedges-program-at-boot.md` — the other place I2C
  health silently changes what the program reports.
