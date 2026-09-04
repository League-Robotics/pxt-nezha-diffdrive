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

// Boot identity banner -- displayed at the bottom of this file, after
// every button/RUN: handler is registered (see that call site's own
// comment for why). Placeholder values: this file cannot read the
// repo's own version file at build time, so tools/make_deploy.py
// substitutes both into this exact scratch-copy text before every
// real build. Left as obviously-fake placeholders here on purpose --
// this checked-in source, run unsubstituted, should read as visibly
// wrong rather than silently plausible.
const BOOT_VERSION = "00.00"
const BOOT_ROBOT = "unknown"

// The v6 radio link is OPT-IN as of 2026-08-29 (see radioEnabled_ in
// src/comms/protocol.h): the extension no longer brings the radio up on
// its own, so that a student's program can use MakeCode's own radio
// blocks for a joystick.
//
// This program is the opposite case and MUST turn it on. Everything in
// tools/ drives the robot over the zavaz relay, and an untethered run
// reports its results back by radio -- USB only reaches the bench stand,
// where the wheels are off the ground. Without this call every one of
// those tools goes silent with no error, which looks exactly like a dead
// robot (.claude/rules/playfield-testing.md has the checklist for that
// symptom; this would be a new way to trigger it).
//
// No channel argument on purpose: enableRadioLink() uses the per-robot
// channel make_deploy.py injected into kChannel, so `--robot tovez`
// still lands on channel 3 rather than vevov's 4.
//
// 2026-09-02: OFF BY DEFAULT. The WiFi link (below) is now the
// untethered carrier; the v6 radio is only brought up when the deploy
// says so -- `tools/make_deploy.py --radio-link`, or
// `connection.v6_radio_link: true` in the robot's radio-robot-lib
// config -- substituted into this placeholder in the scratch copy.
// While it stays false, the radio is untouched and MakeCode's own
// `radio` blocks (a student's joystick) work in the same program.
const BOOT_RADIO_LINK = false
if (BOOT_RADIO_LINK) diffDrive.enableRadioLink()

// The WiFi transport (Planet X Ai-WB2-12F on J1) is opt-in the same way:
// the same v6 wire on UDP :7654, plus an mDNS advertisement. A build
// with no config/wifi_secrets.json baked in (tools/make_deploy.py) keeps
// it off even with this call, so a bench without the module loses
// nothing.
diffDrive.enableWifiLink()

let touring = false
// Set by RUN:abort (below); tickToCompletion() -- the single choke point
// every tickedMove()/tickedGoTo() leg goes through -- checks this and
// stops early. Each tour's own for loop also checks it after every
// leg/corner and breaks, so a tour issues no further legs and no further
// OCAL: corner fixes once an abort lands. Reset to false at the START of
// each tour, so a previous abort does not poison the next run.
let aborted = false
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
        // RUN:abort landed mid-leg -- stop() for real (stopMove(), a real
        // stop since sprint 016 ticket 001) and return early instead of
        // ticking this move to its own completion. The single choke point
        // tickedMove()/tickedGoTo() (and therefore legToward() and every
        // tour) shares, so no separate abort plumbing is needed in any of
        // them for the CURRENT leg to stop promptly.
        if (aborted) {
            diffDrive.stopMove()
            return
        }
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

// ---- RUN:arc trajectory sampling --------------------------------------
// A request/reply round trip DURING a move is dangerous (src/shims.cpp's
// probe() doc comment: a 197.5 mm leg collapsed to 0.3 mm), and
// subscribing v6 POSE telemetry then sending a cleartext RUN: line hangs
// the link outright (clasi/issues/cleartext-run-hangs-the-link-under-
// active-telemetry.md) -- so RUN:arc's heading trajectory cannot be read
// live off the wire at all. Instead this samples diffDrive.heading()
// itself, once per tick, on THIS fiber while the move runs -- the same
// "a test program samples into arrays and dumps afterwards instead"
// pattern probe()'s own comment already prescribes for exactly this
// class of problem -- and dumps the trajectory as ARCT: lines after the
// move completes. No telemetry subscription is ever needed, so the link
// hang above cannot trigger.
//
// A 180 deg arc runs about 2.8 s at ~24 ms/tick (roughly 120 ticks);
// this cap leaves comfortable headroom above that and stops growing the
// array unbounded if a tick stall ever makes a move run long.
const ARC_SAMPLE_CAP = 200
let hSamples: number[] = []
let hSamplesCapped = false

