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
// verifies it), RUN:fix, RUN:seed, RUN:probe, RUN:arm, RUN:gap,
// RUN:pivot:<deg> (relative in-place pivot, encoder/gyro only -- no
// OTOS), RUN:turnrate:<deg/s> (sets the yaw rate the NEXT RUN:pivot
// uses).
//
// Every move runs as an explicit startMove/startGoTo + driveTick() loop
// in THIS file, so the tick loop stays visible, instrumentable test
// code.
let touring = false
let maxGapMs = 0
// The yaw rate the NEXT RUN:pivot uses -- set by RUN:turnrate, so
// turn_sweep.py's rate-then-angle two-step (RUN:turnrate:<rate> then
// RUN:pivot:<deg>) mirrors its old two-RUN-command shape. RUN:pivot
// always applies this explicitly (never leaves it at whatever an
// unrelated handler last set), so a bare RUN:pivot with no preceding
// RUN:turnrate is still deterministic.
let pivotYawRate = 90

// Tick driveTick() to completion on this fiber, tracking the largest
// gap between calls (maxGapMs) -- the shared runner behind
// tickedMove/tickedGoTo below, so the tick loop itself is written once.
function tickToCompletion() {
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGapMs) maxGapMs = now - last
        last = now
    }
}

function tickedMove(d: number, y: number) {
    diffDrive.startMove(d, y)
    tickToCompletion()
}

