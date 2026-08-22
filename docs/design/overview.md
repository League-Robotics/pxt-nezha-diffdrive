# DiffDrive — Overview

## What it is

DiffDrive is a MakeCode extension for PXT/micro:bit that gives the
ElecFreaks Nezha brick's two-wheel differential drive **closed-loop**
control from student-facing blocks. An encoder-servoed wheel-speed
controller (the "DiffDrive kernel") runs continuously in its own fiber
on the micro:bit at a 24 ms cadence; every drive/move/pose block just
talks to it.

## Why it exists

Open-loop duty control on this hardware means "turn the motor on X%" —
speed and distance drift with battery level, load, and per-motor
variation, and there's no way to know where the robot actually is.
DiffDrive closes the loop: wheel speeds are measured from encoders and
corrected every cycle, so a commanded straight line stays straight, a
commanded distance lands on the encoder, and the robot's pose
`(x, y, heading)` is always available from odometry — without the
student writing any control code themselves.

## Who uses it and how

Students and teachers building programs in MakeCode for micro:bit.
Installed as an extension by pasting the repo URL
(`https://github.com/League-Robotics/pxt-nezha-diffdrive`) into the
Extensions dialog. From there, the `DiffDrive` block category exposes:

- **Drive** — continuous velocity commands (`set wheel speeds`,
  `drive ... turning ...`) and stopping (`stop`, `emergency stop`).
- **Move** — position-mode moves that travel a distance and/or turn an
  angle, or curve to a point, either blocking (`move`, `go to`),
  non-blocking with polling (`start move`, `moving?`, `stop move`), or
  as a loop that runs student code every tick during the move
  (`while moving`, `while going to`).
- **Pose** — read back `(x, y, heading)` at any time, or reset it.
- **Setup** — calibrate track width and wheel travel for a chassis
  that differs from the reference kit, set default move speed/turn
  rate, and (advanced) reach into individual kernel tuning parameters
  through a config escape hatch.

Programs run identically in the browser simulator (against a
lightweight kinematic stand-in) and on real hardware (against the real
closed-loop kernel), so students can develop without a physical robot
in hand.

## How it's built

Three layers, cleanly separated:

1. **Kernel** (`diffdrive.h`/`.cpp`) — a platform-agnostic closed-loop
   wheel-speed controller: PID + feedforward, per-wheel correction
   curves, adaptive bias, stall/deficit/wedge fault detection, lease-
   based command expiry, e-stop. It knows nothing about I2C, encoders
   counts vs. mm, or MakeCode — it talks to four small ports it
   defines itself (`Motor`, `Clock`, `Sleeper`, `FiberLauncher`).
2. **Ports** (`nezha_port.h`/`.cpp`, `platform_ports.h`) — this
   package's implementations of those ports for the Nezha brick over
   I2C and for the CODAL runtime underneath MakeCode/micro:bit,
   including an anti-latch write-shaping pipeline that guards several
   measured hardware failure modes of the brick.
3. **Shim + blocks** (`src/shims.cpp`, `src/main.ts`) — composes the kernel and
   ports into a lazily-initialized rig, adds odometry (dead-reckoning
   from encoder counts, since the kernel itself has no chassis
   geometry) and a position-mode move engine, and exposes it all as
   cm/deg student-facing MakeCode blocks.

## Provenance

The kernel is vendored from the
[radio-robot](https://github.com/League-Robotics/radio-robot) firmware
and is maintained there — this repo carries the MakeCode packaging on
top of it. The Nezha motor port is a faithful reduction of that
firmware's battle-tested anti-latch motor leaf. See
`specification.md` §12 for the maintenance boundary (what's edited
here vs. upstream) and a path discrepancy worth resolving between the
README and the source comments.

## Status

v1.0.0, working, shipping as a GitHub-hosted MakeCode extension.
Versioned to intentionally outrank the firmware's own
`0.YYYYMMDD.n` tag scheme.

This overview is additive context, not a replacement for
`specification.md`, which is the authoritative, complete reference for
the block API, the kernel's control behavior, and the hardware
integration.
