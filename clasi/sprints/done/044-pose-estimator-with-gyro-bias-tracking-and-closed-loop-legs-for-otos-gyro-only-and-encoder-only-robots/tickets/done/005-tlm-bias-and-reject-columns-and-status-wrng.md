---
id: '005'
title: TLM bias and reject columns and STATUS wrng
status: done
use-cases:
- SUC-004
- SUC-003
depends-on:
- '004'
github-issue: ''
issue:
- otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
- high/goto-under-closed-profile-terminates-legs-early.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# TLM bias and reject columns and STATUS wrng

## Description

Add `bias` (cdeg/min) and a reject counter to TLM FULL; surface wrongWayCount (`wrng`) in STATUS. Update golden_telemetry fixture, wire_adapter column table, and verify downstream parsers (radio-robot-lib, robot-console) tolerate extra columns; note any needed changes in those repos as follow-ups.

## Acceptance Criteria

- [x] TLM FULL carries bias and rejects, updating live at rest
- [x] STATUS reports wrng
- [x] Golden telemetry tests updated and green
- [x] Downstream parser compatibility checked and recorded

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`

## Implementation notes

TLM FULL appends `bias` [cdeg/min, diagValue 42], `rej` [count, 43] and `step` [count, 44] after `cycovr`. Bias is cdeg/min because a typical gyro bias is tens to hundreds of cdeg/min, so integers keep resolution and heading is already cdeg on the wire. `rej` is gyro plus optical rejections (`rejectedCount()`), `step` is `stepCount()`. The snapshot capacity grew from 20 to 24 columns, leaving one slot for ticket 010's disturbance counter. The widest realistic FULL frame is now 100 B thdr / 157 B t, under the 200 B radio cap.

STATUS now ends `... posmove=<n> wrng=<n> sens=<optical|gyro|enc>`. `wrng` reads the same diagValue(25) as the TLM column, which is unchanged. `sens` is `sensorConfigName()` of diagValue(45). `stepCount` is in TLM only: adding it would push the worst-case STATUS line past the 240 B cap. Adding another field later is one `StatusFields` member, one `kDiag*` constant plus shim case, and one format token.

Live at rest: `idleSense()` runs `odomUpdate(r, true)` at `kIdleSensePeriod` (100 ms) whenever the robot is idle, and bias/rej/step read the estimator directly. This is pinned by a source test; the hardware check is ticket 009.

## Downstream parser findings (read-only)

- robot-console `packages/protocol/src/v6/telemetry.ts` zips `thdr` against `t` by position with opaque column names, so extra columns are tolerated. `StatusPanel.tsx` has a fixed label table and passes unlisted keys through raw (as it already does for `posmove`).
- radio-robot-lib `src/host/robot_v6/codec.py` `parse_kv_fields` is a key=value dict ("unknown keys ignored"); it has no telemetry column table.
- This repo's `tools/tlm.py`, `tests/dev/devlink.py` `_tlm_once`, `tools/mb50.py` and `tools/wire_acceptance.py` bind by column or key name. `tlm.py` rejects a `t` row whose arity differs from its header, which still holds.
- Follow-ups, none blocking: robot-console StatusPanel could label `wrng`, `sens` and `posmove`, and show `bias`, `rej` and `step` if it plots FULL columns.
