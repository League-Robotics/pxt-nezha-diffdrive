// test.ts -- the on-robot bench/playfield test program.
//
// Buttons:  A = RUN:straight:100   B = RUN:tour:world   A+B = RUN:tour:wheels
//
// Wire vocabulary, RUN:<verb>[:arg[:arg...]]
//
//   RECTANGLE TOURS -- start on the NE orange dot facing west, then run
//   counter-clockwise NE -> NW (100 cm) -> SW (60) -> SE (100) -> NE (60).
//     tour:robot        robot-relative frame, encoder position + IMU heading
//     tour:world        OTOS-guided, goToWorld, re-planned every leg
//     tour:wheels       open loop: drive the leg, then turn left
//
//   FIGURE TOURS -- open loop, arcs in 45 deg steps.
//     square[:cm]                                        default 60
//     diamond[:cm]      the square turned 45 deg         default 45
//     circle[:r[:ccw]]                                   default 30, ccw
//     infinity[:r[:laps]]   figure-8                     default 30, 1
//     snake[:r[:bends]]     serpentine, NOT a spline     default 12.5, 4
//
//   SINGLE MOVES
//     straight[:cm]     wheels only: no OTOS, no steering    default 100
//     pivot:<deg>       in-place, encoder/gyro only
//     arc:<deg>         20 cm + <deg>, dumps its heading trajectory as ARCT:
//     goto:<x>:<y>      drive to a world point, cm
//     face:<deg>        turn to an absolute world heading
//     turnrate:<deg/s>  the yaw rate the NEXT pivot uses
//
//   SENSOR AND CONTROL
//     cal[:1]           OTOS lever-arm calibration; :1 verifies the result
//     fix               log one world fix
//     seed              seed the world pose to the NE dot
//     seedxy:<x>:<y>:<h>  seed it from an external fix (the overhead camera)
//     probe  arm  gap
//     abort  clearestop
//
// Design notes -- the tick model, job lifecycle, abort scope, shaping
// profiles, the arc steps and the measured constants below --
// live in test/DESIGN.md.

// Substituted by tools/make_deploy.py in the scratch copy. Left as
// obviously-fake placeholders here so an unsubstituted build reads as
// visibly wrong rather than silently plausible.
const BOOT_VERSION = "00.00"
const BOOT_ROBOT = "unknown"

// Carriers. Both are opt-in so a student program can still use
// MakeCode's own radio blocks; make_deploy.py substitutes the flag.
const BOOT_RADIO_LINK = false
if (BOOT_RADIO_LINK) diffDrive.enableRadioLink()
diffDrive.enableWifiLink()

let touring = false
let aborted = false
let maxGap = 0  // [ms]
let jobVerb = ""
let pivotYawRate = 90   // [deg/s] used by the next RUN:pivot

// Sample the OTOS every Nth driveTick(), on the ticking fiber. 4 ticks
// at the kernel's 24 ms cycle is 96 ms, the closest whole-tick match to
// the 10 Hz the old background sampler ran at.
const OTOS_SAMPLE_TICKS = 4
let otosSampleTickCount = 0
let sampleWorld = true

// The one tick loop every leg in this file runs through.
function tickToCompletion() {
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGap) maxGap = now - last
        last = now
        otosSampleTickCount += 1
        if (sampleWorld && otosSampleTickCount >= OTOS_SAMPLE_TICKS) {
            otosSampleTickCount = 0
            diffDrive.readWorld()
        }
        if (aborted) {
            diffDrive.stopMove()
            return
        }
    }
}

// Tick-serviced basic.pause(): handlers run ON the protocol fiber, so a
// blocking pause stops that fiber from answering PING/ESTOP/abort.
// Runs the full duration unconditionally, like basic.pause() itself.
function tickWait(duration: number) {  // [ms]
    const deadline = control.millis() + duration
    while (control.millis() < deadline) {
        diffDrive.driveTick()
    }
}

function tickedMove(d: number, y: number) {
    diffDrive.startMove(d, y)
    tickToCompletion()
}

function tickedGoTo(x: number, y: number) {
    diffDrive.startGoTo(x, y)
    tickToCompletion()
}

// ---- RUN:arc trajectory sampling --------------------------------------
// Sampled on this fiber during the move and dumped afterwards: a
// request/reply round trip DURING a move collapses it (see shims.cpp's
// probe() doc comment). A 180 deg arc is ~120 ticks; the cap is
// headroom above that, not a working limit.
const ARC_SAMPLE_CAP = 200
let hSamples: number[] = []
let hSamplesCapped = false

