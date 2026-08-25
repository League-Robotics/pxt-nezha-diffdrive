/**
 * DiffDrive — closed-loop differential drive for the Nezha brick.
 *
 * Student-facing units: cm, cm/s, degrees, degrees/s. Positive yaw is
 * counter-clockwise (right wheel forward). Pose is (x, y, heading) in
 * robot start coordinates: x forward, y left.
 *
 * The wheel servo runs in its own fiber on the micro:bit (the DiffDrive
 * kernel, 24 ms cadence); every command below just talks to it. The
 * hardware implementations live in the .cpp files; the function bodies
 * here are the browser-simulator fallbacks.
 */

enum ConfigField {
    //% block="max duty %"
    MaxDuty = 0,
    //% block="full-duty wheel speed"
    FullDutyVelocity = 1,
    //% block="PID kp"
    Kp = 2,
    //% block="PID ki"
    Ki = 3,
    //% block="PID integral limit"
    IMax = 4,
    //% block="accel feedforward"
    Kaff = 5,
    //% block="PID output limit"
    PidMax = 6,
    //% block="twist hold gain"
    TwistHoldGain = 7,
    //% block="speed floor"
    SpeedFloor = 8,
    //% block="position error limit"
    PosErrMax = 9,
    //% block="stall speed"
    StallSpeed = 10,
    //% block="stall demand"
    StallDemand = 11,
    //% block="stall window ms"
    StallWindow = 12,
    //% block="lambda enabled"
    LambdaEnabled = 13,
    //% block="crawl pulse"
    CrawlPulse = 14,
    //% block="default cruise speed"
    DefaultCruise = 15,
    //% block="rotational slip"
    RotationalSlip = 16,
    //% block="clear stall latch"
    StallClear = 17
}

//% color=#0f9c5a icon="" block="DiffDrive"
namespace diffDrive {
    let defaultSpeed = 15      // [cm/s]
    let defaultYawRate = 90    // [deg/s]

    // Start the wire-protocol loop (its own CODAL fiber -- see
    // protocol.h) as soon as this extension's code loads, independent
    // of whether any block below is ever placed in a user's program.
    // This is what makes the boot/HELLO identity banner go out
    // "without any host request" (sprint.md SUC-001). Idempotent (the
    // underlying Protocol object guards itself), and a no-op in the
    // simulator (see the shim body below) -- there's no serial link or
    // fiber scheduler to start there.
    _startProtocol()

    // ================= public API: velocity commands =================

    /**
     * Set the two wheel speeds. Continuous-mode command: the robot only
     * moves while something keeps ticking the control loop -- run a
     * `while (diffDrive.driveTick())` loop after calling this to keep
     * the robot moving. If nothing ticks (e.g. your loop exits or the
     * program pauses), a safety watchdog stops the robot within about
     * 150 ms; a fresh move or tick loop resumes right away, no
     * clear-emergency-stop needed. (Position-mode blocks like move()
     * and whileMoving() tick internally, so this only matters for
     * setWheelSpeeds()/driveTwist().)
     * @param left left wheel speed, eg: 15
     * @param right right wheel speed, eg: 15
     */
    //% block="set wheel speeds left %left right %right cm/s"
    //% left.min=-50 left.max=50 right.min=-50 right.max=50
    //% group="Drive"
    export function setWheelSpeeds(left: number, right: number): void {
        _setWheels(Math.round(left * 10), Math.round(right * 10))
    }

    /**
     * Drive with a body speed and yaw rate. Continuous-mode command:
     * the robot only moves while something keeps ticking the control
     * loop -- run a `while (diffDrive.driveTick())` loop after calling
     * this to keep the robot moving. If nothing ticks, a safety
     * watchdog stops the robot within about 150 ms; a fresh move or
     * tick loop resumes right away, no clear-emergency-stop needed.
     * @param speed forward speed, eg: 15
     * @param yawRate turn rate CCW+, eg: 0
     */
    //% block="drive %speed cm/s turning %yawRate deg/s"
    //% speed.min=-50 speed.max=50 yawRate.min=-180 yawRate.max=180
    //% group="Drive"
    export function driveTwist(speed: number, yawRate: number): void {
        _driveTwist(Math.round(speed * 10), Math.round(yawRate * 100))
    }

