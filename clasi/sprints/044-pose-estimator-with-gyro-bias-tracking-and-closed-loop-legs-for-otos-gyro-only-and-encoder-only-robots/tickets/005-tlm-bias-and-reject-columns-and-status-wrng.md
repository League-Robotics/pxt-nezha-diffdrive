---
id: '005'
title: TLM bias and reject columns and STATUS wrng
status: open
use-cases: [SUC-004, SUC-003]
depends-on: ['004']
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

- [ ] TLM FULL carries bias and rejects, updating live at rest
- [ ] STATUS reports wrng
- [ ] Golden telemetry tests updated and green
- [ ] Downstream parser compatibility checked and recorded

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
