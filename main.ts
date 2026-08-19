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

    // MessageBus source id for the wire protocol's RUN:<n> verb -- must
    // match kRunEventSource in protocol.cpp. The C++ handler raises an
    // event with the test number as the event value; handlers
    // registered here dispatch on it.
    const RUN_EVENT_SOURCE = 0x2001

    /**
     * Run code when a RUN:<n> command arrives over the wire protocol
     * (USB serial). Register your test functions against numbers so
     * the bench host can trigger them remotely -- the same functions a
     * button handler can call. The handler receives the test number n.
     * Handlers run on their own fiber, so a long test (a full tour)
     * doesn't block the protocol.
     */
    //% block="on run command $n"
    //% draggableParameters="reporter"
    //% group="Move"
    export function onRunCommand(handler: (n: number) => void): void {
        control.onEvent(RUN_EVENT_SOURCE, 0, function () {
            handler(control.eventValue())
        })
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
}
