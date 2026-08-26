---
id: '003'
title: Build checkpoint, then flash vevov (ch 4) and tovez (ch 3) and confirm each
  on its own relay
status: open
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

- [ ] `built/binary.hex` is produced at approximately **1.44 MB** — sprint
      018 measured a known-good build at **1,448,621 bytes**. **Check the
      byte size explicitly, by reading the file size, not just by checking
      that the build logged success.** A 27%-short hex has previously passed
      a clean-looking build log — see
      `clasi/issues/make-deploy-accepts-a-silently-incomplete-hex.md`. If the
      size is short, wipe `.tmp/deploy-head` using Python's `shutil.rmtree`
      (plain `rm -rf` may be sandbox-denied in this environment) and rebuild
      from a clean scratch copy before retrying.
- [ ] Zero `:0400000A` markers in the hex.
- [ ] No `.tmp/deploy-head/built/dockeryt/` directory present.
- [ ] No `srec_cat` invocation and no `INTERNAL ERROR` anywhere in the build
      log.
- [ ] All ten nezha-diffdrive translation units appear as `Building CXX
      object` lines in the build log (confirms the vendored/core sources
      actually compiled, not a stale cached object).

Run this checkpoint once per robot (vevov, then tovez), since ticket 001
makes the build per-robot — a channel-3 build for tovez and a channel-4
build for vevov are two separate build artifacts, not one hex reused.

## Flashing and Verification

- [ ] Flash **vevov** from its own (channel 4) build.
- [ ] Flash **tovez** from its own (channel 3) build.
- [ ] After each flash, verify the robot's identity and channel:
  - `ID` returns the expected robot name for that board.
  - The boot banner displays `IconNames.Rollerskate` followed by the version
    string in the `DD.RR` format ticket 002 defined (day-of-month, dot,
    zero-padded revision — confirm the digits match the actual build's
    version, not a fixed example).
- [ ] Confirm each robot on its **own** relay: vevov over **zavaz** (channel
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

- [ ] Build checkpoint (all sub-items above) passes for both vevov's and
      tovez's builds, with byte size checked explicitly by reading the file,
      not inferred from a clean log.
- [ ] vevov is flashed, responds to `ID` with its own name, shows the boot
      banner with the correct version, and is confirmed reachable over
      zavaz on channel 4.
- [ ] tovez is flashed, responds to `ID` with its own name, and shows the
      boot banner with the correct version. It is confirmed reachable either
      over getez on channel 3, or (if getez is unavailable) over a USB bench
      link — with the fallback explicitly noted, not silently substituted.
- [ ] vevov's role announcement is confirmed as `NEZHA2`/robot, not
      `RADIOBRIDGE`/relay.
- [ ] Any erase-sector/mass-erase recovery encountered during flashing is
      recorded in the ticket's closing notes rather than treated as a defect
      to chase.
- [ ] `clasi design validate`, `ruff`, `tsc --noEmit`, and the full pytest
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
