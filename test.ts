// test.ts -- square-drive integration test (SUC-006). On button A,
// reset pose and drive a 30 cm square: (30 cm straight, 90 deg turn)
// x 4, ending with the fourth turn so the robot returns to its start
// position AND orientation. Uses only main.ts's public blocks -- no
// dependency on this sprint's wire-protocol work. Runs in the browser
// simulator (pose model) and on hardware (real kernel); verify in the
// simulator that poseX()/poseY()/heading() return to (approximately)
// zero after the run.
//
// Hardware verification is deferred to the stakeholder, post sprint
// close, on master. When run on real hardware, resolve the target
// micro:bit by name ("zetuv") via the mbdeploy tool -- never a
// hard-coded serial port or a guess from a /dev listing. See
// clasi/issues/test-on-microbit-zetuv-via-mbdeploy.md.
input.onButtonPressed(Button.A, function () {
    diffDrive.resetPose()
    for (let i = 0; i < 4; i++) {
        diffDrive.move(30, 0)
        diffDrive.move(0, 90)
    }
   
})
