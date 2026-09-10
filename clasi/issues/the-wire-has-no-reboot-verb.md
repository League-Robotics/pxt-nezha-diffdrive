---
status: pending
---

# The wire has no REBOOT verb, so "takes effect at next boot" cannot be tested remotely

## Description

Sprint 038 landed a credential store whose contract is explicitly *"a
`WIFICRED SET` takes effect at the next boot"*. Nothing in the v6
vocabulary can produce that boot.

This blocked ticket 004's power-cycle measurement outright (see that
ticket's Results section, and
`captures/wifi-credential-store-20260909/notes.md`). Every reboot
available to a remote operator is entangled with something else:

| way to reboot a board | why it does not work here |
|---|---|
| `mbdeploy deploy` | mass-erases the chip — destroys the very store under test |
| opening/reopening the USB serial port | the on-robot Pi's serial daemon holds the port open continuously, so it never fires |
| power-cycling the Nezha brick | needs a hand on the robot; on gopiv the brick is switched off anyway |
| a `RUN:` verb that drives the motors | resets the board as a side effect on some builds, but moves the robot — unacceptable as a test step, and unavailable with the brick off |

So the one behaviour the feature is defined by is the one behaviour no
remote session can exercise.

## Proposed resolution

Add a `REBOOT` verb (name TBD) that performs a clean software reset.

- **Unsequenced or sequenced?** It mutates the robot profoundly, which
  argues sequenced by `.claude/rules/playfield-testing.md`'s rule — but
  the reply can never arrive after the reset, so the ack semantics need
  thinking about. Consider acking BEFORE resetting, with a short delay
  so the ack reaches the wire.
- **Safety.** Must refuse, or stop the motors first, while a move is
  active — a reset mid-move with the wheels driven is exactly the
  wedge state `b2305e8`'s fault handlers were added to escape.
- It should work on every carrier, since the point is remote
  provisioning: USB, radio, and WiFi.

## Why it is worth doing beyond this one test

Provisioning a fleet becomes a single scripted exchange —
`WIFICRED SET`, `REBOOT`, wait for the mDNS announcement — with no
hands on hardware. Today that loop needs someone standing at the
playfield for the middle step.

## Affected code

- `src/comms/wire_handler.{h,cpp}` — the verb, its table entry, `HELP`
- `src/comms/wire_adapter.{h,cpp}` — the seam down to the platform
- `src/platform/` — the actual reset call
- `tools/robotlink.py` — `_V6_VERBS` mirror
- `docs/robot-connections.md`
