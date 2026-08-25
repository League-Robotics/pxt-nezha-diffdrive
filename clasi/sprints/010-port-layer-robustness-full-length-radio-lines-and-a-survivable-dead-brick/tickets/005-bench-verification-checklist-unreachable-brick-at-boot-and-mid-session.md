---
id: '005'
title: 'Bench verification checklist: unreachable brick at boot and mid-session'
status: open
use-cases: ['SUC-002']
depends-on: ['003', '004']
github-issue: ''
issue: unpowered-nezha-brick-wedges-program-at-boot.md
completes_issue: false  # This ticket produces the checklist document,
  # not the executed bench check. The issue itself stays open until a
  # stakeholder actually walks this checklist against real hardware
  # (out of band, after this sprint closes) -- precedent: 004/005,
  # 006/006, 007/008, 008/006 all follow the same "checklist ticket does
  # not itself prove the bench outcome" shape.
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench verification checklist: unreachable brick at boot and mid-session

## Description

Bench-only handoff ticket (precedent: sprint 004 ticket 005, sprint 006
ticket 006, sprint 007 ticket 008, sprint 008 ticket 006) — no code,
no host test. Neither this project's `NezhaMotorPort`
(`nezha_port.cpp` requires `pxt.h`) nor `RadioTransport` has ever had a
host-portable seam for the failure paths this sprint addresses; the
robot behaviors this sprint's Success Criteria require can only be
confirmed live. This ticket produces the checklist a stakeholder runs at
the bench, informed by tickets 003 and 004's findings and by the new
`cyc=` STATUS field.

## Acceptance Criteria

- [ ] A written checklist exists (in this ticket or a linked bench-notes
      file) covering, at minimum:
  - [ ] **Boot-priming path**: with the Nezha brick physically powered
        down or I2C-disconnected, flash and boot the robot. Confirm: the
        boot banner and every subsequent v6 reply (`VER`/`ID`/`STATUS`/
        `GET`) are still emitted (protocol fiber alive); `STATUS` reports
        `connL=0 connR=0`; issuing a command that ticks the kernel (e.g.
        `RUN:straight:0` or a wire motion verb) advances `cyc` above 0
        (the new field from ticket 003) while `i2cFaultCount` climbs and
        `connL`/`connR` stay 0; a motion block/verb becomes a no-op
        rather than hanging the program.
  - [ ] **Mid-session disconnection**: with the robot already ticking
        (a live `while (tickDrive())` loop or an in-flight wire motion
        obligation), physically disconnect the brick. Confirm the same
        signature (`connL`/`connR` drop to 0, `i2cFaultCount` climbs,
        `cyc` keeps advancing, TLM/DIAG/protocol stay alive, motion
        stops being effective) rather than the program hanging.
  - [ ] **Never-ticked control case**: on a robot with a genuinely
        healthy, connected brick that nothing has ticked yet, confirm
        `STATUS` shows `cyc=0 connL=0 connR=0 i2cf=0 ready=0` — the same
        shape as the boot-priming case above at the instant before any
        tick — demonstrating why `cyc=` (not `ready`/`connL`/`i2cf`
        alone) is the correct disambiguator, per SUC-002.
  - [ ] Record actual wall-clock timing observed for the boot-priming
        path with a disconnected brick (how long until the boot banner/
        first reply appears) — this is the direct field measurement
        ticket 004's platform-timeout research could not make without
        hardware, and closes that ticket's own open question either way.
- [ ] The checklist references ticket 004's findings (whatever guard, if
      any, shipped) so the bench operator knows what behavior to expect
      versus what remains unguarded.
- [ ] Results are recorded back into
      `unpowered-nezha-brick-wedges-program-at-boot.md` (or a superseding
      bench-notes update) once actually run — this ticket's own
      completion is the checklist existing and being ready to execute,
      not the bench run itself (see `completes_issue: false` above).

## Implementation Plan

**Approach.** Documentation only — a precise, executable checklist, not
prose description. Depends on tickets 003 (the `cyc=` field the
checklist relies on) and 004 (whatever guard or finding it produces)
so the checklist reflects the sprint's actual shipped state rather than
its planned one.

**Files to create/modify:** a checklist section in this ticket, or a
linked file under this sprint's directory if the stakeholder prefers a
standalone bench-notes document (matching the existing convention of
`clasi/sprints/.../issues/*.md` bench-note files used elsewhere in this
project's sprint history).

**C++11 gate coverage.** N/A — no code changes.

**Testing plan.** N/A — bench-only by construction; see this sprint's
own Test Strategy section for why (`NezhaMotorPort` has no host-portable
seam for a truly non-returning I2C call).

**Documentation updates.** This ticket's own checklist; the sprint's
design overlay records the sprint-level Success Criteria this checklist
exists to satisfy.
