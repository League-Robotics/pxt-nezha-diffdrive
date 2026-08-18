// test.ts -- smoke program: the square tour in four moves, plus a
// loop-form leg with a live pose readout. Runs in the simulator (pose
// model) and on hardware (real kernel).
input.onButtonPressed(Button.A, function () {
    diffDrive.resetPose()
    for (let i = 0; i < 4; i++) {
        diffDrive.move(50, 0)
        diffDrive.move(0, 90)
    }
    basic.showNumber(Math.round(diffDrive.poseX()))
})

input.onButtonPressed(Button.B, function () {
    diffDrive.whileMoving(50, 0, function (x, y, heading) {
        led.plotBarGraph(x, 50)
    })
    diffDrive.stop()
})
