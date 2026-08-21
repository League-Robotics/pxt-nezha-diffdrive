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
//   buttons A+B   / RUN:1  encoder-only square tour (60 cm x4) --
//                          the control case: nothing is consulted
//                          between moves; the world sensor is logged
//                          at each corner for SCORING only
//                   RUN:2  +360 pivot
//                   RUN:4  +180 pivot     RUN:5  -180 pivot
//                   RUN:6  OTOS-guided tour, planned by goToWorld()
//                   RUN:7  OTOS-guided tour, arc computed in this file
//                          (both consult the sensor before EVERY move)
//                   RUN:8  lever-arm calibration (8x45 pivot + leg)
//                   RUN:13 apply lever arm   RUN:14 verify lever arm
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
    diffDrive.emitLine("GAP:" + maxGapMs)
    basic.showString("OK")
    touring = false
}

// ---- instrumented pivot (positive-pivot fault) ----------------------
// Records the drive's own state EVERY TICK during one pivot, then dumps
// it after the move. Sampling on-device rather than polling from the
// host is not a style choice: a request/reply round-trip inside a move
// over the wireless link is measured to be actively dangerous (a
// 197.5 mm leg collapsed to 0.3 mm), and the host cannot see per-tick
// state any other way.
//
// This distinguishes the three candidate explanations for a pivot that
// produces ZERO encoder counts:
//   duty stays 0        -> nothing was ever commanded (move engine)
//   duty non-zero, pos flat -> commanded but the wheels did not turn,
//                              or the encoders are frozen (check wsus)
//   pos moves            -> the wheels did turn and something else lied
function probedPivot(yaw: number) {
    if (touring) return
    touring = true
    diffDrive.setDefaultSpeed(15)
    diffDrive.setDefaultYawRate(45)
    const dl: number[] = [], dr: number[] = []
    const pl: number[] = [], pr: number[] = [], ws: number[] = []
    diffDrive.startMove(0, yaw)
    let n = 0
    while (diffDrive.driveTick()) {
        if (n < 200) {
            dl.push(diffDrive.probe(12))   // applied duty x100
            dr.push(diffDrive.probe(13))
            pl.push(diffDrive.probe(10))   // encoder position
            pr.push(diffDrive.probe(11))
            ws.push(diffDrive.probe(6) + 2 * diffDrive.probe(7))
            n++
        }
    }
    diffDrive.emitLine("PRB:begin:" + yaw + ":" + n)
    for (let i = 0; i < n; i++) {
        diffDrive.emitLine("PRB:" + i + ":" + dl[i] + ":" + dr[i]
            + ":" + pl[i] + ":" + pr[i] + ":" + ws[i])
    }
    diffDrive.emitLine("PRB:end")
    basic.showString("P")
    touring = false
}

// ---- encoder-only tour (the control case) --------------------------
// Navigates entirely on wheel odometry: four fixed 60 cm legs and four
// fixed 90 deg turns, with NOTHING consulted in between. The world
// sensor is read at each corner but ONLY to record where the robot
// really ended up -- that reading never reaches the controller. This
// is the baseline the OTOS-guided tour is measured against, and both
// tours are scored the same way, by the same sensor.
function encoderTour() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(45)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("TOUR:encoder")
    logFix("c0")
    for (let i = 1; i <= 4; i++) {
        basic.showNumber(i)
        tickedMove(60, 0)
        tickedMove(0, 90)
        logFix("c" + i)     // measurement only -- never used to steer
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
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
    encoderTour()
})

// ---- world-frame tours (OTOS) --------------------------------------
// The world sensor is consulted BETWEEN moves only; every move itself
// runs on encoder odometry. RUN:6 lets goToWorld() plan each leg;
// RUN:7 does the same job with the curve computed here in test code and
// issued as a single move() -- the contrast case. RUN:8 collects the
// lever-arm calibration data.

const CORNERS_X = [60, 60, 0, 0]
const CORNERS_Y = [0, 60, 60, 0]

// vevov's lever arm, MEASURED on the playfield 2026-08-20 by RUN:8 +
// tools/otos_levercal.py: eight 45 deg pivots swept the sensor around
// the centre of rotation on a 38.2 mm circle (fit residual rms 1.34 mm,
// max 2.91). The sensor sits 38.2 mm BEHIND the centre of rotation,
// within a millimetre of the centreline. The mounting yaw came from
// the 30 cm straight leg that follows: course 32.0 deg vs a reported
// heading of 31.1.
let armX = -3.82      // [cm] +forward
let armY = -0.07      // [cm] +left
let armYaw = 0.89     // [deg]

function applyArm() {
    diffDrive.setWorldSensorOffset(armX, armY, armYaw)
    diffDrive.emitLine("ARM:" + Math.round(armX * 100)
        + ":" + Math.round(armY * 100) + ":" + Math.round(armYaw * 100))
}

function worldReady(): boolean {
    if (diffDrive.worldTrackingReady()) return true
    if (diffDrive.startWorldTracking()) {
        applyArm()      // the chip is re-inited on begin(); re-apply
        return true
    }
    diffDrive.emitLine("OERR:no-otos")
    basic.showString("NO")
    return false
}

