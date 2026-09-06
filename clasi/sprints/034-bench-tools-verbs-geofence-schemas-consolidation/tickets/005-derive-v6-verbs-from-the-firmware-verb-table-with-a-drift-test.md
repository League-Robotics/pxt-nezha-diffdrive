---
id: '005'
title: Derive _V6_VERBS from the firmware verb table, with a drift test
status: open
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: tools-v6-verbs-geofence-pose-csv-schema.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Derive _V6_VERBS from the firmware verb table, with a drift test

## Description

`tools/robotlink.py`'s `_V6_VERBS` does not match the firmware:

    _V6_VERBS = frozenset((
        'GET', 'SET', 'TLM', 'STOP',
        'MOVE', 'PIVOT', 'WHEELS_V', 'WHEELS_X', 'GO_TO', 'GO_TO_W', 'ARC',
    ))

`MOVE`, `PIVOT`, `GO_TO` and `ARC` are **not firmware verbs**.
`MOVE_X`, `MOVE_V` and `GO_TO_R` are **missing**. `_is_wire()` tests the
first token against this set, so `link.send('MOVE_X 200 0 150 5000')`
goes out with **no `#id`**, parses on the robot as `#0`, falls below
`expectedNext_` (which starts at 1) and is **silently dropped** -- the
exact mechanism the long comment directly above the set describes. It is
latent only because no tool sends v6 motion through `Link` today
(`field_dance.py` and `tests/dev/closure.py` use `FieldLink.seqd`, which
appends an id unconditionally). Ticket 006 is about to route more traffic
through `Link`, which is why this lands first.

This is exactly the failure class this repo's rules exist to catch: a
command that appears sent, never executes, and leaves the odometry
happily reporting travel (`.claude/rules/playfield-testing.md`, "The
robot is OFF -- check this first").

**Verified against the tree, 2026-09-06.** `src/comms/wire_handler.cpp`
`kCommandTable` has **18** entries (there is a `static_assert` on that
count): `HELLO PING ID VER STATUS HELP GET SET TLM WHEELS_X WHEELS_V
MOVE_X MOVE_V GO_TO_R GO_TO_W STOP ESTOP RUN`. Seven are unsequenced,
handled by name before the table walk in `feed()`/`dispatch()`:
`ESTOP PING HELP HELLO ID VER STATUS`. The firmware states the governing
rule in that file in block capitals -- *a verb is sequenced iff its
correctness depends on its position in the stream* -- so the derivation
is: **sequenced = kCommandTable minus those seven** = `GET SET TLM
WHEELS_X WHEELS_V MOVE_X MOVE_V GO_TO_R GO_TO_W STOP RUN` (11).

**The cleartext path is different and must stay unsequenced.** `RUN` the
v6 verb (space form, `RUN <name>`) is in the table and is sequenced.
`RUN:tour:wheels` / `DIAG` cleartext go through a *different parser* and
carry no id -- `.claude/rules/playfield-testing.md` records that
`RUN:tour:wheels` unsequenced returns its `DBG:tour=` receipt normally.
`_is_wire()` must keep distinguishing them.

## Acceptance Criteria

- [ ] `_V6_VERBS` matches the firmware's sequenced set exactly: the four
      phantom verbs are gone, `MOVE_X`/`MOVE_V`/`GO_TO_R` are present.
- [ ] A drift test fails when `_V6_VERBS` and `kCommandTable` diverge --
      whether a verb is added, removed or renamed in the firmware.
- [ ] The drift test also pins the seven unsequenced verbs, so moving a
      verb across that boundary in the firmware fails here.
- [ ] `link.send('MOVE_X ...')` is formatted with a `#<id>`; a test
      asserts it for all three previously-missing verbs.
- [ ] `PING`, `HELLO`, `ID`, `VER`, `STATUS`, `HELP`, `ESTOP` are still
      sent bare -- the existing `test_robotlink.py` assertions on the
      unsequenced seven stay green.
- [ ] A cleartext `RUN:tour:wheels` still goes out unsequenced.
- [ ] The 45-line pre-sprint-024 narrative comment above `_V6_VERBS` is
      replaced. The review supplies the replacement verbatim; use it:
      `# Verbs the firmware sequences (wire_handler.cpp kCommandTable).
      An unsequenced line parses as #0 and is dropped; a verb listed here
      that the robot does NOT sequence burns an id and stalls the
      stream.`

## Implementation Plan

### Approach

**Keep the literal set in `robotlink.py`; add a drift test.** Do not
generate a Python module and do not parse `wire_handler.cpp` at import
time. The sprint's Design Rationale 1 records why: generation earns its
keep for `ConfigField`'s 30-plus rows with block labels, not for 11
strings a reader should be able to see; and import-time parsing would
make every tool depend on a C++ file being present and parseable.

The drift test reads `src/comms/wire_handler.cpp` **as text** --
`tests/host/test_wire_constants_drift.py` is the established precedent
and explains in its own docstring exactly why text, not compilation, is
the right technique for pxt.h-adjacent files. Extend that file rather
than starting a new one.

Parse two things out of the source:
1. The `kCommandTable` initialiser rows (`{"VERB", ...}`).
2. The unsequenced set. Prefer something structural over a hand-typed
   Python list -- e.g. the `std::strcmp(verb, "X") == 0` early-return
   comparisons plus the query-verb block. If you cannot parse the
   unsequenced set reliably, keep it as a literal in the *test* with a
   comment citing the firmware, and assert the arithmetic
   (`len(table) - len(unsequenced) == len(_V6_VERBS)`) so a count change
   still trips. State which you chose and why in the test docstring.

Also sanity-check against the `static_assert(... == 18)` already in the
firmware -- if that number and the parsed row count disagree, the parser
is wrong and the test should say so rather than pass.

### Files

- `tools/robotlink.py` -- the set and its comment.
- `tests/host/test_wire_constants_drift.py` -- the drift test.
- `tests/tools/test_robotlink.py` -- per-verb formatting assertions.

### Re-anchoring

`_V6_VERBS` is at `robotlink.py:183` today, **not** the `:120-123` the
issue cites; `kCommandTable` is at `wire_handler.cpp:307`, not `:314`.
Grep for `_V6_VERBS`, `kCommandTable`, `_is_wire`.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_robotlink.py
  tests/host/test_wire_constants_drift.py -q` (foreground, scoped).
- **New tests to write**: the drift test; a formatting test per verb for
  `MOVE_X`, `MOVE_V`, `GO_TO_R`; a negative test that a cleartext
  `RUN:`-prefixed line is not sequenced; a test that the four phantom
  verbs are absent.
- **Verification command**: `uv run pytest tests/tools/test_robotlink.py
  tests/host/test_wire_constants_drift.py -q`
