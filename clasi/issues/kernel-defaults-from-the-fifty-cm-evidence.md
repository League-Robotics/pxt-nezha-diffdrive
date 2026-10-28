---
status: pending
sprint: '043'
---

# Kernel defaults for the modes that stay on the kernel

The velocity kernel remains the actuator for `WHEELS_V`, `driveTwist`,
line following and any mode the hardware run does not hand to the
motor's position loop. The 2026-10-27 bench runs say how it should be
tuned (`nezha-esp32/docs/fifty-cm.md`, `microbit-comparison.md` §7c,
review findings F9 to F11), `change-plan.md` C18:

- `v_floor 40`, `decel` ≤ 1000, `stop_distance 0.3` took the 50 cm error
  from +3 mm (always long) to 0.6 to 0.8 mm.
- `omega_floor` sits below stiction (≈ 2.3 % duty at the effective track
  width); it should be above it, about 45 °/s body rate.
- `v_max` ≤ 0.9 × full-duty velocity so the feed-forward never saturates;
  with that ceiling `pid_ki` adds nothing at 248 mm/s and its only job
  was correcting position during a saturated brake at 792 mm/s.

## Change

Bake per robot after a two-wheel run on zuvat (sprint 2), with the
captures cited beside each constant.

## Acceptance

Defaults changed only with a capture path in the comment; the host
suite's default-pinning tests updated in the same commit.
