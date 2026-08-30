# Local MakeCode editor (codeserver) workflow

How to serve this extension in a local MakeCode editor, see it from a
disk project, and build/flash a plain V2 hex — without going anywhere
near the public MakeCode site. Written for a developer or maintainer
working on the extension itself (block signatures, `sim.ts`, the
toolbox layout), not a student consuming a published extension URL.

This is the workflow every other MakeCode-facing ticket in sprint 021
verifies through: JS↔Blocks conversion, the web simulator boot check,
the toolbox group review, and the hardware ABI/radio checks all start
here.

## Quick reference

```bash
# 1. serve, from the repo root
pxt serve --noBrowser --noauth --noSerial

# 2. open, then RE-open (see "The ?ws=fs double-navigate" below)
http://localhost:3232/index.html?ws=fs

# 3. build a plain V2 hex, from inside a project folder under projects/
pxt install   # first time only, or after changing dependencies
pxt build     # -> built/binary.hex

# 4. flash it
mbdeploy deploy <target> --hex built/binary.hex
```

## 1. Serving

From the repo root:

```bash
pxt serve --noBrowser --noauth --noSerial
```

`--noBrowser` stops it trying to open a system browser tab (there may
not be one attached to the shell running this); `--noauth` skips the
local auth-token dance that `?ws=fs` also needs to sidestep (see
below); `--noSerial` skips trying to open a serial port for the
in-browser serial console, which this workflow doesn't use.

