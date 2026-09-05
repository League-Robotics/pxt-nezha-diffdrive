# src/platform — hardware ports

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The hardware port implementations: `NezhaMotorPort` (`nezha_port.*`,
motor + encoder over I2C 0x10), `OtosPort` (`otos_port.*`, the optical
world sensor), `platform_ports.h` (the port interfaces they implement),
and `encoder_pose_source.h` (the host-portable dead-reckoning
`PoseSource` fallback `goToW()` uses on OTOS-less robots). Everything
here is CODAL/`pxt.h`-bound except `encoder_pose_source.h`, which is
host-portable (only `motion_engine.h` + libc).

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §7. This file does not
duplicate that content — it exists so `ls src/platform/` points
somewhere.