    // ================= continuous-mode ticking ========================

    /**
     * Advance one control cycle. Run this in a loop --
     * `while (diffDrive.driveTick())` -- after setWheelSpeeds()/
     * driveTwist() to keep the robot moving; the robot only drives
     * while this (or an internally-ticking block like move()) keeps
     * getting called. Self-paces to the drive's control cadence
     * (about 24 ms), so don't add your own pause() in the loop.
     */
    //% block="drive tick"
    //% group="Move"
    export function driveTick(): boolean {
        return _tickDrive()
    }

    // ================= position-mode moves: blocking =================

    /**
     * Drive a distance while turning a yaw angle, then stop. Both at
     * once makes an arc. Waits until the move is done.
     * @param distance distance to travel, eg: 20
     * @param yaw angle to turn CCW+, eg: 0
     */
    //% block="move %distance cm turning %yaw degrees"
    //% group="Move"
    export function move(distance: number, yaw: number): void {
        startMove(distance, yaw)
        while (_tickDrive());
    }

    /**
     * Drive a curved path to a point in robot coordinates, then stop.
     * x is forward, y is left. Waits until the move is done.
     * @param x forward distance, eg: 20
     * @param y leftward distance, eg: 10
     */
    //% block="go to x %x cm y %y cm"
    //% group="Move"
    export function goTo(x: number, y: number): void {
        startGoTo(x, y)
        while (_tickDrive());
    }

    // ================= position-mode moves: async ====================

    /**
     * Start a move without waiting. Poll isMoving() / call stopMove().
     * KNOWN GAP under the tick model: this poll pattern does not, by
     * itself, advance the move -- something must still call
     * driveTick() (or otherwise tick the control loop) concurrently,
     * or the move never progresses and the safety watchdog stops it
     * within about 150 ms. Nothing supplies that tick automatically;
     * prefer move()/whileMoving() unless you are pairing this with your
     * own driveTick() loop.
     */
    //% block="start move %distance cm turning %yaw degrees"
    //% group="Move" advanced=true
    export function startMove(distance: number, yaw: number): void {
        _startMove(Math.round(distance * 10), Math.round(yaw * 100),
            Math.round(defaultSpeed * 10),
            Math.round(defaultYawRate * 100))
    }

    /**
     * Start a go-to without waiting. Same tick-model gap as
     * startMove() -- see its doc comment: without a concurrent
     * driveTick() loop, this does not progress on its own.
     */
    //% block="start go to x %x cm y %y cm"
    //% group="Move" advanced=true
    export function startGoTo(x: number, y: number): void {
        // Constant-curvature arc from the robot origin (heading 0,
        // along +x) through (x, y): turn angle theta = 2*atan2(y, x);
        // arc length s = R*theta with R = (x^2+y^2)/(2y); straight
        // line when y ~ 0.
        if (x == 0 && y == 0) return
        const theta = 2 * Math.atan2(y, x)   // [rad] signed
        let s: number
        if (Math.abs(y) < 0.01) {
            s = x                             // [cm] straight (sign = dir)
        } else {
            const radius = (x * x + y * y) / (2 * y)  // [cm] signed
            s = radius * theta                // [cm] signed arc length
        }
        startMove(s, theta * 180 / Math.PI)
    }

    /**
     * Is a move currently running? Checks state only -- it does not
     * itself advance the move. Under the tick model, a move started
     * with startMove()/startGoTo() only progresses while something
     * else ticks the control loop (e.g. a concurrent driveTick()
     * loop); see startMove()'s doc comment.
     */
    //% block="moving?"
    //% group="Move"
    export function isMoving(): boolean {
        return _updateMove()
    }

