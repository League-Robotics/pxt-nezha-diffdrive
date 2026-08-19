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

Note from bench (2026-08-19): the TX mirror itself is still
UNVERIFIED end-to-end — the bridge-side listen attempts failed on a
serial port error before any clean vevov TLM line was observed at the
bridge (and a possible BLE-vs-radio conflict in the MakeCode build has
not been ruled out). Verify TX at a bridge before building RX on top.
