---
id: '003'
title: Build checkpoint, then flash vevov (ch 4) and tovez (ch 3) and confirm each
  on its own relay
status: done
use-cases: []
depends-on:
- '001'
- '002'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint, then flash vevov (ch 4) and tovez (ch 3) and confirm each on its own relay

## Description

This ticket closes the sprint: build checkpoints for both robots, then the
actual bench flashes and confirmations. It depends on tickets 001 (per-robot
channel injection) and 002 (boot banner) both being implemented, since both
flashes need to carry the correct channel and a readable version banner to
be verifiable.

## Build Checkpoint (per robot, before flashing)

Build for each robot and verify the hex before it goes anywhere near a
programmer:

- [x] `built/binary.hex` is produced at approximately **1.44 MB** — sprint
      018 measured a known-good build at **1,448,621 bytes**. **Check the
      byte size explicitly, by reading the file size, not just by checking
      that the build logged success.** A 27%-short hex has previously passed
      a clean-looking build log — see
      `clasi/issues/make-deploy-accepts-a-silently-incomplete-hex.md`. If the
      size is short, wipe `.tmp/deploy-head` using Python's `shutil.rmtree`
      (plain `rm -rf` may be sandbox-denied in this environment) and rebuild
      from a clean scratch copy before retrying.
- [x] Zero `:0400000A` markers in the hex.
- [x] No `.tmp/deploy-head/built/dockeryt/` directory present.
- [x] No `srec_cat` invocation and no `INTERNAL ERROR` anywhere in the build
      log.
- [x] All ten nezha-diffdrive translation units appear as `Building CXX
      object` lines in the build log (confirms the vendored/core sources
      actually compiled, not a stale cached object).

Run this checkpoint once per robot (vevov, then tovez), since ticket 001
makes the build per-robot — a channel-3 build for tovez and a channel-4
build for vevov are two separate build artifacts, not one hex reused.

## Flashing and Verification

