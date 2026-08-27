---
status: done
sprint: '024'
tickets:
- '002'
---

# Radio link wedges on a sequence gap and reconnect cannot heal it

A robot whose radio wire handler has stalled on a sequence gap streams
`nack 1 0 none` at the 50 ms reliability cadence (20 lines/sec) and no
host tool in `tools/` can clear it. Only a robot reboot does. Found
while diagnosing a live radio connect on 2026-08-26.

## What the wire is actually saying

`nack <nextId> <lastDone> <reason>` — `WireHandler::replyNack()`
(`src/comms/wire_handler.cpp:588`) sends `expectedNext_`, i.e. "send me
THIS id next". `nack 1 0 none` therefore means the radio handler has
accepted **zero** sequenced commands since boot, has completed no
motion, and is deliberately stalled: `gapOutstanding_` is latched and
only clears when a well-formed line carrying exactly id 1 decodes
(`wire_handler.cpp:557`). `emitReliability()` re-nacks on every
reliability tick until then (`protocol.cpp:346-358`).

The stall itself is correct, designed behaviour. The two defects below
are that nothing on the host side can get out of it.

## Defect 1 — `sync_seq()` is off by one on a nack line

`tools/robotlink.py:138-141` matches `^(?:ack|nack)\s+(\d+)` and sets
`self._seq = N` for both. That is right for an ack (`ack N` = "N was
accepted", so the next legal id is N+1, which `_format()` allocates)
and wrong for a nack (`nack N` = "send me N", so the next id must be N
itself). Reading `nack 1` sets `_seq = 1`, `_format()` emits `#2` — a
fresh gap on the same wound. Every reconnect into a stalled robot
re-wedges itself, which is why the state looks permanent.

The bug only bites when the robot is already stalled, so it is
invisible on a healthy link.

## Defect 2 — `open_link()` never sends HELLO

`WireHandler::handleHello()` (`src/comms/wire_handler.cpp:640-652`)
resets `expectedNext_` to 1 and clears `gapOutstanding_`, and
`protocol.md` S8.3 designates HELLO as *the session-start resync a
(re)connecting host performs*. `open_link()`
(`tools/robotlink.py:208-244`) calls `sync_seq()` on both carriers and
never sends HELLO on either — so the one escape hatch the protocol
provides is never used.

HELLO is unsequenced and is not in `_V6_VERBS`, so `link.send('HELLO')`
already passes through un-tagged today. Its reply is the boot banner,
which is also the identity authority (see
`.claude/rules/playfield-testing.md`).

## Proposed fix

1. `sync_seq()`: set `_seq = N - 1` when the matched line is a `nack`,
   `_seq = N` when it is an `ack`. Keep the distinction in the regex
   match, not in a second pass.
2. `open_link()`: send `HELLO` and consume the banner before
   `sync_seq()`, on both USB and radio.
3. Pin both in `tests/tools/` — a fake link that replies `nack 5`
   must produce `#5` as the next command, not `#6`.

## Related

- Radio is lossier than USB and `RadioTransport::onDatagram()`
  (`src/comms/radio_transport.cpp:49-73`) drops a frame outright when
  the previous line is unconsumed and drops every multi-fragment frame,
  so gaps are expected to open there routinely. The handler stalling is
  fine; the host having no way out is not.
- Per-transport isolation means a wedged radio handler leaves USB
  looking perfectly healthy, which makes this easy to misdiagnose as a
  relay or RF fault.
