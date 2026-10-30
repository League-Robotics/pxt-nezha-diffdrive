---
id: '015'
title: STATUS active drops to 0 inside a GO_TO_W
status: done
use-cases:
- SUC-002
depends-on:
- '014'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# STATUS active drops to 0 inside a GO_TO_W

## Description

Found on hardware on 2026-10-29 (tovez, build 012+013,
`captures/sprint044-acceptance-20261028/tovez-status-trace3.jsonl`).
Tracing STATUS at 10 Hz against TLM wheel counts through one
`GO_TO_W 312 -40 120 5 30000` (target behind, so pivot then straight):

    0.69s  active=1 done=3
    2.57s  active=0 done=3   <- pivot ended, closure dwell (ticket 007)
    2.89s  active=1 done=3
    3.07s  active=0 done=3   <- again
    3.30s  active=1 done=3
    5.44s  active=0 done=3
    5.70s  active=0 done=4   <- command really complete
    last wheel movement 5.32s

`done` is right; `active` is not. It reflects the current engine
segment, and the pivot-closure dwell / correction pivots (007) and the
residual trims (008) are separate segments within one command. Any
client that waits for `active` to fall reads a mid-leg pause as arrival.
`tests/dev/devlink.py send_move` did exactly that. It corrupted
tonight's drift runs: legs were planned from mid-leg poses, so camera
chords disagreed with OTOS chords by up to 19 cm (`tovez-drift2-fix.jsonl`
legs 4-11), and arrival misses inflated. `send_move` now waits for `done`;
robot-console, radio-robot-lib and student RUN programs that use
`isMoving()`-style checks may still be affected.

Change: STATUS `active` (and any block/TS "is moving" API backed by the
same state) stays 1 from command start until the command's done fires,
across closure dwell, correction pivots, pending straight and trims.
Check the RUN/blocks path too, e.g. waits on "motion active" in
src/blocks and test/test.ts helpers like tickedMove.

## Acceptance Criteria

- [x] Host test (shims_cpp rig or wire tests): STATUS active stays 1
      through a GO_TO_W with closure corrections and a residual trim, and
      falls in the same tick done advances
- [x] Blocks/TS "moving" helpers checked and consistent; findings noted
- [x] Downstream (robot-console, radio-robot-lib) use of `active`
      checked read-only and recorded
- [x] `uv run pytest tests/host` green; hex builds

## Resolution

Root cause: STATUS `active` (`WireAdapter::status()`) was `ready && !halted &&
(velocityLeft != 0 || velocityRight != 0)`, a wheels-moving bit. `done` reads
the engine's segment state, which stays live across a GO_TO_W's closure dwell,
correction pivots, pending straight and trims, but the wheels are at rest
between those segments.

Change: `MotionEngine::isLegLive()` (segment live and a `goToW()`
closure/goal attached), exposed as `diagValue(47)`, OR-ed into `active`. `done`
and ack timing untouched; plain `MOVE_X`, `WHEELS_*` and `MOVE_V` attach no
closure or goal, so their `active` is unchanged.

Blocks/TS: `moving()` (`isMoveActive() || isPositionMoveActive()`) and
`progress()` follow `seg_.active`, which spans the whole leg, so they were
already consistent. `test/test.ts` `tickedMove` ticks `tickDrive()`, not a
STATUS wait. Nothing changed there.

Downstream (read-only):
- robot-console: `packages/host/src/connect/harvester.ts` parses `active`
  into the status snapshot and `packages/ui/src/components/StatusPanel.tsx`
  shows it as "Moving". Display only; no code waits for it to fall.
- radio-robot-lib: no live consumer of STATUS `active`; only the archived v5
  reference (`src/archive/protocol-v5-ref/protocol.py`) reads an active flag.
- This repo: `tests/dev/devlink.py send_move` already waits on done.

Tests: `tests/host/test_status_active_through_leg.py`.
