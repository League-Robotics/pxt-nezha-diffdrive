// test.ts -- stepwise square-drive test for debugging square closure.
// Button A starts the tour: four legs, each (30 cm straight, 90 deg CCW
// turn). The leg number (1-4) shows on the LED matrix while that leg
// drives; at the end of each leg the robot pauses and waits for a
// button-B press before starting the next leg, so per-leg position and
// heading error can be measured on the bench. A checkmark shows when
// the tour is complete.
//
// Hardware runs resolve the target micro:bit by name via the mbdeploy
// tool -- never a hard-coded serial port. This project's test robot is
// vevov.
let bPressed = false
let touring = false

input.onButtonPressed(Button.B, function () {
    bPressed = true
})

input.onButtonPressed(Button.A, function () {
    if (touring) return
    touring = true
    diffDrive.resetPose()
    for (let leg = 1; leg <= 4; leg++) {
        basic.showNumber(leg)
        diffDrive.move(30, 0)
        diffDrive.move(0, 90)
        if (leg < 4) {
            bPressed = false
            while (!bPressed) {
                basic.pause(50)
            }
        }
    }
    basic.showString("OK")
    touring = false
})