function tickArcSampled(d: number, y: number) {
    hSamples = []
    hSamplesCapped = false
    diffDrive.startMove(d, y)
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGap) maxGap = now - last
        last = now
        if (hSamples.length < ARC_SAMPLE_CAP) {
            hSamples.push(Math.round(diffDrive.heading() * 100))
        } else {
            hSamplesCapped = true
        }
        if (aborted) {
            diffDrive.stopMove()
            return
        }
    }
    // driveTick() applies the final tick's state before returning false,
    // so the settled end-of-move heading is never seen by the loop.
    if (hSamples.length < ARC_SAMPLE_CAP) {
        hSamples.push(Math.round(diffDrive.heading() * 100))
    } else {
        hSamplesCapped = true
    }
}

// 20 centidegree ints per line, well under the wire's 240-byte clip.
const ARCT_CHUNK = 20

function emitTrajectory() {
    // Meta line first: sample count, and whether the cap truncated it.
    diffDrive.emitLine("ARCT:meta:" + hSamples.length
        + ":" + (hSamplesCapped ? 1 : 0))
    let chunk = 0
    for (let i = 0; i < hSamples.length; i += ARCT_CHUNK) {
        let csv = ""
        const end = Math.min(i + ARCT_CHUNK, hSamples.length)
        for (let j = i; j < end; j++) {
            if (j > i) csv += ","
            csv += hSamples[j]
        }
        diffDrive.emitLine("ARCT:" + chunk + ":" + csv)
        chunk += 1
    }
    diffDrive.emitLine("ARCT:done")
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

// OTOS lever arm, relative to the centre of rotation. MEASURED vevov
// 2026-08-28, captures/otos-run-handler-i2c-hang-20260828.md; method and
// camera cross-check in DESIGN.md.
let armX = -5.27      // [cm] +forward
let armY = -0.12      // [cm] +left
let armYaw = 0.89     // [deg] UNVERIFIED -- carried over from 2026-08-21

let armApplied = false

function applyArm() {
    diffDrive.setWorldSensorOffset(armX, armY, armYaw)
    armApplied = true
    diffDrive.emitLine("ARM:" + Math.round(armX * 100)
        + ":" + Math.round(armY * 100) + ":" + Math.round(armYaw * 100))
}

// True once the OTOS is up AND armed. The fast path must still arm:
// worldTrackingReady() only asks whether the chip answers, and an
// un-armed sensor reports its own path, not the centre's.
function worldReady(): boolean {
    if (diffDrive.worldTrackingReady()) {
        if (!armApplied) applyArm()
        return true
    }
    if (diffDrive.startWorldTracking()) {
        applyArm()          // begin() re-inits the chip; re-apply
        return true
    }
    diffDrive.emitLine("OERR:no-otos")
    return false
}

// Log a fix as OCAL:<tag>:<x 0.01cm>:<y 0.01cm>:<h 0.01deg>. A failed
// read is logged: silence would look like a real fix at the origin.
function logFix(tag: string) {
    if (!diffDrive.readWorld()) {
        diffDrive.emitLine("OERR:read-failed:" + tag)
    }
    diffDrive.emitLine("OCAL:" + tag
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
}

// Open loop: every error is permanent, so keep the accuracy-tuned
// shaping. 400/400 is the fleet default and MEASURED best -- see
// DESIGN.md before changing either literal.
function openLoopProfile() {
    diffDrive.setLimits(400, 400, 200, 90)
    diffDrive.setDefaultSpeed(20)
    diffDrive.setDefaultYawRate(90)
}

// Closed loop: RUN:goto's faster shaping, for moves re-measured and
// re-planned every leg.
function closedLoopProfile() {
    diffDrive.setLimits(600, 500, 400, 120)
    diffDrive.setDefaultSpeed(40)
    diffDrive.setDefaultYawRate(120)
}

// ---- job lifecycle ----------------------------------------------------
// Every motion-issuing job is `if (touring) return; beginJob("<VERB>")`
// ... `endJob(jobReason())`. The touring guard stays at the call site:
// several jobs check worldReady() in between, which must run first.
function beginJob(name: string): void {
    touring = true
    aborted = false
    if (name == "GOTO") closedLoopProfile()
    else openLoopProfile()
    maxGap = 0
    jobVerb = name
}

// Abort (operator intent) outranks a coincident e-stop, which outranks
// a clean finish. Call once, at the endJob() site; never recompute
// later, as the wire-reported reason is poll-timing dependent.
function jobReason(): string {
    return aborted ? "abort" : (diffDrive.probe(1) != 0 ? "estop" : "ok")
}

function endJob(reason: string): void {
    diffDrive.emitLine("GAP:" + maxGap)
    diffDrive.emitLine(jobVerb + ":end:" + reason)
    touring = false
}

// ---- tour: robot-relative --------------------------------------------
// The rectangle in a frame anchored where the robot started, so no world
// position is needed. Heading still comes from the IMU every leg.
const RTX = [100, 100, 0, 0]     // [cm] corners in the start frame
const RTY = [0, 60, 60, 0]       // x forward, y left

// Plan from where we ACTUALLY are, every attempt: encoder position for
// the translation, IMU heading for the rotation. A few degrees of
// residual is absorbed by curving to the destination, never corrected
// with a second pivot. startGoTo() owns the pivot-vs-blend split.
function legToward(tx: number, ty: number) {
    for (let attempt = 0; attempt < 3; attempt++) {
        diffDrive.readWorld()
        const h = diffDrive.worldHeading() * Math.PI / 180
        const dx = tx - diffDrive.poseX()
        const dy = ty - diffDrive.poseY()
        if (Math.sqrt(dx * dx + dy * dy) < 2) return      // arrived
        const bx = Math.cos(h) * dx + Math.sin(h) * dy
        const by = -Math.sin(h) * dx + Math.cos(h) * dy
        tickedGoTo(bx, by)
    }
}

function tourRobot() {
    if (touring) return
    if (!worldReady()) return
    beginJob("TOUR")
    // Anchor both sources: encoder pose is the local frame's origin, and
    // the IMU heading is zeroed to it.
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("DBG:tour=robot:profile=open")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        legToward(RTX[i], RTY[i])
        // Before logFix(): an abort must not emit a plausible-looking
        // fix for a corner the robot never reached.
        if (aborted) break
        logFix("c" + (i + 1))
    }
    endJob(jobReason())
    basic.showString("A")
}

// ---- tour: wheels ----------------------------------------------------
function tourWheels() {
    if (touring) return
    beginJob("TOUR")
    sampleWorld = false
    diffDrive.resetPose()
    diffDrive.emitLine("DBG:tour=wheels:profile=open")
    diffDrive.emitLine("DBG:corner=0")
    for (let i = 0; i < 4; i++) {
        tickedMove(LEG_CM[i], 0)     // straight leg
        if (aborted) break           // don't also issue the turn below
        tickedMove(0, 90)            // then LEFT
        if (aborted) break
        diffDrive.emitLine("DBG:corner=" + (i + 1))
    }
    endJob(jobReason())
    sampleWorld = true
    basic.showString("W")
}

// ---- tour: world -----------------------------------------------------
// The sensor is consulted BEFORE every move, so each leg is planned from
// where the robot actually is; it never steers a move in flight.
function tourWorld() {
    if (touring) return
    // NOT worldReady(): that re-inits the sensor, and begin() zeroes the
    // position registers -- throwing away the pose the host just seeded.
    if (!diffDrive.worldTrackingReady()) {
        diffDrive.emitLine("OERR:not-seeded")
        return
    }
    beginJob("TOUR")
    // No seed: the host has already seeded the true world pose from the
    // overhead camera, so the robot can start anywhere on the field.
    diffDrive.emitLine("DBG:tour=world:profile=open")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        diffDrive.goToWorld(CORNERS_X[i], CORNERS_Y[i])
        if (aborted) break
        logFix("c" + (i + 1))
    }
    endJob(jobReason())
    basic.showString("B")
}

