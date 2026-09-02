---
status: done
---
# ESTOP latches with no wire-level way to clear it

**Found**: 2026-08-27, while building `tools/wire_acceptance.py`.

## What happens

`ESTOP` reaches `WireAdapter::onEstop()` → `estopAll()` →
`kernel.estop()` + `emergencyStopMotors()`, both of which set
`estopLatch_` (`src/core/diffdrive.cpp`). `checkCommandable()` then
refuses **every** subsequent motion command at intake, for the life of
the program.

The clear exists — `kernel.estopClear()`, forwarded by
`shims.cpp::estopClear()` — but it is reachable **only from a block**
(`src/blocks/stop.ts:34`, `sim.ts:318`'s `_estopClear`). **No wire verb
exposes it.**

So a host that sends `ESTOP` over serial or radio has bricked motion for
that session and can only recover by rebooting the board.

## Why it matters

`ESTOP` is the verb you send when something is already going wrong. The
recovery path from the emergency state should not be "power-cycle the
robot," particularly on the playfield where the robot may be somewhere
inconvenient and the only link is radio.

It also silently breaks any test or tool that exercises `ESTOP` and then
expects to move again. `tools/wire_acceptance.py` hit exactly this: its
motion cases failed until the run order was changed to put motion
*before* the `ESTOP` case. The failure presents as "the robot won't
move" with no clue pointing at the latch — `STATUS`'s `flags` bit
(`kFlagEstopped`, `wire_adapter.cpp:152`) is the only evidence, and
nothing draws attention to it.

## Evidence

- `src/comms/wire_adapter.cpp:496` `onEstop()` → `estopAll()`
- `src/DESIGN.md:1256-1257` documents both latch-setters and names
  `kernel.estopClear()` as the only clear
- `grep -rn 'estopClear' src/` → only `src/blocks/stop.ts` and
  `src/blocks/sim.ts`; no wire verb
- Reproduced on tovez and gopiv, 2026-08-27: after `ESTOP`, every
  `WHEELS_X` was accepted at the wire level (`ack`) but the wheels never
  turned, and `STATUS` continued to report `ready=0`.

## Options

1. **A wire verb** — e.g. `ESTOP CLEAR`, or a dedicated `RESUME`.
   Note `ESTOP`'s current arity is "maximally forgiving, any trailing
   content answers `estop`" (protocol.md S8.3), so adding a
   discriminated field is a real grammar change, not a free extension.
2. **`HELLO` clears it.** `HELLO` is already the session-reset verb and
   already resets `expectedNext_`/`gapOutstanding_`. Clearing an estop
   is arguably a different class of thing (safety state, not sequence
   state) and doing it implicitly may be surprising — flagged as the
   cheap option, not the recommended one.
3. **Leave it, and surface it loudly** — make the estop latch visible in
   `STATUS` in a way a human reads at a glance, and document that
   recovery is a reboot.

Needs a decision from the stakeholder; this issue does not assume one.
Cross-repo: `radio-robot-lib` owns `protocol.md` §8.3, so option 1 needs
coordination there.

## Related

- `tools/wire_acceptance.py` (its run order encodes this constraint)
- [[i2c-wedge-is-stale-state-not-firmware]] — a different "robot won't
  move" cause found the same night; the two present identically from the
  outside, which is itself an argument for making this one visible.

---

## Triage 2026-09-02 — DONE

`RUN:clearestop` (`test/test.ts`, commit 7d9131c) reaches
`clearEmergencyStop()` over the wire and answers `ESTOP:cleared`. It is
a cleartext `RUN:` verb, not a sequenced v6 one; the cleartext path's
UART wedge is `next/concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`
and lands with sprint 026 ticket 003. If a sequenced verb is still
wanted, add it alongside the rebase verb in
`next/no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md`.
