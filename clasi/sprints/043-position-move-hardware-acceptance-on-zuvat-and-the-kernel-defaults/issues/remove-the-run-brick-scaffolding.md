---
status: in-progress
sprint: '043'
tickets:
- 043-008
---

# Remove the `RUN brick*` probe scaffolding from the test program

`test/test.ts` carries `RUN brick`, `brickx`, `brickraw`, `brickread`
and `brickstop`: raw `pins.i2c*` writes to the brick that bypass the
`BusGuard`, added for the 2026-10-27 measurements. Once the real path
exists (position moves routed through `MOVE_X`/`WHEELS_X`, hard stop on
`STOP`), they are a hazard and go. `tools/mb50.py`'s brick mode moves
onto the real verbs. `change-plan.md` C19.

## Acceptance

The test build has no raw `pins.i2c*` outside the `BusGuard`;
`tools/mb50.py --mode position` drives the real verbs.
