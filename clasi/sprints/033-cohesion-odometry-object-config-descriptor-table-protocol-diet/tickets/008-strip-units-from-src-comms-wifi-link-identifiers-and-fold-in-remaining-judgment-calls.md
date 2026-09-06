---
id: 008
title: Strip units from src/comms/wifi_link.* identifiers and fold in remaining judgment
  calls
status: done
use-cases:
- SUC-005
depends-on:
- '007'
github-issue: ''
issue: strip-units-from-wifi-link-identifiers.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Strip units from src/comms/wifi_link.* identifiers and fold in remaining judgment calls

## Description

**Depends on ticket 007** for sequencing only — this ticket's one
`wire_adapter.cpp` edit (the `yaw` rename in `onMoveX()`) is a
same-file, different-region change from ticket 007's `wire_adapter.cpp`
work; doing it after avoids two agents editing that file concurrently
within this sprint. This ticket is otherwise fully independent and has
**no relationship to sprint 031** — `wifi_link.*` is untouched by that
branch (confirmed 2026-09-05), and the `yaw` rename is a one-line,
same-file-different-region change relative to 031's own edits.

Per `.claude/rules/no-units-in-identifiers.md`: rename every
unit-suffixed identifier in `src/comms/wifi_link.h`/`.cpp` (~70,
e.g. `kCommandTimeoutMs` → `kCommandTimeout` with a trailing `// [ms]`
comment, `nowMs_` → `now_` `// [ms]`, etc.) — this file landed after
sprint 029 ticket 005's identifier inventory and carries the
`tests/host/test_no_units_in_identifiers_source_pin.py` exclusion as a
result. Remove that exclusion once done.

Also fold in three judgment calls sprint 029 ticket 005 explicitly left
for later, named in the issue:

- `yawRadPerS` in `shims.cpp::startMove()` — unit mid-name, not caught
  by the end-anchored naming pattern. Rename to what the quantity IS
  (e.g. `yawRate`), unit in a trailing comment.
- `distanceF` in `shims.cpp::startMove()` — a type-letter suffix, not a
  unit suffix, but the same "name says the representation, not the
  quantity" defect. Rename to `requestedDistance` or similar.
- `yaw` in `wire_adapter.cpp::onMoveX()` for what is actually a
  rotation — rename to `rotation` or similar (this is the one edit in
  `wire_adapter.cpp` — keep it minimal and reviewable given the
  file's sprint-031 sensitivity).

Wire field names and JSON config keys are NOT renamed — this rule is
about code identifiers only (per the rule's own scope note).

## Acceptance Criteria

- [x] Every renamed identifier in `wifi_link.h`/`.cpp` carries a
      trailing `// [unit]` comment on its declaration.
- [x] `tests/host/test_no_units_in_identifiers_source_pin.py`'s
      `wifi_link` exclusion is removed and the test passes.
- [x] `yawRadPerS`, `distanceF` (`shims.cpp::startMove()`), and `yaw`
      (`wire_adapter.cpp::onMoveX()`) are renamed per the rule.
      (`yawRadPerS` was already renamed to `yawRateFloored` by sprint
      032 ticket 007, commit c39f85d, before this ticket opened;
      `distanceF` -> `requestedDistance`; `yaw` -> `engineRotation`,
      since the enclosing parameter is already named `rotation`.)
- [x] No wire field name or JSON config key is touched.
- [x] No behavior change — every rename is value- and control-flow-
      identical (verified by the existing test suite staying green,
      not by re-deriving logic).

## Testing

- **Existing tests to run**: `tests/host/test_wifi_link.py` (must stay
  green, unmodified in behavior-asserting content — this is a pure
  rename); `tests/host/test_no_units_in_identifiers_source_pin.py`.
- **New tests to write**: none — this is a rename with no new behavior
  to cover. The source-pin test with the exclusion removed IS the new
  coverage.
- **Verification command**: `uv run pytest tests/host/`
