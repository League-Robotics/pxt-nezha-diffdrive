---
status: done
sprint: '027'
tickets:
- 027-003
---

# Radio TX during motion hangs the Nezha I2C forever (fw 1.20260829.1)

Priority: **Critical** — the whole fleet was reflashed to 1.20260829.1
on 2026-08-30 and verified only with PING/ID on IDLE robots, which is
exactly the case that still works. Any robot DRIVEN over the radio on
this build dies within one or two commands, with the last motor command
LATCHED in the Nezha brick: the wheels keep spinning until a pyOCD
reset, because STOP and the move timeout are both enforced by the
kernel that just died.

## The mechanism (MEASURED, solid)

Instrumented firmware with single-char serial markers (`captures/
tigez-cal-20260830/`, tigez on farm node meili, 2026-08-30). Markers:
`T`/`t` = tickDrive() enter/exit (this is where ALL motor I2C happens),
`D` = radio datagram event, `S12ab3` = a complete radio send.

Healthy, then fatal:

```
TtTtTtTtTtTtTtTtTt ... TDt S12ab3 T          <- then silence forever
```

Every wedge has the same fingerprint: **a radio transmit completes,
the next motor tick starts (`T`), and never returns (`t` never
prints).** The board hangs inside a Nezha I2C transaction. CODAL's I2C
has no timeout that can fire (see `run-probe-bricks-the-board`), so it
hangs forever and both transports go dead.

Contributing structure: `Protocol::run()` calls `tickDrive()` on the
SAME fiber that polls and writes the radio, and
`NezhaMotorPort::tick()` does `fiber_sleep(4)` BETWEEN its I2C select
and read (`src/platform/nezha_port.cpp:97`) — so another fiber, or a
late radio IRQ completing an async TX, can land inside the transaction
window.

## What is NOT yet established — earlier attribution RETRACTED

An earlier version of this issue blamed `v0.20260829.3..master`
(specifically `comms/protocol.{cpp,h}`). **That attribution was wrong**;
the bisect that produced it was confounded (each variant built on the
previous state with several files differing at once).

Disproof: master built with the single change `radioEnabled_ = true`
— which makes its three gates no-ops and leaves `Protocol::run()`
functionally IDENTICAL to v0.20260829.3's — still dies on the first
move. A comment-stripped diff of `protocol.{cpp,h}` between the two
tags shows only those gates plus `setupRadio()`/`enableRadio()`, and
`pxt.json` differs only in the version string.

So every semantic difference found so far is a no-op, yet:

| build | outcome |
|---|---|
| v0.20260829.3 (1 506 414 B) | survived every trial (~10 move-cycles under radio hammering) |
| master 1.20260829.1 (1 510 374 B) | died 1-2 commands in, 10+ trials, 100% |

The most coherent reading: this is a **genuine race present in BOTH
builds**, whose firing probability depends on code layout/timing. The
older build is LUCKY, not safe. Do not treat v0.20260829.3 as a fix.

## The hang is INSIDE controlStep() -- pure arithmetic (2026-08-30, later)

Marker instrumentation was pushed down through `tickDrive()` ->
`DifferentialDrive::step()` -> the motor ports. Healthy cycle:

```
T 123456 A B wW 7 cC 8 wW 9 cC 0 t
```

(`T/t` tickDrive, `1..6` step phases, `A/B` controlStep enter/exit,
`w/W` and `c/C` every I2C write/read, `7..0` the two port ticks.)

The fatal cycle, every time:

```
... 0 D t S a b T 123456 A          <- then silence forever
```

So the sequence is: a radio datagram arrives (`D`), the tick finishes
normally, a radio TX completes (`Sab`), the next tick starts, reaches
`controlStep()` (`A`) -- and **never returns** (`B` never prints).

`controlStep()` does no I/O, takes no locks, and has no sleeps: it is
pure control arithmetic that ran correctly hundreds of times in the
same session. A permanent hang there, immediately after a radio TX,
points at **memory corruption from the radio path or a hard fault**,
not at a logic bug in the motion code. That also explains why the
failure tracks binary layout rather than any semantic diff.

Ruled OUT by direct measurement (all still died):
- the `stepBusy` concurrency guard in `tickDrive()` (marker shows the
  wait loop never even spins: `g`=0, `F`=0)
- the I2C path itself (every `w/W`/`c/C` pair completes; the hang is
  before the first one of the fatal tick)
