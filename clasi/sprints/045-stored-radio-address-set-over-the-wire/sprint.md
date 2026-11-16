---
id: '045'
title: Stored radio address set over the wire
status: executing
branch: sprint/045-stored-radio-address-set-over-the-wire
use-cases: []
issues:
- stored-radio-address-set-over-the-wire.md
- run-ts-jsdoc-still-says-radio-group-10.md
- high/the-wire-has-no-reboot-verb.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 045: Stored radio address set over the wire

## Goals

1. A robot keeps a radio channel and group in flash that a console can
   set, read back and clear over USB, and that survive flashing a
   different program.
2. The boot order is explicit program setting, then stored, then
   name-derived, and the robot says which one it used.
3. Confirm on hardware that `_reboot` is the remote reset the wire was
   missing, and fix the stale `enableRadioLink()` JSDoc.

## Problem

The fleet channel map (`mbtools` `docs/design/channel-map.md`, step 3)
needs the robot half: today `setupRobot()` takes the radio address from
the micro:bit's name unless the program set one, and nothing writes an
address into the robot. The robot-console radio dialog (Save, then keep it
across re-flashes) has nothing to talk to. Separately, `run.ts`'s
`enableRadioLink()` JSDoc still says "group 10", and
`the-wire-has-no-reboot-verb.md` predates the `_reboot` run command.

## Solution

Mirror the stored Wi-Fi address (`#net.ip`, `_netshow/_netset/_netclear`,
`netstore.*` reports) for the radio: `#radio.ch` and `#radio.grp` settings,
`_radioshow`, `_radioset <channel> <group>`, `_radioclear`, and
`radiostore.values` / `radiostore.fail` reports. A set takes effect at the
next boot; the console follows it with `_reboot`. No live retune.

`the-wire-has-no-reboot-verb.md`: read against the code, `_reboot`
(`program.ts` `reboot()`, registered in `setupRobot()`) satisfies it. It
acks before resetting (`reboot.ok`, flushed, 120 ms pause), refuses with
`reboot.fail` while a program added by `addProgram()` is running, and calls
`stop()` first. It is a run command, not a `REBOOT` wire verb, so it needs
`setupRobot()` in the program and works on any carrier that carries `RUN:`.
Residue to confirm on hardware, not to build: that the ack reaches the host
before the reset on USB, and the behaviour when a raw `MOVE_X` (not a
program) is mid-flight (`stop()` runs, so the motors stop, but this is
UNVERIFIED). A `REBOOT` verb in `wire_handler` is out of scope.

## Success Criteria

- Host tests cover the radio store's validation, boot-order source choice
  and report shape; the full host suite, type-check and toolbox-order tests
  pass.
- On a real robot over USB: set, `_reboot`, boot line and STATUS show the
  stored address; flash another program and then this one, address kept;
  clear and reboot, name-derived address returns. Results cite capture
  files.
- The two issues that are not the main feature move to done with their
  residue noted.

## Scope

### In Scope

- Stored radio address, boot order, source reporting, `_radioshow`,
  `_radioset`, `_radioclear`, in `src/blocks/program.ts` (and a small
  helper module if it keeps `program.ts` cohesive).
- `run.ts` JSDoc fix (the `setupRadio` default of 10 is untouched).
- Hardware acceptance, including `_reboot`.
- Docs: `src/blocks/DESIGN.md` (via the design overlay), `src/DESIGN.md`
  mention, `docs/robot-connections.md`, `setupRobot()` JSDoc command list.

### Out of Scope

- A live radio retune, a `REBOOT` wire verb, STATUS carrying the source
  (the source is in the boot line and `_radioshow`; STATUS's 240 B cap and
  the C++ seam are not worth it).
- The console half (robot-console) and registry (mbtools).
- Release steps. Post-close follow-ups for the team-lead, not tickets: bump
  the version on the 1.x line, tag, then cut a nezha-robot-template release
  built on it so the console's calibration firmware carries the feature.

## Test Strategy

