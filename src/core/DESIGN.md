# src/core — control kernel and host-portable helper headers

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The chassis-agnostic control kernel (`diffdrive.h/.cpp`,
`DiffDrive::DifferentialDrive`) plus two small host-portable helper
headers used by the platform layer: `heading_wrap.h` (OTOS heading
unwrap) and `encoder_glitch_armor.h` (encoder implausible-jump
arbitration). Per the layer map, everything here compiles with libc
only — no I2C, no CODAL, no MakeCode, no geometry.

**Sprint 029** made four small, independently-justifiable patches to
`diffdrive.cpp` (K1-K4: integrate the twist-hold reference from the
post-floor half-differential; freeze the position reference on a stale
encoder tick; anti-windup clamp the position reference; a
`rearmReferences()` deferred request) plus one fleet-bake config change
(K5: `vMin = 0`, since the speed floor moves up to the motion engine's
new `MotionLimits`) — see
[`docs/design/motion-profile-unification.md`](../../docs/design/motion-profile-unification.md)
§4.5. Whether this repo keeps a byte-identical vendored copy of
`radio-robot-elite/src/firm/diffdrive/` (paired-PR for every kernel
change) or owns a local fork (a behavioral fidelity test instead) is an
open stakeholder decision this sprint surfaces but does not resolve —
see `clasi/issues/code-review/decide-the-kernel-fork.md`.

Detail (the kernel's tick model, encoder-servo loop, and API) lives in
[`src/DESIGN.md`](../DESIGN.md) §2; the two helper headers' one-line
contracts are in §1's layer map table, and `encoder_glitch_armor.h`'s
consumer (`NezhaMotorPort::collect()`) is described in §7. This file
does not duplicate that content — it exists so `ls src/core/` points
somewhere.

## position_motor.h — the position-move port seam

`position_motor.h` (`DiffDrive::PositionMotor`, libc only) is a second
interface a hardware port may implement beside `DiffDrive::Motor`. It
lets the motion engine hand a wheel a relative target and let the motor's
own position loop run it, instead of streaming velocity.

- `supportsPositionMove()` — does this port have a built-in move.
- `positionQuantum()` [counts] — the smallest step the motor honours (10
  on the Nezha brick).
- `beginMove(deltaCounts, degPerSec)` — start a relative move; returns
  the delta actually used after quantum rounding.
- `hardStop()` — stop now and hold the current count.
- `moveLive()` — a built-in move is in flight on this wheel.
- `driven()` — the wheel is being driven by either path.

Boundary: no I2C, no timing, no engine knowledge. The kernel
(`diffdrive.*`) neither includes nor knows about it and stays
byte-identical to the vendored copy; a port that implements both
interfaces keeps the kernel out of the way with a move-live latch
(`src/DESIGN.md` §7).
