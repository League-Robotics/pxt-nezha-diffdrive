# src/platform — hardware ports

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The hardware port implementations: `NezhaMotorPort` (`nezha_port.*`,
motor + encoder over I2C 0x10), `OtosPort` (`otos_port.*`, the optical
world sensor), and `platform_ports.h` (the port interfaces they
implement). Everything here is CODAL/`pxt.h`-bound.

Sprint 033 removed this directory's one host-portable file,
`encoder_pose_source.h` — the dead-reckoning `PoseSource` fallback
`goToW()` uses on OTOS-less robots is now `Odometry`
(`../motion/odometry.h`), which computes the pose it reports instead of
adapting fields someone else computed, and lives with the rest of the
motion layer.

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §7. This file does not
duplicate that content — it exists so `ls src/platform/` points
somewhere.