// ---- straight-line test ----------------------------------------------
// WHEELS ONLY -- deliberately no worldReady(), seedPose() or logFix(),
// and no steering. Reports the encoder pose: x is forward travel, y is
// sideways drift, and y is the interesting number.
function straightRun(cm: number) {
    if (touring) return
    beginJob("STRAIGHT")
    diffDrive.resetPose()
    diffDrive.emitLine("DBG:straight=" + cm + ":profile=open")
    tickedMove(cm, 0)
    // cm x100, so 1 mm of drift is still visible as an integer. Its own
    // line, so pose data and pass/fail reason parse independently.
    diffDrive.emitLine("STRAIGHT:pose:"
        + Math.round(diffDrive.poseX() * 100) + ":"
        + Math.round(diffDrive.poseY() * 100) + ":"
        + Math.round(diffDrive.heading() * 100))
    endJob(jobReason())
    basic.showString("S")
}

// ---- lever-arm calibration -------------------------------------------
// With the offsets zeroed a pure pivot sweeps the SENSOR around the
// centre of rotation, so its track is a circle: centre = the robot's
// centre, radius = the arm. verify=true repeats it with the measured arm
// applied, where a correct arm collapses the circle to a point.
function leverCal(verify: boolean) {
    if (touring) return
    if (!worldReady()) return
    beginJob("CAL")
    if (verify) applyArm()
    else diffDrive.setWorldSensorOffset(0, 0, 0)
    // One-off override of the sweep's own slow, fixed rate.
    diffDrive.setDefaultSpeed(15)
    diffDrive.setDefaultYawRate(45)
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("OCAL:begin")
    logFix("p0")
    for (let i = 1; i <= 8 && !aborted; i++) {
        tickedMove(0, 45)
        tickWait(400)              // let the wheels settle before the fix
        logFix("p" + i)
    }
    if (!aborted) {
        tickedMove(30, 0)         // 30 cm straight, for the mounting yaw
        tickWait(400)
        logFix("s1")
    }
    diffDrive.emitLine("OCAL:end")
    endJob(jobReason())
    basic.showString("OK")
}