    /**
     * Fraction of the current move completed, 0 to 1. Checks state
     * only -- same tick-model gap as isMoving(): it does not itself
     * advance the move (see startMove()'s doc comment).
     */
    //% block="move progress"
    //% group="Move" advanced=true
    export function moveProgress(): number {
        return _progress() / 1000
    }

    /**
     * End the current move now (no-op if none). Note: under the tick
     * model, a move started with startMove()/startGoTo() and never
     * paired with a driveTick() loop will not have progressed anyway
     * (see startMove()'s doc comment) -- this just clears the
     * move-engine state.
     */
    //% block="stop move"
    //% group="Move"
    export function stopMove(): void {
        _endMove()
    }

    // ================= loop forms ====================================

    /**
     * Run code while moving. The body gets the live pose each
     * iteration; when the loop exits — move complete or stopMove() —
     * the move is over.
     */
    //% block="while moving %distance cm turning %yaw degrees"
    //% draggableParameters="reporter" handlerStatement=1
    //% group="Move"
    export function whileMoving(distance: number, yaw: number,
        body: (x: number, y: number, heading: number) => void): void {
        startMove(distance, yaw)
        while (_tickDrive()) {
            body(poseX(), poseY(), heading())
        }
        _endMove()
    }

    /**
     * Run code while going to a point. Same contract as whileMoving.
     */
    //% block="while going to x %x cm y %y cm"
    //% draggableParameters="reporter" handlerStatement=1
    //% group="Move"
    export function whileGoingTo(x: number, y: number,
        body: (x: number, y: number, heading: number) => void): void {
        startGoTo(x, y)
        while (_tickDrive()) {
            body(poseX(), poseY(), heading())
        }
        _endMove()
    }

    // ================= world pose (OTOS) =============================
    // The OTOS optical tracking sensor is the WORLD-POSE AUTHORITY, and
    // it is consulted at MOVE BOUNDARIES ONLY (stakeholder doctrine,
    // 2026-08-20): a move runs entirely on encoder odometry; the sensor
    // says where the robot actually ended up, and the NEXT move is
    // planned from that fix. It never steers a move in flight.
    //
    // Every read here is a live I2C burst, so these must be called from
    // the same fiber that calls driveTick() -- never concurrently with
    // one (an OTOS transaction landing inside the Nezha encoder's
    // select->read window destroys that encoder sample).

    /**
     * Start the OTOS sensor. Returns true if it answered.
     * Call once at program start, robot held still.
     */
    //% block="start world tracking"
    //% group="World"
    export function startWorldTracking(): boolean {
        return otosBegin() == 0x5F
    }

    /**
     * Is the world sensor present and answering?
     */
    //% block="world tracking ready?"
    //% group="World"
    export function worldTrackingReady(): boolean {
        return otosGet(7) != 0
    }

    /**
     * Declare where the robot is right now, in world coordinates.
     * Sets BOTH pose sources -- the world sensor and the wheel
     * odometry -- so they start agreed.
     * @param x world x, eg: 0
     * @param y world y, eg: 0
     * @param heading world heading in degrees CCW, eg: 0
     */
    //% block="set world pose to x %x cm y %y cm heading %heading deg"
    //% group="World"
    export function seedPose(x: number, y: number,
        heading: number): void {
        _seedPose(Math.round(x * 10), Math.round(y * 10),
            Math.round(heading * 100))
    }

    /**
     * Take a fresh fix from the world sensor. Returns false if the
     * sensor did not answer; the last good values are kept.
     */
    //% block="read world position"
    //% group="World"
    export function readWorld(): boolean {
        return otosRead()
    }

    /**
     * World x from the most recent fix, in cm.
     */
    //% block="world x (cm)"
    //% group="World"
    export function worldX(): number {
        return otosGet(0) / 100
    }

    /**
     * World y from the most recent fix, in cm.
     */
    //% block="world y (cm)"
    //% group="World"
    export function worldY(): number {
        return otosGet(1) / 100
    }

