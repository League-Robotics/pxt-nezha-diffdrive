// test.ts -- test programs for the extension. Each test is a plain
// function, bound BOTH to a physical trigger and to the wire
// protocol's RUN:<n> command (diffDrive.onRunCommand below), so a
// bench host can trigger the same tests remotely over USB serial:
//
//   button A      / RUN:3  drive straight 80 cm
//   buttons A+B   / RUN:1  square tour
//                   RUN:2  360-degree in-place pivot (bench-safe)
//
// The square tour: four legs, each (30 cm straight, 90 deg CCW turn),
// ending with the fourth turn so the robot returns to its start
// position and orientation. The leg number (1-4) shows on the LED
// matrix while each leg drives; "OK" shows on completion. move() is
// caller-driven under the hood (sprint 002 tick model), so each test
// runs on its own handler fiber.
//
// Hardware runs resolve the target micro:bit by name via the mbdeploy
// tool -- never a hard-coded serial port. This project's test robot is
// vevov.
let touring = false

function runTour() {
    if (touring) return
    touring = true
    diffDrive.resetPose()
    for (let leg = 1; leg <= 4; leg++) {
        basic.showNumber(leg)
        diffDrive.move(30, 0)
        diffDrive.move(0, 90)
    }
    basic.showString("OK")
    touring = false
}

function runPivot() {
    if (touring) return
    touring = true
    basic.showString("P")
    diffDrive.resetPose()
    diffDrive.move(0, 360)
    basic.showString("OK")
    touring = false
}

function runStraight80() {
    if (touring) return
    touring = true
    basic.showString("F")
    diffDrive.resetPose()
    diffDrive.move(80, 0)
    basic.showString("OK")
    touring = false
}

input.onButtonPressed(Button.A, runStraight80)
input.onButtonPressed(Button.AB, runTour)

diffDrive.onRunCommand(function (n: number) {
    if (n == 1) runTour()
    else if (n == 2) runPivot()
    else if (n == 3) runStraight80()
})
