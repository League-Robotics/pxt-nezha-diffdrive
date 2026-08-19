// test.ts -- stepwise square-drive test for debugging square closure,
// plus a loop-style square variant demonstrating the caller-driven
// tick model (sprint 002).
//
// Button A starts the stepwise tour: four legs, each (30 cm straight,
// 90 deg CCW turn), driven with the blocking move() block. The leg
// number (1-4) shows on the LED matrix while that leg drives; at the
// end of each leg (except the last) the robot pauses and waits for a
// button-B press before starting the next leg, so per-leg position and
// heading error can be measured on the bench. A checkmark shows when
// the tour is complete.
//
// Button B starts a loop-style variant of the same 30 cm / 90 deg
// square, built directly on driveTick() instead of the blocking move()
// block: per leg, startMove(...) then
// `while (diffDrive.driveTick()) { ... }` for the straight segment,
// then the same pattern for the turn segment -- the demonstration
// artifact for the caller-driven tick model this sprint introduces
// (mirrors the intent of the old pre-sprint-001 whileMoving/
// plotBarGraph demo, but ticked explicitly rather than internally).
// The loop body plots a live, non-scrolling progress readout: one dot
// per tick, filling row 2 left-to-right as the segment completes.
//
// Button-B role collision: B already has a job mid-tour (advancing the
// button-A stepwise tour to its next leg, via the bPressed gate below).
// Resolution: both tours share the `touring` guard flag. B's handler
// checks `touring` first -- while a tour (button-A's stepwise tour, OR
// an already-running button-B loop-style tour) is in progress, a B
// press only sets bPressed (button A's existing mid-tour "advance to
// next leg" behavior, unchanged) and does nothing else; B only starts
// the loop-style variant when `touring` is false. Sharing one flag
// also means button A's existing `if (touring) return` guard, left
// untouched, incidentally keeps A from starting while B's loop-style
// tour is driving -- the two tours never drive the robot at once.
//
// Hardware runs resolve the target micro:bit by name via the mbdeploy
// tool -- never a hard-coded serial port. This project's test robot is
// vevov.
let bPressed = false
let touring = false

input.onButtonPressed(Button.B, function () {
    if (touring) {
        // A tour is already running (button A's stepwise tour, or this
        // same loop-style variant re-entering) -- a B press here always
        // means "advance the current leg", the existing bPressed gate.
        bPressed = true
        return
    }
    touring = true
    diffDrive.resetPose()
    for (let leg = 1; leg <= 4; leg++) {
        basic.showNumber(leg)
        basic.clearScreen()
        diffDrive.startMove(30, 0)
        while (diffDrive.driveTick()) {
            // Live, non-scrolling pose readout: one progress dot per
            // tick, filling row 2 left-to-right as this segment
            // completes (moveProgress() is 0..1 on hardware; the
            // simulator's progress shim is a coarse 0.5/1.0 stand-in --
            // fine for a compiles-and-runs simulator check). Deliberately
            // not basic.showNumber()/showIcon() here: multi-digit
            // showNumber() scrolls (stakeholder etiquette: no scrolling
            // pose numbers while driving), and showIcon()'s icon table
            // is flash-budget-expensive.
            led.plot(Math.min(4, Math.floor(diffDrive.moveProgress() * 5)), 2)
        }
        basic.clearScreen()
        diffDrive.startMove(0, 90)
        while (diffDrive.driveTick()) {
            led.plot(Math.min(4, Math.floor(diffDrive.moveProgress() * 5)), 2)
        }
    }
    basic.showString("OK")
    touring = false
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
