# src/core — control kernel and host-portable helper headers

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The chassis-agnostic control kernel (`diffdrive.h/.cpp`,
`DiffDrive::DifferentialDrive`) plus two small host-portable helper
headers used by the platform layer: `heading_wrap.h` (OTOS heading
unwrap) and `encoder_glitch_armor.h` (encoder implausible-jump
arbitration). Per the layer map, everything here compiles with libc
only — no I2C, no CODAL, no MakeCode, no geometry.

Detail (the kernel's tick model, encoder-servo loop, and API) lives in
[`src/DESIGN.md`](../DESIGN.md) §2; the two helper headers' one-line
contracts are in §1's layer map table, and `encoder_glitch_armor.h`'s
consumer (`NezhaMotorPort::collect()`) is described in §7. This file
does not duplicate that content — it exists so `ls src/core/` points
somewhere.
