---
id: '002'
title: 'CutebotMotorPort + CutebotDevice: PWM path, revision probe, encoder, e-stop'
status: open
use-cases: ["SUC-002"]
depends-on: ["001"]
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# CutebotMotorPort + CutebotDevice: PWM path, revision probe, encoder, e-stop

## Description

Depends on ticket 001 (the board seam must exist so
`DIFFDRIVE_BOARD_CUTEBOT_PRO` has somewhere to plug in). Implement the
Cutebot Pro's raw-PWM actuation path only — the `0x80` onboard-loop
path and the actuation policy are ticket 004; this ticket proves the
same category of correctness the Nezha port already has, one board
level down.

Per `docs/design/cutebot-pro-support.md` §1.2 (v2 wire frames), §2.1
(the port), §3.A (what to watch), and §7 (host testing):

- `src/platform/cutebot_port.h/.cpp`: `CutebotMotorPort final : public
  DiffDrive::Motor`, implementing all 14 calls
  (`begin`/`requestSample`/`setDuty`/`emergencyStop`/`tick`/
  `position`/`velocity`/`appliedDuty`/`connected`/`sampleTime`/
  `rebaseline`/`wedged`/`wedgeSuspect`, `src/core/diffdrive.h:25-44`)
  against a shared `CutebotDevice` object both wheels' ports bind to
  (the Cutebot takes both wheels' duties in ONE `0x10` frame, so one
  wheel's `tick()` stages, the other's ships).
- `CutebotDevice`: the 0x10 slave's session state — the revision probe
  (`99 15 01 00 00 00 88`, cached for the session, §1.1) run once at
  the first `begin()`; v2 frame encode
  (`FF F9 <cmd> <len> <params...>`, §1.2) for cmd `0x10` (wheel,
  abs% L, abs% R, dirbits) coalescing both wheels' staged duties into
  one write per kernel cycle; cmd `0xA0 [3]`/`[4]` + a 4-byte read for
  each wheel's accumulated degrees, converted to kernel counts
  (degrees ×10 = counts, matching the Nezha port's "1 count = 0.1°"
  convention); cmd `0x50` to zero an encoder (`rebaseline()` stays a
  software offset, no bus traffic, exactly like `NezhaMotorPort` —
  `0x50` is for a real hardware zero, not used by `rebaseline()`); the
  per-board `diffdrive_emergency_stop` frame for a Cutebot (writes the
  `0x10` zero-PWM frame with no dependency on any object, mirroring
  `nezha_port.cpp:52-65`'s fault-context contract).
- A failed read (simulated NACK in this sprint) holds the previous
  `sampleTime()` rather than fabricating a zero velocity — the same
  contract `NezhaMotorPort`/`src/DESIGN.md` §7 states for the Nezha
  port ("a port whose read FAILS must hold `sampleTime()`, not report
  velocity zero").
- The 1 ms post-write busy-wait the ELECFREAKS extension uses after
  every `i2cCommandSend()` (§1.2) must go through
  `diffDrive::vfpSafeSleep()` (`src/platform/vfp_guard.h`), never a
  spin or a raw `fiber_sleep()` — per
  `.claude/rules/fiber-yield-safety.md`, any CODAL-facing sleep not
  routed through the guard is a defect
  `test_vfp_guard_source_pin.py`-style pinning should catch.
- `configureMotor`'s Cutebot behaviour (§10.2, the open stakeholder
  question this sprint resolves): `CutebotMotorPort::configureWiring()`
  accepts a sign change (flips which physical direction is "forward"
  for that wheel) and **refuses** any request that would change which
  physical wheel a side addresses (the Cutebot's wheels are fixed to
  the one 0x10 slave — there is no second port to move to). Route the
  refusal through the wire's existing `Result` refusal-code path
  (`src/DESIGN.md` §4's `kBadArg`/`kRange`/etc. taxonomy), not a silent
  no-op; pick the specific code and record the choice in this ticket's
  own completion notes as **stakeholder-reviewable** — it resolves an
  explicitly open design-doc question, not a settled convention.
- Host testing (`docs/design/cutebot-pro-support.md` §7):
  `tests/host/sim_cutebot_bus.h` — a fake 0x10 slave answering v2
  frames, the revision probe, `0xA0 [3]/[4]` in degrees from a shared
  `SimWheel` (reuse the existing Nezha sim's physics class), and `0x50`
  clears. (The `0x80` onboard-loop simulation is ticket 004's, once the
  path exists to simulate.) `cutebot_port_shim.cpp` +
  `test_cutebot_port.py`: frame bytes and direction bits for every sign
  combination, the coalesced two-wheel write (exactly one `0x10` frame
  per kernel cycle — not two), degrees-to-counts conversion,
  `rebaseline()`, `emergencyStop()` bytes, `connected()` and held
  `sampleTime()` on a simulated NACK, and the `configureWiring()`
  sign-flip/port-refusal behaviour above.

## Acceptance Criteria

- [ ] `CutebotMotorPort` implements all 14 `DiffDrive::Motor` calls;
      `test_cutebot_port.py` exercises every one against
      `sim_cutebot_bus.h`.
- [ ] Exactly one `0x10` frame is shipped per kernel cycle for a pair
      of `CutebotMotorPort`s (proven by counting frames the sim bus
      receives across one `tick()` of both wheels), never two.
- [ ] Encoder degrees ×10 = counts conversion is exact and covered for
      both positive and negative directions.
- [ ] A simulated NACK on the encoder read holds the previous
      `sampleTime()` and does not report a fabricated zero velocity.
- [ ] `emergencyStop()` and the fault-context
      `diffdrive_emergency_stop` frame for the Cutebot board are pinned
      by a source-level test analogous to the Nezha frame's own
      pinning.
- [ ] `configureWiring()` accepts a sign-only change and refuses a
      port-changing request via the existing `Result` refusal-code
      path, covered by `test_cutebot_port.py`; the chosen refusal code
      is documented in this ticket's completion notes as a
      stakeholder-reviewable choice.
- [ ] No CODAL sleep in the new code bypasses `vfpSafeSleep()`/
      `vfpSafeYield()`.
- [ ] Full host suite stays green; ticket 001's byte-identical-Nezha
      guarantee is unaffected (no shared file touched by both tickets
      regresses the other's acceptance criteria).

## Testing

- **Existing tests to run**: full `uv run pytest`; ticket 001's
  byte-identity/host-suite checks re-run to confirm this ticket adds
  code without disturbing the Nezha path.
- **New tests to write**: `cutebot_port_shim.cpp` / `test_cutebot_port.py`
  (see Description); `tests/host/sim_cutebot_bus.h` as a shared fixture
  for this and later tickets (004, 006).
- **Verification command**: `uv run pytest tests/host/test_cutebot_port.py`
  during development, full `uv run pytest` before completion.
