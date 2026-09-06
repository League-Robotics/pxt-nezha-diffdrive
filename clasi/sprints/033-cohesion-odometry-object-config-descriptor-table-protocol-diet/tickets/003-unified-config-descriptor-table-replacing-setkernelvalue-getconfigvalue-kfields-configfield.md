---
id: '003'
title: Unified config descriptor table replacing setKernelValue/getConfigValue/kFields/ConfigField
status: in-progress
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

- [ ] Every wire config name (all ~34 total, the 10 shaping fields
      via `kLimitsFields` unchanged plus the ~24 this ticket covers)
      round-trips through SET/GET in a host test.
- [ ] `WireAdapter::kFields` and the TS `ConfigField` enum are the same
      length and agree name-for-name (drift test).
- [ ] `protocol.h:361`'s comment is corrected to name ordinal 28, not
      30.
- [ ] No ordinal has more than one definition across
      `setKernelValue`/`getConfigValue`/`kFields`/`ConfigField`.
- [ ] `diagValue()` is untouched by this ticket — confirmed by a diff
      review, not just by omission.
- [ ] `kLimitsFields` and `tests/host/test_config_descriptor_table.py`
      (sprint 029's shaping-field table) are untouched.

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