// goTo-shaped sibling of tickedMove: startGoTo() only ARMS the move
// (see its own doc comment in motion.ts) -- something must still tick
// it on this fiber to make it progress.
function tickedGoTo(x: number, y: number) {
    diffDrive.startGoTo(x, y)
    tickToCompletion()
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

let armApplied = false

function applyArm() {
    diffDrive.setWorldSensorOffset(armX, armY, armYaw)
    armApplied = true
    diffDrive.emitLine("ARM:" + Math.round(armX * 100)
        + ":" + Math.round(armY * 100) + ":" + Math.round(armYaw * 100))
}

function worldReady(): boolean {
    // MEASURED BUG, vevov 2026-08-25: this fast path used to `return
    // true` outright. worldTrackingReady() only asks "is the chip
    // answering" (otosGet(7) -> connected_), and ANY earlier
    // otosBegin() -- RUN:probe is enough -- makes it true. So the very
    // first worldReady() after a probe short-circuited here and the
    // lever arm was NEVER applied, silently, for the whole session.
    //
    // The sensor then reports the SENSOR's path, not the centre's, so
    // every in-place pivot injects a phantom translation of
    // 2 * 38.2mm * sin(theta/2) into the world pose. Measured against
    // overhead-camera truth: an 84 deg pivot with no arm reported
    // 52 mm of travel while the robot physically moved 2.5 mm. With the
    // arm applied, an identical 90 deg pivot reported 1.2 mm and agreed
    // with the camera to 2.1 mm. Four corners per tour turned that into
    // a 58 mm closure error that the robot itself scored as 22 mm.
    //
    // armApplied (not the chip's state) is the guard: otosBegin() does
    // NOT clear OtosPort's offsetX_/offsetY_/offsetYaw_ members, so
    // once applied the arm survives a re-begin; the flag only stops
    // this from re-emitting the ARM: line on every call.
    if (diffDrive.worldTrackingReady()) {
        if (!armApplied) applyArm()
        return true
    }
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
    // A failed read is logged explicitly: silence would be
    // indistinguishable from a real fix at the origin.
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
    diffDrive.setDefaultSpeed(20)
    diffDrive.setDefaultYawRate(90)
}

// ---- tour A: robot-relative -----------------------------------------
// "Robot-relative" means the tour never needs a WORLD position -- the
// rectangle is expressed in a frame anchored where the robot started,
// where its own position begins at (0,0). It does NOT mean flying
// blind: heading comes from the IMU every leg, because a gyro heading
// is far better than one differenced out of wheel encoders, and a
// heading error is what rotates an entire rectangle.
//
// Every leg is planned as ONE body twist from the CURRENT pose and the
// CURRENT measured heading. A few degrees of residual after a turn is
// never corrected with another turn -- it is absorbed by curving to
// the destination, which costs nothing and avoids the settle time and
// overshoot of a second pivot.
const RTX = [100, 100, 0, 0]     // [cm] corners in the start frame
const RTY = [0, 60, 60, 0]       // x forward, y left

function legToward(tx: number, ty: number) {
    // Plan from where we ACTUALLY are: encoder position for the
    // translation, IMU heading for the rotation. Re-measured every
    // attempt, so a leg that lands short (or long) gets replanned from
    // where the robot actually ended up, not where it was aimed.
    for (let attempt = 0; attempt < 3; attempt++) {
        diffDrive.readWorld()
        const h = diffDrive.worldHeading() * Math.PI / 180
        const dx = tx - diffDrive.poseX()
        const dy = ty - diffDrive.poseY()
        if (Math.sqrt(dx * dx + dy * dy) < 2) return      // arrived
        const bx = Math.cos(h) * dx + Math.sin(h) * dy
        const by = -Math.sin(h) * dx + Math.cos(h) * dy
        // startGoTo() (motion.ts) owns the pivot-vs-blend split and
        // short-arc wrap internally -- one call drives this leg's
        // pivot, if any, then its residual chord, reaching (bx, by)
        // for ANY bearing. No separate pivot-first branch is needed
        // here any more.
        tickedGoTo(bx, by)
    }
}

function tourRobot() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    openLoopProfile()
    maxGapMs = 0
    // Anchor BOTH sources at the start: encoder pose is the local
    // frame's origin, and the IMU heading is zeroed to it.
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("DBG:tour=robot")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        legToward(RTX[i], RTY[i])
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

// ---- straight-line test ---------------------------------------------
// WHEELS ONLY. No OTOS, no world frame, no heading correction: this
// deliberately does not call worldReady(), seedPose() or logFix(), and
// it does not steer. startMove(d, 0) runs on the encoders alone, so
// whatever the robot does here is what the drivetrain does -- consult
// the sensor and you are testing the sensor instead.
//
// Reports the ENCODER pose at the end: x is forward travel, y is how
// far it drifted sideways. y is the interesting number, because a
// perfectly straight run has y = 0 and nothing in this path is
// correcting it.
function straightRun(cm: number) {
    if (touring) return
    touring = true
    openLoopProfile()
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.emitLine("DBG:straight=" + cm)
    tickedMove(cm, 0)
    diffDrive.emitLine("GAP:" + maxGapMs)
    // cm x100, so a 1 mm drift is still visible as an integer.
    diffDrive.emitLine("STRAIGHT:end:"
        + Math.round(diffDrive.poseX() * 100) + ":"
        + Math.round(diffDrive.poseY() * 100) + ":"
        + Math.round(diffDrive.heading() * 100))
    basic.showString("S")
    touring = false
}

// ---- tour B: world --------------------------------------------------
// The sensor is consulted BEFORE EVERY MOVE, so each leg is planned
// from where the robot actually is. The move itself still runs on
// encoder odometry; the sensor never steers it in flight.
function tourWorld() {
    if (touring) return
    // Deliberately NOT worldReady(): that re-inits the sensor when it
    // looks unready, and begin() zeroes the position registers -- which
    // would throw away the pose the host just seeded and send the robot
    // off from a phantom origin.
    if (!diffDrive.worldTrackingReady()) {
        diffDrive.emitLine("OERR:not-seeded")
        basic.showString("NO")
        return
    }
    touring = true
    // 200 mm/s (stakeholder); 60 cm/s was near the drivetrain ceiling.
    // Accuracy-tuned shaping restored: the earlier "taper too slow"
    // reading was actually the yaw-taper double-count bug
    // (MotionEngine::serviceMove) masking as a profile problem.
    diffDrive.setTaperWindows(400, 180)
    diffDrive.setTaperFloors(25, 12)
    diffDrive.setRampMs(400)
    diffDrive.setDefaultSpeed(20)
    diffDrive.setDefaultYawRate(90)
    maxGapMs = 0
    // NO seed here: the host has already seeded the true world pose
    // from the overhead camera (RUN:seedxy), so the robot can start
    // anywhere on the field and simply drive to the first dot.
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
// Button A is the straight-line test, not tour A. tourRobot() is still
// reachable over the radio as RUN:tour:robot.
input.onButtonPressed(Button.A, function () {
    straightRun(100)
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

// RUN:straight[:cm] -- the same test over the radio, so it can be run
// without reaching onto the field and nudging the robot. Defaults to
// the 100 cm that button A does.
diffDrive.onRun("straight", function (arg: number) {
    straightRun(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 100)
})

diffDrive.onRun("cal", function (arg: number) {
    leverCal(arg != 0)
})

diffDrive.onRun("fix", function (arg: number) {
    // worldReady() FIRST, not just logFix(). logFix() calls readWorld()
    // directly, so a bare RUN:probe -> RUN:fix on the bench used to
    // report a pose with NO lever arm applied -- the sensor's position,
    // not the robot centre's, off by up to 38.2 mm and silently
    // plausible. That is exactly the reading that sent a 2026-08-25
    // bench session chasing a drivetrain fault that did not exist.
    // worldReady() is idempotent and cheap once the chip is up.
    if (!worldReady()) return
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

// Seed the world pose from an EXTERNAL fix -- the overhead camera.
// RUN:seedxy:<x>:<y>:<h> in cm/cm/deg. This is the bench stand-in for
// the v6 SEED verb; without it the tours can only assume they start on
// the NE dot, and a robot placed anywhere else silently runs its whole
// tour in a shifted frame.
diffDrive.onRun("seedxy", function (arg: number) {
    if (!worldReady()) return
    diffDrive.seedPose(diffDrive.runArg(0), diffDrive.runArg(1),
        diffDrive.runArg(2))
    logFix("seeded")
})

// Drive to a world point: RUN:goto:<x>:<y> in cm. Used to reposition
// onto the start dot between tours.
diffDrive.onRun("goto", function (arg: number) {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setTaperWindows(120, 80)
    diffDrive.setTaperFloors(45, 35)
    diffDrive.setRampMs(180)
    diffDrive.setDefaultSpeed(40)
    diffDrive.setDefaultYawRate(120)
    diffDrive.goToWorld(diffDrive.runArg(0), diffDrive.runArg(1))
    logFix("arrived")
    diffDrive.emitLine("GOTO:end")
    touring = false
})

// Turn in place to an absolute world heading: RUN:face:<deg>. The
// tours start facing west, and goToWorld only controls POSITION.
diffDrive.onRun("face", function (arg: number) {
    if (touring) return
    if (!worldReady()) return
    touring = true
    diffDrive.setDefaultYawRate(90)
    // Close the loop HERE, on the robot, against its own IMU heading.
    // Bouncing "measure, turn, measure" over the wireless link made the
    // host hunt: every round trip added latency and a fresh chance for
    // a lost command, so it oscillated instead of converging. On-device
    // it settles in one or two passes with no radio in the loop.
    for (let i = 0; i < 4; i++) {
        diffDrive.readWorld()
        let err = arg - diffDrive.worldHeading()
        while (err > 180) err -= 360
        while (err <= -180) err += 360
        if (Math.abs(err) <= 2) break
        tickedMove(0, err)
    }
    logFix("faced")
    diffDrive.emitLine("FACE:end")
    touring = false
})

// Relative in-place pivot: RUN:pivot:<deg>. Encoder/gyro only -- no
// OTOS, no world frame, deliberately no worldReady()/readWorld() call
// anywhere in this handler. rotation_check.py, pivot_truth.py,
// truth_check.py and turn_sweep.py all use this over radio on the
// floor, replacing the old dead numeric PIVOT_VERB offsets (2/4/5).
diffDrive.onRun("pivot", function (arg: number) {
    if (touring) return
    touring = true
    diffDrive.setTaperWindows(400, 180)
    diffDrive.setTaperFloors(25, 12)
    diffDrive.setRampMs(400)
    diffDrive.setDefaultYawRate(pivotYawRate)
    maxGapMs = 0
    tickedMove(0, diffDrive.runArg(0))
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("PIVOT:end")
    touring = false
})

// Sets the yaw rate the NEXT RUN:pivot command uses: RUN:turnrate:<deg/s>.
// turn_sweep.py sweeps rate against angle with this then RUN:pivot in
// a two-step call, mirroring the old dead numeric two-step shape
// (RUN:57000+rate then RUN:58360+deg). Does not move the robot itself.
diffDrive.onRun("turnrate", function (arg: number) {
    pivotYawRate = diffDrive.runArg(0)
})

