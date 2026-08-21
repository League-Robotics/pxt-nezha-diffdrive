// test.ts -- the bench/playfield test programs.
//
// Three tours, all starting ON THE NORTHEAST ORANGE DOT FACING WEST and
// running counter-clockwise around the rectangle the four orange dots
// define (100 x 60 cm, from the AprilCam playfield map):
//
//     NE -> NW (100 cm) -> SW (60) -> SE (100) -> NE (60)
//
//   button A      RUN:tour:robot   robot-relative goTo, encoder only
//   button B      RUN:tour:world   goToWorld, OTOS-guided
//   buttons A+B   RUN:tour:wheels  open loop: leg, then turn left
//
// Other named commands: RUN:cal (lever-arm calibration; RUN:cal:1
// verifies it), RUN:fix, RUN:seed, RUN:probe, RUN:arm, RUN:gap.
//
// Every move runs as an explicit startMove + driveTick() loop in THIS
// file, so the tick loop stays visible, instrumentable test code.
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

// ---- the playfield's four orange dots -------------------------------
// A1-centred, +x east, +y north:
//   NW (-50, 30)   NE ( 50, 30)
//   SW (-50,-30)   SE ( 50,-30)
const START_X = 50
const START_Y = 30
const START_H = 180        // [deg] facing west
const CORNERS_X = [-50, -50, 50, 50]
const CORNERS_Y = [30, -30, -30, 30]
const LEG_CM = [100, 60, 100, 60]

// vevov's lever arm, MEASURED on the playfield 2026-08-20 (RUN:cal +
// tools/otos_levercal.py): eight 45 deg pivots swept the sensor around
// the centre of rotation on a 38.2 mm circle, fit residual rms 1.34 mm.
// The sensor sits 38.2 mm BEHIND the centre, within a millimetre of the
// centreline; the mounting yaw came from the 30 cm straight leg after.
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
        applyArm()          // begin() re-inits the chip; re-apply
        return true
    }
    diffDrive.emitLine("OERR:no-otos")
    basic.showString("NO")
    return false
}

// Log a fix as OCAL:<tag>:<x 0.01cm>:<y 0.01cm>:<h 0.01deg>.
function logFix(tag: string) {
    // A FAILED read used to log the previous (usually zero) values,
    // which is indistinguishable from a real fix at the origin.
    if (!diffDrive.readWorld()) {
        diffDrive.emitLine("OERR:read-failed:" + tag)
    }
    diffDrive.emitLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}

// Open-loop profile: every error is permanent, so keep the
// accuracy-tuned shaping. 40 cm/s -- 25 was a leftover from low-speed
// accuracy work, and the motors only reach 12-18% duty there.
function openLoopProfile() {
    diffDrive.setTaperWindows(400, 180)
    diffDrive.setTaperFloors(25, 12)
    diffDrive.setRampMs(400)
    diffDrive.setDefaultSpeed(40)
    diffDrive.setDefaultYawRate(90)
}

// ---- tour A: robot-relative -----------------------------------------
// Each corner is named in the robot's OWN frame -- x forward, y left --
// so this tour never consults a world position. Encoder odometry only.
//
// Turn-first is what makes "entirely to its left" a rectangle rather
// than a semicircle: a target at 90 deg bearing reached by a constant
// curvature arc bulges 30 cm OUTSIDE the rectangle, which on this
// playfield is past the west edge.
function goToRobot(fwd: number, left: number) {
    const bearing = Math.atan2(left, fwd)
    if (Math.abs(bearing) >= 50 * Math.PI / 180) {
        tickedMove(0, bearing * 180 / Math.PI)
        tickedMove(Math.sqrt(fwd * fwd + left * left), 0)
        return
    }
    const theta = 2 * bearing
    if (Math.abs(left) < 0.01) {
        tickedMove(fwd, 0)
    } else {
        tickedMove((fwd * fwd + left * left) / (2 * left) * theta,
            theta * 180 / Math.PI)
    }
}

function tourRobot() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    openLoopProfile()
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=robot")
    logFix("c0")
    goToRobot(LEG_CM[0], 0)          // straight ahead first
    logFix("c1")
    for (let i = 1; i < 4; i++) {
        basic.showNumber(i + 1)
        goToRobot(0, LEG_CM[i])      // then entirely to the left
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("A")
    touring = false
}

// ---- tour A+B: wheels -----------------------------------------------
function tourWheels() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    openLoopProfile()
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=wheels")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        tickedMove(LEG_CM[i], 0)     // straight leg
        tickedMove(0, 90)            // then LEFT
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("W")
    touring = false
}

// ---- tour B: world --------------------------------------------------
// The sensor is consulted BEFORE EVERY MOVE, so each leg is planned
// from where the robot actually is. The move itself still runs on
// encoder odometry; the sensor never steers it in flight.
function tourWorld() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    // FAST profile. This tour re-fixes before every leg, so a move only
    // has to land close and the next fix corrects it -- the shaping the
    // open-loop tours need buys this one nothing but seconds.
    diffDrive.setTaperWindows(120, 80)
    diffDrive.setTaperFloors(45, 35)
    diffDrive.setRampMs(180)
    diffDrive.setDefaultSpeed(60)
    diffDrive.setDefaultYawRate(150)
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=world")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        diffDrive.goToWorld(CORNERS_X[i], CORNERS_Y[i])
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("TOUR:end")
    basic.showString("B")
    touring = false
}

// ---- lever-arm calibration ------------------------------------------
// With the offsets zeroed a pure pivot sweeps the SENSOR around the
// centre of rotation, so its track is a circle: centre = the robot's
// centre, radius = the arm. verify=true repeats it with the measured
// arm applied, where a correct arm collapses the circle to a point.
function leverCal(verify: boolean) {
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
        basic.pause(400)          // let the wheels settle before the fix
        logFix("p" + i)
    }
    basic.showString("S")
    tickedMove(30, 0)             // 30 cm straight, for the mounting yaw
    basic.pause(400)
    logFix("s1")
    diffDrive.emitLine("OCAL:end")
    basic.showString("OK")
    touring = false
}

// ---- buttons --------------------------------------------------------
input.onButtonPressed(Button.A, function () {
    tourRobot()
})
input.onButtonPressed(Button.B, function () {
    tourWorld()
})
input.onButtonPressed(Button.AB, function () {
    tourWheels()
})

// ---- named run commands ---------------------------------------------
diffDrive.onRun("tour", function (arg: number) {
    const which = diffDrive.runArgText(0)
    if (which == "robot") tourRobot()
    else if (which == "world") tourWorld()
    else tourWheels()
})

diffDrive.onRun("cal", function (arg: number) {
    leverCal(arg != 0)
})

diffDrive.onRun("fix", function (arg: number) {
    logFix("now")
})

diffDrive.onRun("arm", function (arg: number) {
    applyArm()
})

diffDrive.onRun("probe", function (arg: number) {
    diffDrive.emitLine("OPROBE:" + diffDrive.otosBegin()
        + ":" + diffDrive.otosGet(7))
})

diffDrive.onRun("gap", function (arg: number) {
    diffDrive.emitLine("GAP:" + maxGapMs)
})

diffDrive.onRun("seed", function (arg: number) {
    worldReady()
    diffDrive.seedPose(START_X, START_Y, START_H)
    basic.pause(300)
    const ok = diffDrive.readWorld()
    diffDrive.emitLine("SEED:read:" + (ok ? 1 : 0)
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
})
