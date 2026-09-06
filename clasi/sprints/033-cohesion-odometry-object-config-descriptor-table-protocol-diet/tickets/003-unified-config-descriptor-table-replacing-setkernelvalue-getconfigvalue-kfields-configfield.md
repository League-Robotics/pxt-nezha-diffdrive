---
id: '003'
title: Unified config descriptor table replacing setKernelValue/getConfigValue/kFields/ConfigField
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: config-descriptor-table-softstop-goto-deadline.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Unified config descriptor table replacing setKernelValue/getConfigValue/kFields/ConfigField

## Description

**Re-anchor scope against what sprint 029 already shipped (verified
2026-09-05) — do not redo it.** Sprint 029 ticket 004 already built
`kLimitsFields` (`shims.cpp` ~1097), a `{ordinal, setter, field}` table
over `MotionLimits` covering exactly the 10 shaping fields (`v_floor`,
`stop_distance`, `accel`, `decel`, `v_max`, `jerk`, `omega_max`,
`omega_floor`, `arrive_dist`, `arrive_yaw`), with its own host test,
`tests/host/test_config_descriptor_table.py`. **Leave `kLimitsFields`
and that test alone.** This ticket's scope is the *other* ~24 config
ordinals: `setKernelValue()`/`getConfigValue()` still switch on them
individually (92 `case` labels total in `shims.cpp` as of this
reading); `WireAdapter::kFields` (`wire_adapter.cpp:125`) and the TS
`ConfigField` enum (`blocks/motion.ts:16`) are separately hand-kept —
and are not even the same length as each other today, direct
present-tense evidence of the drift this ticket fixes.

Build one descriptor table `{name, ordinal, get, set, unit}` in
`shims.cpp` covering those ~24 ordinals (kernel PID/stall/lambda
fields, `default_cruise`, `rotational_slip`, `stall_clear`, `rebase`,
`estop_clear`). `setKernelValue()`/`getConfigValue()` consult it before
falling through to any remaining per-field logic that doesn't fit the
table shape (e.g. `stall_clear`/`rebase`/`estop_clear`'s
write-triggered-action semantics — keep those as documented special
cases within the table's `set` slot, not exceptions requiring a
separate switch). `WireAdapter::kFields` reads names/ordinals from the
same table. Generate the TS `ConfigField` enum from it via a script
(PXT cannot import the C++ table directly), with a drift test asserting
the checked-in enum matches a fresh generation run — document how and
when to re-run the generator.

