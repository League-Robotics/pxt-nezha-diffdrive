---
status: pending
---

# Strip units from identifier names in src/comms/wifi_link.*

Priority: **Low** · Follow-up to `strip-units-from-identifier-names.md`
(sprint 029 ticket 005).

## Description

`src/comms/wifi_link.{h,cpp}` (the WiFi transport, merged to master
2026-09-03) landed after the code review's identifier inventory was
taken and was not in ticket 005's file list, so it still carries ~70
unit-suffixed identifiers (`kCommandTimeoutMs`, `nowMs_`, ...). The
source-pin test `tests/host/test_no_units_in_identifiers_source_pin.py`
excludes the two files with a documented reason.

Also left by ticket 005 as judgment calls, worth folding in here:
`yawRadPerS` in `shims.cpp:startMove()` (unit mid-name, not caught by
the end-anchored pattern) and the collision-avoidance spellings
`distanceF` (`shims.cpp:startMove()`) and `yaw` for a rotation in
`wire_adapter.cpp:onMoveX()` — pick names that say what the quantity
is (`requestedDistance`, `rotation`) rather than a type letter.

## Remedy

Rename per `.claude/rules/no-units-in-identifiers.md`, each with its
`// [unit]` trailing comment; remove the pin test's `wifi_link`
exclusion; scoped host tests green.
