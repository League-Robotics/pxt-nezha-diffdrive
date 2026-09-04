---
id: '006'
title: 'One calibration of record: camlink.py reads field_calibration.json, robotlink.py
  derives the relay address from the board name'
status: done
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: code-review/one-calibration-of-record-camlink-robotlink.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One calibration of record: camlink.py reads field_calibration.json, robotlink.py derives the relay address from the board name

## Description

Independent of tickets 001-005 (touches only `tools/`); must land
before ticket 007, since the bench acceptance gates (G1-G6) need a
trustworthy camera mount and a reachable radio link to measure the new
profile against, not a stale mount or a silent robot (sprint.md
Solution section).

**TL-02 (Critical)**: `tools/camlink.py:55`'s `MOUNTS[53]` table and
`Cam.__init__` → `ensure_registered()`'s unconditional `register_tag()`
call overwrite the aprilcam daemon's *persistent* registry
(`state_dir/mounts/registry.json`) on every tool start, silently
discarding the 2026-09-02 tag-53 remount recorded in
`field_calibration.json`. Delete `MOUNTS`. `field_calibration.json`
becomes the one calibration of record: `camlink.py` loads it and
registers only what it loaded, and only on an explicit `--register`
flag — never as a constructor side effect.

**TL-01**: `tools/robotlink.py:21-22`'s `ZAVAZ_CHANNEL = 4, ZAVAZ_GROUP
= 10` is stale since vevov's 2026-08-30 move to 37/43
(`.claude/rules/playfield-testing.md`). Derive the relay address from
the board name (the same base-5 `!N` derivation the relay itself uses,
per `radio-address-derived-from-board-name`) or read it from
`field_calibration.json` when present; fix
`test_robotlink.py:183`'s pinned stale constant.

**TL-11**: `field_calibration.json` currently stores the fixed +90°
yaw convention as a probe-fitted 91.116° — exactly the recurrence
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` forbids. Store
only the sub-degree mount residual; the +90° convention itself is never
re-derived or persisted as a measured value.

## Acceptance Criteria

- [x] Starting any `camlink.py`-using tool (with no `--register` flag)
      leaves the aprilcam daemon's registry unchanged — verified by
      reading the registry before and after.
- [x] `--register` is the only path that calls `register_tag()`, and it
      registers only what was loaded from `field_calibration.json`.
- [x] `MOUNTS` is deleted from `camlink.py`.
- [x] `open_link(radio=True)` on vevov gets a pong on the first try
      (channel/group correctly derived or read, not the stale 4/10).
- [x] `test_robotlink.py:183`'s pinned stale constant is fixed to match
      the derivation/read-from-file behavior.
- [x] `field_calibration.json`'s stored yaw value is the sub-degree
      mount residual only, never a probe-fitted absolute like 91.116°.

## Implementation Plan

**Approach**: `camlink.py` — replace the hardcoded `MOUNTS` dict with a
loader that reads `tools/field_calibration.json`'s tag-mount section;
gate `register_tag()` calls behind an explicit CLI flag
(`--register`), never called from `Cam.__init__`/`ensure_registered()`.
`robotlink.py` — replace the `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP` constants
with a function deriving channel/group from the board name (reusing
the existing base-5 derivation this project or `radio-robot-lib`
already implements — check for an importable helper before
reimplementing) or reading an explicit override from
`field_calibration.json`.

**Files to create/modify**:
- `tools/camlink.py`
- `tools/robotlink.py`
- `tools/field_calibration.json` (strip the probe-fitted yaw value down
  to the sub-degree residual, per TL-11)
- `tests/tools/test_robotlink.py` (fix the pinned stale constant)
- `tests/tools/test_camlink.py` (new/updated: assert no registry
  mutation on plain construction; assert `--register` does register)

**Testing plan**: `tests/tools/test_camlink.py`,
`tests/tools/test_robotlink.py`, scoped run. A live-daemon integration
check (registry unchanged before/after a tool start) may need a fake/
mock aprilcam daemon if the existing test suite has one; otherwise this
is confirmed at bench time in ticket 007 as well.

**Documentation updates**: `tools/DESIGN.md`'s "Link layer" section —
**already updated** in this sprint's `design/` overlay
(`clasi/sprints/029-.../design/DESIGN.md`, committed) per Mode 2a; this
ticket's implementation should match what that overlay already
describes, and `close_sprint`'s `design_overlay_apply` step will land
it on the real `tools/DESIGN.md` automatically — no separate real-file
edit needed here (unlike tickets 001/003/004, which hit the
`seed_sprint_design_overlay` slug collision documented in sprint.md's
Open Question notes).
