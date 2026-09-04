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
