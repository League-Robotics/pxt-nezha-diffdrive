# The first I2C command can wedge the program dead, with no recovery

**Found**: 2026-08-27 overnight, on vevov, tovez and gopiv.

## What happens

A robot boots, answers `HELLO`, `STATUS`, `PING`, `VER` — the whole wire
protocol, on both carriers — and then the **first command that touches
I2C** (`RUN:probe`, or any motion verb) produces no reply and kills the
program. After that the board is silent on serial *and* radio until it
is reflashed. In one case the USB device de-enumerated entirely
(`device reports readiness to read but returned no data`).

Sprint 010 ("a survivable dead brick") bounded the stuck call at ~11 s,
but a bound is not recovery: the program stayed unusable indefinitely.
Measured 2026-08-27: polled `PING` every 4 s for 20 s after the wedge,
no reply, then the device dropped off USB.

## What it is NOT

Ruled out by measurement the same night — recording these because each
one cost real time:

- **Not the brick being unpowered.** The stakeholder confirmed power,
  and `RUN:probe` later answered `OPROBE:95:1` on the same board.
- **Not a firmware regression from the 2026-08-27 wire work.** Both
  bench boards run the current build with `RUN:probe` answering 3/3 and
  the full acceptance suite at 29/29, and 8/8 motion soak cycles each.
- **Not OTOS absence.** gopiv has no OTOS (`OPROBE:0:0`) and does not
  wedge.

It correlates with the board having **sat idle for a long period**. A
reflash reliably cures it — which is what makes it so easy to
misdiagnose, because the reflash in a bisect step silently fixes the
thing being bisected (see the memory note
`i2c-wedge-is-stale-state-not-firmware`).

## Why it matters

1. **It is indistinguishable from a dead robot.** Post-sprint-024
   firmware is silent when idle by design, so a wedged robot and a
   healthy one look identical until you send something — and the thing
   you naturally send to check (`RUN:probe`) is the thing that wedges it.
2. **It is unrecoverable over the air.** On the playfield the only link
   is radio, and no radio command can revive it. It needs a physical
   reflash or power cycle.
3. **It costs hours of misattribution.** This one presented, over one
   night, as: an unpowered brick, a dead robot, a firmware regression,
   and a bad radio link. It was none of them.

## What would fix it

- A **bounded, non-fatal** I2C transaction: a hard timeout that returns
  an error to the caller instead of parking the fiber, so `RUN:probe`
  answers `OPROBE:0:0`-style rather than never returning. gopiv already
  demonstrates the good shape — the call returns fast when the device
  is simply absent.
- Failing that, a **watchdog that restarts the protocol fiber**, so the
  wire stays answerable even when the motion side is stuck. Answering
  `STATUS` while wedged would turn an invisible failure into a
  diagnosable one.
- Either way, `STATUS` should be able to say "the I2C side is stuck" —
  today `wedge=` exists in the status line but read 0 throughout.

## Evidence

- `RUN:probe` → `otosBegin()` + `otosGet(7)` (`test/test.ts:550-553`)
- Wedge reproduced on vevov (radio + USB) and on tovez/gopiv after idle
- Recovery only ever observed via reflash
- Contrast: after a fresh flash, tovez `OPROBE:95:1` 3/3, gopiv
  `OPROBE:0:0` 3/3, both then 8/8 motion soak cycles

## Related

- Memory: `i2c-wedge-is-stale-state-not-firmware` (and the bisect trap)
- `clasi/issues/estop-latches-with-no-wire-level-clear.md` — the other
  "robot won't move" cause found the same night; they present identically
- `.claude/rules/playfield-testing.md`'s "The robot is OFF" section,
  which this refines: the signature it describes is real, but the cause
  it names (no power) is only one of several.
