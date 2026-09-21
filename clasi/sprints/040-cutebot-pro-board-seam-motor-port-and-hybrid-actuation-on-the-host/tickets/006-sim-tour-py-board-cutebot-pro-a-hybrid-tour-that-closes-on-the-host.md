---
id: '006'
title: 'sim_tour.py --board cutebot-pro: a hybrid tour that closes on the host'
status: open
use-cases: ["SUC-003", "SUC-005"]
depends-on: ["004", "005"]
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# sim_tour.py --board cutebot-pro: a hybrid tour that closes on the host

## Description

Depends on ticket 004 (the full hybrid stack — port, tap, policy, sim
onboard loop — must exist) and ticket 005 (the `--board` selection
needs to reach `sim_tour.py` the same way it reaches
`make_deploy.py`, and this ticket may reuse `_inject_board()`'s naming).
This is the sprint's headline proof point per its own Success Criteria:
a hybrid tour that closes on the host, before any board is touched.

Per `docs/design/cutebot-pro-support.md` §7 and §9:

- Extend `tests/host/sim_tour.py` with a `--board cutebot-pro` option
  (alongside its existing implicit Nezha default), composing the
  simulated `CutebotDevice`/`sim_cutebot_bus.h` in place of the
  existing simulated Nezha bus for the tour's `Rig`-equivalent
  construction.
- Run the existing tour shape (or the smallest existing named tour
  `sim_tour.py` already supports) at `onboard_pid` 0, 1, and 2 in turn,
  scored the same way the Nezha host tour already is (closure — the
  tour returns to its start pose within the existing pass bar).
- `onboard_pid 0` is the control case (pure PWM, proving ticket 002's
  work end-to-end through a real move sequence, not just unit tests);
  `onboard_pid` 1 and 2 are the hybrid cases this sprint exists to
  prove — the tour must close at all three, since a failure specific to
  1 or 2 would point at the policy or the sim onboard loop rather than
  the port.

## Acceptance Criteria

- [ ] `sim_tour.py --board cutebot-pro` runs to completion (no crash,
      no host-side exception) at `onboard_pid` 0, 1, and 2.
- [ ] The tour closes (returns to within the existing host-sim pass
      bar of its start pose) at all three `onboard_pid` values.
- [ ] `sim_tour.py`'s existing `--board`-less invocation (Nezha)
      remains unchanged in behavior and output.
- [ ] A CI-runnable form of this exists (a `test_*.py` wrapper calling
      `sim_tour.py`'s underlying function directly, not only a
      documented manual command) so `uv run pytest` covers it, per this
      sprint's "every acceptance criterion is host-verifiable" hard
      constraint.

## Testing

- **Existing tests to run**: full `uv run pytest`; the existing Nezha
  `sim_tour.py` invocation/test to confirm no shared-code regression.
- **New tests to write**: a pytest wrapper (e.g.
  `test_sim_tour_cutebot.py`) invoking `sim_tour.py --board
  cutebot-pro` at each `onboard_pid` value and asserting closure.
- **Verification command**: `uv run pytest tests/host/test_sim_tour_cutebot.py`,
  then full `uv run pytest`.