// ---- figure tours ----------------------------------------------------
// ARC SEGMENT SIZE, HISTORY: moveX() used to split any move with a
// nonzero distance and |yaw| >= 50 deg into a pivot THEN a straight, so
// an arc asked for in 90 deg pieces came out as a SQUARE. That split is
// gone (reports/move-x-arc-space-20260906.md): move() is one
// constant-radius arc at any angle. The 45 deg steps are kept as
// written, not required.

// One constant-curvature arc of `deg` degrees on a circle of `rCm`. Arc
// length = r * theta, which is what move()'s distance argument wants.
function arcSegment(rCm: number, deg: number) {
    const distCm = rCm * Math.abs(deg) * Math.PI / 180.0
    tickedMove(distCm, deg)
}

// A full circle as 8 arcs of 45 deg. Positive rCm turns CCW (left).
function circleRun(rCm: number, ccw: boolean) {
    for (let i = 0; i < 8; i++) {
        if (aborted) return
        arcSegment(rCm, ccw ? 45 : -45)
    }
}

function squareTour(sideCm: number) {
    if (touring) return
    beginJob("SQUARE")
    diffDrive.emitLine("DBG:tour=square:side=" + sideCm)
    for (let i = 0; i < 4; i++) {
        diffDrive.emitLine("DBG:leg=" + (i + 1))
        tickedMove(sideCm, 0)
        if (aborted) break
        tickedMove(0, 90)
        if (aborted) break
    }
    diffDrive.stopMove()
    endJob(jobReason())
    basic.showIcon(IconNames.Yes)
}

// The square turned 45 deg, so its legs run diagonally. Sized smaller:
// a square of side S turned 45 deg spans S*sqrt2 in BOTH axes, so 45 cm
// sides span 63.6 cm, which is what fits the field's tight axis.
function diamondTour(sideCm: number) {
    if (touring) return
    beginJob("DIAMOND")
    diffDrive.emitLine("DBG:tour=diamond:side=" + sideCm)
    tickedMove(0, 45)                    // enter the diamond
    for (let i = 0; i < 4; i++) {
        if (aborted) break
        diffDrive.emitLine("DBG:leg=" + (i + 1))
        tickedMove(sideCm, 0)
        if (aborted) break
        tickedMove(0, 90)
    }
    diffDrive.stopMove()
    endJob(jobReason())
    basic.showIcon(IconNames.Yes)
}

// Driven CCW from a point on its own circumference the centre sits
// 90 deg to the left, so it spans +-r across the start heading and
// 0..2r along it.
function circleTour(rCm: number, ccw: boolean) {
    if (touring) return
    beginJob("CIRCLE")
    diffDrive.emitLine("DBG:tour=circle:r=" + rCm + ":ccw=" + (ccw ? 1 : 0))
    circleRun(rCm, ccw)
    diffDrive.stopMove()
    endJob(jobReason())
    basic.showIcon(IconNames.Yes)
}

