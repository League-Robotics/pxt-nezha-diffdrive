---
id: '015'
title: Bake final kernel gains and per-wheel calibration as firmware defaults; rebuild
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['011', '012']
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bake final kernel gains and per-wheel calibration as firmware defaults; rebuild

**Type: (b) desk work — programmer/team-lead build step. No hardware.**

## Description

Bake ticket 011's converged `(kp, ki, kaff)` gain values into
`src/shims.cpp`'s `Config` defaults (replacing today's `kp = 0.0f`,
`ki = 6.0f`). Bake ticket 012's converged twist-hold value likewise, or
— if ticket 012 recommended the `travel_calib` fallback instead — add a
per-wheel `travel_calib` to `motion/motion_engine.h`'s `travelCalib_`
and to radio-robot-lib's `config/robots/tovez.json`
(`geometry.firmware_bake`), per `make_deploy.py`'s existing bake
convention. Cite the captures from tickets 011/012 that justify each
value — do not bake a number without a named artifact behind it.

Rebuild the consolidated firmware with these new defaults. Per
`git-commits.md`'s version-bump cadence, do NOT run `dotconfig version
bump` mid-sprint — that happens once at `close_sprint`.

## Acceptance Criteria

- [ ] `shims.cpp`'s gain defaults match ticket 011's converged values,
      with a comment citing the capture.
- [ ] Twist-hold default (or `travel_calib` bake, per ticket 012's
      recommendation) matches ticket 012's converged value, with a
      comment citing the capture.
- [ ] If `travel_calib` is baked, `radio-robot-lib/config/robots/
      tovez.json`'s `geometry.firmware_bake` is updated to match, and
      the citation names both files.
- [ ] Firmware rebuilds cleanly (plain build, no `DIFFDRIVE_FAULT_SPIN`)
      and passes `uv run pytest tests/host/`.
- [ ] No other robot's config (vevov, gopiv, etc.) is touched by this
      ticket.

## Testing

- **Existing tests to run**: full `tests/host/` suite (a default-value
  change can shift other tests' assumptions — run broadly, not
  scoped).
- **New tests to write**: a regression test pinning the new default
  gain values (so a future change can't silently drift them back),
  following whatever pattern `tests/host/test_config_descriptor_table.py`
  or similar already uses for baked defaults.
- **Verification command**: `uv run pytest tests/host/`
