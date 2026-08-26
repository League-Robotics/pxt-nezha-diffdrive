namespace diffDrive {
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

    // E-stop latch (sprint 007 ticket 004, closes R-13/BLK-07): mirrors
    // hardware's estopLatch_ (diffdrive.h/.cpp). Set by _estopAll(),
    // cleared only by _estopClear(); gates _setWheels()/_driveTwist()/
    // _startMove() at INTAKE, mirroring checkCommandable()'s
    // Status::kRefusedEstopped gate -- not a per-tick override like
    // step()'s own `effective = kModeNeutral` (diffdrive.cpp), because
    // nothing else in this simulator can introduce velocity between
    // calls, so intake refusal alone is sufficient. _stopAll() (plain
    // "stop") deliberately never touches this latch, the same
    // stop-vs-latch distinction shims.cpp's deliverStopNow() documents
    // for hardware.
    let simEstopped = false

    // Tick-engine sim state: _tickDrive()'s simulator body mirrors
    // shims.cpp's absolute-deadline pacing (tickDrive(), 24 ms
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
        // Capture the velocity/yaw-rate in effect for THIS step before
        // any end-of-move zeroing below, and clip this step's own
        // contribution to the fraction of dt actually needed to reach
        // the target, so a move that finishes partway through a step
        // neither overshoots nor undershoots.
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
    export function _setWheels(left: int32, right: int32): void {
        simIntegrate()
        if (simEstopped) return
        simVel = (left + right) / 2
        // Differential-drive kinematics: omega [rad/s] = (v_right -
        // v_left) [mm/s] / trackWidth [mm] -- the same relation
        // _driveTwist() below applies in reverse (its hardware shim
        // computes `twistMmS = yawRad * 0.5 * effectiveTrackWidth()`,
        // shims.cpp), and the divisor hardware itself uses via
        // effectiveTrackWidth() (motion_engine.h). 115 here is this
        // simulator's fixed stand-in for the caliper-measured
        // trackWidth_ (114.2 mm, motion_engine.h) -- setGeometry() is
        // a no-op in the simulator (see _setGeometry below), so there
        // is no live value to read. (Previously divided by 10 first
        // as well, an erroneous effective 1150 mm track that turned
        // 10x too slowly -- R-12/BLK-06.)
        simYawRate = (right - left) / 115  // [rad/s]
        simMoveActive = false
    }

    //% shim=diffDrive::driveTwist
    export function _driveTwist(speed: int32, yawRate: int32): void {
        simIntegrate()
        if (simEstopped) return
        simVel = speed
        simYawRate = (yawRate / 100) * Math.PI / 180
        simMoveActive = false
    }

    //% shim=diffDrive::startMove
    export function _startMove(distance: int32, yaw: int32, speed: int32,
        yawRate: int32): void {
        simIntegrate()
        if (simEstopped) return
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
    export function _updateMove(): boolean {
        simIntegrate()
        return simMoveActive
    }

    // [mm] [mm] [mm/s] [mm] [ms] -- simulator stand-in for
    // MotionEngine::goToR()'s arc reduction (motion_engine.cpp): bearing
    // = atan2(y, x), turn angle theta = 2*bearing wrapped to the short
    // arc (|theta| <= pi, same wrap goToR() applies, KERN-03) so a
    // target behind the robot turns the short way, not almost a full
    // circle. Unlike hardware, this simulator has no wheel-duty
    // constraint forcing goToR()'s own >=50 deg pivot-then-straight
    // split (KERN-02) -- blending the whole arc as one segment, the same
    // way _startMove() already blends distance+yaw, reaches (x, y)
    // exactly, so no split is needed here. `timeout` is a hardware-only
    // deadline backstop (MotionEngine::goToR()'s header comment);
    // nothing can strand a move in this simulator, so it is unused.
    // Params typed `number`, not `int32` like this file's older
    // shim-fallback functions -- int32 locals/params on a function with
    // a TS body fail the JS->Blocks decompiler with TS9256; the native
    // shim ABI is governed by the C++ signature, not this declaration,
    // so `number` here is hardware-safe (int32-sim-params-break-blocks-
    // conversion.md, which still needs to sweep this file's existing
    // int32 functions -- out of scope here, but no reason to add one
    // more).
    //% shim=diffDrive::engineGoToR
    export function _goToR(x: number, y: number, speed: number,
        arrive: number, timeout: number): void {
        simIntegrate()
        if (simEstopped) return
        const chord = Math.sqrt(x * x + y * y)
        if (chord <= arrive) return
        const bearing = Math.atan2(y, x)   // [rad] already short-arc
        let theta = 2 * bearing            // [rad] |.| < 2*pi
        if (theta > Math.PI) theta -= 2 * Math.PI
        else if (theta <= -Math.PI) theta += 2 * Math.PI
        let s: number
        if (Math.abs(y) < 0.1) {           // ~0.1 mm: call it straight
            s = x
        } else {
            const radius = (x * x + y * y) / (2 * y)
            s = radius * theta
        }
        const spd = speed > 0 ? speed : 1
        const duration = Math.abs(s) / spd
        if (duration <= 0) return
        simMoveRemainMm = Math.abs(s)
        simMoveRemainRad = Math.abs(theta)
        simVel = s / duration
        simYawRate = theta / duration
        simMoveActive = true
    }

    // Simulator body for the tick engine: integrate one step (kinematic
    // stand-in for kernel.step()+serviceMove()), then self-pace to the
    // next absolute 24 ms schedule with basic.pause(), same anchoring
    // rule as tickDrive() in shims.cpp -- so blocking/loop forms built
    // on `while (_tickDrive())` behave the same way in the browser as
    // on hardware. Always steps (simIntegrate()), even with no move
    // active, matching the hardware contract that continuous-mode
    // driving depends on.
    //
    // Returns `simMoveActive || simVel != 0 || simYawRate != 0` (sprint
    // 007 ticket 002, closes R-10/API-01) -- the simulator-state mirror
    // of shims.cpp's `commandLooksActive(r)`, not raw `simMoveActive`.
    // simIntegrate() (just above) already zeroed simVel/simYawRate
    // synchronously, in this same call, if a position-mode move
    // completed on this step -- there is no motor coast-down to model
    // in the browser, so no settle-loop equivalent is needed the way
    // shims.cpp's tickDrive() needs one on hardware -- so a move's final
    // tick still returns false here, same as before. A continuous-mode
    // command (setWheelSpeeds()/driveTwist(), which leave
    // simMoveActive == false but simVel/simYawRate nonzero) now keeps
    // this true instead of returning false on the very first tick, the
    // same fix as shims.cpp's own. See
    // tests/host/test_continuous_drive_command_looks_active.py for the
    // host-side proof of the equivalent hardware condition (this
    // simulator body itself is not host-testable -- no automated check
    // reaches main.ts; see this ticket's C++11 Gate Coverage).
    //% shim=diffDrive::tickDrive
    export function _tickDrive(): boolean {
        simIntegrate()
        simCycleCount += 1
        const stillCommanded = simMoveActive || simVel != 0 || simYawRate != 0

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
        return stillCommanded
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
    export function _progress(): int32 {
        simIntegrate()
        return simMoveActive ? 500 : 1000
    }

    //% shim=diffDrive::endMove
    export function _endMove(): void {
        simIntegrate()
        simMoveActive = false
        simVel = 0
        simYawRate = 0
    }

    //% shim=diffDrive::stopAll
    export function _stopAll(): void {
        simIntegrate()
        simMoveActive = false
        simVel = 0
        simYawRate = 0
    }

    //% shim=diffDrive::estopAll
    export function _estopAll(): void {
        _stopAll()
        simEstopped = true
    }

    //% shim=diffDrive::estopClear
    export function _estopClear(): void {
        simEstopped = false
    }

    // Stall latch clear/readback (sprint 007 ticket 001): no-ops in the
    // simulator -- there is no stall model in the browser, matching
    // this file's existing precedent for setGeometry/setKernelValue's
    // simulator fallbacks (specification.md §5).
    //% shim=diffDrive::clearStall
    export function _clearStallLatch(): void { }

    //% shim=diffDrive::isStalled
    export function _isStalled(): boolean { return false }

    //% shim=diffDrive::poseX
    export function _poseX(): int32 {
        simIntegrate()
        return Math.round(simX)
    }

    //% shim=diffDrive::poseY
    export function _poseY(): int32 {
        simIntegrate()
        return Math.round(simY)
    }

    //% shim=diffDrive::poseHeading
    export function _poseHeading(): int32 {
        simIntegrate()
        return Math.round(simHeading * 180 / Math.PI * 100)
    }

    //% shim=diffDrive::resetPose
    export function _resetPose(): void {
        simIntegrate()
        simX = 0
        simY = 0
        simHeading = 0
    }

    //% shim=diffDrive::setGeometry
    export function _setGeometry(trackWidth: int32, calib: int32): void { }

    //% shim=diffDrive::setKernelValue
    export function _setKernelValue(field: int32, value: int32): void { }

    //% shim=diffDrive::startProtocol
    export function _startProtocol(): void { }

    // ---- OTOS (zeguz bench bring-up) -- shim-only surface, no blocks.
    // Call only from the fiber that calls driveTick(): an OTOS I2C
    // transaction interposed in the Nezha encoder's select->read
    // window destroys the encoder sample. Sim fallbacks report a
    // sensor that is absent.

    /**
     * Read one diagnostic value. See diagValue() in shims.cpp for the
     * index list: 2 stall halted (see isStalled(), the named block for
     * this same bit), 10/11 encoder positions, 12/13 applied duty x100,
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
    export function runCommandText(slot: int32): string {
        return ""
    }

    //% shim=diffDrive::seedPose
    export function _seedPose(x: int32, y: int32, heading: int32): void {
        simIntegrate()
        simX = x
        simY = y
        simHeading = heading / 100 * Math.PI / 180
    }
}