// Deliberately its own tick loop rather than a flag on the shared
// tickToCompletion() above: every other caller of that function (both
// tours, RUN:pivot, RUN:face, legToward()) stays completely untouched by
// this ticket's change.
function tickArcSampled(d: number, y: number) {
    hSamples = []
    hSamplesCapped = false
    diffDrive.startMove(d, y)
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGapMs) maxGapMs = now - last
        last = now
        if (hSamples.length < ARC_SAMPLE_CAP) {
            hSamples.push(Math.round(diffDrive.heading() * 100))
        } else {
            hSamplesCapped = true
        }
        // See tickToCompletion()'s identical check: stop for real and
        // return early rather than sampling this move to its own
        // completion.
        if (aborted) {
            diffDrive.stopMove()
            return
        }
    }
    // One more sample after the loop exits. driveTick() already applied
    // the FINAL tick's state before returning false, so that settled
    // end-of-move heading is never seen by the `while` loop above (the
    // same reason straightRun() and RUN:pivot only read heading() after
    // their own tick loop has returned, not on the loop's last
    // iteration).
    if (hSamples.length < ARC_SAMPLE_CAP) {
        hSamples.push(Math.round(diffDrive.heading() * 100))
    } else {
        hSamplesCapped = true
    }
}

// Dump hSamples as ARCT: lines, chunked well under the wire's 240-byte
// line cap (serial_transport.h/radio_transport.h's kMaxLineBytes and
// protocol.cpp's Protocol::emitLine all share that one 240-byte clip).
// 20 centidegree ints per line is a wide margin even at 6 digits + sign
// + comma each.
const ARCT_CHUNK = 20