**Fix the `protocol.h:281` defect precisely.** `protocol.h:361`'s
comment claims the RUN-queue overflow counter is "readable (diagValue
ordinal 30)" — the actual reader is `case 28: return
protocolRunDropCount();` (`shims.cpp:1153`). Ordinal 30 does not exist
in `diagValue()`'s switch (falls to `default: return 0`); in the
*separate* config-ordinal namespace, 30 is `omega_max`. Correct the
comment to name ordinal 28. **Do not fold `diagValue()` into this
table** — see sprint.md's Design Rationale for why (diag ordinals are
read-only with no natural `set`/`unit`, and the issue's own Remedy
doesn't ask for that merge).

**Sprint 031 coordination**: `WireAdapter::kFields` lives in the same
file (`wire_adapter.cpp`) as sprint 031's unmerged
`resolvePendingReason()` changes — different functions, low-medium
collision risk, but read 031's actual diff before editing this file if
it is still unmerged when this ticket runs.

## Acceptance Criteria

- [x] Every wire config name (all 31 total, the 11 shaping ordinals
      via `kLimitsFields` unchanged plus the 20 this ticket covers)
      round-trips through SET/GET in a host test
      (`tests/host/test_config_surface_single_source.py`:
      `test_every_table_name_is_reachable_over_the_wire` covers all 31
      names including the write-only `rebase`;
      `test_every_stored_field_round_trips_its_value` proves the stored
      ones give back what was written).
- [x] `WireAdapter::kFields` and the TS `ConfigField` enum are the same
      length and agree name-for-name (drift test). `kFields` is DELETED:
      `wire_adapter.cpp` now includes `comms/config_fields.h`, the one
      table, and `ConfigField` is generated from it. Length + name
      agreement is asserted by
      `test_wire_constants_drift.py::test_config_field_table_ordinals_match_config_field_enum`;
      the stronger byte-for-byte property is
      `tests/tools/test_gen_config_field_enum.py`. `rebase` (32) and
      `estop_clear` (33) become enum members -- they were the two
      wire-only names that made the lists different lengths.
- [x] `protocol.h:361`'s comment is corrected to name ordinal 28, not
      30 (and the same error in `src/DESIGN.md`'s RUN-bridge paragraph
      and component diagram).
- [x] No ordinal has more than one definition across
      `setKernelValue`/`getConfigValue`/`kFields`/`ConfigField`.
      `setKernelValue()`/`getConfigValue()` have no switch left; both
      read `kLimitsFields` then `kConfigAccessors`, and
      `test_config_surface_single_source.py::test_shims_cpp_implements_exactly_the_ordinals_the_table_names`
      rejects an ordinal in both tables, an ordinal named with no
      behaviour, and behaviour with no name.
- [x] `diagValue()` is untouched by this ticket -- confirmed by
      `git diff src/shims.cpp | grep diagValue` returning nothing.
- [x] `kLimitsFields` and `tests/host/test_config_descriptor_table.py`
      (sprint 029's shaping-field table) are untouched. The table's
      rows, its `LimitsFieldEntry` struct and `findLimitsField()` are
      byte-identical; three COMMENT lines around it were corrected
      (its header comment promised "a later ticket extends this same
      table", which is not what this ticket did, and two row comments
      pointed at the now-deleted `kFields`). The test file is not
      modified at all.

## Testing

- **Existing tests to run**:
  `tests/host/test_config_descriptor_table.py` (must stay green,
  unmodified in intent — it covers the OTHER 10 fields);
  `test_wire_motion_verbs.py`'s
  `test_get_set_sweeps_every_kfields_entry_without_overflow` (extend
  to cover the full, now-unified `kFields`).
- **New tests to write**: a full-surface SET/GET round-trip test over
  every non-shaping config name; a `ConfigField`-vs-table drift test
  (generator output compared against the checked-in TS enum).
- **Verification command**: `uv run pytest tests/host/`

## Implementation Notes

**The split, and why.** The surface is one list plus one behaviour
table, not one table, and the seam is portability rather than taste:

- `src/comms/config_fields.h` -- `kConfigFields[]`, `{name, ordinal,
  unit}`, 31 rows in bare-`GET`-dump order, plus `findConfigField()`.
  Host-portable (no `pxt.h`), so it compiles into every host wire test
  and is syntax-checked at the target's C++11 by
  `tests/host/config_fields_syntax_check.cpp`. `wire_adapter.cpp`
  includes it and keeps no copy.
- `src/shims.cpp` -- `kConfigAccessors[]`, `{ordinal, get, set}` over
  the 20 non-shaping ordinals, alongside the untouched `kLimitsFields`
  for the other 11. This half cannot move to the header: every accessor
  reaches into `Rig`/the kernel/the motion engine and therefore needs
  `pxt.h`.

The accessors are named `cfgGetX`/`cfgSetX` functions rather than
lambdas written inline in the table, because a non-capturing lambda's
conversion to a function pointer is not a constant expression until
C++17 and both embedded targets compile at C++11 -- an inline-lambda
table would be `const` rather than `constexpr`, i.e. built by a startup
constructor into RAM instead of sitting in flash.

Keeping the names host-portable while the behaviour stays behind
`pxt.h` is what let this land without touching
`test_config_descriptor_table.py`'s `_SHIM_SOURCES` (a new `.cpp` would
have forced an edit there, and that file is off-limits by AC).

**`diagValue()` stays separate**, per sprint.md's Design Rationale:
read-only ordinals with no `SET` and no natural unit. The
`protocol.h`/`DESIGN.md` "ordinal 30" defect was cross-table confusion,
fixed by precision, not by merging the two namespaces.

**Generator**: `uv run python tools/gen_config_field_enum.py` (add
`--check` for a no-write drift report). Re-run whenever a row in the
header is added, renamed, renumbered or removed, and commit both files.
Each row carries a `// ConfigField.<Name>: "<label>"` annotation; a row
without one stops the generator rather than being skipped.

**The test double moved too.** `tests/host/wire_motion_verb_shim.cpp`
now mirrors production's shape (`kWaConfigAccessors`), not just its
math, and `test_config_surface_single_source.py` fails if the double
and production cover different ordinals -- every compiled SET/GET test
in `tests/host/` runs against that double.

**Nothing here is measured on hardware**; no firmware was built or
flashed for this ticket. All verification is host-side.
