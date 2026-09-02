---
id: '003'
title: Wire SET/GET exposure for the new and existing shaping knobs
status: done
use-cases:
- SUC-004
depends-on:
- '001'
github-issue: ''
issue: trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire SET/GET exposure for the new and existing shaping knobs

## Description

Five shaping knobs (`distTaper_`, `yawTaper_`, `distFloor_`,
`turnFloor_`, `rampMs_`) are reachable only from TypeScript today —
none is in `kFields[]` (`wire_adapter.cpp:103-144`) — so every profile
experiment currently costs a reflash. Ticket 001 adds four more
(`aAccelMmS2_`, `aDecelMmS2_`, `vMaxMmS_`, `brakeFrac_`) with the same
problem. Expose all nine as SET/GET wire fields at ordinals 19-27,
following the `pivot_overrun` precedent exactly (`git show b99294f
--name-only` for that ticket's own touch list) so a Tier-2 bench sweep
never costs a reflash.

Fix ordinal assignment (additive only, 0-18 untouched):

| Ordinal | `ConfigField` member | Wire name | Engine field |
|---|---|---|---|
| 19 | `Accel` | `accel` | `aAccelMmS2_` |
| 20 | `Decel` | `decel` | `aDecelMmS2_` |
| 21 | `VMax` | `v_max` | `vMaxMmS_` |
| 22 | `BrakeFrac` | `brake_frac` | `brakeFrac_` |
| 23 | `DistTaper` | `dist_taper` | `distTaper_` |
| 24 | `YawTaper` | `yaw_taper` | `yawTaper_` |
| 25 | `DistFloor` | `dist_floor` | `distFloor_` |
| 26 | `TurnFloor` | `turn_floor` | `turnFloor_` |
| 27 | `RampMs` | `ramp_ms` | `rampMs_` |

This is the full 8-file touch list from the issue — two drift tests
enforce every one of these files stays in sync, so skipping any file
below fails CI, not silently:

1. `src/blocks/motion.ts:16-55` — `ConfigField` enum member (ordinal
   source of truth), each with a `//% block="..."` label.
2. `src/comms/wire_adapter.cpp:103-143` — `kFields[]` row; the
   trailing `// ConfigField.Name` comment is load-bearing (a drift
   test parses it).
3. `src/shims.cpp:949-999` (`setKernelValue`) and `:1013-1047`
   (`getConfigValue`) — both switch statements need a case for every
   new ordinal; a drift test asserts every ordinal has both.
4. `src/motion/motion_engine.h:561-567` area — already has the field
   plus setter (ticket 001); confirm the getter (also ticket 001) is
   present for the read-back cases added here.
5. `tests/host/wire_motion_verb_shim.cpp:279-380` — the hand-mirrored
   test double; add the new ordinals here too.
6. `tests/host/motion_engine_shim.cpp:341-353` — add `meSetX()`/
   `meGetX()`-style exports for the four new engine fields (the five
   existing ones may already have exports; confirm and add any
   missing).
7. `tests/host/test_block_toolbox_order.py:134-143` — hardcoded enum
   baseline; extend through ordinal 27.
8. `docs/design/specification.md:207-228` — §4.8 table; this ticket
   may leave the prose/table update itself to ticket 005 (sequenced
   after this one) but must not leave the drift tests failing in the
   meantime — confirm which of the two drift tests
   (`test_wire_constants_drift.py`,
   `test_block_toolbox_order.py`) actually reads `specification.md`
   before deferring it.

Constraint: `//%` PXT shims are capped at 4 params (5 crashes PXT with
TS9200, `shims.cpp:1099-1110`). The generic `setKernelValue(field,
value)`/`getConfigValue(field)` shims already used for ordinals 0-18
are 2-param and unaffected by adding rows to their switch — no new
`//%` shim function is required for the generic path. Only pair new
setters (as `setTaperWindows` does) if this ticket also adds a
dedicated multi-argument convenience block for these fields; if the
generic `set config %field to %value` block is sufficient (as it is
for ordinals 0-18), no such convenience block is needed here and this
constraint does not bind.

## Acceptance Criteria

- [x] All nine ordinals (19-27, per the table above) added to every
      file in the 8-file touch list, in that ordinal order.
- [x] `SET <name> <value>` / `GET <name>` round-trips correctly for
      each of the nine (wire-adapter test double and the real compiled
      engine agree).
- [x] Ordinals 0-18 are byte-for-byte unchanged — no reordering, no
      renumbering.
- [x] `uv run pytest tests/host/test_block_toolbox_order.py
      tests/host/test_wire_constants_drift.py` passes.
- [x] A bare `GET` dump lists all 27 fields in `ConfigField`
      declaration order.
- [x] Each new engine-side setter keeps the same "invalid input
      silently keeps the prior value" validation style as
      `setPivotOverrunMm()`/`setRotationalSlip()` (ticket 001 already
      implements the validation; this ticket only wires the SET/GET
      dispatch to it).

## Implementation Plan

**Approach**: Work through the 8-file touch list in the order listed
above (enum first, since it is the ordinal source of truth per
`wire_adapter.cpp`'s own comment at line 95). Add one `kFields[]` row
and one pair of switch cases per ordinal, mirroring case 18
(`pivot_overrun`)'s shape exactly for each.

**Files to modify**: all eight listed above.

## Testing

- **Existing tests to run**: `tests/host/test_block_toolbox_order.py`,
  `tests/host/test_wire_constants_drift.py` (both drift tests, run
  BEFORE this ticket's changes too, to confirm the exact current
  failure mode/baseline these ordinals must satisfy).
- **New tests to write**: extend `wire_motion_verb_shim.cpp`'s test
  double with the nine new ordinals; extend
  `test_block_toolbox_order.py`'s baseline through ordinal 27.
- **Verification command**: `uv run pytest tests/host/test_block_toolbox_order.py tests/host/test_wire_constants_drift.py`
