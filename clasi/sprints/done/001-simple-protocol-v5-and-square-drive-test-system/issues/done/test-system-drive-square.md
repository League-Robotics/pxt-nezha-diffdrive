---
status: done
sprint: '001'
tickets:
- 001-006
---

# Test system: test.ts drives a 30 cm square on button A

## Description

Create a test system for the extension by adding a `test.ts`. The test
program exercises the closed-loop drive API end to end:

1. On startup, the program waits for **button A** to be pressed.
2. When pressed, the robot drives a **square with 30 cm sides**.
3. The pattern is straight-then-turn: each side is a 30 cm straight
   segment followed by a 90° turn.
4. The sequence **ends with a turn** (4 straights + 4 turns total), so
   the robot finishes in the **same position and orientation** it
   started in.

## Acceptance sketch

- `test.ts` exists and compiles as the PXT test file for the extension.
- Pressing button A triggers exactly one square traversal.
- The traversal is: (drive 30 cm straight, turn 90°) × 4.
- Net displacement and net heading change after the run are zero — the
  robot returns to its starting position and orientation.
