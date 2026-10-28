---
status: pending
---

# The jerk-limited path skips the speed floor and overshoots 13 mm at full speed

`src/motion/velocity_shaper.cpp` (around lines 104 to 106): when
`jerk > 0` the shaper's ramp-down ignores `vFloor`, so the command decays
through the stiction band and the wheel coasts. With `jerk 0` the floor
applies and the stop lands. Review finding F8; the 13 mm overshoot at
full speed is in the sprint 031 bench notes.

## Change (`change-plan.md` C9)

The jerk path ramps down to the floor and never through it, the same
clamp the non-jerk path already applies.

## Acceptance

`tests/host/test_velocity_shaper.py`: with `jerk > 0` the last nonzero
command is ≥ the floor; existing shaper tests unchanged.