function emitTrajectory() {
    // meta line first: total sample count and whether ARC_SAMPLE_CAP was
    // hit (in which case the trajectory below is truncated, not the
    // whole move) -- read this before trusting the chunk lines' count.
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

// vevov's lever arm, MEASURED on the playfield 2026-08-20 (RUN:cal +
// tools/otos_levercal.py): eight 45 deg pivots swept the sensor around
// the centre of rotation on a 38.2 mm circle, fit residual rms 1.34 mm.
// The sensor sits 38.2 mm BEHIND the centre, within a millimetre of the
// centreline; the mounting yaw came from the 30 cm straight leg after.
// OTOS lever arm -- sensor position relative to the CENTRE OF ROTATION.
// RE-MEASURED vevov 2026-08-28 after the chassis rebuild (front caster
// removed, drive wheels moved forward), which MOVED the centre of
// rotation and so invalidated the -3.82 cm measured 2026-08-21.
// Capture: captures/otos-run-handler-i2c-hang-20260828.md.
//
// Method: with applyArm() not yet run the OTOS reports the SENSOR's own
// path, so eight 45 deg in-place pivots trace a circle of radius |arm|
// about the centre; least-squares fit of otos_i = C + R(theta_i).arm
// over 9 rest readings gave x -52.7 mm, y -1.2 mm, residuals 1.4 mm
// median / 1.9 mm max.
//
// CROSS-CHECK, independent: the overhead camera's tag-53 mount solved
// to 53.4 mm behind the centre the same day, by the same fit shape but
// a different instrument. Two sensors agreeing to 0.7 mm is what makes
// this trustworthy rather than merely fitted.
let armX = -5.27      // [cm] +forward
let armY = -0.12      // [cm] +left
// UNVERIFIED: yaw was NOT re-measured -- the pivot fit constrains the
// arm's POSITION, not the sensor's angular mounting. Carried over from
// 2026-08-21. Re-measure by comparing OTOS heading against camera
// heading at rest across several headings.
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
//
// Sprint 029 ticket 004 (design motion-profile-unification.md S4.7):
// the old setTaperWindows/setTaperFloors/setRampMs triple collapses
// into one setLimits(accel, decel, vMax, omegaMax) call -- design
// S4.7's own exact literals for this profile. Floors and stop_distance
// are per-robot (the deploy bake, or `set config`), never per profile,
// so they stay OUT of this function, same as before this ticket.
// setDefaultSpeed/setDefaultYawRate are a SEPARATE mechanism (the
// move()/goTo() blocks' own default cruise speed/yaw rate, unrelated to
// MotionLimits shaping) and are unaffected by this ticket.
function openLoopProfile() {
    diffDrive.setLimits(300, 300, 200, 90)
    diffDrive.setDefaultSpeed(20)
    diffDrive.setDefaultYawRate(90)
}

// Closed-loop profile: RUN:goto's fast shaping, for moves that get
// re-measured and re-planned every leg (a sensor fix corrects whatever
// this profile's speed costs in accuracy), unlike the open-loop tours
// where every error is permanent. Same setLimits() collapse as
// openLoopProfile() above, design S4.7's own literals for this profile.
function closedLoopProfile() {
    diffDrive.setLimits(600, 500, 400, 120)
    diffDrive.setDefaultSpeed(40)
    diffDrive.setDefaultYawRate(120)
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
    aborted = false
    openLoopProfile()
    maxGapMs = 0
    // Anchor BOTH sources at the start: encoder pose is the local
    // frame's origin, and the IMU heading is zeroed to it.
    diffDrive.resetPose()
    diffDrive.seedPose(0, 0, 0)
    diffDrive.emitLine("DBG:tour=robot:profile=open")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        legToward(RTX[i], RTY[i])
        // Checked BEFORE logFix() below: an abort mid-leg must not emit a
        // plausible-looking OCAL: fix for a corner the robot never
        // reached.
        if (aborted) break
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    // How the tour ended: an abort takes priority even if e-stop also
    // tripped at the same moment (the operator's actual intent), then
    // e-stop (diffDrive.probe(1) -- Output.estopped, shims.cpp's
    // diagValue() case 1, no new firmware surface), then a clean finish.
    const reason = aborted ? "abort" : (diffDrive.probe(1) != 0 ? "estop" : "ok")
    diffDrive.emitLine("TOUR:end:" + reason)
    basic.showString("A")
    touring = false
}

// ---- tour A+B: wheels -----------------------------------------------
function tourWheels() {
    if (touring) return
    if (!worldReady()) return
    touring = true
    aborted = false
    openLoopProfile()
    maxGapMs = 0
    diffDrive.resetPose()
    diffDrive.seedPose(START_X, START_Y, START_H)
    diffDrive.emitLine("DBG:tour=wheels:profile=open")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        tickedMove(LEG_CM[i], 0)     // straight leg
        if (aborted) break           // don't also issue the turn below
        tickedMove(0, 90)            // then LEFT
        // Checked BEFORE logFix() below: an abort mid-leg must not emit a
        // plausible-looking OCAL: fix for a corner the robot never
        // reached.
        if (aborted) break
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    // See tourRobot()'s identical comment above for the reason priority.
    const reason = aborted ? "abort" : (diffDrive.probe(1) != 0 ? "estop" : "ok")
    diffDrive.emitLine("TOUR:end:" + reason)
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
    diffDrive.emitLine("DBG:straight=" + cm + ":profile=open")
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
    aborted = false
    // 200 mm/s (stakeholder); 60 cm/s was near the drivetrain ceiling.
    // Accuracy-tuned shaping restored: the earlier "taper too slow"
    // reading was actually the yaw-taper double-count bug
    // (MotionEngine::serviceMove) masking as a profile problem.
    openLoopProfile()
    maxGapMs = 0
    // NO seed here: the host has already seeded the true world pose
    // from the overhead camera (RUN:seedxy), so the robot can start
    // anywhere on the field and simply drive to the first dot.
    diffDrive.emitLine("DBG:tour=world:profile=open")
    logFix("c0")
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        // SCOPE BOUNDARY (sprint 016 ticket 005): goToWorld() runs its
        // OWN internal `while (_tickDrive())` loop inside
        // src/blocks/world.ts, which this sprint does not touch -- so a
        // plain abort here cannot interrupt THIS leg mid-flight, only the
        // next one, via the `if (aborted) break` immediately below. An
        // e-stop, unlike abort, still interrupts the CURRENT leg promptly
        // regardless: ticket 002's serviceMove() fix already makes
        // _tickDrive() return false on the next tick once out.estopped is
        // set, so world.ts's own loop exits on its own with no change
        // needed here.
        diffDrive.goToWorld(CORNERS_X[i], CORNERS_Y[i])
        // Checked BEFORE logFix() below: an abort must not emit a
        // plausible-looking OCAL: fix for a corner the robot never
        // reached (or only partially reached, for THIS leg specifically,
        // per the scope-boundary note above).
        if (aborted) break
        logFix("c" + (i + 1))
    }
    diffDrive.emitLine("GAP:" + maxGapMs)
    // See tourRobot()'s identical comment above for the reason priority.
    const reason = aborted ? "abort" : (diffDrive.probe(1) != 0 ? "estop" : "ok")
    diffDrive.emitLine("TOUR:end:" + reason)
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

// RUN:abort -- unlike every other RUN handler here, this one does NOT
// guard on `touring`: an abort sent while nothing is touring is a
// harmless no-op (nothing ever reads `aborted` outside a tour/tickedMove
// leg), and an abort sent WHILE a tour is running must land even though
// that tour's own handler is mid-execution on its own fiber -- RUN
// handlers already interleave (that is exactly why `touring` exists as a
// re-entrancy guard for the MOVE-issuing handlers in the first place).
// Clear the emergency-stop latch. ESTOP is reachable over the wire but
// nothing was: once latched, every motion verb was silently ignored and
// the ONLY recovery was a reflash or a power cycle. Found the hard way
// on 2026-08-28 -- an ESTOP (sent to catch a runaway) left the robot
// unable to move, mid-regression, with no way back over the link.
//
// diffDrive.clearEmergencyStop() already existed as a block; this just
// gives it a wire-reachable name. Deliberately its OWN verb rather than
// folding it into STOP: STOP is issued constantly and reflexively, and
// making it silently disarm a safety latch would be worse than the
// problem being fixed.
diffDrive.onRun("clearestop", function (arg: number) {
    diffDrive.clearEmergencyStop()
    diffDrive.emitLine("ESTOP:cleared")
})

diffDrive.onRun("abort", function (arg: number) {
    aborted = true
})

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
    closedLoopProfile()
    diffDrive.emitLine("DBG:goto:profile=closed")
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
    openLoopProfile()
    // One-off override: anchor the yaw rate explicitly rather than
    // inherit whatever profile the previous handler left behind (the
    // bug this ticket fixes -- RUN:face used to set ONLY this value).
    // Numerically a no-op today since openLoopProfile()'s own default
    // yaw rate is already 90, but the accuracy profile -- not
    // closedLoopProfile() -- is the right anchor: this handler's job
    // is to close a heading loop precisely.
    diffDrive.setDefaultYawRate(90)
    diffDrive.emitLine("DBG:face:profile=open")
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
    openLoopProfile()
    // One-off override: pivotYawRate (set by RUN:turnrate) replaces
    // openLoopProfile()'s own 90 deg/s. This also makes defaultSpeed
    // deterministically 20 (from openLoopProfile()) instead of
    // stale-inherited from whatever handler ran previously -- harmless
    // for a pure in-place pivot, since pivots do not use defaultSpeed,
    // but now deterministic rather than implicit.
    diffDrive.setDefaultYawRate(pivotYawRate)
    diffDrive.emitLine("DBG:pivot:profile=open")
    maxGapMs = 0
    tickedMove(0, diffDrive.runArg(0))
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("PIVOT:end")
    touring = false
})

