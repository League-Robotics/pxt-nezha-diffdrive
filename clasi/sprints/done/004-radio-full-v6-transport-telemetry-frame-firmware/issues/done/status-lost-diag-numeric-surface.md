---
status: done
sprint: '004'
tickets:
- 004-004
---

# STATUS reproduces DIAG's flags but lost its numeric surface, including the I2C fault counter

Sprint 003's v6 cutover retired the `DIAG` verb. `STATUS` was taken as its
replacement, and it does reproduce DIAG's eight boolean flags — but none of
its roughly fifteen NUMERIC fields survived, and there is no v6 verb in the
catalog that carries them.

What DIAG reported that STATUS does not:

```
i2cf=<n>     I2C fault counter        <- the important one
pos=<l>/<r>  raw encoder positions
duty=<l>/<r> commanded duty
vel=<l>/<r>  measured wheel velocity
cyc=<n>      kernel cycle count
sat, def, ovr, err, ln, vb, wh, wpk, egl, lexc
```

## Why the I2C counter specifically matters

An unpowered or wedged Nezha brick is a REAL, RECURRING failure on this
hardware — there is a standing issue for it
(`unpowered-nezha-brick-wedges-program-at-boot.md`). The way that failure has
actually been diagnosed at the bench is by reading `i2cf` climbing while
`conn` stays 0/0. A boolean "wedge" flag tells you something is wrong; the
counter tells you it is the bus and how fast it is degrading.

During sprint 003's own bench work, `DIAG` output was used directly to confirm
a `face` command was executing (`duty=-1200/1000, vel=-1500/1167`) when the
question was whether the verb had run at all.

## What to do

Decide where the numeric surface belongs in v6. Candidates:

- extend `STATUS`'s `k=v` reply — it is already documented as "order not
  guaranteed, unknown keys ignored", so adding numeric keys is
  backward-compatible by construction
- or carry them in the telemetry frame that
  [[v6-has-no-telemetry-frame-bench-tooling-collects-nothing]] has to build
  anyway, since most of these are projections of the same
  `DifferentialDrive::output()`

The second is probably right — these are output projections, not status — but
`i2cf` and `conn` are genuinely status rather than telemetry, so the split
needs a moment's thought rather than a bulk move.

## Addendum (code review 2026-08-23, R-22/WIRE-06, CONFIRMED)

A related, sharper gap surfaced in the same session: `wire_adapter.cpp:226`
hardcodes `out.otos = false` in `status()` unconditionally — even when an
OTOS is physically connected and `engineGoToW()` (`shims.cpp:891-892`) is
actively gating its own behavior on `otosRef().connected()` being true. So
`STATUS`'s `otos=` field can confidently tell a bench operator "no OTOS"
while a `GO_TO_W` move is using one right now — worse than a missing
numeric field, this is an actively wrong boolean. `shims.cpp:970`'s
`otosGet(7)` already returns exactly this connected/disconnected boolean,
so the fix costs one line, not a new shim entry point. Ticket 004 (this
sprint) now includes this fix alongside its `i2cf=` work, since both are
one-line `status()` corrections sourced from already-forward-declared
accessors. Left unfixed, this would misroute sprint 005's closed-loop
tooling, which is exactly the audience `status-lost-diag-numeric-surface`
exists to serve.