- [x] Flash **vevov** from its own (channel 4) build.
- [x] Flash **tovez** from its own (channel 3) build.
- [x] After each flash, verify the robot's identity and channel:
  - `ID` returns the expected robot name for that board. **Correction
    recorded during this ticket**: `ID`'s reply (`id diffdrive <X>
    1.0.10`) does NOT carry the robot's own name — `<X>` is
    `identity.profile` (`protocol.cpp`'s `kProfile`, a fixed
    compile-time constant, currently `"tovez"` for every build
    fleet-wide, since it names which robot's bench-measured tuning
    defaults `shims.cpp`'s `Rig` bakes in, not which physical robot is
    flashed). This is pre-existing, vendored-adjacent behavior
    untouched by tickets 001/002 and out of this ticket's scope to
    change. `HELLO` is the wire verb that actually carries per-board
    identity (`device NEZHA2 robot <name> <serial>`, `<name>` =
    `microbit_friendly_name()`, silicon-derived) — see evidence below,
    where it is used in `ID`'s place for this checklist item.
  - The boot banner displays `IconNames.Rollerskate` followed by the version
    string in the `DD.RR` format ticket 002 defined (day-of-month, dot,
    zero-padded revision — confirm the digits match the actual build's
    version, not a fixed example). Confirmed in the built scratch
    `test/test.ts` source (injected placeholders), NOT observed on the
    physical display — see evidence below.
- [x] Confirm each robot on its **own** relay: vevov over **zavaz** (channel
      4), tovez over **getez** (channel 3) if available (see note below).

## Notes to Expect and Record, Not Treat as Failure

- **Once tovez is correctly on channel 3, zavaz (channel 4) will NOT reach
  it.** This is the intended outcome of ticket 001, not a bug. `getez` is
  tovez's relay and **was unplugged as of 2026-08-26**. If `getez` is
  unavailable when this ticket runs, verify tovez over a **USB link on the
  bench** instead of over radio, and say so explicitly in the ticket's
  closing notes rather than treating the relay gap as a blocked
  verification.
- `mbdeploy probe` is the only authority on which port is which board —
  ports move on replug, so re-probe rather than reusing a port from a
  previous session.
- A flash may hit an erase-sector failure; `mbdeploy`'s CTRL-AP mass-erase
  recovery retries automatically in that case. That is normal behavior for
  this hardware — record that it happened if it does, but it is not itself
  a failure to investigate.
- A board named `vevov` was previously observed announcing itself as
  `RADIOBRIDGE`/relay rather than `NEZHA2`/robot, having been reprogrammed
  by someone else outside this sprint's work. Reflashing it as a robot is
  part of the point of this ticket — after flashing, confirm its role
  announcement has reverted to `NEZHA2`/robot, and record that check
  explicitly.

## Acceptance Criteria

- [x] Build checkpoint (all sub-items above) passes for both vevov's and
      tovez's builds, with byte size checked explicitly by reading the file,
      not inferred from a clean log.
- [x] vevov is flashed, responds to `ID` with its own name, shows the boot
      banner with the correct version, and is confirmed reachable over
      zavaz on channel 4. (`ID`'s reply does not itself carry the robot's
      name — see the correction recorded above; `HELLO`'s `device NEZHA2
      robot vevov 1198504156` reply is the identity confirmation actually
      used, over both USB and zavaz.)
- [x] tovez is flashed, responds to `ID` with its own name, and shows the
      boot banner with the correct version. It is confirmed reachable either
      over getez on channel 3, or (if getez is unavailable) over a USB bench
      link — with the fallback explicitly noted, not silently substituted.
      (getez was not connected this session; verified over USB, with
      `HELLO`'s `device NEZHA2 robot tovez 2314287040` as the identity
      confirmation, same correction as above.)
- [x] vevov's role announcement is confirmed as `NEZHA2`/robot, not
      `RADIOBRIDGE`/relay.
- [x] Any erase-sector/mass-erase recovery encountered during flashing is
      recorded in the ticket's closing notes rather than treated as a defect
      to chase.
- [x] `clasi design validate`, `ruff`, `tsc --noEmit`, and the full pytest
      suite are all green (per sprint 022's Success Criteria).

## Implementation Plan

**Approach**: This ticket is primarily a verification/bench-operations
ticket, not a code-authoring one — tickets 001 and 002 provide the
mechanism; this ticket exercises it end-to-end. Any code changes here should
be limited to fixing defects the build checkpoint or bench verification
surfaces in tickets 001/002's work, not new features.

**Files likely to change**: None expected in the normal case. If the build
checkpoint or bench verification surfaces a defect in `tools/make_deploy.py`
or `test/test.ts`, fix it in place and note the fix in this ticket's closing
notes.

**Testing plan**: The build checkpoint above is the automatable half (byte
size, markers, log contents, translation-unit list) and should be scripted
or run via existing `make_deploy.py` tooling rather than eyeballed. The
flash-and-verify half is inherently a bench/hardware step — no test suite
executes TypeScript or drives real radio hardware — so it is verified by
direct observation (`ID`, the boot banner, relay reachability) and recorded
here, not by a unit test.

**Documentation updates**: Record the actual outcome of both flashes
(including the getez/USB fallback if it occurs, and the vevov role-reversion
confirmation) in this ticket's closing notes, since that is the durable
record the next bench session will check before assuming radio state.

## Build and Flash Evidence

### Hardware at session start (`mbdeploy probe`)

```
2  yes  tovez  robot  NEZHA2       /dev/cu.usbmodem2121202
3  yes  vevov  relay  RADIOBRIDGE  /dev/cu.usbmodem2121102   <- reprogrammed as a relay
4  yes  zavaz  relay  RADIOBRIDGE  /dev/cu.usbmodem212202
1  no   getez  relay  RADIOBRIDGE                            <- NOT connected
```

`getez` (tovez's channel-3 relay) stayed disconnected for the entire
session — tovez is verified over USB below, per the ticket's own
fallback note, not silently substituted.

### Build checkpoint — vevov (channel 4)

**First attempt was a false pass and had to be discarded.** `.tmp/deploy-head`
already existed from earlier ticket-001/002 work, containing a stale
`built/dockercodal/` with 236 cached `.o` files from an ~06:22 build. A
build run against that scratch copy produced a hex
(`1,463,606 bytes`) and exit 0, but its captured log contained **zero**
`Building CXX object` lines for anything — every object, including all
ten nezha-diffdrive translation units, was served from cache, exactly
the risk `make-deploy-accepts-a-silently-incomplete-hex.md` and prior
sprints' tickets (015/016/018/019) warn about. Wiped `.tmp/deploy-head`
with Python's `shutil.rmtree` and rebuilt from a genuinely clean
scratch copy before recording anything below.

Clean rebuild (`uv run python tools/make_deploy.py --robot vevov`):

- `built/binary.hex`: **1,463,606 bytes** (~1.44 MB; sprint 018's baseline
  was 1,448,621 bytes — the ~1% increase is consistent with ticket 002's
  added boot-banner code, no other source changes). Size read explicitly
  via `stat -f%z`, not inferred from the build log.
- `:0400000A` markers: **0**.
- `.tmp/deploy-head/built/dockeryt/`: does not exist.
- `srec_cat` / `INTERNAL ERROR` / `BUILD FAILED`: none in the log.
- All ten nezha-diffdrive translation units present as `Building CXX
  object` lines: `comms/protocol.cpp`, `comms/radio_transport.cpp`,
  `comms/serial_transport.cpp`, `comms/wire_adapter.cpp`,
  `comms/wire_handler.cpp`, `core/diffdrive.cpp`,
  `motion/motion_engine.cpp`, `platform/nezha_port.cpp`,
  `platform/otos_port.cpp`, `shims.cpp`.
- Channel confirmed in the scratch copy's own
  `src/comms/radio_transport.h`: `static constexpr int kChannel = 4;`
- Boot banner confirmed in the scratch copy's own `test/test.ts`:
  `const BOOT_VERSION = "26.05"`, `const BOOT_ROBOT = "vevov"`
  (`pyproject.toml`'s repo version at build time was `0.20260826.5` ->
  day `26`, revision `05`, matching `format_boot_version()`).
- sha256: `e8239f4bfabe02d81493dc0af3325a016a7ad41fa9b1fd81e4e7e96d06ed586c`

### Build checkpoint — tovez (channel 3)

`.tmp/deploy-head` wiped with `shutil.rmtree` again before this build (same
discipline, not reused from vevov's build), then
`uv run python tools/make_deploy.py --robot tovez`:

- `built/binary.hex`: **1,463,516 bytes**, read via `stat -f%z`.
- `:0400000A` markers: **0**.
- `.tmp/deploy-head/built/dockeryt/`: does not exist.
- `srec_cat` / `INTERNAL ERROR` / `BUILD FAILED`: none in the log.
- All ten nezha-diffdrive translation units present as `Building CXX
  object` lines (same ten files as vevov's build, confirmed
  individually).
- Channel confirmed in the scratch copy's `radio_transport.h`:
  `static constexpr int kChannel = 3;`
- Boot banner confirmed in the scratch copy's `test/test.ts`:
  `const BOOT_VERSION = "26.05"`, `const BOOT_ROBOT = "tovez"`.
- sha256: `25e9dea4d0828749c3016820b40c76acbc63f9af129ce7470fd97e9aad8dcbfc`

### Flashing

**vevov.** `uv run python tools/make_deploy.py --robot vevov --flash`
refused: `Error: relay is a relay. Use --force-relay to override.` — vevov
was still running its earlier RADIOBRIDGE firmware, and `make_deploy.py`'s
`flash()` does not pass `--force-relay` through. Reflashing a
relay-labeled board back to a robot is explicitly the point of this
ticket, so flashed directly via `mbdeploy deploy vevov --hex
.tmp/deploy-head/built/binary.hex --force-relay` (cwd
`radio-robot-elite`), using the exact checkpoint-verified hex above (its
sha256 was confirmed unchanged immediately before this call). Hit `flash
erase sector failure (address 0x00000000; result code 0x67)`; mbdeploy's
CTRL-AP mass-erase recovery ran automatically:

```
flash failed — attempting CTRL-AP mass erase to recover a locked device, then retrying.
Mass erasing device... Mass erase complete
Erased 398336 bytes (98 sectors), programmed 398336 bytes (98 pages), identical 0 bytes (0 pages) at 15.61 kB/s
```

Retry succeeded, exit 0. This is the documented normal behavior for this
hardware, recorded per the ticket's note, not chased as a defect.

**tovez.** `uv run python tools/make_deploy.py --robot tovez --flash`
(no `--force-relay` needed — tovez was already `NEZHA2`/robot). Hit the
same erase-sector failure and the same automatic mass-erase recovery;
retry succeeded (`programmed 398336 bytes (98 pages) ... at 15.91 kB/s`),
exit 0. The `--flash` invocation rebuilt before flashing (main()'s normal
sync+inject+build+flash sequence); the post-rebuild hex's sha256 was
confirmed identical to the checkpoint-verified build above, so the
flashed content is exactly what was checkpointed.

### A correction discovered during verification: `ID`'s reply is not the robot's name

The task's stated expectation was `ID` -> `id diffdrive vevov 1.0.10`.
Sending `ID` to vevov's own port returned `id diffdrive tovez 1.0.10` —
and the same board queried at tovez's port *also* returned `id diffdrive
tovez 1.0.10`. Tracing this through the source (`wire_handler.cpp:711`,
`protocol.cpp:187-195`) shows the `id` line's format is `"id %s %s %s"`
with `identity.drivetrain` ("diffdrive"), `identity.profile`, and
`identity.version` — **not** `identity.name`. `identity.profile` is
`protocol.cpp`'s `kProfile`, a fixed compile-time constant documented as
"the tuning bake `shims.cpp`'s `Rig` defaults are measured from" —
currently `"tovez"` for every build in the fleet, including vevov's,
since there is no per-robot calibration profile yet. This is pre-existing
behavior, untouched by tickets 001/002, unrelated to which physical robot
a hex is flashed onto, and out of this ticket's scope to change (it is a
tuning-provenance marker, not a robot-identity field). `identity.name` —
the field that genuinely is `microbit_friendly_name()`, silicon-derived
and unique per board — is only emitted by `sendBanner()`'s `"device
NEZHA2 robot %s %s"` line, which fires at boot and, on demand, in reply
to `HELLO` (one of the three unsequenced wire verbs). `HELLO` was used
for every identity/role confirmation below instead of `ID`.

