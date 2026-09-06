---
id: '015'
title: Bake final kernel gains and per-wheel calibration as firmware defaults; rebuild
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '011'
- '012'
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

- [ ] ~~`shims.cpp`'s gain defaults match ticket 011's converged
      values, with a comment citing the capture.~~ **N/A, scope
      narrowed at dispatch**: ticket 011 closed WITHOUT converging (no
      candidate held either bar; best was kp=0.10/ki=0/kaff=0 at peak
      220 vs a 210 bar and rise 652 vs a 600 bar). There is no
      converged value to bake. `cfg.kp = 0.0f` / `cfg.ki = 6.0f` are
      left untouched, per explicit team-lead instruction at this
      ticket's dispatch.
- [x] Twist-hold default matches the converged value, with a comment
      citing the capture. `cfg.twistHoldGain` raised 2.0 -> 4.0 in
      `src/shims.cpp` (Config defaults, in the `ensure()` seed), citing
      `captures/session-b-20260905/` (g3-cruise100/,
      g3-cruise100-x12/, twist-4-x12/, twist-6/) — MEASURED tovez
      2026-09-05, firmware 1.20260904.5: gain 2 (old default) mean
      |dheading| 2.88 deg/18 legs, gain 4 = 2.10 deg/12 legs (the best
      of the three on the largest sample), gain 6 = 1.67 deg but only
      6 legs (not comparable, needs a 12-leg rerun). The comment also
      records that a 6-leg run at gain 4 gave 0.98 deg and did NOT
      replicate at 12 legs.
- [ ] ~~If `travel_calib` is baked, ...~~ **N/A, out of scope at
      dispatch**: per-wheel `travel_calib` was explicitly excluded —
      its sign is unresolved (straight-leg decomposition implies left
      +0.78% long; a direct per-wheel camera measurement, n=6/wheel,
      implies the RIGHT wheel +1.07% long instead, and the two means
      are within noise of each other, t~1.3). Baking the wrong sign
      would double the error; no robot config (tovez or otherwise) was
      touched for this.
- [x] Firmware rebuilds cleanly (plain build, no `DIFFDRIVE_FAULT_SPIN`)
      and passes `uv run pytest tests/host/`. Rebuilt via
      `uv run python tools/make_deploy.py --robot tovez` (after
      clearing a stale `.tmp/deploy-head` scratch cache per
      make_deploy's own triage message); log confirms
      `WiFi link ENABLED, ssid='Busboom Mesh'` (config/wifi_secrets.json
      present) and every nezha-diffdrive translation unit compiled.
      Hex copied to
      `captures/session-b-20260905/tovez-1.20260904.5-twist4-bake.hex`
      (1,722,851 bytes; sha256
      339dd60b91ed459f2efba6e039506057e8933dbd52e1b6d95abbd689df8e81ed).
      `uv run pytest tests/host/ tests/tools/` — 1272 passed.
- [x] No other robot's config (vevov, gopiv, etc.) is touched by this
      ticket. Only `src/shims.cpp` and
      `tests/host/test_wire_constants_drift.py` were changed.

## Testing

- **Existing tests to run**: full `tests/host/` suite (a default-value
  change can shift other tests' assumptions — run broadly, not
  scoped). Also ran `tests/tools/` per dispatch instruction. Result:
  1272 passed, 0 failed.
- **New tests to write**: a regression test pinning the new default
  gain values (so a future change can't silently drift them back),
  following whatever pattern `tests/host/test_config_descriptor_table.py`
  or similar already uses for baked defaults. Added
  `test_twist_hold_gain_default_is_pinned_at_4` and
  `test_twist_hold_gain_default_comment_cites_the_measurement` to
  `tests/host/test_wire_constants_drift.py` (a single-file regression
  pin, same text-based-read shape as that file's other
  `cfg.<field> = <value>` pins, e.g. `cfg.cyclePeriod`).
- **Verification command**: `uv run pytest tests/host/`

## Completion Notes (ticket 015)

Hardware was not available this session (on-robot Pi off the
network), so this ticket was scoped at dispatch to bake exactly ONE
measured constant — `twist_hold_gain` 2.0 -> 4.0 — and explicitly NOT
the kernel PID gains (011 unconverged) or a per-wheel `travel_calib`
(012's sign unresolved). See the annotated acceptance criteria above
for the full rationale on each excluded item. Ticket 012 itself
remains `open` (its own hardware session is not this ticket's scope);
this ticket only consumes the twist-hold sweep data already captured
under `captures/session-b-20260905/`.