// Split move: RUN:arc:<deg>. ONE combined tickedMove(20, deg) call --
// 20 cm translation plus a rotation -- matching the shape
// (`move(20, 180)`) that measured the sprint 015 ticket 005
// phase-handoff defect (twistRef_ unwinding its own pivot at the
// phase 1 -> phase 2 handoff) and its fix. moveX()'s own reduction
// (src/blocks/motion.ts's startGoTo() doc comment) only splits into
// pivot-then-straight for |deg| >= 50 -- below that this is a single
// blended move and never exercises the split-move path at all, so a
// meaningful confirmation run needs |deg| >= 50 (as firmware trusts
// the caller here, same as RUN:pivot, this is not enforced below).
// Deliberately no worldReady()/readWorld() -- same reasoning as
// RUN:pivot: this measures encoder/gyro heading only, no OTOS.
//
// Uses tickArcSampled() (above), not tickedMove(): it captures the
// heading trajectory itself, sampled on this fiber during the move, and
// ARCT: lines after ARC:end dump it -- see that function's own comment
// for why (a telemetry-subscribed capture of this deadlocks the link).
diffDrive.onRun("arc", function (arg: number) {
    if (touring) return
    touring = true
    openLoopProfile()
    diffDrive.emitLine("DBG:arc:profile=open")
    maxGapMs = 0
    tickArcSampled(20, diffDrive.runArg(0))
    diffDrive.emitLine("GAP:" + maxGapMs)
    diffDrive.emitLine("ARC:end")
    emitTrajectory()
    touring = false
})

