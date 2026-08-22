// testrig.ts -- zeguz OTOS validation rig (2026-08-20).
//
// The rig: Nezha M1 spins a drum underneath the OTOS sensor; M2 is a
// dummy. The OTOS itself is mounted on a 360-degree servo whose signal
// is on Nezha jack J1 (micro:bit P8, fallback P1), so the sensor can
// be rotated over the moving drum. Purpose: validate the OTOS driver
// (connect, gyro responds to servo rotation, position advances with
// the drum) before integrating it into the motion layer.
//
// Console: rides the protocol's text RUN:<n> verb (the serial RX is
// owned by the C++ protocol parser, so raw TS serial reading is not
// available; RUN is the scriptable text verb). Vocabulary:
//
//   RUN:20          OTOS begin/probe        -> "OID:<productId>"
//   RUN:21          OTOS zero pose          -> "OZOK"
//   RUN:22          stream OTOS 10 s        -> "OTS:..." lines
//   RUN:23          OTOS IMU bias cal       -> "OCOK" (keep rig still!)
//   RUN:24          stream OTOS 30 s
//   RUN:26          stop streaming          -> "OSEND"
//   RUN:30000+us    servo pulse us on the selected pin (500..2500)
//   RUN:33001/33008 select servo pin P1 / P8
//   RUN:41000+mmps  drum surface speed [mm/s], signed via offset
//                   (41000 = stop, 41100 = +100 mm/s, 40900 = -100)
//   RUN:50500+mm    lever arm offset_x   [mm], -500..500
//   RUN:52500+mm    lever arm offset_y   [mm], -500..500
//   RUN:54180+deg   lever arm offset_yaw [deg], -180..180
//
// Stream line: OTS:<ms>:<x 0.1mm>:<y 0.1mm>:<h cdeg>:<vx mm/s>:<vy>:<om cdeg/s>
//
// ONE worker fiber does ALL I2C (kernel ticks + OTOS reads,
// sequentially) -- an OTOS transaction interposed in the encoder's
// select->read settle window destroys the encoder sample (Phase F).
// The RUN handler only queues; it never touches the bus.

let rigPending = -1
let rigServoPin = AnalogPin.P8
let rigDrumMmps = 0
let rigStreamUntil = 0
let rigNextErrMs = 0
let rigOffX = 0      // [mm] lever arm under test
let rigOffY = 0      // [mm]
let rigOffYaw = 0    // [deg]

// onRunCommand answers EVERY run command and so takes the verb name as
// well as the argument. This rig predates the named-verb dispatch and
// still wants only the number.
diffDrive.onRunCommand(function (name: string, n: number) {
    rigPending = n
})

// Lever-arm test hook. On this rig the servo rotates the sensor about
// its OWN axis, so the sensor never translates: with a non-zero arm
// configured, a rotation in place must make the reported CENTRE trace a
// circle of exactly the arm's radius. That is the direct test of
// sensorToCentre(), and the exact shape of the reference project's
// measured double-correction bug.
function rigApplyOffset() {
    diffDrive.setWorldSensorOffset(rigOffX / 10, rigOffY / 10, rigOffYaw)
    serial.writeLine("OFOK:" + rigOffX + ":" + rigOffY + ":" + rigOffYaw)
}

function rigExec(n: number) {
    if (n == 20) {
        serial.writeLine("OID:" + diffDrive.otosBegin())
    } else if (n == 21) {
        diffDrive.otosZero()
        serial.writeLine("OZOK")
    } else if (n == 22) {
        rigStreamUntil = control.millis() + 10000
        serial.writeLine("OSON")
    } else if (n == 23) {
        diffDrive.otosCalibrate(0)
        serial.writeLine("OCOK")
    } else if (n == 24) {
        rigStreamUntil = control.millis() + 30000
        serial.writeLine("OSON")
    } else if (n == 26) {
        rigStreamUntil = 0
        serial.writeLine("OSEND")
    } else if (n >= 30500 && n <= 32500) {
        pins.servoSetPulse(rigServoPin, n - 30000)
        serial.writeLine("SVOK:" + (n - 30000))
    } else if (n == 33001) {
        rigServoPin = AnalogPin.P1
        serial.writeLine("SPOK:1")
    } else if (n == 33008) {
        rigServoPin = AnalogPin.P8
        serial.writeLine("SPOK:8")
    } else if (n >= 50000 && n <= 51000) {
        rigOffX = n - 50500
        rigApplyOffset()
    } else if (n >= 52000 && n <= 53000) {
        rigOffY = n - 52500
        rigApplyOffset()
    } else if (n >= 54000 && n <= 54360) {
        rigOffYaw = n - 54180
        rigApplyOffset()
    } else if (n >= 40000 && n <= 42000) {
        rigDrumMmps = n - 41000
        if (rigDrumMmps == 0) {
            diffDrive.stop()
        } else {
            // Drum is the rig's LEFT wheel (M1). cm/s at the public API.
            diffDrive.setWheelSpeeds(rigDrumMmps / 10, 0)
        }
        serial.writeLine("DROK:" + rigDrumMmps)
    }
}

basic.showString("Z")

basic.forever(function () {
    if (rigPending >= 0) {
        const n = rigPending
        rigPending = -1
        rigExec(n)
    }
    if (rigDrumMmps != 0) {
        diffDrive.driveTick()  // self-paced ~24 ms; keeps the lease fed
    }
    if (control.millis() < rigStreamUntil) {
        if (diffDrive.otosRead()) {
            serial.writeLine("OTS:" + control.millis()
                + ":" + diffDrive.otosGet(0) + ":" + diffDrive.otosGet(1)
                + ":" + diffDrive.otosGet(2) + ":" + diffDrive.otosGet(3)
                + ":" + diffDrive.otosGet(4) + ":" + diffDrive.otosGet(5))
        } else {
            if (control.millis() >= rigNextErrMs) {
                rigNextErrMs = control.millis() + 1000
                serial.writeLine("OERR:" + diffDrive.otosGet(6)
                    + ":" + diffDrive.otosGet(7))
            }
            if (rigDrumMmps == 0) basic.pause(200)
        }
        if (rigDrumMmps == 0) basic.pause(20)
    } else if (rigDrumMmps == 0) {
        basic.pause(50)
    }
})