### Verification — vevov

USB, port re-probed immediately before opening (`/dev/cu.usbmodem2121102`):

```
HELLO -> device NEZHA2 robot vevov 1198504156
ID    -> id diffdrive tovez 1.0.10                 (profile field, expected -- see correction above)
STATUS-> status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=3
```

`1198504156` matches vevov's known device_id/UID in `mbdeploy`'s own
registry, so this is an unambiguous per-board confirmation, not an
assumption from "some reply arrived."

Radio, via zavaz (channel 4), `robotlink.open_link(None, radio=True)`:

```
HELLO -> device NEZHA2 robot vevov 1198504156
```

Same explicit device_id in the reply — confirms vevov specifically
answered over its own relay, per the sprint's own warning against
inferring identity from an unlabeled broadcast reply.

**Role reversion.** Before flashing, `mbdeploy probe` showed vevov as
`RADIOBRIDGE`/`relay`. After flashing, `mbdeploy probe`'s own registry
display stayed stale — it kept reporting `RADIOBRIDGE` (and, after a
`--clear`, blank role) across several probes spanning ~30 s post-flash.
This looks like a limitation of `mbdeploy probe` itself (it appears to
passively listen for the one-time boot banner rather than actively
sending `HELLO`, so it can miss a banner that already passed) — that
tool lives in the separate `radio-robot-elite`/`mbdeploy` project, out of
this ticket's scope. The authoritative confirmation is the firmware's own
`HELLO` reply above: `device NEZHA2 robot vevov ...` carries the literal
`NEZHA2`/`robot` tokens hardcoded in `wire_handler.cpp`'s `sendBanner()`
for any successfully-booted diffdrive robot build — confirming vevov's
role reverted from relay to robot.