On startup you'll see a `Build failed: target build failed: ENOENT: no
such file or directory, scandir 'libs'` block near the top of the
output. **This is harmless** — it's `pxt-microbit`'s own bundled
target failing to rebuild its default-project cache (a directory the
target ships without), and it happens before the actual server starts.
Keep reading past it; the log ends with:

```
Server listening on port 3232
```

Leave this process running in its own terminal for the rest of the
session — `pxt serve` also runs a second, internal workspace-sync
server (`starting local ws server at 3233...`) that the editor talks
to for reading/writing files on disk.

## 2. Seeing local projects

Open:

```
http://localhost:3232/index.html?ws=fs
```

`?ws=fs` selects the **filesystem workspace** — without it, the editor
defaults to browser-local-storage projects and never looks at disk at
all. With it, "projects" in the editor's home screen are folders under
`<the directory pxt serve was run from>/projects/`, one folder per
`pxt.json`.

**The double-navigate**: the first page load consumes a local auth
token embedded in the URL and then redirects, dropping the `?ws=fs`
query string in the process — you land on the plain in-browser-storage
workspace instead. Navigate to the same `?ws=fs` URL a **second** time
and it sticks. If the project list looks empty or unfamiliar, this is
almost always why — reload the URL once more before troubleshooting
anything else.

`projects/` itself is **not** committed to this repo — it's covered by
the "Local MakeCode editor droppings" block in `.gitignore` (along with
`_history` and pxt's `.header.json`/`.simstate.json` files, wherever
they land). You create the folders you need; nothing under `projects/`
survives a fresh checkout.

## 3. Testing blocks via a consumer project

The extension's own package (this repo's root `pxt.json`) opens in the
editor as a **JavaScript-only** project — MakeCode doesn't render an
extension's own definitions as blocks when you open the extension
itself. To see and test the blocks, create a separate project *inside*
`projects/` that depends on the extension by a `file:` path:

```
mkdir -p projects/blocktest
```

`projects/blocktest/pxt.json`:

```json
{
    "name": "blocktest",
    "dependencies": {
        "core": "*",
        "nezha-diffdrive": "file:../..",
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

`file:../..` resolves relative to `projects/blocktest/` — two levels
up lands on the repo root, whose own `pxt.json` already declares
itself as the `nezha-diffdrive` package. Pointing straight at the repo
root (rather than a separately maintained copy of the source tree)
means an edit to `src/blocks/sim.ts` or any other extension file is
picked up by the served editor immediately, with no copy step — this
was confirmed live 2026-08-26: with this exact `pxt.json` in place,
`pxt serve`'s `/api/list` endpoint (what the `?ws=fs` workspace is
built on) enumerated `blocktest` correctly, and `pxt install` + `pxt
build` both resolved the `file:../..` dependency and began compiling
against the repo's real `src/` sources.

`projects/blocktest/main.ts` (a minimal remote-testable program — see
"The remote-testing pattern" below for what `onRun` and the button
handler are doing):

```ts
diffDrive.onRun("go", function (arg) {
    basic.showIcon(IconNames.Yes)
    diffDrive.move(20, 0)
    basic.showIcon(IconNames.Happy)
})
input.onButtonPressed(Button.A, function () {
    diffDrive.move(20, 0)
})
basic.showIcon(IconNames.Heart)
```

The equivalent `main.blocks` (paste as-is; MakeCode will offer to
switch to the Blocks editor once it's present):

```xml
<xml xmlns="https://developers.google.com/blockly/xml"><variables></variables><block type="pxt-on-start" x="20" y="20"><statement name="HANDLER"><block type="basic_show_icon"><field name="i">IconNames.Heart</field></block></statement></block><block type="device_button_event" x="263" y="20"><field name="NAME">Button.A</field><statement name="HANDLER"><block type="diffDrive_move"><value name="distance"><shadow type="math_number"><field name="NUM">20</field></shadow></value><value name="yaw"><shadow type="math_number"><field name="NUM">0</field></shadow></value></block></statement></block><block type="diffDrive_onRun" x="657" y="20"><value name="name"><shadow type="text"><field name="TEXT">go</field></shadow></value><value name="HANDLER_DRAG_PARAM_arg"><block type="argument_reporter_number" deletable="false"><field name="VALUE">arg</field></block></value><statement name="HANDLER"><block type="basic_show_icon"><field name="i">IconNames.Yes</field><next><block type="diffDrive_move"><value name="distance"><shadow type="math_number"><field name="NUM">20</field></shadow></value><value name="yaw"><shadow type="math_number"><field name="NUM">0</field></shadow></value><next><block type="basic_show_icon"><field name="i">IconNames.Happy</field></block></next></block></next></block></statement></block></xml>
```

**Known current limitation**: as of this writing, several `sim.ts`
fallback functions (`_setWheels`, `_driveTwist`, `_startMove`,
`_setGeometry`, `probe`, `setTaperWindows`, `setTaperFloors`, and
others) still declare `int32`-typed parameters, and MakeCode's
decompiler typechecks the extension's whole fallback surface — not
just the functions a given program calls — on every JS→Blocks
conversion. Until that's fixed, converting *any* project that depends
on this extension raises `TS9256: bit sizes are not supported for
locals and parameters` in the Problems pane, and the web simulator
crashes at boot the same way for the same reason (some of those same
functions have empty `{}` bodies, which pxt treats as native-only).
Both are tracked and fixed by this same sprint's tickets 002/003 — if
you hit either error while working through this doc before those
tickets land, that's the expected, already-diagnosed state, not a
mistake in this workflow.

## 4. Patience: the first-open freeze

The **first** time you open a project that depends on this extension
(not the extension's own JS-only view — a consumer project like
`blocktest` above), the tab freezes for **roughly 1–4 minutes**. This
is the editor's main-thread TypeScript typecheck running over the
extension's full surface for the first time in that browser session.
It is not a hang — do not close the tab or kill `pxt serve`. Subsequent
opens (same browser session) are fast; a hard reload of the tab pays
the freeze again.

## 5. The `_history` auto-save wedge

Symptom: the editor's title bar or a banner reports **"Project
Auto-Save Disabled"**, and further edits stop reaching disk even
though the editor itself keeps responding.

Cause: a 409 conflict writing the project's `_history` file (living
inside the project folder, e.g. `projects/blocktest/_history`) — the
filesystem workspace's undo/autosave log. This happens when more than
one editor client (two tabs, or a tab left open from a previous
session) has the same project open and both try to append to the same
history file.

Recovery:

1. Close every other browser tab/client with that project open.
2. Delete the project's `_history` file (`rm
   projects/blocktest/_history`) — it's an autosave/undo log, not your
   source; your `main.ts`/`main.blocks` are untouched.
3. Reload the editor tab.

## 6. Flashing: build a plain V2 hex, not MakeCode's Download

**Do not use the editor's own Download button for this board.** It
produces a **universal hex** (a single file carrying both V1 and V2
firmware images, auto-detected on flash) — a format the CODAL/V2
flashing path this project uses (`mbdeploy`/pyocd) cannot parse. Worse,
if a universal hex flash fails partway, its failure path **mass-erases
the board**, which a plain hex's failure path does not do.

Build a plain V2 hex from the CLI instead, from inside the consumer
project's folder:

```bash
cd projects/blocktest
pxt install   # first time, or whenever dependencies change --
              # skipping this fails with "Package not installed: core"
pxt build
```

This repo's own root `pxt.json` already sets `"disablesVariants":
["mbdal"]` (mbdal is the legacy V1/DAL variant), so a plain `pxt build`
against it produces a **V2-only** hex with no extra flags needed — the
universal-hex problem is specific to the editor's Download button, not
to `pxt build` itself. The V2 hex lands at `projects/blocktest/built/
binary.hex`.

First build is slow: `pxt build` here compiles locally via a Docker
container (`pext/yotta:...`, matching the GCC 5.4 cross-compiler this
target needs), and the first run also downloads several yotta targets
from GitHub (`bbc-microbit-classic-gcc`, `mbed-gcc`, `microbit`,
`microbit-dal`) — expect it to take several minutes and pull a Docker
image the first time. This machine has `PXT_FORCE_LOCAL=1` set in the
shell profile, which is what selects the local Docker path over
MakeCode's cloud compiler; if a fresh shell doesn't have it set, `pxt
build` may instead try the cloud compiler, which behaves differently
(and may need its own auth). Set `PXT_FORCE_LOCAL=1` yourself if in
doubt.

Then flash it:

```bash
mbdeploy deploy <target> --hex projects/blocktest/built/binary.hex
```

`<target>` is a board name/port/UID `mbdeploy` recognizes (`mbdeploy
list` shows what it currently sees; `mbdeploy probe` refreshes the
registry if a board doesn't show up). If `mbdeploy` reports **"Unable
to claim interface"**, a browser tab somewhere is holding a WebUSB
pairing to that same board (from a previous MakeCode Download attempt,
or a simulator/pairing dialog left open) — WebUSB claims the same DAP
interface `mbdeploy` needs, exclusively. Close or navigate away from
that tab first, then retry.

For a repeatable, per-robot build (radio channel injection, a scratch
copy with test files stripped, build-log triage) rather than this
manual single-project flow, see `tools/make_deploy.py` and its
"Build / deploy" section in `tools/DESIGN.md` — that tool is not part
of this doc's scope and is what sprint 023's build-gate work hardens
further.

## 7. The remote-testing pattern

Bind test behavior to a name with `diffDrive.onRun("name", handler)`
(as in the `blocktest` example above) rather than only a button press,
and trigger it remotely with a cleartext line over serial or radio:

```
RUN:go
```

No `#<id>` sequence number is needed here — `RUN:`/`DIAG` cleartext
commands are parsed by a different path than the v6 sequenced wire
protocol (`TLM`, `SET`, etc.), and that sequenced path is the one that
silently drops an unsequenced line. See `.claude/rules/
playfield-testing.md` ("v6 wire commands MUST carry a sequence id") for
the full story on that distinction — it does not apply here.

`onRun`'s dispatch is library-internal (a `MessageBus` event handled
inside `src/blocks/run.ts`) and emits **no acknowledgment of its
own** — sending `RUN:go` gets you the normal wire keepalive/ack
traffic, nothing that confirms `go`'s handler actually ran. Prove the
program did what you expect one of two ways instead:

- Subscribe to pose telemetry (`TLM POSE #1` — the `#1` is required,
  see the same rule file's "v6 wire commands" section) and watch the
  robot's reported position/heading change.
- Have the handler itself call `diffDrive.emitLine("...")` (a real
  wire write, `shims.cpp`'s `emitLine` → `Protocol::emitLine()`) to
  send an explicit text receipt, and read that back over the
  connection.

`tools/robotlink.py` is the reference implementation for both: it
attaches sequence ids to `TLM`/`SET`-style commands automatically and
adopts the robot's own sequence counter on connect, while leaving
cleartext `RUN:`/`DIAG` lines unsequenced.

## See also

- `.claude/rules/playfield-testing.md` — field/bench operational facts
  (v6 sequencing, RUN verb dispatch, camera/OTOS/bench-stand gotchas)
  that apply once you're driving a robot through this same editor's
  consumer projects.
- `tools/DESIGN.md` — the automated build/deploy pipeline
  (`make_deploy.py`) for per-robot hex builds, as opposed to this doc's
  manual, single-project flow.
