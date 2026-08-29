# The OTOS was never broken: I2C from a RUN handler hangs the board

**2026-08-28.** `RUN:probe` bricked vevov and tovez repeatedly — silent
to `PING`/`HELLO`/`STATUS`/`VER`/`ID` on **both radio and USB**, cured
only by a reflash. It was read as a dead or unwired OTOS. It was
neither.

## The measurement that settled it

A diagnostic build added `diffDrive.i2cProbe(addr7)` (a 1-byte write to
one 7-bit address, returning the raw driver status) and `RUN:iaddr:<a>`
to call it, emitting `IADDR:try:<a>` BEFORE each attempt so a hang still
names its address.

| target | address | result |
|---|---|---|
| full sweep from 0x08 | — | hung at the FIRST address, `SCAN:try:8` last line |
| **Nezha brick** | **0x10 (16)** | **HUNG** — `IADDR:try:16`, no result, board dead |

0x10 is the **Nezha motor controller** — a device that unquestionably
works: minutes later, on the same robot and the same bus, a `MOVE_X`
completed with `connL=1 connR=1 cyc=335 i2cf=0`.

So the address is irrelevant, the device is irrelevant, and the OTOS
was never implicated. **Any `uBit.i2c` transaction issued from a RUN
handler hangs the board.** The motion fiber talks to the same bus fine.

`src/DESIGN.md` already warned of this shape — the protocol fiber "must
never trigger a fresh OTOS sample" — but the warning was about
corrupting an encoder sample, not about hanging outright, and nothing
stopped `RUN:probe` from doing exactly the forbidden thing.

Why a hang rather than an error: an ABSENT device NACKs, raising
`NRF_TWIM_EVENT_ERROR`, which CODAL handles cleanly. Only *no error and
no completion* spins `NRF52I2C::waitForStop()`, whose silicon-errata
branch does `locked = 0` and so can never reach its own 10 s timeout.
The loop never `fiber_sleep`s, so one spin starves every fiber — hence
total silence rather than a slow verb. (Source reading, NOT instrumented.)

## The fix

Two changes in `test/test.ts`, both about WHERE the call happens:

1. **Bring the OTOS up on the MAIN fiber at boot**, not from a RUN
   handler: `diffDrive.otosBegin()` in top-level code.
2. **Sample it from a background fiber** at 10 Hz:
   `control.inBackground(... diffDrive.readWorld() ...)`. `otosGet()` is
   CACHE-ONLY (`wire_adapter.h`), and every existing `readWorld()` caller
   sat inside a RUN handler — so nothing ever refilled the cache and
   `ox/oy/oh` read `(0,0,0)` forever. That is exactly the flat series the
   orange-dots tour had to chart as "no data".

## Result — measured, both robots

| | before | after |
|---|---|---|
| `otos=` (vevov) | 0 | **1** |
| `otos=` (tovez) | 0 | **1** |
| non-zero OTOS telemetry frames | 0 / 153 | **147 / 147** |
| `RUN:probe` | bricks the board | not needed; boot does it |

`oh` tracked live (8 -> 13 cdeg across a move). `ox/oy` stayed 0, which
is CORRECT for the conditions: vevov was on a bench, off the playfield
(camera showed AprilTag 1 only, no tag 53), and the OTOS is an OPTICAL
FLOOR sensor — no surface motion, no translation. **UNVERIFIED:** OTOS
translation has not yet been confirmed against camera truth on the
field. That is the next test, and until it is run `ox/oy` are not known
to be right, only known to be sampled.

`i2cf` went 0 -> 3 during the sampled run. Small, but not zero, and the
OTOS and Nezha ports share the bus with NO mutual exclusion — watch it.

## Corrections this forced

- "OTOS is not acknowledging at 0x17 / probably unwired" — WRONG. 0x10
  hangs identically and 0x10 demonstrably works.
- "tovez wedged too" was first called at 4.5 s, INSIDE CODAL's 10 s
  timeout. A reflash was spent on it. The 90 s retest happened to agree,
  but the original basis was unsound.
- `0x10` is the **Nezha**, not the OTOS (which is `0x17`, confirmed
  against radio-robot-elite's `kOtosDeviceAddr`).
- Several robots were simply **switched off** during earlier tests; an
  unpowered brick clamps the bus and produces the same hang.

## Note for anyone reading telemetry

**zeguz is broadcasting v5 `TLM:`/`DIAG:` lines on the radio channel**
and they interleave with vevov's replies. Filter them, or move zeguz,
before trusting a capture.
