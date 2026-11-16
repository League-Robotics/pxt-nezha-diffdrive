// Fixture for the stored-radio-address bench acceptance (sprint 045 ticket
// 003): radiostore_a.ts plus one extra run command. Never drives the wheels.
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

diffDrive.onRun("hello", function (arg: number) {
    diffDrive.emitLine("RADIOSTORE:hello")
})

diffDrive.onRun("pressa", function (arg: number) {
    control.raiseEvent(EventBusSource.MICROBIT_ID_BUTTON_A, EventBusValue.MICROBIT_BUTTON_EVT_CLICK)
})

diffDrive.onRun("pressb", function (arg: number) {
    control.raiseEvent(EventBusSource.MICROBIT_ID_BUTTON_B, EventBusValue.MICROBIT_BUTTON_EVT_CLICK)
})

diffDrive.emitLine("RADIOSTORE:boot program=b v=" + BOOT_VERSION + " robot=" + BOOT_ROBOT)