    /**
     * World heading from the most recent fix, in degrees CCW.
     */
    //% block="world heading (deg)"
    //% group="World"
    export function worldHeading(): number {
        return otosGet(2) / 100
    }

    /**
     * Recalibrate the sensor's gyro bias. The robot must be parked and
     * completely still for about a second.
     */
    //% block="calibrate world sensor" advanced=true
    //% group="World"
    export function calibrateWorldSensor(): void {
        otosCalibrate(0)
        basic.pause(800)
    }

    /**
     * Where the sensor sits relative to the robot's centre of rotation
     * (x forward, y left, cm) and its own mounting rotation (degrees).
     * Measured by the lever-arm calibration, then set once at startup.
     */
    //% block="set world sensor offset x %x cm y %y cm yaw %yaw deg"
    //% group="World" advanced=true
    export function setWorldSensorOffset(x: number, y: number,
        yaw: number): void {
        otosSetOffset(Math.round(x * 100), Math.round(y * 100),
            Math.round(yaw * 100))
    }

    // ---- goToWorld ---------------------------------------------------
    // Drive to a world point, planning from OTOS fixes taken BETWEEN
    // moves. Shaped after the v6 GOTO verb (protocol-v6-spec.md 5.3:
    // target, speed, arrival tolerance, required timeout) and after the
    // reference firmware's navigator, with one deliberate difference
    // the stakeholder specified: NO mid-move retargeting. Each move is
    // planned from a fresh fix and then runs to completion on encoder
    // odometry; a small bearing error is absorbed by yawing WHILE
    // driving (the arc), not by steering corrections in flight.

    let arriveTolCm = 1.0        // [cm] v6 GOTO `arrive`
    // Pivot first beyond this bearing error. 12 deg, NOT the 50 this
    // started at: a capped arc physically cannot reach a target that is
    // meaningfully off-bearing -- it drives a bounded curve and lands
    // short, which left the tour stopping partway to three of four
    // corners. Pointing at the target first makes every drive nearly
    // straight, and that is what actually hit the dots (0.7-12.7 cm
    // when it was done host-side; this moves it onto the robot).
    // Anything under 12 deg is left to curve out over the leg.
    let turnFirstDeg = 12.0

    /**
     * How close counts as "arrived", in cm.
     * @param tol eg: 1
     */
    //% block="set arrival tolerance %tol cm" advanced=true
    //% group="World"
    export function setArrivalTolerance(tol: number): void {
        arriveTolCm = Math.max(0.1, tol)
    }

