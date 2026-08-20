// test.ts -- test programs in GENERATOR form (stakeholder direction,
// 2026-08-20): every move runs as an explicit startMove + driveTick()
// loop in THIS file -- no blocking move() wrappers -- so the tick loop
// is visible, instrumentable test code. The loop records the maximum
// inter-tick gap (ms) seen during the last test as a starvation
// diagnostic: a healthy loop ticks every ~24 ms; gaps far beyond that
// mean some other fiber stole the loop mid-move (the suspected cause
// of intermittent leg overshoot).
//
//   button A      / RUN:3  drive straight 80 cm
//   button B              alternate +-360 pivot
//   buttons A+B   / RUN:1  square tour (30 cm + 90 deg, x4)
//                   RUN:2  +360 pivot
//                   RUN:4  +180 pivot     RUN:5  -180 pivot
//                   RUN:9  show last test's max tick gap [ms] on the LED
//
// Hardware runs resolve the target micro:bit by name via mbdeploy.
// This project's test robot is vevov.
let touring = false
let maxGapMs = 0

function tickedMove(d: number, y: number) {
    diffDrive.startMove(d, y)
    let last = control.millis()
    while (diffDrive.driveTick()) {
        const now = control.millis()
        if (now - last > maxGapMs) maxGapMs = now - last
        last = now
    }
}

function runSeg(d: number, y: number, reps: number) {
    if (touring) return
    touring = true
    maxGapMs = 0
    diffDrive.resetPose()
    for (let i = 1; i <= reps; i++) {
        if (reps > 1) basic.showNumber(i)
        if (d != 0) tickedMove(d, 0)
        if (y != 0) tickedMove(0, y)
    }
    serial.writeLine("GAP:" + maxGapMs)
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
    else if (n == 9) basic.showNumber(maxGapMs)
})
