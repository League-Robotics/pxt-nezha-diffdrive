---
status: done
sprint: '017'
tickets:
- 017-004
---

# `src/DESIGN.md` is 44% sprint-history appendix, and something appends one per sprint

Priority: **Medium** -- the deletion is easy; the recurrence guard is the point.

## Measured

| Section | Lines |
|---|---:|
| S1-S11 -- the actual design | 1143 |
| S12 Sprint 006 / S13 Sprint 007 / S14 Sprint 008 / S15 Sprint 012 / S16 Sprint 013 -- "architecture diagram and change summary" | **902** |
| total | 2045 |

**902 lines, 44%.**

This is the design-doc analogue of the ticket-archaeology comment anti-pattern
`docs/code-review/guidelines.md` already bans in source, and it fails the same
way. S15 is the clearest case: 315 lines describing sprint 012's split of
`main.ts` into six modules -- whose product now lives in `src/blocks/`, a
directory S15 does not know exists, because S16 moved it one sprint later. A
reader must hold S9, S15 and S16 simultaneously to work out what is true.

## What to change

Each of these sections already exists, verbatim, in its own sprint's
`clasi/sprints/NNN-*/design/` overlay. Keeping S1-S11 and deleting S12-S16 loses
nothing and halves the document.

**The recurrence guard matters more than the deletion.** Something in the
sprint-close path appends one of these per sprint. Whatever that is should stop,
or the section grows back by sprint 018.