// A figure-8: two circles joined at a point on their circumferences, the
// second curving the other way, so the robot returns to the crossing
// point each lap.
function infinityTour(rCm: number, laps: number) {
    if (touring) return
    beginJob("INFINITY")
    diffDrive.emitLine("DBG:tour=infinity:r=" + rCm + ":laps=" + laps)
    for (let lap = 0; lap < laps; lap++) {
        diffDrive.emitLine("DBG:lap=" + (lap + 1))
        circleRun(rCm, true)         // lobe A, CCW
        if (aborted) break
        circleRun(rCm, false)        // lobe B, CW
        if (aborted) break
    }
    diffDrive.stopMove()
    endJob(jobReason())
    basic.showIcon(IconNames.Yes)
}

// A serpentine: alternating half-circles, the open cousin of the
// infinity figure. Its defaults advance 8r = 100 cm PERPENDICULAR to
// the start heading -- the first half circle turns the robot 180 deg,
// so progress is sideways -- so stage it facing the short axis.
function snakeTour(rCm: number, bends: number) {
    if (touring) return
    beginJob("SNAKE")
    diffDrive.emitLine("DBG:tour=snake:r=" + rCm + ":bends=" + bends)
    for (let b = 0; b < bends; b++) {
        diffDrive.emitLine("DBG:bend=" + (b + 1))
        const ccw = (b % 2) == 0
        for (let i = 0; i < 4; i++) {      // half circle = 4 x 45 deg
            if (aborted) break
            arcSegment(rCm, ccw ? 45 : -45)
        }
        if (aborted) break
    }
    diffDrive.stopMove()
    endJob(jobReason())
    basic.showIcon(IconNames.Yes)
}

// ---- buttons ---------------------------------------------------------
input.onButtonPressed(Button.A, function () {
    straightRun(100)
})
input.onButtonPressed(Button.B, function () {
    tourWorld()
})
input.onButtonPressed(Button.AB, function () {
    tourWheels()
})

// ---- named run commands ----------------------------------------------

// abort and clearestop bypass the RUN queue -- dispatched reentrantly,
// nested inside whatever handler is mid-tick, on the same fiber. So
// neither guards on `touring`, and both stay flag-only and non-blocking.
// clearestop is its own verb, never folded into STOP, which is issued
// reflexively and must never silently disarm a safety latch.
diffDrive.onRun("clearestop", function (arg: number) {
    diffDrive.clearEmergencyStop()
    diffDrive.emitLine("ESTOP:cleared")
})

// stopMove() ends whatever move is CURRENTLY in flight, in any file --
// including goToWorld()'s own tick loop, which cannot see `aborted`.
diffDrive.onRun("abort", function (arg: number) {
    aborted = true
    diffDrive.stopMove()
})

diffDrive.onRun("tour", function (arg: number) {
    const which = diffDrive.runArgText(0)
    if (which == "robot") tourRobot()
    else if (which == "world") tourWorld()
    else tourWheels()
})

diffDrive.onRun("straight", function (arg: number) {
    straightRun(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 100)
})

diffDrive.onRun("cal", function (arg: number) {
    leverCal(arg != 0)
})

diffDrive.onRun("fix", function (arg: number) {
    // worldReady() first, not just logFix(): logFix() calls readWorld()
    // directly, so a bare RUN:probe -> RUN:fix would report the SENSOR's
    // position with no lever arm applied -- silently plausible, and off
    // by up to 38.2 mm.
    if (!worldReady()) return
    logFix("now")
})

diffDrive.onRun("arm", function (arg: number) {
    applyArm()
})

// Hardware verification for the `configure motor` block (sprint-less,
// 2026-09-12). Reports the LIVE wiring straight out of the two ports
// (diag 35-38), so a host can see whether a configureMotor() call
// actually landed -- the thing that could not be seen when it shipped
// as a silent no-op.
function emitWiring(tag: string) {
    diffDrive.emitLine("WIRE " + tag
        + " leftPort=" + diffDrive.probe(35)
        + " leftSign=" + diffDrive.probe(36)
        + " rightPort=" + diffDrive.probe(37)
        + " rightSign=" + diffDrive.probe(38)
        + " connL=" + diffDrive.probe(4)
        + " connR=" + diffDrive.probe(5))
}

