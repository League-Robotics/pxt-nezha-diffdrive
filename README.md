# DiffDrive — closed-loop differential drive for micro:bit + Nezha

MakeCode extension for PXT/microbit. Drives the ElecFreaks Nezha
brick's two-wheel differential drive **closed loop**: an encoder-servoed
wheel-speed controller (the DiffDrive kernel) runs in its own fiber on
the micro:bit at a 24 ms cadence, and every block talks to it.

Unlike open-loop duty control, wheel speeds are measured and corrected
continuously — straight means straight, distances land on the encoder,
and the robot's pose (x, y, heading) is always available from odometry.

## Blocks / JavaScript

```js
// velocity commands — run until superseded or stopped
diffDrive.setWheelSpeeds(15, 15)     // cm/s per wheel
diffDrive.driveTwist(15, 45)         // cm/s forward, deg/s CCW

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

Defaults are tuned for the standard Nezha kit; adjust with the Setup
blocks (`set track width`, `set wheel calibration`, `set default
speed`, and the advanced `set config` escape hatch).

## Wiring assumptions

Left wheel on M2 (mirrored), right wheel on M1 — the standard two-motor
chassis. The motor ports and directions are compile-time defaults in
`shims.cpp`.

## Provenance

The wheel kernel is vendored from the
[radio-robot](https://github.com/Busboombot/radio-robot) firmware
(`src/firm/diffdrive/`, comments stripped for size) and is maintained
there; this branch carries the MakeCode packaging. The Nezha motor port
is a faithful reduction of that firmware's anti-latch motor leaf.

## Supported targets

* for PXT/microbit

(The metadata above is needed for package cataloging.)

## License

MIT
