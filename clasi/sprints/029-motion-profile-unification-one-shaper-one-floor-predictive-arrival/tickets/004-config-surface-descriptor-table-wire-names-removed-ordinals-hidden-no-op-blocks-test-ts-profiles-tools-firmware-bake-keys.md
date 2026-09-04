---
id: '004'
title: 'Config surface: descriptor table, wire names, removed ordinals, hidden no-op
  blocks, test.ts profiles, tools/firmware_bake keys'
status: open
use-cases: [SUC-003, SUC-004]
depends-on: ['003']
github-issue: ''
issue: code-review/one-velocity-shaper-profile-object-out-of-servicemove.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Config surface: descriptor table, wire names, removed ordinals, hidden no-op blocks, test.ts profiles, tools/firmware_bake keys

## Description

Design §4.7's one descriptor table, replacing the three parallel
switches (kernel `ConfigField` ordinals, engine setters, block-level
shims). Needs ticket 003 (`MotionLimits`/`limits()` must exist and be
wired in first).

**Wire names** (`comms/wire_adapter.cpp`'s `kFields` table): `accel`
(19), `decel` (20), `jerk` (28), `v_max` (21), `omega_max` (30),
`v_floor` (8, ordinal unchanged, now writes `limits` not the kernel),
`omega_floor` (34, new), `stop_distance` (18, replaces `pivot_overrun`),
`arrive_dist` (35, new), `arrive_yaw` (36, new). Ordinals 22-27, 29, 31
(`brake_frac`, `dist_taper`, `yaw_taper`, `dist_floor`, `turn_floor`,
`ramp_ms`, `plateau_min_s`, `profile_exit`) are **removed** and answer
`err 1` on both GET and SET for one release (design §4.7) — a stale
bench script fails loudly instead of silently setting nothing.

**Blocks** (`blocks/motion.ts`): `setTaperWindows`/`setTaperFloors`/
`setRampMs` become hidden no-op shims for one release (saved MakeCode
projects still compile); `ConfigField`'s TS enum gains the new names
and drops the removed ones. Default to hidden no-op unless the
stakeholder has by now answered design §12's open question 3 (may be
removed outright).

**`test.ts` profiles** (`test/test.ts`): `openLoopProfile()`/
`closedLoopProfile()` each become one `setLimits({accel, decel, vMax,
omegaMax})` call (design §4.7's exact literals) — floors and
`stopDistance` stay per-robot, from the deploy bake, never from a
profile.

**`tools/` and `firmware_bake`**: grep `tools/` for the removed field
names (`tools/field_dance.py` and any `SET` call site) and update to
the new names; `radio-robot-lib/config/robots/*.json`'s
`pivot_overrun_mm` key becomes `stop_distance_mm` — this is a
cross-repo change (design §12 open question 2) — update this repo's
`make_deploy.py` bake-key handling and **flag** (do not silently
assume complete) the `radio-robot-lib` config-file side if it is out of
this repo's reach to edit directly.

## Acceptance Criteria

- [ ] `tests/host/test_config_descriptor_table.py` (design §9.5): every
      wire name in the table round-trips through SET/GET; the removed
      names answer `err 1` on both GET and SET.
- [ ] `test.ts`'s two profile functions each reduce to a single
      `setLimits()` call (design §4.7's exact literals).
- [ ] `tools/field_dance.py` and every other `tools/` SET call site use
      the new field names; a grep for the nine removed names returns
      nothing under `tools/`.
- [ ] `make_deploy.py`'s bake-key handling uses `stop_distance_mm`
      (retains a documented fallback/migration note if
      `radio-robot-lib`'s own config files haven't yet been updated
      cross-repo).
- [ ] Blocks: `setTaperWindows`/`setTaperFloors`/`setRampMs` compile as
      hidden no-ops; a MakeCode project using them still builds.
- [ ] `pivot_overrun` no longer appears in `kFields` or any `blocks/`
      surface (the fleet-config side is ticket 007's/cross-repo
      responsibility to complete, per sprint.md's Success Criteria).

## Implementation Plan

**Approach**: One descriptor table (name, ordinal, field pointer/setter,
removed-marker) that `GET`/`SET` both consult, replacing the three
independently-maintained mappings. Removed ordinals get an explicit
sentinel entry that both verbs check first and reply `err 1`.

**Files to create/modify**:
- `src/comms/wire_adapter.cpp` (`kFields` table)
- `src/shims.cpp` (`ConfigField` enum / `getConfigValue`/
  `setKernelValue` plumbing, if the descriptor lives partly here)
- `src/blocks/motion.ts` (hidden no-op shims, enum updates)
- `test/test.ts` (two profile functions)
- `tools/field_dance.py` and any other `tools/*.py` with a `SET
  dist_floor`/`turn_floor`/etc. call site
- `tools/make_deploy.py` (bake-key handling)
- `tests/host/test_config_descriptor_table.py` (new)

**Testing plan**: `tests/host/test_config_descriptor_table.py`, scoped
run. Manual/bench confirmation that `err 1` actually reaches a real
wire client is folded into ticket 007's bench acceptance run rather
than duplicated here.

**Documentation updates**: `src/DESIGN.md` §5 (Wire adapter — real-file
edit, same rationale as tickets 001/003: the overlay collision means
`src/DESIGN.md` updates land directly on the real file this sprint) —
update the `kFields`/ordinal description to reflect the new descriptor
table and the removed ordinals' `err 1` behavior, replacing the
per-ordinal narrative currently there (e.g. the `pivot_overrun`
ordinal-18 paragraph).
