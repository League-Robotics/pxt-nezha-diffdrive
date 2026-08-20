---
status: done
tickets:
- NONE
---

# DEVICE banner never reaches the bridge — multi-fragment radio messages are lost

## Description

Bench-measured on vevov + zavaz relay (2026-08-19, channel 4 group 10).
The sprint 002 radio TX mirror delivers `TLM` perfectly but **never**
delivers the `DEVICE:` banner. Measured, robot->relay:

- 333/333 `TLM` lines delivered across an in-place pivot — byte-identical
  to the same robot's USB stream, 100%, 18.4 lines/s on both transports.
- 0 `DEVICE:` banners, across three separate captures: one spanning a
  genuine reflash/reboot (75 s), and one sending 5x `HELLO` over USB with
  the radio long since warm. USB returned 5/5 banners in that same run;
  radio returned 0/5.

So it is not a radio warm-up race on the lazy `ensureRadioReady()` first
send — a warm radio drops the banner just as reliably.

## Root cause

Message length, crossing the fragment boundary:

- This PXT build does not override `MICROBIT_RADIO_MAX_PACKET_SIZE`, so it
  compiles at CODAL's default **32** (`MicroBitConfig.h`). Minus
  `radio_transport.h`'s 3-byte `[SEQ][FLAGS][LEN]` header, the on-air MTU
  is **29 bytes**. This is exactly sprint.md's Open Question 1, left
  unresolved and never bench-checked.
- `TLM:<x>:<y>:<h>` is ~14 bytes -> ONE fragment (`START|END`) -> arrives.
- `DEVICE:NEZHA2:robot:vevov:1198504156` is 36 bytes + the appended `\n`
  = 37 -> **TWO** fragments (`START|MORE` then `END`) -> never arrives.

Every single-fragment message this robot has ever sent arrives; the only
multi-fragment message it sends never does. The fleet's own firmware —
which the RADIOBRIDGE relay is built against — sets
`MICROBIT_RADIO_MAX_PACKET_SIZE: 250` in `codal.json`, and the relay runs
`!MODE RAW250`, so on the fleet's side a 37-byte line is a single
fragment and the START..END reassembly path is effectively never
exercised against a real multi-fragment sender.

Ruled out — relay-side filtering or a long-message limit at the bridge.
A relay-to-relay probe on the same channel/group delivered 4/4 copies of
each of: an 11-byte line, a 36-byte `DEVICE:`-prefixed line, a 37-byte
non-`DEVICE:` line, and a 29-byte line. The relay neither swallows
`DEVICE:` lines as discovery traffic nor chokes on length. (Caveat: those
travel as single fragments in the relay's own 250-byte framing, so that
probe does not directly exercise START..END reassembly.)

## Why it matters

`TLM:<x>:<y>:<h>` carries no identity. With the banner missing, a host
listening on the air cannot tell which robot it is hearing — every robot
on channel 4 produces an identical-looking stream. That blocks untethered
field validation (the whole point of the radio mirror) and it blocks the
radio RX command plane in
[radio-rx-command-plane-run-over-bridge.md](radio-rx-command-plane-run-over-bridge.md),
whose reassembly work would be built on a fragment path with a known,
unverified hole.

## Next steps

Not yet attempted — pick one and bench-verify:

1. Raise `MICROBIT_RADIO_MAX_PACKET_SIZE` to 250 in this extension's build
   to match the fleet, so the banner is a single fragment. Needs the
   pxt-microbit mechanism for CODAL defines from an extension's
   `pxt.json`, which was not identified — it may not be reachable from an
   extension at all, only from the target.
2. Verify what the relay actually does with a genuine `START|MORE` +
   `END` pair from our framing, and fix whichever side is wrong. This is
   the real fix if RX is ever built.
3. Shorten the banner under 29 bytes. Cheapest, but a workaround: it
   leaves the multi-fragment path broken for anything added later.

Reproduce with the bench scripts under this session's scratchpad
(`relay_listen.py`, `radio_liveness.py`, `banner_test.py`,
`relay_pair_test.py`).