// Sets the yaw rate the NEXT RUN:pivot command uses: RUN:turnrate:<deg/s>.
// turn_sweep.py sweeps rate against angle with this then RUN:pivot in
// a two-step call, mirroring the old dead numeric two-step shape
// (RUN:57000+rate then RUN:58360+deg). Does not move the robot itself.
diffDrive.onRun("turnrate", function (arg: number) {
    pivotYawRate = diffDrive.runArg(0)
})

// ---- boot identity banner ---------------------------------------------
// Deliberately LAST: every button handler and RUN: verb above is a
// synchronous, near-instant registration call, so putting them first
// costs nothing, while basic.showIcon()/basic.showString() below BLOCK
// this fiber for as long as they take to display. A command arriving
// during that window needs its handler already registered to be
// dispatched at all -- reversing this order would mean a RUN: line
// landing in the first couple of seconds after boot has nothing to
// call. The protocol fiber's own boot banner (the wire-level HELLO
// reply, protocol.cpp's Protocol::run()) runs on its own separate
// CODAL fiber, started from the extension's top-level code ahead of
// this file's own top-level code either way, so it is unaffected by
// this ordering regardless.
// ---- OTOS bring-up: MAIN FIBER, at boot --------------------------------
//
// MEASURED 2026-08-28 (vevov and tovez, over radio AND usb): ANY
// uBit.i2c transaction issued from a RUN handler hangs the board
// permanently -- silent to every verb on both carriers, cured only by a
// reflash. Confirmed against 0x10, the NEZHA BRICK, on a robot whose
// MOTION fiber talks to that same address successfully seconds later
// (connL=1 connR=1, cyc advancing, i2cf=0). Neither the address nor the
// device is at fault; the CALLING CONTEXT is.
//
// Capture: captures/otos-run-handler-i2c-hang-20260828.md.
//
// So RUN:probe could never have started the OTOS, and every world-frame
// path that reached otosBegin() through a RUN handler carried the same
// defect. Bringing it up HERE -- on the main fiber during boot, before
// any RUN handler can be dispatched -- is the fix. The result is emitted
// so `otos=` in STATUS can be checked against the product id that
// produced it, rather than being trusted on its own.
const otosBootId = diffDrive.otosBegin()
diffDrive.emitLine("OTOS:boot:id=" + otosBootId
    + ":connected=" + diffDrive.otosGet(7))
