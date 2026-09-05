---
id: '006'
title: 'Kernel FF/I gain retune: candidate values from the host lagged-rig model'
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Kernel FF/I gain retune: candidate values from the host lagged-rig model

**Type: (b) desk work — programmer, using the host simulation harness.
No hardware.**

## Description

tovez's kernel runs `kp = 0`, `ki = 6` (`src/shims.cpp` defaults) and
overshoots a 200 mm/s step to 226-256 mm/s, with measured acceleration
up to 993 mm/s² on a 400-limited command
(`tovez-drivetrain-tuning-and-restated-acceptance-bars.md`). Before
touching hardware, use `tests/host/test_profile_probe.py`'s `LaggedRig`
(or equivalent lagged host model) to search candidate `kp`/`ki`/`kaff`
values that keep a simulated 200 mm/s step's peak ≤ 210 mm/s and
acceleration ≤ 1.5×`accel` under the same lag (`lag_s 0.13`, baked
radio-robot-lib eafccd2) tovez already runs.

Produce a short, ranked list of candidate gain sets with their
predicted peak/accel from the model — this ticket does NOT bake
anything into `shims.cpp`; ticket 011 tries the top candidates live on
hardware via `SET`, and ticket 015 bakes whichever one converges.

## Acceptance Criteria

- [x] At least 2-3 candidate `(kp, ki, kaff)` sets identified via the
      host lagged-rig model, each with predicted peak speed and
      acceleration for a 200 mm/s step at `lag_s 0.13`.
- [x] The model's prediction methodology (harness file, invocation) is
      documented so ticket 011 can reproduce it, or extend it if the
      first candidates don't hold up on hardware.
- [x] No firmware default is changed by this ticket.

## Testing

- **Existing tests to run**: `tests/host/test_profile_probe.py`.
- **New tests to write**: a parametrized sweep (or a short script built
  on the same harness) that reports peak/accel per candidate gain set;
  commit it if it's reusable for a future robot's tuning, not just a
  throwaway.
- **Verification command**: `uv run pytest tests/host/test_profile_probe.py`
