---
status: in-progress
sprint: '013'
tickets:
- 013-003
---

# Arc moves (move with distance AND yaw) abort — distance never driven

## Problem

Eric: `move 20 cm turning 180 degrees` "doesn't really turn 180°.
It's not even really close." Measured on tovez 2026-08-25 (blocktest
firmware built from the extension at 447135a, patched-sim copy; wire
pose h is centidegrees):

| command | believed end pose | verdict |
|---|---|---|
| `move(0, 180)` (pivot) | Δh = 18076 (180.76°), x,y ≤ 14 mm | correct |
| `move(20, 0)` (straight) | 200.3 mm on 200 mm commanded | correct |
| `move(20, 90)` (arc) | Δh = 7733 (77.3°), **x ≈ 0**, y = 19 mm | wrong |
| `move(20, 180)` (arc) | Δh = 256 (**2.56°**), x = 0, y = 1 mm | very wrong |

Pattern: pivots and straights are fine; when BOTH distance and yaw are
nonzero, the distance component never executes (x stays ~0) and the
yaw component terminates early — the tighter the arc, the earlier
(2.6° of 180°, 77° of 90°). The kernel then reports the move complete,
so the TS `move()` blocking loop exits normally. Suspects worth
checking first in the motion engine's arc path: the stall latch
tripping on the slow inner wheel, the completion predicate for
combined distance+yaw profiles, and the speed floor interacting with
the arc's wheel-speed mix.

Repro tooling: `projects/blocktest` (local MakeCode fs workspace) has
`RUN:turn:<deg>` (pivot), `RUN:go` (straight 20 cm), `RUN:arc:<deg>`
(20 cm + yaw), and pose is watchable with `TLM POSE #1` over USB
serial. Fix needs camera or eyeball truth as well as believed pose —
believed-correct-but-physically-wrong is the other half of Eric's
report and must be ruled in or out on the floor after the abort bug is
fixed.
