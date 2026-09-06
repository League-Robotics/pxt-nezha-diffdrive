---
id: '020'
title: Make accel a per-robot firmware_bake key and bake 800 for tovez
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Make accel a per-robot firmware_bake key and bake 800 for tovez

Type (b): programmer-implementable, no hardware.

## Description

`tools/make_deploy.py`'s `_GEOMETRY_BAKE_RES` / `_GEOMETRY_BAKE_FILES` /
`_inject_geometry()` (around lines 1023-1189) bake per-robot constants
from `radio-robot-lib/config/robots/<robot>.json`'s
`geometry.firmware_bake` block into the scratch copy of `src/motion/
*.h` used for a robot's build. Today's keys are `travel_calib`,
`trackwidth`, `rotational_slip` (all three target
`motion_engine.h`), and `lag_s` / `stop_distance_mm` (both target
`motion_limits.h`, following ticket 018/sprint 029 ticket 009's
pattern — see `_GEOMETRY_BAKE_FILES`'s own comment for why the bake
spans two files). Add `accel` as a sixth key, in exactly this pattern:

- `_GEOMETRY_BAKE_RES['accel']` — a regex targeting
  `MotionLimits::accel` in `src/motion/motion_limits.h` (line 48:
  `float accel = 400.0f;      // [mm/s^2] dominant-wheel accel
  ceiling`), same shape as the existing `lag`/`stopDistance` regexes
  immediately above it in the dict.
