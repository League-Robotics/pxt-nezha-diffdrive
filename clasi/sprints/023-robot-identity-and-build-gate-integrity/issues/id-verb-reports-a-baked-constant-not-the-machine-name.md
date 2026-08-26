---
status: in-progress
sprint: '023'
tickets:
- 023-002
- 023-003
---

# `ID` reports a baked constant, not the machine name

## Problem

`ID` answers with the same robot name on every board in the fleet.

`WireHandler::execId` (`src/comms/wire_handler.cpp:711`) emits
`id <drivetrain> <profile> <version>`. The `<profile>` field is `kProfile`,
a hand-written constant at `src/comms/protocol.cpp:41` frozen at `"tovez"`.
So vevov, tovez, and any future board all reply `id diffdrive tovez 1.0.10`.

Meanwhile `Protocol::buildIdentity()` (`src/comms/protocol.cpp:~190`) DOES
populate `identity.name` from `microbit_friendly_name()` — the per-board name
burned into the chip — and `execId` never emits it. The struct field is right
there at `src/comms/wire_handler.h:102`.

Measured 2026-08-26: after flashing vevov (ch 4) and tovez (ch 3), `ID`
replied identically on both boards.

## Cost

A robot was misidentified from its `ID` reply during sprint 022's flash
verification. Identity had to be recovered from `HELLO`
(`device NEZHA2 robot <name> <serial>`) instead. On a broadcast radio group,
a verb named `ID` that cannot tell you which robot answered is a trap, and it
has now sprung once.

## Direction (Eric, 2026-08-26)

`ID` must report **the machine name, read from the chip**
(`microbit_friendly_name()`).

**Explicitly rejected:** baking the value per-robot at deploy time from the
robot JSON stem — the way `radio-robot-elite` does it via
`Config::kRobotProfileName` (`radio-robot-elite/src/firm/main.cpp:60-66`).
Rejected because it re-introduces the same class of failure: a baked value is
only ever as correct as the build that produced it, and can be stale or wrong.
The friendly name is burned into the hardware and cannot lie about which board
you are talking to.

## Constraint: the wire format is shared

`id <drivetrain> <profile> <version>` is pinned in three places OUTSIDE this
repo:

- `radio-robot-lib/docs/design/protocol.md:518` (canonical spec)
- `radio-robot-lib/tests/protocol/golden_vectors.txt:89` (conformance fixture)
- `radio-robot-lib/src/protocol/protocol_handler.cpp:623` (independent
  implementation)

Changing field order or count is a cross-repo protocol change and must be
coordinated, not done unilaterally. Appending the name as a fourth field is
backward-compatible for any positional consumer reading fields 0..2; a
cross-repo grep on 2026-08-26 found no consumer that parses the reply at all.
Which shape to adopt is part of this work, not settled here.

## Open question

`src/comms/protocol.cpp:29-33` documents `kProfile` as "the tuning bake
shims.cpp's Rig [uses]". If the machine name moves onto the wire, what — if
anything — `profile` still means needs settling. See
[[three-way-contradiction-on-which-tuning-bake-the-kernel-defaults-are]].

## Verification

Flash two different boards. `ID` must return each board's own name, and that
name must agree with the same board's `HELLO` reply. Agreement between `ID`
and `HELLO` is the acceptance test.