// Apply the lever arm HERE too. applyArm() is pure software
// (setWorldSensorOffset + a log line, no I2C), so it is safe on this
// fiber. It previously ran only via worldReady() inside a RUN handler,
// which is the context that hangs -- so in practice the arm was NEVER
// applied and the OTOS reported the SENSOR's path, injecting
// 2*|arm|*sin(theta/2) of phantom translation into every pivot (~53 mm
// per 90 deg corner at the measured arm, four corners per tour).
if (diffDrive.otosGet(7) != 0) {
    applyArm()
}

// ---- OTOS sampling --------------------------------------------------
//
// otosGet() is a CACHE-ONLY read (wire_adapter.h says so explicitly), so
// without something periodically calling otosRead() the telemetry's
// ox/oy/oh sit at (0,0,0) forever. MEASURED 2026-08-28 on vevov, right
// after the boot init above made otos=1: every one of 153 frames read
// ox=oy=oh=0 while the encoders logged 246 mm of travel. That is also
// what the orange-dots tour recorded and had to chart as "no data".
//
// Sampled from a BACKGROUND fiber, not a RUN handler -- RUN-handler I2C
// hangs the board outright (see the boot init above for the
// measurement). 10 Hz is deliberately slower than the 50 ms telemetry
// tick: wire_adapter.h warns that an OTOS transaction interposed in the
// Nezha encoder's select->read settle window destroys that encoder
// sample, and the two ports share the bus with NO mutual exclusion.
// `i2cf` in STATUS is the counter that would expose it if this starts
// colliding -- watch it before trusting a run.
control.inBackground(function () {
    while (true) {
        diffDrive.readWorld()
        basic.pause(100)
    }
})


// ---- Tour programs, callable over the wire as RUN:<name> --------------
// The same three figures the bench runner drives from .tour files, but
// living ON the robot so a tour can be started with one wire command and
// runs without a host in the loop. Each is written against
// diffDrive.move(distance_cm, yaw_deg) -- "both at once makes an arc".
//
// ARC SEGMENT SIZE IS NOT FREE. moveX() splits any move with a nonzero
// distance and |yaw| >= 50 deg into a pivot THEN a straight, so an arc
// asked for in 90 deg pieces comes out as a SQUARE. Every arc below is
// 45 deg for that reason (measured 2026-09-01: 90 deg pieces drew a
// square, 45 deg pieces drew the circle).

// One constant-curvature arc of `deg` degrees on a circle of `rCm`.
// Arc length = r * theta, which is what move()'s distance argument wants.
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

// RUN:square[:cm] -- the square tour, default 60 cm sides.
function squareTour(sideCm: number) {
    if (touring) return
    touring = true
    aborted = false
    diffDrive.emitLine("DBG:tour=square:side=" + sideCm)
    for (let i = 0; i < 4; i++) {
        basic.showNumber(i + 1)
        tickedMove(sideCm, 0)
        if (aborted) break
        tickedMove(0, 90)
        if (aborted) break
    }
    diffDrive.stopMove()
    touring = false
    basic.showIcon(IconNames.Yes)
}

// RUN:infinity[:radius_cm[:laps]] -- a figure-8: two circles joined at a
// point on their circumferences, the second curving the other way, so the
// robot returns to the crossing point each lap.
function infinityTour(rCm: number, laps: number) {
    if (touring) return
    touring = true
    aborted = false
    diffDrive.emitLine("DBG:tour=infinity:r=" + rCm + ":laps=" + laps)
    for (let lap = 0; lap < laps; lap++) {
        basic.showNumber(lap + 1)
        circleRun(rCm, true)         // lobe A, CCW
        if (aborted) break
        circleRun(rCm, false)        // lobe B, CW
        if (aborted) break
    }
    diffDrive.stopMove()
    touring = false
    basic.showIcon(IconNames.Yes)
}

