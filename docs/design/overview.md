# DiffDrive — Overview

## What it is

DiffDrive is a MakeCode extension for PXT/micro:bit that gives the
ElecFreaks Nezha brick's two-wheel differential drive **closed-loop**
control from student-facing blocks. An encoder-servoed wheel-speed
controller (the "DiffDrive kernel") steps at a 24 ms cadence on
whichever fiber ticks it — blocking moves tick internally, continuous
driving runs a `driveTick()` loop, and a starvation-watchdog fiber
stops the robot within ~150 ms if the ticking caller disappears (the
"tick model", since sprint 002); every drive/move/pose block just
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
- **World** — the OTOS optical world sensor (start tracking, seed the
  world pose, read fixes, `go to world x y`), consulted at move
  boundaries only.
- **Setup** — calibrate track width and wheel travel for a chassis
  that differs from the reference kit, set default move speed/turn
  rate, and (advanced) reach into individual kernel tuning parameters
  through a config escape hatch.

Programs run identically in the browser simulator (against a
lightweight kinematic stand-in) and on real hardware (against the real
closed-loop kernel), so students can develop without a physical robot
in hand.

## How it's built

Layers, cleanly separated (the full breakdown is in
`../../src/DESIGN.md`):

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
3. **Motion engine** (`motion_engine.h`/`.cpp`) — chassis geometry
   and the two-primitive motion reduction (constant-ratio wheel
   segments) plus the move engine's taper/ramp/deadline shaping;
   host-portable, shared by the blocks and the wire protocol
   (extracted from the shim layer in sprint 003).
4. **Wire protocol** (`wire_handler.*`, `wire_adapter.*`,
   `protocol.*`, `serial_transport.*`, `radio_transport.*`) — the
   protocol-v6 ASCII line grammar with its ack/nack reliability
   layer, dispatched over USB serial (radio RX is a RUN-only
   carve-out), added in sprint 003 replacing the binary v5 wire.
5. **Shim + blocks** (`src/shims.cpp`, `src/main.ts`) — composes the kernel and
   ports into a lazily-initialized rig, adds odometry (dead-reckoning
   from encoder counts, since the kernel itself has no chassis
   geometry), the tick engine and starvation watchdog, and the OTOS
   world-sensor surface, and exposes it all as cm/deg student-facing
   MakeCode blocks.

## Provenance

The kernel is vendored from the
[radio-robot](https://github.com/League-Robotics/radio-robot) firmware,
currently at `src/firm/diffdrive/`, and is maintained there — this repo
carries the MakeCode packaging on top of it. The Nezha motor port is a
faithful reduction of that firmware's battle-tested anti-latch motor
leaf. See `src/DESIGN.md` §2 for the current path, upstream repo, and
maintenance boundary — the one authoritative place those details live,
rather than restated independently here and in `specification.md` §12.

## Status

v1.0.10, working, shipping as a GitHub-hosted MakeCode extension.
Versioned to intentionally outrank the firmware's own
`0.YYYYMMDD.n` tag scheme. Code reflects work through sprint 003
(protocol v6, motion API, host test harness); sprints 004/005
(telemetry frames, radio command plane) are planned, not built.

This overview is additive context, not a replacement for
`specification.md`, which is the authoritative, complete reference for
the block API, the kernel's control behavior, and the hardware
integration.
