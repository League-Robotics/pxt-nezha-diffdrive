namespace diffDrive {
    // ================= stopping ======================================

    // Stop group (sprint 021 ticket 004, approved layout in
    // block-toolbox-groups-reorganization.md): the three top-level
    // safety controls (stop, emergency stop, is stalled) outweigh the
    // two latch-clearing blocks (clear emergency stop, clear stall
    // latch), which stay advanced -- recovery, not stopping.

    /**
     * Stop driving (normal stop).
     */
    //% block="stop"
    //% group="Stop" weight=180
    export function stop(): void {
        _stopAll()
    }

    /**
     * Emergency stop: latch off until clearEmergencyStop().
     */
    //% block="emergency stop"
    //% group="Stop" weight=170
    export function emergencyStop(): void {
        _estopAll()
    }

    /**
     * Clear the emergency-stop latch.
     */
    //% block="clear emergency stop" advanced=true
    //% group="Stop" weight=150
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
    //% group="Stop" weight=160
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
    //% group="Stop" weight=140
    export function clearStallLatch(): void {
        _clearStallLatch()
    }
}
