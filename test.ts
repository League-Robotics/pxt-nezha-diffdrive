// test.ts -- test programs in GENERATOR form (stakeholder direction,
// 2026-08-20): every move runs as an explicit startMove + driveTick()
// loop in THIS file -- no blocking move() wrappers -- so the tick loop
// is visible, instrumentable test code. The loop records the maximum
// inter-tick gap (ms) seen during the last test as a starvation
// diagnostic: a healthy loop ticks every ~24 ms; gaps far beyond that
// mean some other fiber stole the loop mid-move (the suspected cause
// of intermittent leg overshoot).
//
//   button A      / RUN:3  drive straight 80 cm
//   button B              alternate +-360 pivot
//   buttons A+B   / RUN:1  square tour (60 cm + 90 deg, x4)
//                   RUN:2  +360 pivot
//                   RUN:4  +180 pivot     RUN:5  -180 pivot
//                   RUN:6  world square tour via goToWorld()
//                   RUN:7  world square tour, curve computed here
//                   RUN:8  lever-arm calibration (8x45 pivot + leg)
//                   RUN:9  show last test's max tick gap [ms] on the LED
//                   RUN:10 log one world fix    RUN:11 gyro bias cal
//
// Hardware runs resolve the target micro:bit by name via mbdeploy.
// This project's test robot is vevov.
let touring = false
let maxGapMs = 0

function tickedMove(d: number, y: number) {
    diffDrive.startMove(d, y)
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGapMs) maxGapMs = now - last
        last = now
    }
}

function runSeg(d: number, y: number, reps: number) {
    if (touring) return
    touring = true
    // Tour profile (stakeholder, 2026-08-20): fast straights, slow
    // turns. Set inside the runner, where execution is guaranteed (a
    // top-level call was silently ineffective -- file-init order).
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(45)
    maxGapMs = 0
    diffDrive.resetPose()
    for (let i = 1; i <= reps; i++) {
        if (reps > 1) basic.showNumber(i)
        if (d != 0) tickedMove(d, 0)
        if (y != 0) tickedMove(0, y)
    }
    serial.writeLine("GAP:" + maxGapMs)
    basic.showString("OK")
    touring = false
}

let pivotCCW = true

input.onButtonPressed(Button.A, function () {
    runSeg(80, 0, 1)
})
input.onButtonPressed(Button.B, function () {
    runSeg(0, pivotCCW ? 360 : -360, 1)
    pivotCCW = !pivotCCW
})
input.onButtonPressed(Button.AB, function () {
    runSeg(60, 90, 4)
})

// ---- world-frame tours (OTOS) --------------------------------------
// The world sensor is consulted BETWEEN moves only; every move itself
// runs on encoder odometry. RUN:6 lets goToWorld() plan each leg;
// RUN:7 does the same job with the curve computed here in test code and
// issued as a single move() -- the contrast case. RUN:8 collects the
// lever-arm calibration data.

const CORNERS_X = [60, 60, 0, 0]
const CORNERS_Y = [0, 60, 60, 0]

function worldReady(): boolean {
    if (diffDrive.worldTrackingReady()) return true
    if (diffDrive.startWorldTracking()) return true
    serial.writeLine("OERR:no-otos")
    basic.showString("NO")
    return false
}

// Log a fix as OCAL:<tag>:<x 0.1mm>:<y 0.1mm>:<h cdeg>. Units are the
// shim's own, so the host tools never re-round what the device already
// rounded.
function logFix(tag: string) {
    diffDrive.readWorld()
    serial.writeLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}

function worldTour(useGoTo: boolean) {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(45)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        const tx = CORNERS_X[i]
        const ty = CORNERS_Y[i]
        if (useGoTo) {
            diffDrive.goToWorld(tx, ty)
        } else {
            // Same plan, computed here: one fix, one arc, one move.
            diffDrive.readWorld()
            const ph = diffDrive.worldHeading() * Math.PI / 180
            const dx = tx - diffDrive.worldX()
            const dy = ty - diffDrive.worldY()
            const bx = Math.cos(ph) * dx + Math.sin(ph) * dy
            const by = -Math.sin(ph) * dx + Math.cos(ph) * dy
            const theta = 2 * Math.atan2(by, bx)
            let s = bx
            if (Math.abs(by) >= 0.01) {
                s = (bx * bx + by * by) / (2 * by) * theta
            }
            tickedMove(s, theta * 180 / Math.PI)
        }
        logFix("c" + (i + 1))
    }
    serial.writeLine("GAP:" + maxGapMs)
    basic.showString("OK")
    touring = false
}

// Lever-arm calibration: with offsets zeroed, a pure pivot sweeps the
// SENSOR around the centre of rotation, so its reported track is a
// circle whose centre is the robot's centre and whose radius is the
// arm. Eight fixes around a full turn give the host tool a circle to
// fit; the straight leg afterwards gives the mounting yaw.
function leverCal() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setWorldSensorOffset(0, 0, 0)
    diffDrive.setDefaultSpeed(15)
    diffDrive.setDefaultYawRate(45)
    diffDrive.seedPose(0, 0, 0)
    serial.writeLine("OCAL:begin")
    logFix("p0")
    for (let i = 1; i <= 8; i++) {
        basic.showNumber(i)
        tickedMove(0, 45)
        basic.pause(400)      // let the wheels settle before the fix
        logFix("p" + i)
    }
    basic.showString("S")
    tickedMove(30, 0)         // 30 cm straight, for the mounting yaw
    basic.pause(400)
    logFix("s1")
    serial.writeLine("OCAL:end")
    basic.showString("OK")
    touring = false
}

diffDrive.onRunCommand(function (n: number) {
    if (n == 1) runSeg(60, 90, 4)
    else if (n == 2) runSeg(0, 360, 1)
    else if (n == 3) runSeg(80, 0, 1)
    else if (n == 4) runSeg(0, 180, 1)
    else if (n == 5) runSeg(0, -180, 1)
    else if (n == 6) worldTour(true)
    else if (n == 7) worldTour(false)
    else if (n == 8) leverCal()
    else if (n == 9) basic.showNumber(maxGapMs)
    else if (n == 10) logFix("now")
    else if (n == 11) diffDrive.calibrateWorldSensor()
})