- the mid-transaction fiber yield in `step()` (replaced with a
  non-yielding busy-wait `settleNoYield()` -- kept, it is a genuine
  robustness fix, but it did not stop the wedge)

## ROOT CAUSE (2026-08-30, pyOCD on the wedged chip)

`eric@` ssh + `sudo /home/jtl/mbdeploy/.venv/bin/python3 -m pyocd
commander -t nrf52833` halted tigez IN the wedged state. The CPU is not
hung -- it has **hard-faulted**:

| register | value | meaning |
|---|---|---|
| `xpsr` | `0x210b0003` | IPSR = 3 -> executing the **HardFault** handler |
| `HFSR` (E000ED2C) | `0x40000000` | FORCED (a configurable fault escalated) |
| `CFSR` (E000ED28) | `0x00008200` | **PRECISERR + BFARVALID** -- precise data bus error |
| `BFAR` (E000ED38) | `0x474E4988` | the faulting address |
| `pc` | `0x0004044a` | `HardFault_Handler`, `gcc_startup_nrf52833.S:303` |

Exception stack frame at `sp = 0x2001fce0`:
`r3 = 0x474E4950` -- bytes `50 49 4E 47` = **"PING"**, the literal radio
payload -- and stacked `PC = 0x00029f5e` =
**`DifferentialDrive::controlStep()`, `src/core/diffdrive.cpp:667`**
(stacked LR `0x0002a4b5` = same function, line 664).

`BFAR - r3 = 0x474E4988 - 0x474E4950 = 0x38`: the code dereferenced a
`this` pointer whose value IS the ASCII text "PING", at member offset
0x38. **Radio payload bytes are landing on a live pointer.** That is
memory corruption from the radio path, not a motion-code bug -- which
is why it tracks binary layout and why every fix aimed at the motion
code failed.

### Why it presents as a total, silent freeze

`HardFault_Handler` resolves to the **default weak handler in
`codal-nrf52/nrfx_mods/mdk/gcc_startup_nrf52833.S:303` -- an infinite
loop**. Nothing panics, nothing reboots, nothing draws to the display
(blank screen, confirmed by the stakeholder), every fiber stops
(measured: an independent heartbeat fiber blinking an LED and printing
a dot every 400 ms goes silent too), and the Nezha brick holds its last
motor command, so **the wheels keep spinning until a pyOCD reset**.

### Two separable defects

1. **The corruption** (root cause, not yet localised): radio RX/TX text
   overwrites a pointer. Note `RadioTransport::rxLine_` is 240 bytes
   while `Protocol::rxLineBuf_` is 64 -- `tryReceiveLine()` does clamp
   to `outCap`, so the copy itself looks bounded; the overrun is
   elsewhere. `onDatagram()` also writes `rxLine_`/`rxLen_`/`rxReady_`
   from a DIFFERENT fiber than the one reading them, with no lock.
2. **The unsafe failure mode** (independent, fixable now): a fault
   spins forever with the motors latched. A HardFault handler that
   stops the motors and reboots -- or even just `microbit_panic()` --
   turns every occurrence into a visible, self-recovering event instead
   of a runaway robot. **Fix this first; it is small, safe, and removes
   the physical hazard regardless of the root cause.**

## NEXT INSTRUMENT NEEDED

Two cheap observations would settle it, both currently blocked:

1. **The micro:bit LED matrix in the wedged state.** A CODAL panic
   scrolls a sad face + code, which names the fault class immediately.
   Nobody has looked at the display while wedged (it was power-cycled
   first both times).
2. **A debugger on the wedged chip.** pyOCD can halt and read the PC /
   fault registers, naming the exact instruction. Needs shell on the
   farm node holding the board (`jtl@192.168.1.150`); this session's
   ssh key is not authorized there.

## Fixes tried, all still dead

1. Defer radio RX out of the I2C window (`i2cBusy_` flag; onDatagram
   sets `deferred_`, protocol fiber drains after the tick). The
   deferral demonstrably fires (`x` marker) — board still dies.
2. `fiber_sleep(2)` settle after `datagram.send()` — still dies.
3. 4 KB fiber stacks (`device_stack_size`) — still dies.
4. Eager radio bring-up at the top of `run()` — still dies.

## Next step (mechanism-driven, not commit-driven)