diffDrive.onRun("wire", function (arg: number) {
    emitWiring("now")
})

// Spin ONE side briefly and report the brick's RAW counter either side
// of it (diag 39/40). Raw does not pass through fwdSign, so the sign of
// its delta is which way the motor physically turned -- the measurement
// probe(10)/(11) cannot make, since those move with fwdSign and stay
// self-consistent under a flip.
//
// arg: 0 = left forward, 1 = right forward. Bench stand only (wheels
// up): this drives a wheel for 600 ms.
diffDrive.onRun("spinone", function (arg: number) {
    const isRight = arg == 1
    const before = isRight ? diffDrive.probe(40) : diffDrive.probe(39)
    const posBefore = isRight ? diffDrive.probe(11) : diffDrive.probe(10)
    const t0 = control.millis()
    while (control.millis() - t0 < 600) {
        diffDrive.setWheelSpeeds(isRight ? 0 : 12, isRight ? 12 : 0)
        diffDrive.driveTick()
    }
    diffDrive.stop()
    const after = isRight ? diffDrive.probe(40) : diffDrive.probe(39)
    const posAfter = isRight ? diffDrive.probe(11) : diffDrive.probe(10)
    diffDrive.emitLine("SPIN " + (isRight ? "right" : "left")
        + " rawBefore=" + before + " rawAfter=" + after
        + " rawDelta=" + (after - before)
        + " posDelta=" + (posAfter - posBefore)
        + " sign=" + (isRight ? diffDrive.probe(38) : diffDrive.probe(36))
        + " port=" + (isRight ? diffDrive.probe(37) : diffDrive.probe(35)))
})

// arg encodes one configureMotor() call as SPD: Side*100 + Port*10 + Dir,
// Dir 1 = forward, 2 = reversed. Left M2 reversed is 22; right M1
// forward is 111. One integer because onRun carries exactly one.
diffDrive.onRun("setwire", function (arg: number) {
    const side = Math.idiv(arg, 100) % 10
    const port = Math.idiv(arg, 10) % 10
    const dir = arg % 10
    emitWiring("before")
    diffDrive.configureMotor(
        side == 1 ? MotorSide.Right : MotorSide.Left,
        port == 4 ? MotorPort.M4 : port == 3 ? MotorPort.M3
            : port == 2 ? MotorPort.M2 : MotorPort.M1,
        dir == 2 ? MotorDirection.Reversed : MotorDirection.Forward)
    emitWiring("after")
})

diffDrive.onRun("probe", function (arg: number) {
    diffDrive.emitLine("OPROBE:" + diffDrive.otosBegin()
        + ":" + diffDrive.otosGet(7))
})

diffDrive.onRun("gap", function (arg: number) {
    diffDrive.emitLine("GAP:" + maxGap)
})

diffDrive.onRun("seed", function (arg: number) {
    worldReady()
    diffDrive.seedPose(START_X, START_Y, START_H)
    tickWait(300)
    const ok = diffDrive.readWorld()
    diffDrive.emitLine("SEED:read:" + (ok ? 1 : 0)
        + ":" + Math.round(diffDrive.worldX() * 100)
        + ":" + Math.round(diffDrive.worldY() * 100)
        + ":" + Math.round(diffDrive.worldHeading() * 100))
})

// Seed from an EXTERNAL fix -- the overhead camera. Without it the tours
// can only assume they start on the NE dot, and a robot placed anywhere
// else silently runs its whole tour in a shifted frame.
diffDrive.onRun("seedxy", function (arg: number) {
    if (!worldReady()) return
    diffDrive.seedPose(diffDrive.runArg(0), diffDrive.runArg(1),
        diffDrive.runArg(2))
    logFix("seeded")
})

diffDrive.onRun("goto", function (arg: number) {
    if (touring) return
    if (!worldReady()) return
    beginJob("GOTO")
    diffDrive.emitLine("DBG:goto:profile=closed")
    diffDrive.goToWorld(diffDrive.runArg(0), diffDrive.runArg(1))
    logFix("arrived")
    endJob(jobReason())
})

