---
id: '003'
title: Document dutl/dutr units in tlm.py and both source comments
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: wire-and-shim-minor-defects.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Document dutl/dutr units in tlm.py and both source comments

## Decision already made -- do not re-open

The stakeholder-approval gate for this sprint (recorded via
`record_gate_result`, see `get_sprint_phase("019")`) already resolved the one
open question here: **document the existing `dutl`/`dutr` scale; do NOT
change it.** The wire format is observed by bench tooling and captured logs
whose parsers already assume the current x100-of-percent scale (`probe(12)`
== 10000 at 100% duty) -- changing the scale would silently reinterpret every
historical capture. If the scale is ever to change, that is a deliberate wire
protocol change with the tooling updated in the same sprint, not this one.
This ticket is documentation-only: it does not touch the numeric scale
anywhere.

## Description

The unit chain, as it exists today:

| Layer | Value | Unit |
|---|---|---|
| `NezhaMotorPort::appliedDuty()` | `lastWrittenPct_ / 100.0f` | fraction, [-1, 1] |
| `src/core/diffdrive.cpp:795` | `left_.appliedDuty() * 100.0f` | percent, per `diffdrive.h:136`'s `[%]` doc |
| `src/shims.cpp:797` `diagValue(12)`/`diagValue(13)` | `out.appliedDutyLeft * 100.0f` / `...Right * 100.0f` | percent x100 |
| wire `dutl`/`dutr` columns (`probe(12)`/`probe(13)`) | same | **10000 at 100% duty** |

Both existing source comments describe this as "duty x100" (`src/shims.cpp:766`
and `src/blocks/sim.ts:289`), which reads naturally as "percent" and is wrong
by 100x -- the wire value is percent multiplied by 100 a SECOND time (once in
`diffdrive.cpp` to go fraction->percent, again in `shims.cpp`'s `diagValue`).

`tools/tlm.py` is the module that calls itself, in its own header comment
(`tools/tlm.py:249`), *"the only place any wire -> engineering-unit scale
factor is written"* -- and its unit table (lines 248-259) documents `x`, `y`,
`ox`, `oy`, `h`, `oh`, `vl`, `vr` but **omits `dutl`/`dutr` entirely**. A bench
operator reading a capture has no source in this repo that states the true
scale.

`tests/tools/test_tlm.py:346` already carries `'dutl': -1300` as fixture data
(i.e. -13% duty, at the current double-x100 scale) with no unit assertion
tying that number to a documented meaning.

**Note**: `src/core/diffdrive.{h,cpp}` is the vendored, byte-stable kernel --
`diffdrive.h:136`'s `[%]` doc for `appliedDutyLeft`/`appliedDutyRight` is
itself correct (it is percent, at that layer) and must NOT be edited. The
100x-wrong comments this ticket fixes are in `src/shims.cpp` and
`src/blocks/sim.ts`, both of which are project-owned, not vendored.

## What to change

1. `tools/tlm.py` -- add `dutl`/`dutr` to the unit-conversion helpers section
   (lines 248-284: the header comment block plus `pose_cm`/`otos_cm`/
   `wheels_mms`). Follow the established pattern: extend the header comment
   (lines 248-259) with the derivation chain (fraction -> x100 in the kernel
   -> x100 again in `diagValue`, landing on percent x100 / "10000 == full
   duty"), and add a `duty_pct` (or similarly named) helper function
   alongside `pose_cm`/`otos_cm`/`wheels_mms` that documents and returns the
   value in a clearly labeled unit (either pass the raw wire value through
   with a name that makes the x100 explicit, e.g. returning "duty x100,
   percent" as-is, or divide by 100 to hand back true percent -- implementer's
   call, but the function's own docstring must state which it does, mirroring
   `wheels_mms()`'s "kept as a real function... so this stays the one place
   that fact is asserted" reasoning).
2. `src/shims.cpp:766` -- correct the "duty x100" comment (near the
   `diagValue` doc block, ordinals 12/13) to state the true scale precisely,
   e.g. "duty, percent x100 (10000 == full duty)" rather than the
   ambiguous-reads-as-percent "duty x100".
3. `src/blocks/sim.ts:289` -- same correction to the "12/13 applied duty
   x100" comment.
4. Do NOT change any numeric scale factor anywhere in this chain
   (`NezhaMotorPort`, `diffdrive.cpp`, `shims.cpp`'s `diagValue`, or
   `tlm.py`'s new helper) -- see "Decision already made" above.

## Acceptance Criteria

- [x] `tools/tlm.py`'s unit table documents `dutl`/`dutr` with the full
      derivation (fraction -> x100 in the kernel -> x100 again in
      `diagValue`), matching the module's own claim to be the one place this
      is written down.
- [x] `src/shims.cpp:766`'s duty comment states the correct scale (percent
      x100, 10000 == full duty), not the ambiguous "duty x100".
- [x] `src/blocks/sim.ts:289`'s duty comment gets the same correction.
- [x] No numeric scale factor changed anywhere -- `probe(12)` at 100% duty
      still reads 10000 after this ticket, exactly as before.
- [x] `src/core/diffdrive.{h,cpp}` untouched.
- [x] A test pins the documented unit against the actual runtime value, so a
      future change to the double-x100 scale (deliberate or accidental) is
      caught rather than silently re-interpreted.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_tlm.py` (confirm
  the existing `dutl: -1300` fixture and any related assertions still pass
  unchanged), `uv run pytest tests/host/` (no C++ logic changes, but
  `shims.cpp`'s comment-adjacent tests should still be green).
- **New tests to write**: a `tests/tools/test_tlm.py` test that calls the new
  `dutl`/`dutr` helper (or the documented conversion) against a known input
  and asserts the documented scale (e.g. a raw wire value of 10000 maps to
  100% duty, or whatever the helper's chosen return convention is) -- this is
  the test that would have caught `tlm.py`'s current omission, since today
  there is no function to call and no assertion tying the wire value to a
  stated unit.
- **Verification command**: `uv run pytest tests/tools/test_tlm.py`
