---
status: pending
---

# ensure() is not re-entrant — two Rigs can be constructed

Found 2026-08-31 during the radio-wedge corruption hunt (source
reading, this repo at b2305e8; full context in
`reports/radio-wedge-analysis-20260831.md`, Addendum).

## The defect

`static Rig& ensure()` in `src/shims.cpp` (~line 188) does:

```c
if (rig == nullptr) {
  rig = new Rig();
  ...
}
```

`rig` is assigned only after `new Rig()` **returns** — i.e. after the
allocation AND the full constructor chain. If anything in that
construction path yields the fiber, a second fiber that calls any shim
during the window sees `rig == nullptr` and constructs a **second
Rig**: the first is leaked half-built, both constructors drive the same
Nezha I2C hardware interleaved, and whichever assignment lands last
wins.

The yield is plausible: the boot priming path contains
`fiber_sleep(4)` (`src/platform/nezha_port.cpp:201`). **UNVERIFIED**
whether that priming is reachable from the Rig/port constructors or
only from the first tick — settling that (one read of the constructor
chain, or a marker on entry/exit of `Rig::Rig()` around a forced
concurrent shim call) decides whether this is a live race or only a
latent one.

The window is real in practice regardless of which side it lands on:
the Rig is constructed lazily on the FIRST motor command, and this
project drives robots from two transports at once (USB serial + radio),
so "two fibers issue their first engine call near-simultaneously" is a
normal session shape, not an exotic one.

## Consequences if it fires

- A leaked, half-constructed Rig (heap churn at the worst possible
  moment — first motion).
- Doubled I2C initialization interleaved on one bus — the exact bus
  whose wedges this repo has a long history with.
- Not shown to be the heap-metadata corrupter behind
  `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`, but it
  lives in the same neighborhood (first radio-session move) and should
  be closed before it muddies further forensics.

## Fix shape

Standard: set a `constructing` latch (or assign a sentinel) before
`new Rig()`, or serialize ensure() behind a one-shot fiber-safe init.
Cheap to fix; the test is a concurrent first-command from both
transports.
