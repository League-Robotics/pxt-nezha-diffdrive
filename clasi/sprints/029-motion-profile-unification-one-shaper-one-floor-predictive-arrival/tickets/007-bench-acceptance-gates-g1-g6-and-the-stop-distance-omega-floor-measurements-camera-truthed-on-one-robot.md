---
id: '007'
title: 'Bench acceptance: gates G1-G6 and the stop_distance/omega_floor measurements,
  camera-truthed, on one robot'
status: in-progress
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
depends-on:
- '004'
- '006'
github-issue: ''
issue:
- code-review/pivot-end-predictive-termination-and-yaw-floor.md
- code-review/one-velocity-shaper-profile-object-out-of-servicemove.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench acceptance: gates G1-G6 and the stop_distance/omega_floor measurements, camera-truthed, on one robot

## Description

Design §10, on one robot, via the wire, camera as truth. Needs ticket
004 (the config surface must be live to `SET` the new field names) and
ticket 006 (the bench-tool calibration fix — G1-G6 must measure the new
profile against a trustworthy camera mount and a reachable radio link,
not a stale mount or a silent robot; sprint.md's Solution section
sequences this explicitly).

**Run `uv run tools/field_dance.py` first**, per
`.claude/rules/field-dance-first.md`, before any commanded motion —
this is a standing project safety rule, not specific to this ticket,
but load-bearing here since this ticket is the sprint's first real
on-robot run.

**The six gates** (design §10.1, all camera-truthed per
`.claude/rules/measurement-citations.md` — every number names its
capture):
- **G1 pivot accuracy** — 12× `MOVE_X 0 ±1571 100 5000` alternating,
  camera at rest before/after each; mean |error| ≤ 0.5°, sd ≤ 0.4°, no
  per-tick `dutl`/`dutr` sign reversal in the last 10 ticks.
- **G2 arc endpoint** — 6× `MOVE_X 300 785 100 8000` (45°); endpoint
  within 5 mm of (270, 112) body-frame.
- **G3 straight** — 6× `MOVE_X 600 0 200 8000`; camera leg length
  600±3 mm; peak `vl`/`vr` ≤ 220 mm/s; no leg-end bump (monotone in the
  last 10 ticks).
- **G4 jerk** — same as G3, differentiate `vl`/`vr` twice from `TLM
  FULL`; first tick ≤ floor; thereafter |Δv/Δt| ≤ 1.5×`accel`; no tick
  above 2×`decel` at the end.
- **G5 continuous** — `WHEELS_V 200 200 2000` from rest; rise ≤
  1.5×`accel`; no overshoot above 210 mm/s.
- **G6 square tour closure** — `RUN:square` × 3; closure ≤ the current
  baseline (`reports/gopiv-closure-20260901.md`); no regression is the
  bar, improvement is expected.

**The two measurements** (design §10.2):
- **`stop_distance`**: 10 pivots at the yaw floor only (`MOVE_X 0 1571
  <floor-equivalent cruise>`), residual overshoot at rest by camera,
  converted to per-wheel mm. Store in `firmware_bake.stop_distance_mm`.
  Expected order: 0.3-1 mm.
- **`omega_floor`**: from rest, `WHEELS_V ±v ∓v 1500` sweeping v down
  from 70 mm/s per wheel; lowest v with sustained rotation over the
  whole 1.5 s. Expected order: 15-30°/s.

