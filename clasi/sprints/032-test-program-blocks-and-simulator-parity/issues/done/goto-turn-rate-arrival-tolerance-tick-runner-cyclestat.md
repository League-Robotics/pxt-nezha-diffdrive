---
status: done
sprint: '032'
tickets:
- 032-007
- 032-008
---

# Blocks: goTo pivot honours the default turn rate; arrival tolerance applies to both go-to blocks; one tick runner; delete cycleStat; one stop block

Priority: **Low** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: BT-08, BT-13, BT-14, BT-15, BT-23 ([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)). Triage #18.

## Description

- "set default turn rate ... for move/goTo" is false for `goTo`: `goToR`'s
  pivot runs at the linear cruise (~143 deg/s at the 15 cm/s default).
- Three copies of "start, then `while (_tickDrive())`" (`motion.ts`,
  `world.ts`, `test.ts`), two of which differ on `_endMove()`.
- `turnFirstDeg` is a `let` nothing writes; "set arrival tolerance" gates
  only `goToWorld` while `goTo` hard-codes 1 mm.
- `stop` and `stop move` are now one operation with two blocks.
- `cycleStat`/`_cycleStat` have no caller anywhere.

## Remedy

Convert the default yaw rate to a pivot cruise in `startGoTo` (or fix both
comments); `world.ts` calls `move()`/`goTo()`; decide `_endMove()` once;
`const turnFirstDeg`; pass `arriveTolCm` into `_goToR`; one stop block
with `stopMove` as a hidden alias; delete `cycleStat`.

Note: the motion-profile design's `omegaMax` and `MotionLimits` may
absorb the yaw-rate half; sequence this after that sprint.