// RUN:snake[:radius_cm[:bends]] -- a serpentine: alternating
// half-circles, the open cousin of the infinity figure. Each bend is a
// half circle of `rCm` driven as 4 arcs of 45 deg, and consecutive
// bends alternate direction.
//
// NOT a spline, and it used to claim to be one. A spline is a fitted
// curve followed with pure pursuit -- the host drives that one, because
// it needs the sampled path and a steering loop. This is a chain of
// circular arcs, so the name says so.
function snakeTour(rCm: number, bends: number) {
    if (touring) return
    touring = true
    aborted = false
    diffDrive.emitLine("DBG:tour=snake:r=" + rCm + ":bends=" + bends)
    for (let b = 0; b < bends; b++) {
        basic.showNumber(b + 1)
        const ccw = (b % 2) == 0
        for (let i = 0; i < 4; i++) {      // half circle = 4 x 45 deg
            if (aborted) break
            arcSegment(rCm, ccw ? 45 : -45)
        }
        if (aborted) break
    }
    diffDrive.stopMove()
    touring = false
    basic.showIcon(IconNames.Yes)
}

diffDrive.onRun("square", function (arg: number) {
    squareTour(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 60)
})

diffDrive.onRun("infinity", function (arg: number) {
    const r = diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 30
    const laps = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) : 1
    infinityTour(r, laps)
})

// Defaults match the snake tour file: r = 12.5 cm, 4 bends, which
// advances 8r = 100 cm across the field's long axis and swings 2r =
// 25 cm either side. The advance runs PERPENDICULAR to the start
// heading -- the first half circle turns the robot 180 deg, so progress
// is sideways -- so stage it facing the short axis.
diffDrive.onRun("snake", function (arg: number) {
    const r = diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 12.5
    const bends = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) : 4
    snakeTour(r, bends)
})

// RUN:diamond[:cm] -- the square turned 45 deg to the start heading, so
// its legs run diagonally. A 45 deg entry pivot, then the same four
// legs and four corners. Sized smaller than the square because a
// square of side S turned 45 deg spans S*sqrt2 in BOTH axes: 45 cm
// sides span 63.6 cm, which is what fits the field's tight axis.
function diamondTour(sideCm: number) {
    if (touring) return
    touring = true
    aborted = false
    diffDrive.emitLine("DBG:tour=diamond:side=" + sideCm)
    tickedMove(0, 45)                    // enter the diamond
    for (let i = 0; i < 4; i++) {
        if (aborted) break
        basic.showNumber(i + 1)
        tickedMove(sideCm, 0)
        if (aborted) break
        tickedMove(0, 90)
    }
    diffDrive.stopMove()
    touring = false
    basic.showIcon(IconNames.Yes)
}

diffDrive.onRun("diamond", function (arg: number) {
    diamondTour(diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 45)
})

// RUN:circle[:radius_cm[:ccw]] -- one full circle as 8 arcs of 45 deg.
// Driven CCW from a point on its own circumference the centre sits
// 90 deg to the left, so it spans +-r across the start heading and
// 0..2r along it.
function circleTour(rCm: number, ccw: boolean) {
    if (touring) return
    touring = true
    aborted = false
    diffDrive.emitLine("DBG:tour=circle:r=" + rCm + ":ccw=" + (ccw ? 1 : 0))
    circleRun(rCm, ccw)
    diffDrive.stopMove()
    touring = false
    basic.showIcon(IconNames.Yes)
}

diffDrive.onRun("circle", function (arg: number) {
    const r = diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 30
    const ccw = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) != 0 : true
    circleTour(r, ccw)
})

basic.showIcon(IconNames.Rollerskate)
basic.showString(BOOT_ROBOT + " " + BOOT_VERSION)
