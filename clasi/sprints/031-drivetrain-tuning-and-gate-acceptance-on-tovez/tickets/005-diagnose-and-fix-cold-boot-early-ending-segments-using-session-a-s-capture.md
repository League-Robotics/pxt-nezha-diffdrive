---
id: '005'
title: Diagnose and fix cold-boot early-ending segments using Session A's capture
status: open
use-cases: [SUC-003]
depends-on: ['001']
github-issue: ''
issue: segment-moves-end-early-just-after-boot.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Diagnose and fix cold-boot early-ending segments using Session A's capture

**Type: (b) desk code change — programmer. Depends on ticket 001's
hardware capture.**

## Description

Using ticket 001's 8 Hz STATUS captures from three cold boots,
determine the cause of each early-ending segment:

- The two pivot/wrong-way cases (`MotionEngine::wrongWayCount()` read 2
  before a clean run) are already explained: `Segment::wrongWay()`'s
  margin (25% of the yaw target) is crossed by the wheels' start-up
  skew on the very first moves after boot. Fix: evaluate `wrongWay()`
  only after the dominant axis has progressed a minimum distance, so a
  brief start-up skew can't trip it before real motion begins.
- The two straight-line stops (`yawTarget == 0`, no wrong-way path) are
  UNEXPLAINED as of this sprint's planning. Ticket 001's fresh 8 Hz
  captures must show whether it's the stall latch (`updateLatch`,
  500 ms window, firing on a slow first spin-up) or a refused
  `kernel_.drive()`. Only implement the fix that the capture actually
  points to — do not guess ahead of the data.
- If it IS the stall latch: gate the stall detector on the shaper
  having commanded above the floor for longer than the measured lag
  (`lag_s`), so a slow-starting first move can't look like a stall.

Both fixes are host-testable with a lagged, skewed wheel model (the
`LaggedRig`-style harness in `tests/host/test_profile_probe.py`).

## Acceptance Criteria

- [ ] Ticket 001's capture is cited by path for each of the four
      original early-end cases, with the determined cause stated per
      case (wrong-way margin vs. stall latch vs. refused `drive()`).
- [ ] The wrong-way margin's cold-boot false-positive is fixed
      (minimum-progress gate) with a host test reproducing the pre-fix
      false trip and confirming the fix.
- [ ] Whichever mechanism the capture points to for the straight-line
      stops is fixed, with a host test using a lagged, skewed wheel
      model reproducing the pre-fix early end.
- [ ] No regression to legitimate wrong-way/stall detection on a
      genuinely stuck or reversed robot — existing host tests for those
      paths still pass.

## Testing

- **Existing tests to run**: `tests/host/` motion-engine and
  diffdrive-kernel suites (wrong-way, stall-latch coverage).
- **New tests to write**: lagged/skewed-wheel-model regression tests
  for both the wrong-way false-positive and whichever straight-line
  mechanism the capture confirms.
- **Verification command**: `uv run pytest tests/host/`
