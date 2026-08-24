---
status: done
sprint: '007'
tickets:
- 007-004
---

# Simulator parity: setWheelSpeeds turns 10× too slowly; e-stop never latches

Priority: **Medium** — code review 2026-08-23, R-12 + R-13 (BLK-06 +
BLK-07; both CONFIRMED).

Two places the browser simulator contradicts hardware in ways that mislead
students exactly where they develop (UC-016):

1. **Stray `/10` (R-12)**: the `set wheel speeds` simulator body
   (`main.ts:804`) divides the yaw term by 10 — pinned two ways:
   dimensional analysis, and disagreement with `_driveTwist`'s correct sim
   math in the same file. A turn tuned in the simulator rotates 10× faster
   on hardware.
2. **No e-stop latch (R-13)**: hardware refuses post-e-stop commands at two
   layers (`diffdrive.cpp:311` gate + step's latch-forced neutral :484);
   the simulator refuses nothing. The UC-011 "forgot to clear emergency
   stop" trap — the classic student pitfall the use cases call out — is
   invisible in the simulator.

## What to do

- Delete the stray `/10`; add a comment pinning sim math to the hardware
  conversion it mirrors.
- Latch e-stop in the sim state and refuse Drive/Move sim bodies until
  cleared, mirroring the two-layer hardware behavior.
- specification.md §5 (simulator gaps) currently omits e-stop entirely —
  update it to match whichever behavior ships.
