---
status: in-progress
sprint: '042'
tickets:
- 042-011
---

# `nudge()` and `beginNudgeWheels()` round to whole millimetres

`src/blocks/motion.ts:364` and `src/shims.cpp:740` pass the nudge
distance as an integer mm, so a 1.79 mm pulse (the measured unit,
`captures/039-003-pulse-gate-20260916/notes.md`) cannot be asked for
and sub-millimetre trims round away. Review finding F12.

## Change (`change-plan.md` C10)

Both take hundredths of a millimetre on the shim boundary; the block
keeps its cm/mm face and scales.

## Acceptance

Host test on the shim arity pin; sim parity test still passes; a
0.5 mm nudge request reaches the engine as 50 hundredths.