**Docs**: update `src/DESIGN.md` §3 (real file — record the measured
`stopDistance`/`omegaFloor` field comments the same way
`travelCalib`/`trackWidth`/`rotationalSlip` already carry their
measurement history) and `docs/design/specification.md`'s constants
table (design §11's own ticket-5 note). **Retire `pivot_overrun`** from
every robot config — this is the `radio-robot-lib` `firmware_bake`
cross-repo change (design §12 open question 2); flag explicitly in this
ticket's close-out if it cannot be completed from this repo alone.

## Acceptance Criteria

- [ ] `field_dance.py` passes before any other commanded motion this
      ticket runs.
- [ ] G1-G6 all pass, each cited with its capture artifact
      (`.claude/rules/measurement-citations.md`).
- [ ] `stop_distance` and `omega_floor` measured, recorded in
      `firmware_bake.stop_distance_mm` and `MotionLimits::omegaFloor`'s
      default, and cited with their capture artifacts.
- [ ] `src/DESIGN.md` §3 updated (real file) with the measured
      constants' field-comment history.
- [ ] `docs/design/specification.md`'s constants table updated.
- [ ] `pivot_overrun` retired from every robot config this repo
      controls; the `radio-robot-lib` cross-repo side is explicitly
      flagged if not completed here.
- [ ] Design §7's predicted "after" numbers (already confirmed on ideal
      wheels by ticket 003's probe) are now confirmed or contradicted on
      real hardware — record which.

## Implementation Plan

**Approach**: Bench session, one robot — confirm the current robot
assignment for this session/machine before starting (no standing
ownership table; per project practice this is set per session, not
inherited from prior notes), one continuous sitting where practical.
Run `field_dance.py`, then the two §10.2 measurements first (they feed
`firmware_bake`), then G1-G6 in order.

**Files to create/modify**:
- `radio-robot-lib/config/robots/<robot>.json` (or flag as cross-repo
  if inaccessible) — `stop_distance_mm`, drop `pivot_overrun_mm`.
- `src/DESIGN.md` §3 (real file)
- `docs/design/specification.md` (constants table)
- `captures/bench-acceptance-029-<date>/` (new — camera captures, TLM
  logs; `captures/` is gitignored by project convention, so `git add
  -f` any capture cited by a MEASURED claim, per
  `.claude/rules/measurement-citations.md` — a citation naming a path
  git never tracked points at nothing for the next reader)
- `reports/` (project convention: chart/image writeups ship as
  markdown under repo-root `reports/`, not a bare image file, if this
  session produces charts)

**Testing plan**: No new automated test — this is a hardware
acceptance run. The automated coverage (`test_profile_probe.py` et al.)
was already established in ticket 003; this ticket confirms it on real
hardware.

**Documentation updates**: `src/DESIGN.md` §3, `docs/design/
specification.md`, plus whatever `reports/` writeup the bench session
produces.

## Session Notes (2026-09-03, tovez, PARTIAL -- stopped at placement check)

Full account: `captures/bench-acceptance-029-20260903/notes.md`
(includes camera captures cited below).

**Build and flash: PASS.** `make_deploy.py --robot tovez --radio-link`
failed its first attempt on a real defect -- `src/shims.cpp:1481`'s
`setLimits()` (added by ticket 004) had its `//%` shim declaration
split across two lines, which the PXT packager cannot parse (every
other `//%` shim in the file is single-line; the file's other
multi-line declarations are deliberately *not* `//%`-annotated).
Fixed by joining the declaration onto one line; no behavior change.
Rebuilt clean: `.tmp/deploy-head/built/binary.hex` (1680281 bytes).
Flashed via `mbdeploy deploy tovez --remote --hex ...` to farm node
meili (ENUM 6) -- first erase attempt failed
(`result code 0x67`), mbdeploy's automatic CTRL-AP mass-erase recovery
fixed it, retry programmed cleanly (418816 bytes, 0 identical). Post-
flash: `HELLO` -> `device NEZHA2 robot tovez 2314287040`, `VER` ->
`ver 1.20260903.1`, `ID` -> `id diffdrive tovez 1.20260903.1 tovez`.

**Camera/placement check: STOPPED, no motion commanded.**
`mcp__aprilcam__get_tags` on `arducam-ov9782-usb-camera`, two polls
~8 s apart, returned only the ArUco border tags -- no AprilTag-family
tag at all, meaning neither AprilTag 1 (field centre) nor AprilTag 52
(tovez) was visible. A raw and a deskewed frame
(`captures/bench-acceptance-029-20260903/raw-frame-placement-check.jpeg`,
`deskewed-frame-placement-check.jpeg`) show why: **the playfield
currently has the KIPR line-following mat laid over it with soda cans
as obstacles**, covering AprilTag 1, and tovez is not on the field at
all. Lights confirmed on both by the Shelly (`output: true`) and by
the frame itself (not dark).

Per the ticket's mandatory order, this is a stop condition: no
`field_dance.py`, mount registration, or `MOVE_X` was run. **Needs a
human**: clear the KIPR mat and cans off the playfield, place tovez at
field centre, before the next session can continue from step 3
(`field_dance.py` / mount registration) through G1-G6 and the §10.2
measurements. All of the ticket's acceptance criteria beyond
build/flash remain unmet for that reason -- see checklist below.