// Log a fix as OCAL:<tag>:<x 0.1mm>:<y 0.1mm>:<h cdeg>. Units are the
// shim's own, so the host tools never re-round what the device already
// rounded.
function logFix(tag: string) {
    diffDrive.readWorld()
    diffDrive.emitLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}

// ---- OTOS-guided tour ----------------------------------------------
// The same square, but the sensor is consulted BEFORE EVERY MOVE: each
// leg is planned from where the robot actually is, not from where the
// previous leg was supposed to have left it. The move itself still runs
// purely on encoder odometry -- the sensor never steers it in flight.
//
// useGoTo picks who does the planning: goToWorld() in the library
// (which will also pivot first past a 50 deg bearing error, and nudge
// if it lands outside tolerance), or the explicit one-fix-one-arc
// computation right here in test code.
function worldTour(useGoTo: boolean) {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(45)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("TOUR:" + (useGoTo ? "goto" : "move"))
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        const tx = CORNERS_X[i]
        const ty = CORNERS_Y[i]
        if (useGoTo) {
            diffDrive.goToWorld(tx, ty)
        } else {
            // Consult the sensor, then commit to one arc.
            diffDrive.readWorld()
            const ph = diffDrive.worldHeading() * Math.PI / 180
            const dx = tx - diffDrive.worldX()
            const dy = ty - diffDrive.worldY()
            const bx = Math.cos(ph) * dx + Math.sin(ph) * dy
            const by = -Math.sin(ph) * dx + Math.cos(ph) * dy
            const bearing = Math.atan2(by, bx)
            // Turn-first when the target is badly off-bearing: an arc
            // to a point behind the robot is a huge useless loop.
            if (Math.abs(bearing) >= 50 * Math.PI / 180) {
                tickedMove(0, bearing * 180 / Math.PI)
                diffDrive.readWorld()          // re-fix before driving
                const ph2 = diffDrive.worldHeading() * Math.PI / 180
                const dx2 = tx - diffDrive.worldX()
                const dy2 = ty - diffDrive.worldY()
                const bx2 = Math.cos(ph2) * dx2 + Math.sin(ph2) * dy2
                const by2 = -Math.sin(ph2) * dx2 + Math.cos(ph2) * dy2
                tickedMove(arcLen(bx2, by2), 2 * Math.atan2(by2, bx2)
                    * 180 / Math.PI)
            } else {
                tickedMove(arcLen(bx, by), 2 * bearing * 180 / Math.PI)
            }
        }
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("OK")
    touring = false
}

// Arc length of the constant-curvature path from the robot's origin,
// heading along +x, through the body-frame point (bx, by).
function arcLen(bx: number, by: number): number {
    if (Math.abs(by) < 0.01) return bx          // straight
    return (bx * bx + by * by) / (2 * by) * (2 * Math.atan2(by, bx))
}

// Lever-arm calibration: with offsets zeroed, a pure pivot sweeps the
// SENSOR around the centre of rotation, so its reported track is a
// circle whose centre is the robot's centre and whose radius is the
// arm. Eight fixes around a full turn give the host tool a circle to
// fit; the straight leg afterwards gives the mounting yaw.
// verify=true runs the identical sweep with the MEASURED arm applied
// instead of zeroed. A correct arm collapses the circle to a point:
// re-fitting the verify run must return an arm near zero, and the
// reported centre must hold still through the whole turn. That is the
// same check the reference project used to catch its double-corrected
// arm (a pure pivot traced a 42.7 mm circle instead of holding still).
function leverCal(verify: boolean = false) {
    if (touring) return
    if (!worldReady()) return
    touring = true
    if (verify) applyArm()
    else diffDrive.setWorldSensorOffset(0, 0, 0)
    diffDrive.setDefaultSpeed(15)
    diffDrive.setDefaultYawRate(45)
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("OCAL:begin")
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
    diffDrive.emitLine("OCAL:end")
    basic.showString("OK")
    touring = false
}

diffDrive.onRunCommand(function (n: number) {
    if (n == 1) encoderTour()
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
    // Probe: report the sensor's product id (0x5F = 95 when present)
    // and its connected flag, WITHOUT moving the robot. A fix of
    // 0:0:0 is otherwise ambiguous -- genuinely at origin, or never
    // started.
    else if (n == 12) {
        const id = diffDrive.otosBegin()
        diffDrive.emitLine("OPROBE:" + id + ":" + diffDrive.otosGet(7))
    }
    // Set the lever arm LIVE, so a re-calibration does not need a
    // reflash -- flashing needs USB, USB only reaches the bench stand,
    // and the calibration only works on the floor. Encoded signed:
    // 50500+mm for x, 52500+mm for y, 54180+deg for yaw, then RUN:13
    // applies and echoes them.
    else if (n == 13) applyArm()
    else if (n == 14) leverCal(true)      // verify the measured arm
    else if (n == 15) probedPivot(180)    // instrumented +180 (fails)
    else if (n == 16) probedPivot(-180)   // instrumented -180 (works)
    else if (n >= 50000 && n <= 51000) armX = (n - 50500) / 10
    else if (n >= 52000 && n <= 53000) armY = (n - 52500) / 10
    else if (n >= 54000 && n <= 54360) armYaw = n - 54180
})
