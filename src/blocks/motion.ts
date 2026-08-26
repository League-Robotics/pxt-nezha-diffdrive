/**
 * DiffDrive — closed-loop differential drive for the Nezha brick.
 *
 * Student-facing units: cm, cm/s, degrees, degrees/s. Positive yaw is
 * counter-clockwise (right wheel forward). Pose is (x, y, heading) in
 * robot start coordinates: x forward, y left.
 *
 * There is no dedicated motor fiber: the robot only moves while
 * something keeps ticking the control loop (driveTick(), or an
 * internally-ticking block like move()/goTo()) -- see driveTick()'s
 * own doc comment. The functions exported below are the real
 * block-API bodies, calling into the hardware shim layer (the .cpp
 * files); the browser-simulator fallbacks live in sim.ts.
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

    // weight= below (through whileGoingTo()) pins Drive/Move toolbox
    // order to the pre-split baseline (sprint 012 ticket 007) -- without
    // it, order ties break on file layout, which the module split
    // changed.

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
    //% group="Drive" weight=200
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
    //% group="Drive" weight=190
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
    //% group="Move" weight=200
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
    //% group="Move" weight=170
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
    //% group="Move" weight=160
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
    //% group="Move" advanced=true weight=150
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
    //% group="Move" advanced=true weight=140
    export function startGoTo(x: number, y: number): void {
        // Calls goToR() directly (the //%-exposed engineGoToRArmed/
        // engineSetGoToDeadline shim pair -- split in two, sprint 015
        // ticket 006, because a single five-parameter shim crashes the
        // PXT packager with TS9200; see sim.ts's _setGoToDeadline()/
        // _goToR() comments) instead of reducing to (distance, yaw) and
        // going through startMove()/moveX(): moveX()'s own >=50 deg
        // split reissues an arc-length/arc-angle pair as
        // pivot-then-straight, which lands at a DIFFERENT point than
        // the arc that pair was computed for. goToR() owns its own
        // bearing-then-chord split and short-arc wrap instead
        // (motion_engine.cpp), reaching (x, y) exactly.
        if (x == 0 && y == 0) return
        const xMm = Math.round(x * 10)
        const yMm = Math.round(y * 10)
        const speedMmS = Math.round(defaultSpeed * 10)
        // arrive: 1 mm -- tight enough that "on target" means on
        // target, loose enough not to fight int-mm rounding.
        const arriveMm = 1
        // timeout: goToR() drives a <=180 deg pivot (its own short-arc
        // wrap) THEN the straight-line chord -- two SEQUENTIAL phases,
        // not one blended segment like startMove()'s reconciliation, so
        // their worst-case durations are summed, not maxed, using the
        // same defaultYawRate/defaultSpeed startMove() itself would use
        // for those two axes; +1500 ms mirrors startMove()'s own
        // end-of-move taper backstop (shims.cpp).
        const chordCm = Math.sqrt(x * x + y * y)
        const pivotS = 180 / defaultYawRate
        const straightS = chordCm / defaultSpeed
        const timeoutMs = Math.round((pivotS + straightS) * 1000) + 1500
        // Must precede _goToR() immediately -- see
        // Rig::pendingGoToDeadlineMs_'s comment (shims.cpp) for the
        // one-shot handoff contract this pair relies on.
        _setGoToDeadline(timeoutMs)
        _goToR(xMm, yMm, speedMmS, arriveMm)
    }

    /**
     * Is a move currently running? Calls _updateMove()
     * (MotionEngine::serviceMove() in the hardware shim), which
     * re-scales the taper/ramp, reissues the drive command, and can
     * end the move at its deadline backstop -- so this call DOES
     * advance the move as a side effect of checking it, not "state
     * only". It does not itself step the kernel (that is driveTick()'s
     * job): without a concurrent driveTick() loop, a move polled only
     * through isMoving() still stalls and the safety watchdog stops it
     * -- see startMove()'s doc comment for that gap.
     */
    //% block="moving?"
    //% group="Move" weight=130
    export function isMoving(): boolean {
        return _updateMove()
    }

    /**
     * Fraction of the current move completed, 0 to 1. Checks state
     * only -- same tick-model gap as isMoving(): it does not itself
     * advance the move (see startMove()'s doc comment).
     */
    //% block="move progress"
    //% group="Move" advanced=true weight=120
    export function moveProgress(): number {
        return _progress() / 1000
    }

    /**
     * Stop the robot now -- including a continuous drive command in
     * progress (setWheelSpeeds()/driveTwist()), the same full-stop
     * contract stop() has (stop.ts). A no-op if the robot was already
     * idle. Note: under the tick model, a move started with
     * startMove()/startGoTo() and never paired with a driveTick() loop
     * will not have progressed anyway (see startMove()'s doc comment).
     */
    //% block="stop move"
    //% group="Move" weight=110
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
    //% group="Move" weight=100
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
    //% group="Move" weight=90
    export function whileGoingTo(x: number, y: number,
        body: (x: number, y: number, heading: number) => void): void {
        startGoTo(x, y)
        while (_tickDrive()) {
            body(poseX(), poseY(), heading())
        }
        _endMove()
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
