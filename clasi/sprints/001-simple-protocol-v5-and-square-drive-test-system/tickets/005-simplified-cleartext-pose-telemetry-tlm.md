---
id: '005'
title: Simplified cleartext pose telemetry (TLM)
status: done
use-cases:
- SUC-004
depends-on:
- '001'
- '002'
github-issue: ''
issue: implement-simple-protocol-v5.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Simplified cleartext pose telemetry (TLM)

## Description

Emit a cleartext, pose-only `TLM` line (`x`, `y`, `heading`) on a
regular cadence from the protocol loop, reading pose via the same
`Rig`/odometry accessors `main.ts`'s Pose blocks already use
(`poseX`/`poseY`/`poseHeading`-equivalent). No binary framing, no
COBS/CRC, no ack data on this line — this is this sprint's one
deliberate deviation from the reference spec's binary
`ReplyEnvelope`/`Telemetry` framing (protocol-v5.md §8), per
`implement-simple-protocol-v5.md`'s explicit scope.

## Acceptance Criteria

- [x] `TLM` line is emitted on a regular cadence, independent of
      whether the host has sent any command.
- [x] `TLM` line carries exactly `x`, `y`, `heading` in cleartext — no
      other fields, no binary framing, no ack-ring data.
- [x] TLM emission does not starve the protocol loop's ability to read
      and dispatch incoming commands within the same fiber's
      cooperative scheduling (e.g., check for pending input each cycle
      alongside emitting telemetry).
- [x] Pose values read via the odometry accessors reflect the same
      pose a concurrent MakeCode `pose x`/`pose y`/`heading` block read
      would return.
- [x] No changes to `diffdrive.h`/`diffdrive.cpp` or to the existing
      odometry math in `shims.cpp`.

## Implementation Plan

**Approach**: Add a telemetry emission path within (or alongside) the
Protocol/Comms module from tickets 001/002, writing directly through
the Transport module on its own cadence, reading pose via the same
accessors `shims.cpp` already exposes to `main.ts`
(`poseX`/`poseY`/`poseHeading`). Exact cadence (e.g., matching the
kernel's ~24 ms period, or a coarser rate) is an implementer decision —
sprint.md does not mandate a specific rate.

**Files to create/modify**: the Protocol/Comms module, or a small
sibling telemetry file (implementer's choice, per sprint.md's
"Telemetry as a focused piece of the Protocol/Comms module or a small
sibling file").

**Testing plan**: Desk-check formatting and cadence logic. The browser
simulator does not exercise this path (protocol layer is C++-only,
reached over serial). Hardware bench verification deferred to the
stakeholder via `mbdeploy`/"zetuv"
(`test-on-microbit-zetuv-via-mbdeploy.md`) — once on hardware, ticket
006's square-drive test can serve as a convenient motion source to
visually check `TLM` output against, per
`implement-simple-protocol-v5.md`'s own cross-reference.

**Documentation updates**: None beyond code comments.
