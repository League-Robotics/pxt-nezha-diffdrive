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

// ---- turn accuracy-vs-speed sweep ----------------------------------
// A parameterised pivot, so the host can sweep angle against yaw rate.
// The rate is set first (RUN:57000+rate) and then the angle commanded
// (RUN:58360+deg), because one RUN value cannot carry both.
//
// Each turn reports its own view -- encoder differential, tick count,
// peak duty -- alongside whatever the overhead camera measured, so a
// disagreement between the two is visible rather than assumed. Peak
// duty is the saturation warning: once it pins at 10000 the commanded
// rate is beyond what the drivetrain can deliver and the result says
// more about the motors than about the controller.
let sweepRate = 45      // [deg/s]

function sweepTurn(deg: number) {
    if (touring) return
    touring = true
    diffDrive.setDefaultSpeed(15)
    diffDrive.setDefaultYawRate(sweepRate)
    const p0L = diffDrive.probe(10)
    const p0R = diffDrive.probe(11)
    let peak = 0
    let n = 0
    const t0 = control.millis()
    diffDrive.startMove(0, deg)
    while (diffDrive.driveTick()) {
        const dl = Math.abs(diffDrive.probe(12))
        const dr = Math.abs(diffDrive.probe(13))
        if (dl > peak) peak = dl
        if (dr > peak) peak = dr
        n++
    }
    const ms = control.millis() - t0
    const dL = diffDrive.probe(10) - p0L
    const dR = diffDrive.probe(11) - p0R
    // TRN:<commanded deg>:<rate deg/s>:<encoder diff counts>:<ticks>
    //     :<ms>:<peak duty x100>:<wrong-way aborts>
    diffDrive.emitLine("TRN:" + deg + ":" + sweepRate
        + ":" + Math.round((dR - dL) / 2) + ":" + n + ":" + ms
        + ":" + peak + ":" + diffDrive.probe(25))
    touring = false
}

let pivotCCW = true

// A = robot-relative tour, B = world tour, A+B = wheels tour.
// All three start on the NE orange dot facing west.
input.onButtonPressed(Button.A, function () {
    tourRobot()
})
input.onButtonPressed(Button.B, function () {
    worldTour(true)
})
input.onButtonPressed(Button.AB, function () {
    tourWheels()
})

// ---- world-frame tours (OTOS) --------------------------------------
// The world sensor is consulted BETWEEN moves only; every move itself
// runs on encoder odometry. RUN:6 lets goToWorld() plan each leg;
// RUN:7 does the same job with the curve computed here in test code and
// issued as a single move() -- the contrast case. RUN:8 collects the
// lever-arm calibration data.

// ---- the playfield's four orange dots -------------------------------
// From the AprilCam playfield map (main-playfield, A1-centred, +x east
// +y north): a 100 x 60 cm rectangle.
//   NW (-50, 30)   NE ( 50, 30)
//   SW (-50,-30)   SE ( 50,-30)
//
// Every tour STARTS ON THE NORTHEAST DOT FACING WEST and runs
// counter-clockwise, so each leg after the first turns LEFT:
//   NE -> NW (100 cm) -> SW (60) -> SE (100) -> NE (60)
const START_X = 50, START_Y = 30, START_H = 180   // [cm, cm, deg] west
const CORNERS_X = [-50, -50, 50, 50]
const CORNERS_Y = [30, -30, -30, 30]
const LEG_CM = [100, 60, 100, 60]

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
    // readWorld()'s return value used to be discarded, so a FAILED read
    // silently logged the previous (often zero) values -- indistiņguishable
    // from a real fix at the origin.
    if (!diffDrive.readWorld()) {
        diffDrive.emitLine("OERR:read-failed:" + tag)
    }
    diffDrive.emitLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}

// ---- tour 1 (button A): ROBOT-RELATIVE -----------------------------
// Each corner is named in the robot's OWN frame -- x forward, y left --
// so the tour never consults a world position at all. Encoder odometry
// only; the world sensor is read at each corner for SCORING.
//
// Turn-first is what makes "entirely to its left" a rectangle rather
// than a semicircle: a target at 90 deg bearing would otherwise be
// reached by a constant-curvature arc bulging 30 cm OUTSIDE the
// rectangle -- off the west edge of this playfield. Beyond 50 deg of
// bearing error the robot turns in place first, then drives straight.
function goToRobot(fwd: number, left: number) {
    const bearing = Math.atan2(left, fwd)          // [rad]
    if (Math.abs(bearing) >= 50 * Math.PI / 180) {
        tickedMove(0, bearing * 180 / Math.PI)     // turn in place
        tickedMove(Math.sqrt(fwd * fwd + left * left), 0)
        return
    }
    const theta = 2 * bearing
    if (Math.abs(left) < 0.01) {
        tickedMove(fwd, 0)                          // straight
    } else {
        tickedMove((fwd * fwd + left * left) / (2 * left) * theta,
            theta * 180 / Math.PI)
    }
}

function tourRobot() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(90)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=robot")
    logFix("c0")
    // Straight ahead first, then each next corner is entirely to the left.
    goToRobot(LEG_CM[0], 0)
    logFix("c1")
    for (let i = 1; i < 4; i++) {
        basic.showNumber(i + 1)
        goToRobot(0, LEG_CM[i])
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("A")
    touring = false
}

// ---- tour 3 (buttons A+B): WHEELS ----------------------------------
// The plain open-loop square: drive a leg, turn left 90, repeat.
// Nothing is consulted between moves; the world sensor is logged at
// each corner for SCORING only.
function tourWheels() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultSpeed(25)
    diffDrive.setDefaultYawRate(90)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=wheels")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        tickedMove(LEG_CM[i], 0)    // straight leg
        tickedMove(0, 90)           // then LEFT
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("W")
    touring = false
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
    diffDrive.setDefaultYawRate(90)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=" + (useGoTo ? "world" : "worldarc"))
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
    if (n == 1) tourWheels()      // superseded encoderTour
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
    // Seed/read round trip, no motion: seed the NE dot, wait, read back.
    else if (n == 34) {
        worldReady()
        diffDrive.seedPose(START_X, START_Y, START_H)
        diffDrive.emitLine("SEED:wrote:" + START_X + ":" + START_Y
            + ":" + START_H)
        basic.pause(300)
        const ok = diffDrive.readWorld()
        diffDrive.emitLine("SEED:read:" + (ok ? 1 : 0)
            + ":" + Math.round(diffDrive.worldX() * 100)
            + ":" + Math.round(diffDrive.worldY() * 100)
            + ":" + Math.round(diffDrive.worldHeading() * 100))
    }
    else if (n == 31) tourRobot()         // = button A
    else if (n == 32) worldTour(true)     // = button B
    else if (n == 33) tourWheels()        // = buttons A+B
    else if (n == 15) probedPivot(180)    // instrumented +180 (fails)
    else if (n == 16) probedPivot(-180)   // instrumented -180 (works)
    // Sweep control: set rate, then command an angle.
    else if (n >= 57001 && n <= 57600) sweepRate = n - 57000
    else if (n >= 58000 && n <= 58720) sweepTurn(n - 58360)
    else if (n >= 50000 && n <= 51000) armX = (n - 50500) / 10
    else if (n >= 52000 && n <= 53000) armY = (n - 52500) / 10
    else if (n >= 54000 && n <= 54360) armYaw = n - 54180
})
