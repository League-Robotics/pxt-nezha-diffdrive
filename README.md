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
internally — you don't supply the loop for those; they keep driving on
their own until the block returns, exactly as before. (For the two loop
forms, "internally" still means *on your fiber* — see "Keep the loop
body quick" below.)

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

### Keep the loop body quick

The tick source is a *fiber*, not a thread, and it is the one your code
runs on. Whatever you put inside a `while (diffDrive.driveTick())` loop
or a `whileMoving`/`whileGoingTo` handler runs between two ticks — so a
blocking call in there stops the ticking as surely as exiting the loop
does, and the starvation watchdog above stops the robot. For the loop
forms it also **ends the move**, so `driveTick()` returns false and the
loop exits. The usual symptom: "my loop quits as soon as my sensor
fires." The sensor is fine; the blocking call in that branch is not.

The common culprits are the display and sound blocks, which pause after
drawing. Most take an interval you can set to `0`:

```js
basic.showIcon(IconNames.Heart)      // pauses 600 ms -- kills the move
basic.showIcon(IconNames.Heart, 0)   // draws and returns -- fine
```

`basic.showLeds` (400 ms) takes the same argument, and `<image>.plotImage()`
is the no-interval draw `showIcon` is built on.

`basic.showString` is different: its interval is a *scroll speed*
(150 ms per character), not a one-shot pause, so there's no value that
makes it non-blocking — the whole scroll blocks. `basic.showNumber` is
`showString` underneath and behaves the same way, so passing `0` does
not rescue it either. Show text and numbers outside the loop.

`basic.pause` and `music.playTone` block for as long as you asked them
to. `basic.clearScreen`, `led.plot`/`unplot`, pin reads and I2C sensor
reads all return immediately and are fine.

(Intervals above are read from the vendored pxt core —
`pxt_modules/core/icons.ts`, `core/basic.ts`, `core/shims.d.ts` — not
measured on hardware.)

When something really does have to block, set a variable in the loop and
do the slow part on another fiber — fibers are cooperative, so a pause
over there yields to the tick loop instead of stalling it:

```js
let sawLine = false
control.inBackground(function () {
    while (true) {
        if (sawLine) { basic.showIcon(IconNames.Heart) }
        else { basic.clearScreen() }
        basic.pause(50)
    }
})
diffDrive.whileMoving(100, 0, function (x, y, heading) {
    sawLine = PlanetX_Basic.TrackbitChannelState(
        PlanetX_Basic.TrackbitChannel.One,
        PlanetX_Basic.TrackbitType.State_0)
})
```

Two rules for that second fiber: don't let it tick the drive too (no
`driveTick()`, no move blocks, no `startDrive()`), and keep the world-
sensor blocks out of it — both are bus-ownership conflicts with the
ticking loop.

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
master. To cut a release, `dotconfig version bump --major 1` then
`python3 tools/publish_extension.py --sync-version` — `config/dotconfig.yaml`
is the single source of truth and `pxt.json` mirrors it. See
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
