diffDrive.onRun("go", function (arg) {
    basic.showIcon(IconNames.Yes)
    diffDrive.move(20, 0)
    basic.showIcon(IconNames.Happy)
})
diffDrive.onRun("turn", function (arg) {
    basic.showIcon(IconNames.Yes)
    diffDrive.move(0, arg == 0 ? 180 : arg)
    basic.showIcon(IconNames.Happy)
})
diffDrive.onRun("arc", function (arg) {
    basic.showIcon(IconNames.Yes)
    diffDrive.move(20, arg == 0 ? 180 : arg)
    basic.showIcon(IconNames.Happy)
})
diffDrive.onRun("probe", function (arg) {
    diffDrive.emitLine("PROBE:" + arg + "=" + diffDrive.probe(arg))
})
diffDrive.onRun("clearstall", function (arg) {
    diffDrive.clearStallLatch()
    diffDrive.driveTick()
    diffDrive.emitLine("CLEARED:stalled=" + (diffDrive.isStalled() ? 1 : 0))
})
diffDrive.onRun("floors", function (arg) {
    diffDrive.setTaperFloors(45, 35)
    diffDrive.emitLine("FLOORS:45,35")
})
diffDrive.onRun("floorsdefault", function (arg) {
    diffDrive.setTaperFloors(25, 12)
    diffDrive.emitLine("FLOORS:25,12")
})
diffDrive.onRun("windows", function (arg) {
    diffDrive.setTaperWindows(400, arg == 0 ? 1 : arg)
    diffDrive.emitLine("WINDOWS:400," + (arg == 0 ? 1 : arg))
})
diffDrive.onRun("windowsdefault", function (arg) {
    diffDrive.setTaperWindows(400, 180)
    diffDrive.emitLine("WINDOWS:400,180")
})
input.onButtonPressed(Button.A, function () {
    diffDrive.move(20, 0)
})
basic.showIcon(IconNames.Heart)
