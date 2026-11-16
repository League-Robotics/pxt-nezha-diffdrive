// Fixture for the stored-radio-address bench acceptance (sprint 045 ticket
// 003). Never drives the wheels. radiostore_b.ts is this program plus one
// extra run command.
const BOOT_VERSION = "00.00"
const BOOT_ROBOT = "unknown"

diffDrive.setupRobot()

diffDrive.addProgram("pause", images.createImage(`
. . . . .
. # . # .
. # . # .
. # . # .
. . . . .`), function () {
    basic.pause(6000)
})

diffDrive.onRun("pressa", function (arg: number) {
    control.raiseEvent(EventBusSource.MICROBIT_ID_BUTTON_A, EventBusValue.MICROBIT_BUTTON_EVT_CLICK)
})

diffDrive.onRun("pressb", function (arg: number) {
    control.raiseEvent(EventBusSource.MICROBIT_ID_BUTTON_B, EventBusValue.MICROBIT_BUTTON_EVT_CLICK)
})

diffDrive.emitLine("RADIOSTORE:boot program=a v=" + BOOT_VERSION + " robot=" + BOOT_ROBOT)
