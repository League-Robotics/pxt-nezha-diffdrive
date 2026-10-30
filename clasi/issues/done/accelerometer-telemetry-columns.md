---
status: done
---

# TLM FULL carries the micro:bit accelerometer (`ax ay az apk`)

Landed out of process at the sprint 044 close, 2026-10-29. Built and
flown on tovez 2026-10-29 (`tovez-016-accel.hex` onward).

- `accelSense()` (shims.cpp) reads `uBit.accelerometer` at 50 Hz from
  every protocol pass, moving or not; the accelerometer is on the
  internal I2C bus, outside the bus guard. Integer only.
- diag 48-50 are x y z in mg; 51 is the largest per-axis jump between
  reads since 51 was last read (read clears).
- Host tests: `tests/host/test_shims_cpp_accelerometer.py`, the wire
  projection and constants-drift pins.

At rest tovez reads az ~ -1064 mg and apk 4-16 mg. What it shows for
shoves and lifts is in `lift-corrupts-position-use-the-accelerometer.md`.
