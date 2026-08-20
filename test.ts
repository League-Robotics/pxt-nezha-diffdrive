// test.ts -- test programs, deliberately compact: the deploy image is
// flash-tight (TS region), so all tests share one parameterized
// runner. Triggers: buttons and the wire/radio RUN:<n> command.
//
//   button A      / RUN:3  drive straight 80 cm
//   button B              alternate +-360 pivot (P/Q on the LED)
//   buttons A+B   / RUN:1  square tour (30 cm + 90 deg, x4)
//                   RUN:2  +360 pivot
//                   RUN:4  +180 pivot     RUN:5  -180 pivot
//
// Hardware runs resolve the target micro:bit by name via mbdeploy.
// This project's test robot is vevov.
let touring = false

function runSeg(d: number, y: number, reps: number) {
    if (touring) return
    touring = true
    diffDrive.resetPose()
    for (let i = 1; i <= reps; i++) {
        if (reps > 1) basic.showNumber(i)
        if (d != 0) diffDrive.move(d, 0)
        if (y != 0) diffDrive.move(0, y)
    }
    basic.showString("OK")
    touring = false
}

let pivotCCW = true

input.onButtonPressed(Button.A, function () {
    runSeg(80, 0, 1)
})
input.onButtonPressed(Button.B, function () {
    runSeg(0, pivotCCW ? 360 : -360, 1)
    pivotCCW = !pivotCCW
})
input.onButtonPressed(Button.AB, function () {
    runSeg(30, 90, 4)
})

diffDrive.onRunCommand(function (n: number) {
    if (n == 1) runSeg(30, 90, 4)
    else if (n == 2) runSeg(0, 360, 1)
    else if (n == 3) runSeg(80, 0, 1)
    else if (n == 4) runSeg(0, 180, 1)
    else if (n == 5) runSeg(0, -180, 1)
})