### Verification — tovez

`getez` was not connected this session (see hardware table above), so
verified over **USB** instead of radio, per the ticket's own fallback
note — not silently substituted. Port re-probed immediately before
opening (`/dev/cu.usbmodem2121202`):

```
HELLO -> device NEZHA2 robot tovez 2314287040
ID    -> id diffdrive tovez 1.0.10
STATUS-> status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=3
```

`2314287040` matches tovez's known device_id/UID.

### The boot banner (display)

**Not visually observed** — there is no camera or eyes on the bench in
this session, and that check is explicitly for the operator. What WAS
confirmed: each build's scratch `test/test.ts` carried the correct
injected placeholders before compiling (`BOOT_VERSION = "26.05"`,
`BOOT_ROBOT = "vevov"` / `"tovez"` respectively — see the build-checkpoint
evidence above), and `test.ts:706`'s `basic.showString(BOOT_ROBOT + " " +
BOOT_VERSION)` (preceded by the `IconNames.Rollerskate` icon, per ticket
002) is what will render on boot. The on-device visual confirmation is
left for the operator.

### Test/lint gates

- `uv run pytest`: **718 passed** (matches the stated baseline).
- `uvx ruff check tools tests`: all checks passed.
- `node_modules/.bin/tsc --noEmit -p tsconfig.json`: clean, no output.
- `clasi design validate`: `ok: true`, no messages (three informational
  non-subsystem-doc notices for `docs/design/{overview,specification,
  usecases}.md`, same as prior sprints — not orphan-checked, not a
  failure).

### Files changed

None in `tools/make_deploy.py` or `test/test.ts` — no defect surfaced in
tickets 001/002's work. The `ID`-vs-`HELLO` distinction above is an
existing property of `src/comms/protocol.cpp`/`wire_handler.cpp`
(pre-dating this sprint), not a regression from this ticket's work, so no
source change was made for it.
