---
status: pending
sprint: '033'
---

# Tools: _V6_VERBS drift-tested against the firmware verb table; geofence wired into every driving tool; one pose-CSV schema

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: TL-04, TL-05, TL-06 ([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #20.

## Description

- **TL-04.** `robotlink.py:120-123` `_V6_VERBS` names `MOVE/PIVOT/GO_TO/ARC`
  (not firmware verbs) and omits `MOVE_X/MOVE_V/GO_TO_R`
  (`wire_handler.cpp:314-323`); a `MOVE_X` sent through `Link` gets no
  `#id` and is silently dropped by the robot.
- **TL-05.** The geofence (08-26 D-08) exists in `field.py:42-85` with zero
  callers; `tour_run.place()`, `Repositioner.go()` and `tour_closedloop`
  drive unchecked; a second, different field size lives in
  `tests/host/test_run_tour_programs.py:171-172`.
- **TL-06.** Three pose-CSV schemas (mm/cdeg vs cm/deg) across
  `tour_capture`/`tour_watch`/`tour_practice`, and `tour_chart.py:107-121`
  picks a reader by column count -- a `tour_watch` CSV plots 10x small
  with no error.

## Remedy

Generate or drift-test `_V6_VERBS` against `kCommandTable`; one
`check_path()` call in every tool that commands motion, one field size;
one CSV schema with a header line the reader keys on.
