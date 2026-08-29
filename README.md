# DiffDrive — closed-loop differential drive for micro:bit + Nezha

MakeCode extension for PXT/microbit. Drives the ElecFreaks Nezha
brick's two-wheel differential drive **closed loop**: an encoder-servoed
wheel-speed controller (the DiffDrive kernel) runs at a 24 ms cadence.
Position-mode blocks (`move`, `goTo`, `whileMoving`, `whileGoingTo`)
keep it ticking for you; continuous-mode commands (`setWheelSpeeds`,
`driveTwist`) need your own `while (diffDrive.driveTick())` loop to
keep it ticking — see "The tick contract" below.

Unlike open-loop duty control, wheel speeds are measured and corrected
continuously — straight means straight, distances land on the encoder,
and the robot's pose (x, y, heading) is always available from odometry.

## Use as Extension

In [MakeCode for micro:bit](https://makecode.microbit.org/), open a
project, click the gear menu → **Extensions**, and paste this repo's
URL:

```
https://github.com/League-Microbit/pxt-diff-drive
```

That repository is generated from this one — see "Publishing" below.

## Blocks / JavaScript

```js
// velocity commands — continuous mode: keep the robot moving by
// ticking the control loop yourself (see "The tick contract" below)
diffDrive.setWheelSpeeds(15, 15)     // cm/s per wheel
diffDrive.driveTwist(15, 45)         // cm/s forward, deg/s CCW
while (diffDrive.driveTick()) {
    // your code here; leaving the loop lets the robot coast to a stop
    if (input.buttonIsPressed(Button.A)) diffDrive.stop()
}

// position moves — blocking
diffDrive.move(20, 0)                // 20 cm straight
diffDrive.move(0, 90)                // pivot 90 degrees CCW
diffDrive.goTo(30, 20)               // curved path to a point
                                     // (x forward, y left, robot frame)

// loop form — your code runs DURING the move; leaving the loop ends it
diffDrive.whileMoving(50, 0, function (x, y, heading) {
    if (input.buttonIsPressed(Button.A)) diffDrive.stopMove()
})

// pose
diffDrive.poseX(); diffDrive.poseY(); diffDrive.heading()
diffDrive.resetPose()

// stopping
diffDrive.stop()
diffDrive.emergencyStop()
```

The continuous-mode example above (`setWheelSpeeds`/`driveTwist` +
`while (diffDrive.driveTick())`) is pinned against silent regression by
`tests/host/test_continuous_drive_command_looks_active.py`, which
proves the condition `driveTick()`'s return value depends on to keep
that loop running instead of exiting on its first iteration.

Defaults are tuned for the standard Nezha kit; adjust with the Setup
blocks (`set track width`, `set wheel calibration`, `set default
speed`, and the advanced `set config` escape hatch).

## The tick contract

The robot only moves while something keeps ticking its control loop.
`move`, `goTo`, `whileMoving`, and `whileGoingTo` already tick
internally — nothing changes for those; they keep driving on their own
until the block returns, exactly as before.

`setWheelSpeeds` and `driveTwist` are different: they're continuous-
mode commands, and starting one is not enough to keep the robot
moving. Follow it with a `while (diffDrive.driveTick())` loop:

```js
diffDrive.setWheelSpeeds(15, 15)   // or driveTwist(...)
while (diffDrive.driveTick()) {
    // runs once per ~24 ms control cycle -- read a sensor, check a
    // button, whatever your program needs. Don't add your own
    // pause() here; driveTick() already paces itself.
    if (input.buttonIsPressed(Button.A)) diffDrive.stop()
}
```

This exact idiom is pinned against regression the same way:
`tests/host/test_continuous_drive_command_looks_active.py` proves the
`appliedDuty`/move-active condition `driveTick()` reports holds true
here (and reads false once a stop actually lands), so docs and code
cannot silently diverge on this contract again.

This is a breaking change from earlier versions of this extension,
where a background fiber ticked the drive for you regardless of what
your code was doing. Now the caller — your loop — is the tick source.

If nothing ticks the loop — it exits, your program pauses, a button
handler returns — a starvation watchdog stops the robot for you,
within about 150 ms. It's a safety net, not an emergency stop: it
doesn't latch, and there's nothing to clear — a fresh `move()` or
`driveTick()` loop resumes driving right away.

See `test/test.ts` for a worked example: button A drives a square with the
blocking `move()` block; button B drives the same square with
`startMove()` + `while (diffDrive.driveTick())` per leg, plus a live
LED readout in the loop body.

## Wiring assumptions

Left wheel on M2 (mirrored), right wheel on M1 — the standard two-motor
chassis. The motor ports and directions are compile-time defaults in
`src/shims.cpp`.

## Local development

Working on the extension itself (blocks, `sim.ts`, the toolbox layout)?
See [`docs/local-editor.md`](docs/local-editor.md) for serving a local
MakeCode editor against this repo, seeing it as a disk project, and
building/flashing a plain V2 hex instead of the editor's own Download.

## Publishing

The extension students install is the small subset of this repo that
`pxt.json`'s `files` list names, plus the `extension/` overlay (its own
README, LICENSE, sample `test.ts`, build check). `tools/publish_extension.py`
assembles that tree and pushes it to
[League-Microbit/pxt-diff-drive](https://github.com/League-Microbit/pxt-diff-drive),
tagging `v<version>` from `pxt.json` when that tag is new;
`.github/workflows/publish-extension.yml` runs it on every push to
master. Bump `version` in `pxt.json` to cut a release. See
[`extension/DESIGN.md`](extension/DESIGN.md).

## Provenance

The wheel kernel is vendored from the
[radio-robot](https://github.com/League-Robotics/radio-robot) firmware
(`src/firm/diffdrive/`, comments stripped for size) and is maintained
there; this repo carries the MakeCode packaging. The Nezha motor port
is a faithful reduction of that firmware's anti-latch motor leaf.

## Supported targets

* for PXT/microbit

(The metadata above is needed for package cataloging.)

## License

MIT