    /**
     * Drive to a point in WORLD coordinates, using the world sensor to
     * decide where the robot is before the leg. Turns in place first
     * only if the target is far off to the side; otherwise curves to it
     * in one arc. ONE PASS: drives the leg and stops, whether or not it
     * lands inside the arrival tolerance -- it does not loop or creep
     * up on the target. Any remaining error is inherited by the next
     * call/hop, which plans fresh from wherever the robot actually is.
     * @param x world x, eg: 60
     * @param y world y, eg: 0
     */
    //% block="go to world x %x cm y %y cm"
    //% group="World"
    export function goToWorld(x: number, y: number): void {
        // ONE PASS. Drive at the point, get as close as the leg gets,
        // stop. No arrival nudging, no creeping up on it, no squaring
        // up -- iterating at the destination is what turned a tour into
        // 44 s of lurch-and-sit, and it buys accuracy the next hop can
        // absorb for free.
        //
        // Whatever error this leg ends with is INHERITED by the next
        // one, which plans from wherever the robot actually is. Over a
        // multi-hop route that converges; correcting in place does not,
        // it just costs time and looks awful.
        //
        // The OTOS is read here, on the robot. That is not the camera:
        // the overhead camera is a diagnostic and never drives a leg.
        readWorld()
        const px = worldX()
        const py = worldY()
        let ph = worldHeading() * Math.PI / 180

        let dx = x - px
        let dy = y - py
        if (Math.sqrt(dx * dx + dy * dy) <= arriveTolCm) return

        let bx = Math.cos(ph) * dx + Math.sin(ph) * dy
        let by = -Math.sin(ph) * dx + Math.cos(ph) * dy
        let bearing = Math.atan2(by, bx)

        // A target well off the bow needs a pivot first -- an arc to a
        // point abeam is a semicircle that leaves the field. This is
        // the ONE re-measure in the pass, and only because the pivot
        // itself changes the geometry the drive is planned from.
        if (Math.abs(bearing) >= turnFirstDeg * Math.PI / 180) {
            tickedMove(0, bearing * 180 / Math.PI)
            readWorld()
            ph = worldHeading() * Math.PI / 180
            dx = x - worldX()
            dy = y - worldY()
            bx = Math.cos(ph) * dx + Math.sin(ph) * dy
            by = -Math.sin(ph) * dx + Math.cos(ph) * dy
            bearing = Math.atan2(by, bx)
        }

        // Curve out the residual bearing -- but CAP THE CURVATURE.
        //
        // theta = 2*bearing, so a bearing still large after the pivot
        // becomes a half-circle: measured on vevov, a leg with 55 deg
        // of residual drove a 110 deg arc and finished 23 cm from where
        // it started while the target was 60 cm away. Legs that began
        // nearly on-bearing were fine, which is exactly this signature.
        //
        // Capping keeps the leg a gentle curve that covers the straight
        // line distance to the target. Any bearing beyond the cap is
        // simply left for the next hop to absorb, which is the same
        // principle as not pivoting twice.
        const dist = Math.sqrt(dx * dx + dy * dy)
        const kMaxArc = 25 * Math.PI / 180
        let b = bearing
        if (b > kMaxArc) b = kMaxArc
        if (b < -kMaxArc) b = -kMaxArc
        if (Math.abs(b) < 0.01) {
            tickedMove(dist, 0)
        } else {
            // Chord `dist` subtending 2b: R = dist / (2 sin b), arc = R*2b
            const radius = dist / (2 * Math.sin(b))
            tickedMove(radius * 2 * b, 2 * b * 180 / Math.PI)
        }
    }

    // Shared runner for goToWorld's legs: start the move, then tick it
    // to completion on THIS fiber (the same fiber that reads the OTOS,
    // so the two can never interleave on the I2C bus).
    function tickedMove(distance: number, yaw: number): void {
        if (distance == 0 && yaw == 0) return
        startMove(distance, yaw)
        while (_tickDrive());
    }

    // ================= configuration =================================

    /**
     * Default speed for move/goTo blocks.
     * @param speed eg: 15
     */
    //% block="set default speed %speed cm/s" advanced=true
    //% group="Setup"
    export function setDefaultSpeed(speed: number): void {
        defaultSpeed = Math.max(1, speed)
    }

    /**
     * Default turn rate for move/goTo blocks.
     * @param yawRate eg: 90
     */
    //% block="set default turn rate %yawRate deg/s" advanced=true
    //% group="Setup"
    export function setDefaultYawRate(yawRate: number): void {
        defaultYawRate = Math.max(1, yawRate)
    }

    /**
     * Distance between the wheels, in cm.
     * @param width eg: 11.5
     */
    //% block="set track width %width cm" advanced=true
    //% group="Setup"
    export function setTrackWidth(width: number): void {
        _setGeometry(Math.round(width * 100), 0)
    }

    /**
     * Wheel travel per shaft degree, in mm/degree.
     * @param calib eg: 0.7837
     */
    //% block="set wheel calibration %calib mm/deg" advanced=true
    //% group="Setup"
    export function setWheelCalibration(calib: number): void {
        _setGeometry(0, Math.round(calib * 10000))
    }

    /**
     * Advanced: set a kernel configuration value directly.
     */
    //% block="set config %field to %value" advanced=true
    //% group="Setup"
    export function setConfigValue(field: ConfigField,
        value: number): void {
        _setKernelValue(field, Math.round(value * 1000))
    }

}
