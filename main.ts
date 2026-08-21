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
    CrawlPulse = 14
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

    // ================= remote test trigger (RUN verb) =================

    // MessageBus source id for the wire protocol's RUN verb -- must
    // match kRunEventSource in protocol.cpp. An event value cannot
    // carry text, so the C++ handler parks the command's payload in a
    // slot and sends the SLOT as the event value; the dispatcher below
    // reads the text back through runCommandText() and routes it by
    // NAME. The wire therefore reads as what it does -- RUN:pivot:180,
    // not RUN:4 -- and arguments ride along as text instead of being
    // encoded into numeric offsets the way the old numbered vocabulary
    // had to (RUN:30000+us for a servo pulse, and so on).
    const RUN_EVENT_SOURCE = 0x2001

    // Parts of the RUN command currently being dispatched: [0] is the
    // name, [1..] its arguments. Safe as shared state because
    // MessageBus delivers these events one at a time, each after the
    // previous handler returns.
    let runParts: string[] = []
    let runNames: string[] = []
    let runHandlers: ((arg: number) => void)[] = []
    let runAnyHandlers: ((name: string, arg: number) => void)[] = []
    let runWired = false

    function wireRunDispatch(): void {
        if (runWired) return
        runWired = true
        control.onEvent(RUN_EVENT_SOURCE, 0, function () {
            const text = runCommandText(control.eventValue())
            if (text.length == 0) return
            runParts = text.split(":")
            const name = runParts[0]
            for (let i = 0; i < runNames.length; i++) {
                if (runNames[i] == name) runHandlers[i](runArg(0))
            }
            for (let i = 0; i < runAnyHandlers.length; i++) {
                runAnyHandlers[i](name, runArg(0))
            }
        })
    }

    /**
     * Run code when the named command arrives over the wire protocol --
     * `RUN:<name>` or `RUN:<name>:<arg>`, e.g. RUN:pivot:180. Bind your
     * test functions to names so the bench host can trigger them
     * remotely, the same functions a button handler calls. The handler
     * receives the first argument as a number (0 when there is none);
     * further arguments are available from runArg(). Handlers run on
     * their own fiber, so a long test (a full tour) doesn't block the
     * protocol. Names are matched exactly, so keep them lower case.
     * @param name the command name to answer to, eg: "tour"
     */
    //% block="on run %name $arg"
    //% draggableParameters="reporter"
    //% group="Move"
    export function onRun(name: string, handler: (arg: number) => void): void {
        wireRunDispatch()
        runNames.push(name)
        runHandlers.push(handler)
    }

    /**
     * Run code when ANY run command arrives, name-bound or not. Runs
     * after every matching onRun() handler, so it can log or reject
     * unknown names.
     */
    //% block="on run command $name $arg"
    //% draggableParameters="reporter"
    //% group="Move"
    export function onRunCommand(
        handler: (name: string, arg: number) => void): void {
        wireRunDispatch()
        runAnyHandlers.push(handler)
    }

    /**
     * The i-th argument of the run command being handled, as a number.
     * 0 when there is no such argument, or it isn't a number.
     * @param i argument index, 0 being the first after the name, eg: 0
     */
    //% blockHidden=true
    export function runArg(i: number): number {
        const text = runArgText(i)
        if (text.length == 0) return 0
        const value = parseFloat(text)
        return isNaN(value) ? 0 : value
    }

    /** The i-th argument of the run command, as text ("" if absent). */
    //% blockHidden=true
    export function runArgText(i: number): string {
        if (i < 0 || i + 1 >= runParts.length) return ""
        return runParts[i + 1]
    }

    /** How many arguments the run command being handled carries. */
    //% blockHidden=true
    export function runArgCount(): number {
        return runParts.length - 1
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
     * within about 150 ms. This sprint does not supply that tick
     * source; prefer move()/whileMoving() unless you are pairing this
     * with your own driveTick() loop.
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

    // ================= pose ==========================================

    /**
     * Robot x position (forward from start) in cm.
     */
    //% block="pose x (cm)"
    //% group="Pose"
    export function poseX(): number {
        return _poseX() / 10
    }

    /**
     * Robot y position (left from start) in cm.
     */
    //% block="pose y (cm)"
    //% group="Pose"
    export function poseY(): number {
        return _poseY() / 10
    }

    /**
     * Robot heading in degrees, CCW positive.
     */
    //% block="heading (deg)"
    //% group="Pose"
    export function heading(): number {
        return _poseHeading() / 100
    }

    /**
     * Reset the pose to (0, 0, 0).
     */
    //% block="reset pose"
    //% group="Pose"
    export function resetPose(): void {
        _resetPose()
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
    let turnFirstDeg = 50.0      // pivot first beyond this bearing error
    let maxNudges = 6            // bounded arrival retries

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
     * decide where the robot is before each leg. Turns in place first
     * only if the target is far off to the side; otherwise curves to it
     * in one arc. Repeats until inside the arrival tolerance.
     * @param x world x, eg: 60
     * @param y world y, eg: 0
     */
    //% block="go to world x %x cm y %y cm"
    //% group="World"
    export function goToWorld(x: number, y: number): void {
        for (let attempt = 0; attempt <= maxNudges; attempt++) {
            // --- boundary fix: where are we, really? ---
            readWorld()
            const px = worldX()
            const py = worldY()
            const ph = worldHeading() * Math.PI / 180

            const dx = x - px
            const dy = y - py
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist <= arriveTolCm) return       // arrived

            // Target in the robot's own frame (x forward, y left).
            const cos = Math.cos(ph)
            const sin = Math.sin(ph)
            const bx = cos * dx + sin * dy
            const by = -sin * dx + cos * dy
            const bearing = Math.atan2(by, bx)    // [rad] signed

            // --- turn-first: only when badly off-bearing ---
            if (Math.abs(bearing) >= turnFirstDeg * Math.PI / 180) {
                tickedMove(0, bearing * 180 / Math.PI)
                continue    // re-fix, then plan the drive from it
            }

            // --- one constant-curvature arc to the target ---
            // Tangent circle through the body-frame point (bx, by):
            // turn angle theta = 2*atan2(by, bx), radius
            // R = (bx^2+by^2)/(2*by), arc length s = R*theta.
            const theta = 2 * bearing
            let s: number
            if (Math.abs(by) < 0.01) {
                s = bx                            // straight
            } else {
                s = (bx * bx + by * by) / (2 * by) * theta
            }
            tickedMove(s, theta * 180 / Math.PI)
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

    // ================= stopping ======================================

    /**
     * Stop driving (normal stop).
     */
    //% block="stop"
    //% group="Drive"
    export function stop(): void {
        _stopAll()
    }

    /**
     * Emergency stop: latch off until clearEmergencyStop().
     */
    //% block="emergency stop"
    //% group="Drive"
    export function emergencyStop(): void {
        _estopAll()
    }

    /**
     * Clear the emergency-stop latch.
     */
    //% block="clear emergency stop" advanced=true
    //% group="Drive"
    export function clearEmergencyStop(): void {
        _estopClear()
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

    // =========== internal shims (simulator fallback bodies) ==========
    // Hardware uses the C++ in shims.cpp; the bodies below are a
    // minimal kinematic stand-in so programs behave in the browser.

    let simX = 0            // [mm]
    let simY = 0            // [mm]
    let simHeading = 0      // [rad]
    let simVel = 0          // [mm/s]
    let simYawRate = 0      // [rad/s]
    let simLastMs = 0
    let simMoveRemainMm = 0
    let simMoveRemainRad = 0
    let simMoveActive = false

    // Tick-engine sim state (sprint 002): _tickDrive()'s simulator body
    // mirrors shims.cpp's absolute-deadline pacing (tickDrive(), 24 ms
    // cadence) so a simulator-run program is timing-observable the same
    // way hardware is -- an anchored deadline while ticks stay
    // consecutive, re-anchored to "now" after a gap.
    const kSimTickPeriodMs = 24
    let simTickDeadlineMs = 0    // 0 = no tick has run yet
    let simCycleCount = 0
    let simTickOverrunCount = 0

    function simIntegrate(): void {
        const now = control.millis()
        let dt = (now - simLastMs) / 1000
        if (dt < 0 || dt > 0.5) dt = 0
        simLastMs = now
        if (dt == 0) return
        // Capture the velocity/yaw-rate actually in effect for THIS
        // step before any end-of-move zeroing below, and clip this
        // step's own contribution to the fraction of dt actually
        // needed to reach the target -- so a move that finishes
        // partway through a step neither overshoots (crediting the
        // whole step) nor undershoots (crediting none of it). At the
        // old 10 ms poll cadence this distinction was invisible for
        // typical durations (the terminating step happened to land
        // with floating-point room to spare); the new, coarser 24 ms
        // tick cadence (main.ts's _tickDrive()) exposed it as a real,
        // test.ts-square-visible pose drift -- caught by this ticket's
        // own net-zero-pose simulator check.
        const stepVel = simVel
        const stepYawRate = simYawRate
        let stepDt = dt
        if (simMoveActive) {
            const dMm = simVel * dt
            const dRad = simYawRate * dt
            let frac = 1
            if (dMm != 0 && simMoveRemainMm < Math.abs(dMm)) {
                const f = simMoveRemainMm / Math.abs(dMm)
                if (f < frac) frac = f
            }
            if (dRad != 0 && simMoveRemainRad < Math.abs(dRad)) {
                const f = simMoveRemainRad / Math.abs(dRad)
                if (f < frac) frac = f
            }
            if (frac < 0) frac = 0
            stepDt = dt * frac

            simMoveRemainMm -= Math.abs(dMm)
            simMoveRemainRad -= Math.abs(dRad)
            if (simMoveRemainMm <= 0 && simMoveRemainRad <= 0) {
                simMoveActive = false
                simVel = 0
                simYawRate = 0
            }
        }
        const mid = simHeading + stepYawRate * stepDt / 2
        simX += stepVel * stepDt * Math.cos(mid)
        simY += stepVel * stepDt * Math.sin(mid)
        simHeading += stepYawRate * stepDt
    }

    //% shim=diffDrive::setWheels
    function _setWheels(left: int32, right: int32): void {
        simIntegrate()
        simVel = (left + right) / 2
        simYawRate = ((right - left) / 10) / 115  // [rad/s] over track
        simMoveActive = false
    }

    //% shim=diffDrive::driveTwist
    function _driveTwist(speed: int32, yawRate: int32): void {
        simIntegrate()
        simVel = speed
        simYawRate = (yawRate / 100) * Math.PI / 180
        simMoveActive = false
    }

    //% shim=diffDrive::startMove
    function _startMove(distance: int32, yaw: int32, speed: int32,
        yawRate: int32): void {
        simIntegrate()
        simMoveRemainMm = Math.abs(distance)
        simMoveRemainRad = Math.abs(yaw / 100) * Math.PI / 180
        let duration = 0
        if (distance != 0) duration = Math.abs(distance) / speed
        if (yaw != 0) {
            const yawDur = Math.abs(yaw) / yawRate
            if (yawDur > duration) duration = yawDur
        }
        if (duration <= 0) return
        simVel = distance / duration
        simYawRate = ((yaw / 100) * Math.PI / 180) / duration
        simMoveActive = true
    }

    //% shim=diffDrive::updateMove
    function _updateMove(): boolean {
        simIntegrate()
        return simMoveActive
    }

    // Simulator body for the tick engine: integrate one step (kinematic
    // stand-in for kernel.step()+serviceMove()), then self-pace to the
    // next absolute 24 ms schedule with basic.pause(), same anchoring
    // rule as tickDrive() in shims.cpp -- so blocking/loop forms built
    // on `while (_tickDrive())` behave the same way in the browser as
    // on hardware. Always steps (simIntegrate()), even with no move
    // active, matching the hardware contract that continuous-mode
    // driving depends on. Returns post-step move-active state.
    //% shim=diffDrive::tickDrive
    function _tickDrive(): boolean {
        simIntegrate()
        simCycleCount += 1
        const moveActive = simMoveActive

        const now = control.millis()
        const consecutive = simTickDeadlineMs != 0 &&
            now < simTickDeadlineMs + kSimTickPeriodMs
        const deadline = consecutive ?
            simTickDeadlineMs + kSimTickPeriodMs : now + kSimTickPeriodMs
        simTickDeadlineMs = deadline

        const wait = deadline - control.millis()
        if (wait > 0) {
            basic.pause(wait)
        } else {
            simTickOverrunCount += 1
        }
        return moveActive
    }

    // Minimal simulator stand-in for cycleStat() -- there is no real
    // fiber/cycle timing to observe in the browser simulator, so this
    // reports the nominal cadence plus the sim's own tick/overrun
    // counters (kept for parity with hardware's field layout) rather
    // than measured timing.
    //% shim=diffDrive::cycleStat
    function _cycleStat(which: int32): int32 {
        switch (which) {
            case 0: return kSimTickPeriodMs * 1000  // nominal period [us]
            case 1: return 0                        // busy [us]: not modeled
            case 2: return simTickOverrunCount
            case 3: return simCycleCount
            default: return 0
        }
    }

    //% shim=diffDrive::progress
    function _progress(): int32 {
        simIntegrate()
        return simMoveActive ? 500 : 1000
    }

    //% shim=diffDrive::endMove
    function _endMove(): void {
        simIntegrate()
        simMoveActive = false
        simVel = 0
        simYawRate = 0
    }

    //% shim=diffDrive::stopAll
    function _stopAll(): void {
        simIntegrate()
        simMoveActive = false
        simVel = 0
        simYawRate = 0
    }

    //% shim=diffDrive::estopAll
    function _estopAll(): void {
        _stopAll()
    }

    //% shim=diffDrive::estopClear
    function _estopClear(): void { }

    //% shim=diffDrive::poseX
    function _poseX(): int32 {
        simIntegrate()
        return Math.round(simX)
    }

    //% shim=diffDrive::poseY
    function _poseY(): int32 {
        simIntegrate()
        return Math.round(simY)
    }

    //% shim=diffDrive::poseHeading
    function _poseHeading(): int32 {
        simIntegrate()
        return Math.round(simHeading * 180 / Math.PI * 100)
    }

    //% shim=diffDrive::resetPose
    function _resetPose(): void {
        simIntegrate()
        simX = 0
        simY = 0
        simHeading = 0
    }

    //% shim=diffDrive::setGeometry
    function _setGeometry(trackWidth: int32, calib: int32): void { }

    //% shim=diffDrive::setKernelValue
    function _setKernelValue(field: int32, value: int32): void { }

    //% shim=diffDrive::startProtocol
    function _startProtocol(): void { }

    // ---- OTOS (zeguz bench bring-up) -- shim-only surface, no blocks.
    // Call only from the fiber that calls driveTick(): an OTOS I2C
    // transaction interposed in the Nezha encoder's select->read
    // window destroys the encoder sample. Sim fallbacks report a
    // sensor that is absent.

    /**
     * Read one diagnostic value. See diagValue() in shims.cpp for the
     * index list: 10/11 encoder positions, 12/13 applied duty x100,
     * 14/15 velocities, 6/7 wedge suspicion.
     */
    //% shim=diffDrive::probe
    export function probe(what: int32): number { return 0 }

    /**
     * End-of-move shaping. Bigger tapers and lower floors trade time
     * for accuracy; a closed-loop caller that takes a fresh fix before
     * every move should spend far less time on it. 0 leaves unchanged.
     */
    //% shim=diffDrive::setTaperWindows
    export function setTaperWindows(distCounts: int32, yawCounts: int32): void { }

    //% shim=diffDrive::setTaperFloors
    export function setTaperFloors(distPct: int32, turnPct: int32): void { }

    //% shim=diffDrive::setRampMs
    export function setRampMs(ms: int32): void { }

    //% shim=diffDrive::otosBegin
    export function otosBegin(): number { return 0 }

    //% shim=diffDrive::otosRead
    export function otosRead(): boolean { return false }

    /**
     * Cached OTOS value: 0=x [0.1mm] 1=y [0.1mm] 2=heading [cdeg]
     * 3=vx [mm/s] 4=vy [mm/s] 5=omega [cdeg/s] 6=product id
     * 7=connected 8=IMU-cal samples remaining
     */
    //% shim=diffDrive::otosGet
    export function otosGet(what: int32): number { return 0 }

    //% shim=diffDrive::otosZero
    export function otosZero(): void { }

    //% shim=diffDrive::otosCalibrate
    export function otosCalibrate(samples: int32): void { }

    //% shim=diffDrive::otosSetOffset
    export function otosSetOffset(x: int32, y: int32, yaw: int32): void { }

    /**
     * Write a line to BOTH transports -- USB serial and the wireless
     * link. Test programs use this instead of serial.writeLine, which
     * reaches the cable only, and the cable only reaches the bench
     * stand where the wheels are off the ground.
     *
     * (Do not write the word r-a-d-i-o followed by a full stop in this
     * file: PXT scans the TypeScript for `<name>.` to auto-add package
     * dependencies, and a prose mention makes it demand a `radio`
     * package this project does not use -- it drives CODAL's radio
     * directly from radio_transport.cpp.)
     */
    //% shim=diffDrive::emitLine
    export function emitLine(text: string): void {
        serial.writeLine(text)
    }

    // Text of the RUN command a run event refers to (the event value is
    // the slot protocol.cpp parked it in). The simulator has no wire, so
    // no run event ever fires there and this body is never reached.
    //% shim=diffDrive::runCommandText
    function runCommandText(slot: int32): string {
        return ""
    }

    //% shim=diffDrive::seedPose
    function _seedPose(x: int32, y: int32, heading: int32): void {
        simIntegrate()
        simX = x
        simY = y
        simHeading = heading / 100 * Math.PI / 180
    }
}
