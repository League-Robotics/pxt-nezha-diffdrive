---
status: pending
---

# ESTOP latches until reboot — no wire verb reaches estopClear()

Priority: Medium. Found 2026-08-31 during the multi-robot field session:
a precautionary `ESTOP` broadcast to all field robots latched tigez
(`flags=33 reason=estop`; every subsequent MOVE_X completes instantly
as a no-op, motors never energized), and the only recovery was a
physical power cycle — the robot was untethered on the field.

The kernel has the clear half (`DifferentialDrive::estopClear()`,
`src/core/diffdrive.h:199`, forwarded by `shims.cpp:810`), but nothing
in `src/comms/`, `blocks/`, or `test.ts` calls it. The wire can latch
(`ESTOP`, unsequenced, wire_handler.cpp) but not unlatch. The NolanNet
bench notes recorded the same gap ("no wire ESTOP-clear").

Diagnostic wrinkle: an estopped robot looks EXACTLY like the
"responds but does not move = power off" pattern over the wire, except
STATUS says `reason=estop` and flags carry bit 1 — the fleet harness
now surfaces that in probe failures.

Fix shape: a sequenced verb (e.g. `ESTOP_CLEAR` or `SET estop 0`) that
calls the kernel's `estopClear()`. Sequenced on purpose — clearing an
emergency stop should never replay from a stale retransmit. Candidate
for the same wire-surface sprint as
`no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md`.

Operational rule until then (encoded in the session harness): routine
halts use `STOP`; `ESTOP` only for true runaway, accepting that it
costs a walk to the robot.
