---
status: in-progress
sprint: '006'
tickets:
- 006-005
- 006-006
---

# Brick MCU reset mid-session teleports odometry ~4 m (bench check + rebaseline)

Priority: **Medium** — code review 2026-08-23, R-07 (KERN-07; code path
CONFIRMED statically, hardware premise UNVERIFIABLE without bench).

If the Nezha brick's MCU resets mid-session (brownout, wiring blip), its
encoder counters restart from zero. The glitch armor's two-strike rule
accepts the discontinuity as truth on the second read; no production path
rebaselines the counters. Statically certain: a ~−50k-count jump maps to a
~4 m pose teleport and a 1–2 M counts/s speed spike. What needs hardware:
whether a brick reset actually zeroes the 0x46 counter registers.

**Decisive bench experiment** (from `verify-kernel.md`): power-cycle the
brick mid-drive while watching DIAG ordinals 10/11 and pose. Distinct from
the filed `unpowered-nezha-brick-wedges-program-at-boot` (boot-time wedge);
this is the mid-session variant. Follow this project's measurement doctrine:
prove the instrument (DIAG capture running) before interpreting the fault.

## What to do

1. Run the bench experiment; record numbers in the issue.
2. If confirmed: rebaseline on discontinuity (treat an impossible delta as
   "reset detected" — re-zero the baseline instead of integrating it), and
   surface a DIAG counter for it.
