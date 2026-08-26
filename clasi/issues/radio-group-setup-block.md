---
status: pending
sprint: '021'
tickets:
- 021-005
---

# Setup block to set the radio group (default 10)

## Problem

Student programs receive RUN commands from the RADIORELAY, and the
fleet convention is radio group 10 — but nothing in the blocks toolbox
exposes or documents radio configuration. Eric wants a block, suitable
for `on start`, that sets the radio group.

## Triage (2026-08-25)

Radio RX is already ON by default: the protocol fiber polls
`RadioTransport::tryReceiveLine()` every loop, which lazily calls
`ensureRadioReady()` — hard-coded `kGroup = 10`, `kChannel = 4`,
`kTransmitPower = 7` (`src/comms/radio_transport.h`). A bare blocks
program that includes the extension already listens on group 10 /
channel 4. Missing: a way to CHANGE the group from blocks, and a
visible/teachable radio setup step in student programs.

## Proposed shape

- New Setup-group block, e.g. `//% block="set radio group %group"`,
  default 10, callable from `on start` (`src/blocks/` + a shim +
  C++ setter in `src/comms/radio_transport.*`).
- Idempotent: before the lazy `ensureRadioReady()` runs it records the
  value; after the radio is up it re-applies via
  `uBit.radio.setGroup()`.
- **2026-08-26 update:** sprint 022 is making the CHANNEL per-robot
  (make_deploy injects each robot's radio_channel; vevov ch 4, tovez
  ch 3, each on its own relay). 021's detail planning must read 022's
  outcome before deciding how the block interacts with channel config —
  the "channel is fixed at 4" assumption below is now stale.
- Channel stays fixed on the fleet channel 4 (zavaz relay); if exposed
  at all, only as an advanced block. Never default anything onto
  channel 3 (getez).
- Doc comment should say plainly: "the robot listens for RUN commands
  from the radio relay on this group."

Pairs naturally with a "Remote" toolbox group holding `on run` /
`on run command` — see [[block-toolbox-groups-reorganization]].
