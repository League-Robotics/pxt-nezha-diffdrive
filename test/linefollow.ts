// linefollow.ts -- the smallest on-robot program that follows a line.
//
// Sensor: ElecFreaks PlanetX Trackbit, a four-channel reflectance array on
// I2C address 0x1A, mounted ahead of the wheels (channel 0 on the robot's
// left). Protocol as in PlanetX_Basic.Trackbit* of
// https://github.com/elecfreaks/pxt-planetx basic.ts: write a register
// byte, read one byte back. Register 4 is the line bitmask, bit i set when
// channel i sees the line. That one byte is all the follower needs.
//
// Build and flash (this file replaces test.ts in the hex):
//   uv run python tools/make_deploy.py --program linefollow.ts --robot vevov
//   mbdeploy deploy --remote vevov --hex .tmp/deploy-linefollow/built/binary.hex
//
// Start it with button A, or over the radio / serial with
//   RUN:line[:speed_cm_s[:max_s[:kp]]]      defaults 8, 90, 60
//   RUN:abort                                stop
//   RUN:linesense                            print 20 sensor samples

// Everything lives in its own namespace so this file can sit next to
// test.ts in the repo type-check without name collisions; PXT runs a
// namespace body at start-up exactly like top-level code.
namespace linefollow {
    const BOOT_VERSION = "00.00"        // both substituted by make_deploy
    const BOOT_ROBOT = "unknown"

    diffDrive.enableRadioLink()

    const TRACKBIT = 0x1a
    function lineBits(): number {
        pins.i2cWriteNumber(TRACKBIT, 4, NumberFormat.Int8LE)
        return pins.i2cReadNumber(TRACKBIT, NumberFormat.UInt8LE, false) & 0x0f
    }

    // Where the line is under the array, in channel units: +1.5 = far left
    // only, -1.5 = far right only, 0 = centred. 999 = nothing seen.
    const WEIGHT = [1.5, 0.5, -0.5, -1.5]
    function lineError(bits: number): number {
        let sum = 0, n = 0
        for (let i = 0; i < 4; i++) if (bits & (1 << i)) { sum += WEIGHT[i]; n++ }
        return n == 0 ? 999 : sum / n
    }

    let running = false
    let aborted = false

    // Proportional steering: yaw rate = kp * error (deg/s, CCW+, so a line to
    // the left turns the robot left). Nothing seen: turn toward the side the
    // line was last on, slower, and give up after 1.5 s.
    function followLine(speed: number, maxS: number, kp: number) {
        if (running) return
        running = true
        aborted = false
        let lastErr = 0, lostSince = -1, reason = "time"
        const t0 = control.millis()
        diffDrive.driveTwist(speed, 0)
        while (diffDrive.driveTick()) {              // one control cycle, ~24 ms
            const now = control.millis() - t0
            if (aborted) { reason = "abort"; break }
            if (now > maxS * 1000) break
            const err = lineError(lineBits())
            if (err == 999) {
                if (lostSince < 0) lostSince = now
                else if (now - lostSince > 1500) { reason = "lost"; break }
                diffDrive.driveTwist(speed * 0.4, lastErr >= 0 ? 90 : -90)
            } else {
                lostSince = -1
                if (err != 0) lastErr = err
                diffDrive.driveTwist(speed, kp * err)
            }
        }
        diffDrive.stopMove()
        diffDrive.emitLine("LINE:end:" + reason + ":" + (control.millis() - t0))
        basic.showString("L")
        running = false
    }

    diffDrive.onRun("line", function (arg: number) {
        const speed = diffDrive.runArgCount() > 0 ? diffDrive.runArg(0) : 8
        const maxS = diffDrive.runArgCount() > 1 ? diffDrive.runArg(1) : 90
        const kp = diffDrive.runArgCount() > 2 ? diffDrive.runArg(2) : 60
        followLine(speed, maxS, kp)
    })
    diffDrive.onRun("abort", function (arg: number) { aborted = true })
    diffDrive.onRun("linesense", function (arg: number) {
        for (let i = 0; i < 20; i++) { diffDrive.emitLine("TB:" + lineBits()); basic.pause(100) }
    })
    input.onButtonPressed(Button.A, function () { followLine(8, 90, 60) })

    basic.showString(BOOT_ROBOT + " " + BOOT_VERSION)
}