- `_GEOMETRY_BAKE_FILES['accel'] = 'motion_limits.h'`.
- No fleet-wide default changes — `accel` stays 400.0f for every robot
  without an explicit `firmware_bake.accel`, exactly like every other
  key in this table (opt-in only; see the file's own block comment
  above `_GEOMETRY_BAKE_RES` starting "So a constant is injected ONLY
  when...").

Then set `radio-robot-lib/config/robots/tovez.json`'s
`geometry.firmware_bake.accel` to `800`, with an `_accel_provenance`
string in the same style as the file's existing
`_rotational_slip_provenance` / `_lag_provenance` / `_stop_distance_
provenance` entries. It must cite:

- The two accel-800 runs: `captures/session-b-20260905/gain-sweep-
  20260905/accel800/` and `.../accel800b/` (4 alternating +-600 mm
  legs each, n=8 combined), and the accel-300 baseline:
  `captures/session-b-20260905/discriminator-20260905/` and
  `.../discriminator-20260905-v2/` (8 legs), all at cruise 100 with
  `rotational_slip` 0.962, camera heading change per leg at rest.
- The numbers: baseline mean|dh| 3.62 deg / max 7.61; accel 800
  mean|dh| 1.35 deg / max 3.45; the forward-after-reverse leg (leg 2,
  the worst case — a breakaway yaw on direction reversal, per
  `docs/sprint-031-postmortem.md` §3a) improved from +4.59/+7.61 deg
  across baseline runs to +1.39/-0.72 deg across accel-800 runs;
  `i2cf` per leg fell from 12-43 to 2-5.
- **The mechanism must be recorded as UNVERIFIED, verbatim in spirit**:
  the postmortem's own ramp-check table (§3a) shows the physical wheel
  ramp did NOT change between accel 300 and accel 800 (759-955 mm/s^2
  at 300 vs 873-894 mm/s^2 at 800 — the drivetrain already ramps
  faster than either commanded ceiling, so neither value is what
  governs the physical ramp). This is not "a faster ramp." The leading
  hypothesis, untested, is that a commanded ramp far below what the
  wheels do anyway saturates the PID early and winds up the twist
  hold. This is a replicated empirical result (two independent n=4
  runs agreeing, n=8 total) with no accepted mechanism — write it that
  way, not as an explained fix.

### Where the running accel=300 actually comes from (read before assuming a boot override)

Grepped `test/test.ts`, `src/shims.cpp`, and `tools/make_deploy.py`:
none of them seed or default `accel` to 300 anywhere — the compiled
fleet default is 400.0f (`motion_limits.h` line 48), and
`radio-robot-lib/config/robots/tovez.json` today has no
`firmware_bake.accel` key at all (confirmed by reading the file's
`geometry.firmware_bake` block directly — no `accel` present). The
postmortem's own section title, "Live-`SET` sweep against the
breakaway yaw," is consistent with 300 having been a transient
`SET accel 300` issued for that test session, the same way
`rotational_slip`/`lag_s` were live-`SET` before ticket 018 baked them
— it does not persist and dies at the next power cycle. This is a
source-reading conclusion, not a measured one; there is no capture
proving what set the running value to 300, and none is needed to
proceed with the bake.

**There IS a real, verifiable mechanism that WOULD silently override a
baked `accel: 800` at the point tovez is most reliably driven, and it
must be fixed or explicitly documented:** `tools/field_dance.py`
(lines 189-190), which `.claude/rules/field-dance-first.md` requires
be run before ANY commanded motion on the playfield, hardcodes:

```python
for f, v in (('accel', 400), ('decel', 400)):
    L.seqd(f'SET {f} {v}')
```

This live-SETs `accel` to the fleet default 400 on every dance run,
regardless of what the connected robot's firmware was built with. Once
`accel: 800` is baked for tovez, every mandatory pre-flight dance would
silently reset it back to 400 for the rest of that session (a live
`SET` persists until power-cycle, same as `rotational_slip`) — defeating
the bake this ticket adds, on the one robot it targets, at exactly the
moment the project's own safety rule requires the script to run.

Fix this: change `field_dance.py`'s accel/decel pre-flight to read the
dance's target robot's (`ROBOT`, already resolved at module scope from
`field_calibration.json`'s `default_robot`) own baked `accel`/`decel`
via `make_deploy._read_robot_firmware_bake(ROBOT)` — already an
importable function, and `field_dance.py` already imports a sibling
helper from the same module (`from make_deploy import
derive_radio_from_name`, near the top of the file) — falling back to
400 only when the robot's `firmware_bake` has no `accel`/`decel` key.
Factor the two-line lookup into a small, separately testable helper
(e.g. `_dance_accel_decel(robot) -> (accel, decel)`) so it can be unit
tested without a live robot connection.

If, after investigating, fixing `field_dance.py` this way turns out to
be wrong or infeasible for a reason not visible from this ticket (e.g.
the dance's own "must not retune the robot" comment at that call site
turns out to mean something stronger than described here), do not
silently skip this — update that comment block to say precisely why a
per-robot baked `accel` is intentionally overridden by the dance, and
record that as the resolution instead. Either way, acceptance criterion
2 below must be satisfied by one of the two outcomes, not left open.

## Acceptance Criteria

- [x] `accel` is added to `_GEOMETRY_BAKE_RES` and `_GEOMETRY_BAKE_FILES`
      (targeting `motion_limits.h`), following the exact pattern of
      `lag_s`/`stop_distance_mm`. A tovez deploy scratch copy of
      `motion_limits.h` has `float accel = 800.0f;` after
      `_inject_geometry()` runs; a robot with no `firmware_bake.accel`
      key produces a byte-identical `motion_limits.h` (keeps the
      compiled 400.0f default). Extend
      `tests/tools/test_make_deploy_geometry.py` in its existing style
      (see its `_LIMITS_HEADER` fixture and the `lag_s`/
      `stop_distance_mm` test cases as the template) to pin both
      behaviors, plus a test that a second robot's config
      (e.g. tigez or vevov) is unaffected by tovez's `accel` bake.
- [x] The source of the running accel=300 is investigated (see above)
      and documented in the ticket's implementation notes / commit, and
      `tools/field_dance.py`'s hardcoded `SET accel 400` / `SET decel
      400` pre-flight (lines ~189-190) is changed to defer to the
      dance's target robot's own baked `accel`/`decel` (via
      `make_deploy._read_robot_firmware_bake`), falling back to 400
      only when unbaked — so the mandatory pre-flight dance does not
      silently defeat this ticket's bake. If that fix is determined to
      be wrong, the alternative is an explicit code comment at that
      call site stating precisely why the dance intentionally
      overrides a per-robot baked `accel`, in place of the fix.
- [x] `radio-robot-lib/config/robots/tovez.json`'s
      `geometry.firmware_bake.accel` is `800`, with an
      `_accel_provenance` note (matching the file's existing provenance
      entries' style) that cites both accel-800 capture directories and
      both baseline capture directories, states the n=8 mean/max
      numbers above, and states in its own words that the mechanism is
      UNVERIFIED (ramp unchanged; leading hypothesis is early PID
      saturation / twist-hold windup; not explained).
- [x] Scoped tests pass: `uv run pytest tests/tools/ -k make_deploy`,
      plus whatever new test module covers the `field_dance.py` change
      (the full suite runs once at `close_sprint`, not per ticket).

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_make_deploy_geometry.py`
  and `tests/tools/test_make_deploy_profile.py` (same monkeypatched
  `RADIO_ROBOT_LIB` convention) to confirm the existing bake keys are
  unaffected.
- **New tests to write**:
  - In `tests/tools/test_make_deploy_geometry.py`: an `accel`-bake test
    (tovez-shaped config with `firmware_bake.accel: 800` → injected
    `motion_limits.h` has `accel = 800.0f`) and a no-bake test (a robot
    config with no `accel` key → `motion_limits.h` byte-identical to
    input) and a cross-robot isolation test (baking `accel` for one
    robot's config leaves a second robot's config/output untouched).
  - A new small test module (e.g.
    `tests/tools/test_field_dance_accel_bake.py`) exercising the
    extracted `_dance_accel_decel(robot)`-style helper against a
    monkeypatched `RADIO_ROBOT_LIB`: asserts it returns `(800, 400)`
    (or whatever `decel` ends up being) for a tovez-shaped config with
    `firmware_bake.accel: 800` and no `decel` key, and `(400, 400)` for
    a robot with no `firmware_bake` block at all. No live robot
    connection required — this must be host-testable, matching every
    other test in this ticket.
- **Verification command**: `uv run pytest tests/tools/ -k "make_deploy or field_dance"`

## Implementation Notes

- **`openLoopProfile()`'s running accel=300, resolved**: grepped
  `test/test.ts` for `openLoopProfile` — it is called only from
  `tourRobot()`, `tourWheels()`, `tourWorld()`, `straightRun()`, and the
  `RUN:face`/`RUN:pivot`/`RUN:arc` handlers, i.e. exclusively via
  `diffDrive.onRun(...)` verb dispatch (`RUN:tour:*`, `RUN:straight`,
  `RUN:face`, `RUN:pivot`, `RUN:arc`). Nothing calls it at boot — the
  file's own boot tail is just `basic.showIcon`/`basic.showString`. But
  these RUN verbs are exactly what students' blocks and every gate
  script (`tests/system/`, `turn_calibration.py`) drive through, so per
  the ticket's own instruction this counts as "a path students/gates
  hit": `openLoopProfile()`'s `setLimits(300, 300, 200, 90)` was changed
  to `setLimits(800, 300, 200, 90)` (accel only; decel/vMax/omegaMax
  unchanged) so the firmware literal agrees with the
  `geometry.firmware_bake.accel: 800` bake below, with a comment citing
  the same two capture directories and the postmortem §3a ramp-check
  caveat.
- **`tools/field_dance.py`'s hardcoded `SET accel 400`/`SET decel 400`,
  confirmed**: read `main()` directly (lines ~189-190 at ticket-open
  time) — `for f, v in (('accel', 400), ('decel', 400)): L.seqd(f'SET
  {f} {v}')`, immediately under a comment stating "the dance is a
  CONVENTION check, so it must not retune the robot." That comment was
  already being violated: a hardcoded 400 live-`SET`s every dance run
  regardless of what the connected robot's firmware bakes. Fixed per
  the ticket's proposed approach: extracted
  `_dance_accel_decel(robot)`, which reads `robot`'s own
  `geometry.firmware_bake` via `make_deploy._read_robot_firmware_bake()`
  (imported alongside the existing `derive_radio_from_name` sibling
  import) and falls back to 400 for either key when unbaked;
  `main()` now calls `accel, decel = _dance_accel_decel(ROBOT)` before
  the `SET` loop. Host-tested with no live robot connection in
  `tests/tools/test_field_dance_accel_bake.py`.
- `radio-robot-lib/config/robots/tovez.json`'s `geometry.firmware_bake`
  now carries `"accel": 800` plus an `_accel_provenance` note citing
  `captures/session-b-20260905/gain-sweep-20260905/accel800{,b}/` (n=8)
  against the `discriminator-20260905{,-v2}/` baseline (n=8), the
  mean/max numbers from the ticket description, and states the
  mechanism is UNVERIFIED per `docs/sprint-031-postmortem.md` §3a
  (physical ramp unchanged 300→800; leading hypothesis is early PID
  saturation / twist-hold windup during the breakaway window, not a
  faster ramp). Committed separately in the `radio-robot-lib` repo
  (commit only, not pushed).
- `src/DESIGN.md`'s `straight_trim` paragraph (ticket 019) had its
  "magnitude is not a physical constant ... sizes from a warm run"
  sentence replaced per team-lead direction, to reflect postmortem
  §2.2a's correction: tovez's leg yaw is a variable, sign-inconsistent
  breakaway on direction reversal, not a constant curvature, so
  tovez's `straight_trim` stays 0 and is not to be sized from a warm
  run.