Make the I2C transaction non-preemptible rather than chasing the
commit: remove the yield inside the transaction window
(`nezha_port.cpp`'s `fiber_sleep(4)` between select and read) so no
other fiber can run mid-transaction, and/or hold radio TX entirely
while a move is active (queue outbound lines, flush between moves).
Test each with the reproducer below, with MANY trials — the failure is
probabilistic, so a single survival proves nothing.

## Clean-room bisect matrix (2026-08-30 late; magni bench, brick ON)

The stakeholder's constraint reframed the hunt: "we haven't had this
problem for weeks -- what changed was not the Lancaster code." All
earlier mixed-file variants (V1-V4) are RETRACTED as evidence: they
shared a pxt `built/` cache across worktrees and could serve stale TS
binaries. The following were rebuilt in clean rooms (fresh worktree, no
inherited TS cache) and judged by full 8-segment square tours over the
radio, same bench, same hour:

| build | result |
|---|---|
| v0.20260829.3 | **6/8 clean, 0 faults** (2 = ordinary radio loss) |
| master b2305e8 | dead on move 1, every time |
| .3 + ab radio_transport.{cpp,h} | **survives** (cyc monotonic, 0 faults) -- transport innocent |
| .3 + ab transport + ab protocol.{cpp,h} (gates forced true) | dead on move 1 |
| ...same, with the .3 export surface restored (setRadioGroup back, setupRadio/enableRadioLink removed) | dead on move 1 |
| ...same, with `radioEnabled_` moved out of the class (layout identical to .3) | **dead AT BOOT** (silent on USB too) |
| master + .3 blocks/test.ts (gate on) | ambiguous (losses then silence) |

The kill therefore tracks the **protocol.{cpp,h} translation unit from
ab796aa**, whose entire surviving functional delta vs .3 is a bool
member plus three always-true reads -- and neither the bool's location
nor the export surface nor the gates individually explains it. Combined
with the measured mechanism (radio FrameBuffer landing on the Rig,
packet text over a vtable pointer), the coherent reading is: **the
corruption hazard is latent and layout/init-gated; ab796aa's changes to
this TU moved live objects into the kill zone.** That also reconciles
"worked for weeks": the gun was always there; the target moved.

## Most promising untested fix (for the next session)

Allocate the Rig EAGERLY at boot, before the radio is ever enabled
(today it is created lazily on the FIRST motion command, i.e. exactly
when radio traffic is in flight). With the Rig allocated below all
radio FrameBuffer churn, the measured corruption cannot land on it.
One-line-ish change in our code (shims/protocol boot path); test with
the square-tour reproducer, then hunt the latent corruption at leisure
behind the fail-safe.

## Reproducer

Bench the robot on the mbdeploy farm, tune a torture-pool relay to its
address, drive `MOVE_X` over USB serial while hammering `PING` over the
radio. Script: `captures/tigez-cal-20260830/` notes. Instrumented
tree kept in the session scratchpad (`wt-dbg`).

## Operational hazards until fixed

- Do NOT drive any 1.20260829.1 robot over the radio.
- A wedge mid-move LATCHES the motors. Fastest remote stop:
  `mbdeploy deploy --remote <name> --hex <any good hex>` (pyOCD halts
  the MCU), then one small `MOVE_X` to take the brick back to zero.
- Radio PING/ID on an IDLE robot is safe — which is why the fleet
  reflash verification missed this entirely.

## Follow-up, 2026-09-02 (sprint 027 ticket 003 retest): RESOLVED, closing

The radio-traffic-during-motion retest this issue was waiting on ran on
tigez: 14 `MOVE_X`-over-USB pivots while `PING` hammered continuously
over the radio relay (`!CG 55 114`), on EACH of two builds — the
VFP-guarded pre-emit-queue build (`1217f19`) and this branch's HEAD —
plus 3 radio-silent negative-control pivots per build. **0/28
radio-hammer trials showed the fault's reset signature** (an unsolicited
boot banner, a `cyc` counter dropping, or a truncated ack — the
observable shape a fault now takes since the fail-safe handler stops
the motors and resets rather than latching them). 298 `PING`s sent, 298
`pong`s received across the two hammer blocks, confirming radio traffic
was genuinely concurrent with every move, not merely configured and
idle. Full transcripts and per-trial detail:
`captures/tigez-radio-retest-20260902/`.

This confirms the "Most promising untested fix" theory from this
issue's own VFP-guard cross-reference (a fiber parked at an unguarded
yield having a pointer-holding register clobbered by another fiber's
float arithmetic) as the actual fix: the fault reproduces on neither
build, including the one that predates the emit-queue work, so the
guarded yield alone — not anything downstream of it — is what stops it.
`src/platform/nezha_port.cpp`'s attribution comment is corrected to
match. Closing.
