---
status: pending
---

# v6 has no telemetry frame, and the bench tooling silently collects nothing

**Read this before the next playfield session.** Sprint 003 replaced the v5
wire protocol with v6. v5 auto-emitted a cleartext line every ~56 ms:

```
TLM:<ms>:<x>:<y>:<h>:<ox>:<oy>:<oh>:<vl>:<vr>
```

v6 has no replacement. `WireHandler::emitTelemetry()` sends only `ack`/`nack`
keepalives — the reliability layer's periodic self-heal — and no data frame at
all. `protocol.md` §5.2 describes telemetry as a projection of the kernel's
`output()`, and `wire_handler.h`'s own header comment flags real telemetry
projection as future work. It was never built.

## Why this is urgent rather than merely missing

The host tools this project runs every bench session parse that exact line:

- `tools/tour_run.py` — its `TLM:` branch will now never fire. It will run,
  complete, and write an EMPTY `_tlm.csv`. The "wheel speed while moving"
  diagnostic — the number that diagnosed the yaw-taper bug — silently becomes
  nothing.
- `tools/tour_capture.py`, `tools/tour_watch.py` — same dependency.

**This fails silently, in the exact shape this project has been bitten by
repeatedly**: an instrument that returns nothing looks identical to a robot
that did nothing. See the `measurement-before-diagnosis` lesson — a tool must
never return the same value for "absent" and "zero". A tour scored against an
empty telemetry file will produce confident, wrong conclusions.

## What to do

1. Decide whether v6 telemetry is the `thdr`/`t` self-describing frame pair
   `protocol.md` §5.2 implies, or something simpler. The spec's own
   `DiffDriveAdapter` projects `DifferentialDrive::output()` — per-wheel
   counts/velocities, not a world-frame pose — so a straight port is not
   sufficient here: this robot's tooling wants pose AND the OTOS pose AND
   measured wheel speeds, which is what the 9-field v5 line carried.
2. Until it exists, make the host tools FAIL LOUDLY rather than write an empty
   file — a missing telemetry stream should be an error, not an empty CSV.

## Related

- The measured wheel speeds in fields 8/9 exist precisely because differencing
  the pose stream does not work at this cadence (24 ms ticks sampled every
  56 ms alias into a ±25% sawtooth). Whatever replaces the frame must keep
  carrying the kernel's own per-tick measurement, not invite a consumer to
  re-derive it.
- [[status-lost-diag-numeric-surface]] is the same story for diagnostics.
