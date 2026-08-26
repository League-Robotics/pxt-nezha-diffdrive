---
status: in-progress
sprint: '021'
tickets:
- 021-001
---

# Document the local MakeCode editor (codeserver) workflow

## Problem

Getting the extension's blocks into a locally-served MakeCode editor
and a student-style program onto a robot required a full evening of
reverse-engineering (2026-08-25). None of it is written down in the
repo; the knowledge currently lives in one session's memory notes.

## What the doc must cover (all verified working)

1. Serve: `pxt serve --noBrowser --noauth --noSerial` from the repo
   root; the "scandir 'libs'" startup error is harmless.
2. See local projects: open
   `http://localhost:3232/index.html?ws=fs` — the `?ws=fs` filesystem
   workspace is what makes disk projects appear; projects live in
   `<serve-cwd>/projects/` (one folder per pxt.json). The first page
   load consumes the auth token and DROPS the query string — navigate
   twice.
3. Test blocks via a consumer project with
   `"nezha-diffdrive": "file:../nezha-diffdrive"` — the extension
   itself opens JS-only.
4. Patience: first open of a project using the extension freezes the
   tab 1–4 minutes (main-thread typecheck). It is not hung.
5. Auto-save wedge: a 409 conflict on the editor's `_history` file
   silently drops the workspace to memory ("Project Auto-Save
   Disabled") and edits stop reaching disk — delete `_history`,
   close other editor clients, reload.
6. Flashing: MakeCode's Download produces a UNIVERSAL hex that
   pyocd/mbdeploy cannot parse (and its failure path mass-erases the
   board). Build instead with `pxt build` in the project folder and
   flash the plain V2 hex via mbdeploy. A browser tab holding a
   MakeCode WebUSB pairing claims the DAP interface — park the tab
   before flashing ("Unable to claim interface" is the symptom).
7. Remote-testing pattern: bind programs to `on run "name"` blocks and
   trigger with cleartext `RUN:name` over serial (no #id needed);
   library dispatch emits no receipt — prove behavior with
   `TLM POSE #1` pose frames or `diffDrive.emitLine()` receipts.

The working scaffold from the original session is embedded below
(the session branch is archived; these are the verified-working files).
`.claude/launch.json` and the gitignore rules are already on master.
Deliverable: a doc under `docs/` (e.g. `docs/local-editor.md`) plus a
README pointer.

### Scaffold: `.claude/launch.json`

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "codeserver",
      "runtimeExecutable": "pxt",
      "runtimeArgs": ["serve", "--noBrowser", "--noauth", "--noSerial"],
      "port": 3232
    }
  ]
}
```

### Scaffold: `projects/blocktest/pxt.json`

The `nezha-diffdrive` dep points at the repo root relative to
`projects/` (a symlink `projects/nezha-diffdrive -> ../` was used):

```json
{
    "name": "blocktest",
    "dependencies": {
        "core": "*",
        "nezha-diffdrive": "file:../nezha-diffdrive-patched",
        "microphone": "*"
    },
    "files": [
        "main.blocks",
        "main.ts",
        "README.md"
    ],
    "preferredEditor": "blocksprj"
}
```

### Scaffold: `projects/blocktest/main.blocks`

```xml
<xml xmlns="https://developers.google.com/blockly/xml"><variables></variables><block type="pxt-on-start" x="20" y="20"><statement name="HANDLER"><block type="basic_show_icon"><field name="i">IconNames.Heart</field></block></statement></block><block type="device_button_event" x="263" y="20"><field name="NAME">Button.A</field><statement name="HANDLER"><block type="diffDrive_move"><value name="distance"><shadow type="math_number"><field name="NUM">20</field></shadow></value><value name="yaw"><shadow type="math_number"><field name="NUM">0</field></shadow></value></block></statement></block><block type="diffDrive_onRun" x="657" y="20"><value name="name"><shadow type="text"><field name="TEXT">go</field></shadow></value><value name="HANDLER_DRAG_PARAM_arg"><block type="argument_reporter_number" deletable="false"><field name="VALUE">arg</field></block></value><statement name="HANDLER"><block type="basic_show_icon"><field name="i">IconNames.Yes</field><next><block type="diffDrive_move"><value name="distance"><shadow type="math_number"><field name="NUM">20</field></shadow></value><value name="yaw"><shadow type="math_number"><field name="NUM">0</field></shadow></value><next><block type="basic_show_icon"><field name="i">IconNames.Happy</field></block></next></block></next></block></statement></block></xml>
```

### Scaffold: `projects/blocktest/main.ts` (the bench-rig RUN verbs)

Includes the diagnostic verbs used in the 2026-08-26 split-pivot
campaign (probe/clearstall — note the mandatory driveTick between
clear and read — taper floors/windows):

```ts
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
```
