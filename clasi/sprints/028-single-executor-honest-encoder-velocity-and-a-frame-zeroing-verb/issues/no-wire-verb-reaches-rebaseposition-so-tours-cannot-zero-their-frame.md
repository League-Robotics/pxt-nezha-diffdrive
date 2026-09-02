---
status: in-progress
sprint: 028
tickets:
- 028-002
---

# No wire verb reaches rebasePosition(), so a tour cannot zero its own frame

Priority: Medium. Stakeholder question that surfaced it (2026-08-30,
bench square chart review): "You shouldn't have to align it
specifically. You just have to set the heading."

The kernel has `rebasePosition()` (deferred request counter,
`src/core/diffdrive.{h,cpp}`, exposed to the TS/blocks layer via
`src/shims.cpp`) — but nothing in `src/comms/` or `test.ts` maps a v6
verb (or a `RUN:` cleartext) to it. A radio-driven tour therefore
starts in whatever boot-anchored odometry frame the robot has
accumulated (on 2026-08-30 the bench robot sat 23 moves / ~103 deg off
axis), and every chart needs host-side rotation to line up.

Fix shape: a sequenced wire verb (e.g. `SET pose 0 0 0` or `REBASE`)
that calls the kernel's rebase. Then leg 1 of any tour defines the
frame by construction and odometry plots come out axis-aligned raw.

Note: tigez has no OTOS (`otos=0` in STATUS); heading is wheel-encoder
integration from boot, so there is no absolute-heading source to seed
from on that chassis — zeroing at tour start is the whole mechanism.

Candidate for the sprint that fixes the master radio-corruption
regression (`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`),
since the fleet should only take new wire surface via a proper build.
