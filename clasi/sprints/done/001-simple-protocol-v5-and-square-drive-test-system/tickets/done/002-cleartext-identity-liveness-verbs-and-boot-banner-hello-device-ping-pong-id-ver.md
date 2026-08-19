---
id: '002'
title: Cleartext identity/liveness verbs and boot banner (HELLO/DEVICE, PING/PONG,
  ID, VER)
status: done
use-cases:
- SUC-001
- SUC-005
depends-on:
- '001'
github-issue: ''
issue: implement-simple-protocol-v5.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Cleartext identity/liveness verbs and boot banner (HELLO/DEVICE, PING/PONG, ID, VER)

## Description

Implement the four cleartext, no-data command verbs — `HELLO`, `PING`,
`ID`, `VER` — and their replies (`DEVICE`, `PONG`, `ID`, `VER`), plus
the unsolicited boot/identity banner, on top of ticket 001's transport
and line-grammar foundation. Reference: protocol-v5.md §2.4.

## Acceptance Criteria

- [x] Boot banner `DEVICE:NEZHA2:robot:<name>:<serial>` is emitted once
      at startup without any host request.
- [x] `HELLO` → replies with the same `DEVICE:` banner.
- [x] `PING` → replies `PONG:t=<ms>`, using the robot's own clock
      (reused from `platform_ports.h`'s `CodalClock`) at
      reply-formatting time, formatted as an integer (matching the
      spec's `newlib-nano` rationale — no floating-point formatting).
- [x] `ID` → replies `ID:<drivetrain>:<profile>:<version>`, built from
      this project's own identity constants.
- [x] `VER` → replies `VER:<version>`, using this extension's existing
      version identity (`pxt.json`'s `version`, currently `1.0.0` —
      see `specification.md` §13 for this project's versioning
      constraint).
- [x] The `name`/`serial` fields in the `DEVICE` banner are a genuinely
      new concept for this project (not currently defined anywhere in
      `specification.md`); the implementer picks a reasonable source
      (e.g., a fixed default plus a setter, or a build-time constant)
      and documents the choice in the PR/ticket notes — this is an
      implementation decision, not pre-specified by this sprint's
      architecture.
- [x] All four replies are sent reliably from the protocol fiber (a
      blocking write within that fiber is an acceptable approximation
      of the spec's `sendReliable()` bounded-wait semantics on this
      single-fiber platform — document the approximation in code
      comments).
- [x] An unrecognized or out-of-place cleartext verb (e.g., a stray
      `DEVICE`/`PONG` received host→robot) does not crash or hang the
      protocol loop. No fault-reporting wire plane is required this
      sprint (consistent with sprint.md Open Question 1's
      fire-and-forget model) — silently ignoring is acceptable.

## Implementation Notes

- `<name>`: fixed default constant `"nezha"` (`kDeviceName` in
  `protocol.cpp`). No per-robot naming config exists yet in this
  extension (no setter, no block) — a follow-up if a future sprint
  ever needs to tell two robots on the same bench apart by name.
- `<serial>`: this micro:bit's own hardware serial number, via CODAL's
  `microbit_serial_number()` — the same source pxt-microbit's own
  `control.deviceSerialNumber()` block reads. Genuinely unique per
  device, nothing invented or cached.
- `<drivetrain>`/`<profile>` (`ID`'s reply): `"diffdrive"` (this
  extension's kinematic type, matching the package name and
  `diffdrive.h`/`.cpp`) and `"tovez"` (the tuning bake `shims.cpp`'s
  `Rig` defaults are measured from — see `shims.cpp`'s own
  "tovez-measured defaults" comment). Both are real, already-existing
  identifiers, not new inventions.
- `<version>` (`ID` and `VER`'s reply): a `kVersion = "1.0.0"` constant
  manually kept in sync with `pxt.json`'s `"version"` field — there is
  no build-time injection mechanism in this repo's C++ build (unlike
  the reference firmware's generated `version_generated.h`), so this
  is the same manual-sync convention `specification.md` §13 already
  documents for this project's versioning. Whoever next bumps
  `pxt.json`'s version should update this constant alongside it.
- Boot-time auto-start wiring: a new `startProtocol()` C++ export
  (`protocol.cpp`) wraps the `protocol()` lazy singleton; `main.ts`'s
  `diffDrive` namespace calls it (`_startProtocol()`) as a top-level
  statement, so it runs once when this extension's compiled code
  loads — independent of whether any block is ever placed in a user's
  program. This is what makes the boot banner go out "without any host
  request" per SUC-001.
- Verification: a real `pxt build` (pxt-microbit target,
  codal-microbit-v2 SDK) in a scratch copy compiled `protocol.cpp.obj`,
  `serial_transport.cpp.obj`, `shims.cpp.obj`, and `diffdrive.cpp.obj`
  cleanly, and compiled `pointers.cpp.obj` (PXT's generated shim
  binding layer), confirming the `_startProtocol()`/`startProtocol()`
  shim wiring resolves correctly. `nezha_port.cpp.obj` failed with the
  same pre-existing, untouched, out-of-scope error ticket 001 already
  documented. Hardware verification (does the banner/replies actually
  reach a serial terminal) remains deferred to the stakeholder via
  `mbdeploy`/"zetuv".

## Implementation Plan

**Approach**: Register `HELLO`/`PING`/`ID`/`VER` in ticket 001's verb
registry as cleartext, no-data verbs. `PONG`'s handler is the only one
needing a runtime read (the clock); `DEVICE`/`ID`/`VER` are static or
near-static string formatting with no `Rig`/kernel dependency.

**Files to create/modify**: the Protocol/Comms module from ticket 001
(add handlers); optionally a small new identity-constants file if the
implementer prefers separating `name`/`serial`/`drivetrain`/`profile`
constants out — add to `pxt.json`'s `files` list if so.

**Testing plan**: Desk-check each reply's exact format against the
spec's grammar (colon-joined throughout — note `PING`'s reply changed
from v4's `"OK pong t=<ms>"` to `"PONG:t=<ms>"`, so there is no legacy
shape to preserve here). No automated test harness exists in this repo
(see sprint.md Test Strategy). Hardware verification deferred to the
stakeholder via `mbdeploy`/"zetuv" (`test-on-microbit-zetuv-via-mbdeploy.md`),
same as ticket 001.

**Documentation updates**: None beyond code comments. Note in the PR
that `name`/`serial` identity is new state this ticket introduces —
worth a follow-up mention in `docs/design/specification.md` in a later
sprint, out of scope here.
