namespace diffDrive {
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

    /**
     * Whether the stall latch has tripped: the robot demanded motion
     * for too long with the wheels not turning, and every Drive/Move
     * block has been silently ignored since. Separate from the
     * emergency-stop latch -- see clearStallLatch(). Always false in
     * the simulator: there is no stall model in the browser.
     */
    //% block="is stalled"
    //% group="Drive"
    export function isStalled(): boolean {
        return _isStalled()
    }

    /**
     * Clear the stall latch so Drive/Move blocks take effect again.
     * Does NOT clear the emergency-stop latch -- the two are
     * independent fault states (see clearEmergencyStop()). A no-op if
     * nothing is latched.
     */
    //% block="clear stall latch" advanced=true
    //% group="Drive"
    export function clearStallLatch(): void {
        _clearStallLatch()
    }
}