diffDrive.onRun("face", function (arg: number) {
    if (touring) return
    if (!worldReady()) return
    beginJob("FACE")
    diffDrive.setDefaultYawRate(90)
    diffDrive.emitLine("DBG:face:profile=open")
    // Close the loop HERE, against the robot's own IMU heading: bouncing
    // "measure, turn, measure" over the wireless link oscillated instead
    // of converging. On-device it settles in one or two passes.
    for (let i = 0; i < 4; i++) {
        if (aborted) break
        diffDrive.readWorld()
        let err = arg - diffDrive.worldHeading()
        while (err > 180) err -= 360
        while (err <= -180) err += 360
        if (Math.abs(err) <= 2) break
        tickedMove(0, err)
    }
    logFix("faced")
    endJob(jobReason())
})

// Encoder/gyro only -- deliberately no worldReady()/readWorld() anywhere
// in this handler. pivotYawRate (set by RUN:turnrate) overrides the
// profile's own 90 deg/s.
diffDrive.onRun("pivot", function (arg: number) {
    if (touring) return
    beginJob("PIVOT")
    diffDrive.setDefaultYawRate(pivotYawRate)
    diffDrive.emitLine("DBG:pivot:profile=open")
    tickedMove(0, diffDrive.runArg(0))
    endJob(jobReason())
})

// One combined 20 cm + <deg> move: a single constant-radius arc at any
// |deg| (HISTORY: this was the shape that measured the sprint 015
// phase-handoff defect, when moveX() still split at |50| deg; the
// handoff now belongs to goToR() alone). Encoder/gyro only.
diffDrive.onRun("arc", function (arg: number) {
    if (touring) return
    beginJob("ARC")
    diffDrive.emitLine("DBG:arc:profile=open")
    tickArcSampled(20, diffDrive.runArg(0))
    endJob(jobReason())
    emitTrajectory()
})

// Does not move the robot: turn_sweep.py sweeps rate against angle with
// this, then RUN:pivot.
diffDrive.onRun("turnrate", function (arg: number) {
    pivotYawRate = diffDrive.runArg(0)
})

diffDrive.onRun("square", function (arg: number) {
    squareTour(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 60)
})

diffDrive.onRun("diamond", function (arg: number) {
    diamondTour(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 45)
})

// runArgOr(0, <default>, 0) rejects an unparseable radius ("RUN:circle:
// abc") and a non-positive one alike as NaN. Refused with an ARGERR:
// line rather than silently substituting: these are student-facing
// verbs, and a typo that quietly ran eight pivots-in-place used to look
// like a normal, if odd, completion (BT-22).
diffDrive.onRun("circle", function (arg: number) {
    const r = diffDrive.runArgOr(0, 30, 0)
    if (isNaN(r)) {
        diffDrive.emitLine("ARGERR:circle:radius:" + diffDrive.runArgText(0))
        return
    }
    const ccw = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) != 0 : true
    circleTour(r, ccw)
})

diffDrive.onRun("infinity", function (arg: number) {
    const r = diffDrive.runArgOr(0, 30, 0)
    if (isNaN(r)) {
        diffDrive.emitLine("ARGERR:infinity:radius:" + diffDrive.runArgText(0))
        return
    }
    const laps = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) : 1
    infinityTour(r, laps)
})

diffDrive.onRun("snake", function (arg: number) {
    const r = diffDrive.runArgOr(0, 12.5, 0)
    if (isNaN(r)) {
        diffDrive.emitLine("ARGERR:snake:radius:" + diffDrive.runArgText(0))
        return
    }
    const bends = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) : 4
    snakeTour(r, bends)
})

// ---- boot: OTOS, then the identity banner ------------------------------
// Bringing the OTOS up on the MAIN fiber at boot keeps the No-ACK I2C
// wedge off the RUN path, where it once bricked two robots, and makes
// STATUS's `otos=` flag meaningful from boot.
const otosBootId = diffDrive.otosBegin()
diffDrive.emitLine("OTOS:boot:id=" + otosBootId
    + ":connected=" + diffDrive.otosGet(7))
// Arming here is pure software (no I2C), and means no tour can start on
// an un-armed sensor.
if (diffDrive.otosGet(7) != 0) {
    applyArm()
}

// LAST, deliberately: showIcon/showString BLOCK this fiber, and a RUN:
// line landing during that window needs its handler already registered
// to be dispatched at all.
basic.showIcon(IconNames.Rollerskate)
basic.showString(BOOT_ROBOT + " " + BOOT_VERSION)
