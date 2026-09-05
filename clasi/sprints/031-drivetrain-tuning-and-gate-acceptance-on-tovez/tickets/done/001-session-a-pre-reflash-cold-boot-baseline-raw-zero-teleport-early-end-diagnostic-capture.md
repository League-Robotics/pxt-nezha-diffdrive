---
id: '001'
title: 'Session A: pre-reflash cold-boot baseline (raw-zero teleport + early-end diagnostic
  capture)'
status: done
use-cases:
- SUC-008
- SUC-003
depends-on: []
github-issue: ''
issue:
- sprint-030-hardware-acceptance-needs-one-bench-session.md
- segment-moves-end-early-just-after-boot.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session A: pre-reflash cold-boot baseline (raw-zero teleport + early-end diagnostic capture)

**Type: (a) hardware/playfield — team-lead executes personally.**

## Description

tovez is currently running firmware `1.20260903.1`, pre-sprint-030. Two
things need a genuinely cold-power-up run on THIS firmware before any
reflash happens, because both need a "before" that a fixed board can no
longer produce:

1. Sprint-030 ticket 004's raw-zero rejection fix needs a **pre-fix
   baseline** cold-power-up run — without it, a clean post-fix run
   proves nothing, since a healthy cold start also looks clean
   (`sprint-030-hardware-acceptance-needs-one-bench-session.md` item 3).
2. The cold-boot early-ending-segment diagnosis
   (`segment-moves-end-early-just-after-boot.md`) needs `DIAG`/STATUS
   `reason=` captured at the instant of an early end on a cold boot,
   polled at 8 Hz from the send — the wrong-way counter explains 2 of
   4 known cases; the other 2 (straight-line stops with no wrong-way
   path) need fresh frames to diagnose.

Combine both into the same power cycles: three cold boots, each
followed by (a) the first ~40 cm of travel logged on camera + encoder,
and (b) the first ~10 `MOVE_X`/pivot segments polled at 8 Hz.

Pre-flight per `playfield-testing.md`: confirm room lights ON (Shelly
`192.168.1.122`), camera calibrated, AprilTag 1 at world (0,0), tag 52's
registration confirmed (`mount_yaw_rad=-pi/2` baked — read `yaw_rad`
straight, never through `robot_heading_from_tag_yaw()`). tovez rides on
zilch (Pi Zero mounted on the robot) — no cable drag; connect over
zilch's serial daemon.

## Acceptance Criteria

- [ ] Three independent cold boots (full power cycle, not a warm
      reconnect), each producing: camera + encoder log of the first
      ~40 cm of travel, and an 8 Hz STATUS poll log of the first ~10
      commanded segments.
- [ ] For each boot, `reason=` at any early-ending segment is captured
      verbatim (not inferred after the fact).
- [ ] Every artifact is committed with `git add -f` (captures/ is
      gitignored) and cited by path, board, and date in the ticket's
      closing note, per `measurement-citations.md`.
- [ ] If a boot shows no early-ending segment in its first 10 moves,
      that is recorded too — absence of the defect on a given boot is
      data, not a reason to stop early.

## Testing

- **Existing tests to run**: none — this is a data-capture ticket, no
  code changes.
- **New tests to write**: none here; ticket 005 turns this capture into
  a host test with a lagged, skewed wheel model.
- **Verification command**: N/A (hardware capture ticket).