`tests/host/` cannot compile or run PXT TypeScript (`tests/host/README.md`),
so the radio logic is tested two ways. The pure decisions (validate a
channel/group pair, choose the source) go in a small side-effect-free TS
file with a text-level source-pin test in the style of
`test_boot_banner_source_pin.py`, plus a Python re-statement of the
validation table checked against the pinned bounds. The existing
`test_typescript_typecheck.py` and `test_block_toolbox_order.py` guard the
block surface. The real proof is the hardware acceptance ticket, driven
over USB with a script in `tests/dev/`.

## Architecture

**Sizing: Compact** — one module (`src/blocks/program.ts`'s setup-robot
area) gains a stored-setting store that mirrors an existing one; no new
cross-module dependency, no dependency-direction change, no data-model
change beyond two more `#` settings keys. Plus two one-line/doc touches.

### What Changed

`program.ts` gains a stored radio address (two `settings` numbers under
`#radio.ch` / `#radio.grp`), a source decision in `setupRobot()` (program,
else stored, else name), three run commands, and a `radiostore.*` report
pair. The boot line becomes `boot radio <name> ch N grp M <source>` where
source is `program`, `stored` or `name`; `_radioshow` reports `channel`,
`group`, `stored` (0/1), `source`, `default_channel`, `default_group`.
`run.ts` gets a JSDoc correction only.

### Why

Gives the console a write path for the fleet channel map while staying
inside the existing pattern, so the Wi-Fi and radio stores read the same
and a reviewer learns one idiom.

### Impact on Existing Components

None beyond the boot line's trailing source word; host tools that parse the
boot line (mbtools, robot-console) must tolerate a trailing token. Checked
by the acceptance ticket. A robot with no stored values behaves as before
(source `name`, or `program` when the program set one).

### Migration Concerns

None. Robots without the keys fall through to the name-derived address.
Older firmware answers `_radioset` as an unknown run command; the console
treats that as "firmware too old".

### Design Rationale

Decision: a set takes effect at the next boot. Context: mid-run retune is
unverified (`clasi/issues/low/changing-the-radio-group-mid-run-is-unverified.md`).
Alternative: apply live. Why not: the radio could go deaf until power
cycle, and the console reboots anyway. Consequence: one extra `_reboot`
per change.

Decision: validation lives in the run command, and an out-of-range or
non-integer value stores nothing and answers `radiostore.fail`. Both values
are validated together so a half-written pair cannot be stored.

### Architecture Self-Review (compact scope)

Cohesion: the module addition has one purpose, "the radio address that
setupRobot() uses". Boundary: store and report in `program.ts`, address
math stays in `run.ts` (`radioAddressForName`). No new cross-module
dependency; the sizing holds. Verdict: APPROVE.

### Open Questions

Whether to keep the group stored at all given the group is name-derived
fleet-wide: stored anyway, per the stakeholder.

## Use Cases

### SUC-001: Set a robot's radio address from the console
- **Actor**: robot-console operator
- **Preconditions**: robot on USB running a program that calls `setupRobot()`
- **Main Flow**: console sends `_radioset ch grp`, reads back `radiostore.values`, sends `_reboot`, reads the boot line
- **Postconditions**: the robot is on the stored address, after a re-flash too
- **Acceptance Criteria**:
  - [ ] set answers with the stored values; invalid values answer `radiostore.fail` and store nothing
  - [ ] boot line and STATUS show the stored address, source `stored`

### SUC-002: Return a robot to its name-derived address
- **Actor**: robot-console operator
- **Main Flow**: `_radioclear`, `_reboot`
- **Postconditions**: boot line shows the name-derived address, source `name`
- **Acceptance Criteria**:
  - [ ] `_radioshow` after clear shows `stored` 0 and the default pair

### SUC-003: Reboot a robot remotely
- **Actor**: operator or script
- **Main Flow**: `_reboot` while idle; board resets and re-announces
- **Acceptance Criteria**:
  - [ ] `reboot.ok` arrives before the reset; `reboot.fail` while a program runs

## GitHub Issues

None.

## Definition of Ready

- [x] Sprint planning document is complete
- [x] Architecture review passed
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Stored radio address, boot order and the _radio run commands | none |
| 002 | Fix the enableRadioLink JSDoc that says group 10 | none |
| 003 | Hardware acceptance of the stored radio address and _reboot | 001, 002 |
