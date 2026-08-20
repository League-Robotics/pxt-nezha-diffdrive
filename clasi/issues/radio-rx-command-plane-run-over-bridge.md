---
status: pending
---

# Radio RX command plane — RUN (and other verbs) over the bridge

## Description

Sprint 002's radio support is TX-only (TLM/DEVICE mirrored out). The
stakeholder wants to trigger test.ts programs remotely; the new RUN:<n>
verb (commit bc34005) does that over USB serial today. For untethered
field runs, RUN (and potentially other command verbs) should also
arrive over the micro:bit radio via the RADIOBRIDGE relays — the
reference Protocol v5 spec's host→robot radio command plane.

Scope: add a radio RX path to radio_transport (fragment reassembly for
the [SEQ][FLAGS][LEN] framing, dedupe/sequence handling), feed
reassembled lines into the same parseLine()/dispatch pipeline the
serial transport uses, gated to a safe verb subset (at minimum RUN;
decide whether motion verbs are acceptable over radio — the reference
spec's ACK story matters if so, since fire-and-forget ESTOP over a
lossy link is a safety question this project has so far ducked by
being wired-only).

Note from bench (2026-08-19, superseding the earlier "TX UNVERIFIED"
note): TX is now **VERIFIED** end-to-end. vevov -> zavaz relay on
channel 4 group 10 delivered 333/333 `TLM` lines across an in-place
pivot, byte-identical to the same robot's USB stream, 18.4 lines/s on
both transports. The relay reassembles our RadioRelay framing and
prints the lines in both its control plane (`< ` prefixed) and its
`!GO` data plane. No BLE-vs-radio conflict: the MakeCode build's radio
works.

One hole remains, and it is a prerequisite for this issue rather than
part of it: the `DEVICE:` banner never arrives over radio, because at
CODAL's default 32-byte packet size it is the only message this robot
sends that needs two fragments. See
[radio-device-banner-never-reaches-the-bridge.md](radio-device-banner-never-reaches-the-bridge.md).
RX work here means implementing exactly that START..END reassembly in
the other direction, so fix the TX-side fragment hole first — it is the
same code path's mirror image, and it is currently unexercised.
