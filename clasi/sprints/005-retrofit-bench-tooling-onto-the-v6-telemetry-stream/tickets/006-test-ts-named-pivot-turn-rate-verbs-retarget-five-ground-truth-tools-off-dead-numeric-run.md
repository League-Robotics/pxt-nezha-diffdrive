---
id: '006'
title: test.ts named pivot/turn-rate verbs; retarget five ground-truth tools off dead
  numeric RUN
status: in-progress
use-cases:
- SUC-008
depends-on:
- '003'
github-issue: ''
issue: testfiles-are-not-type-checked-testrig-is-broken.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# test.ts named pivot/turn-rate verbs; retarget five ground-truth tools off dead numeric RUN

## Description

Closes the RUN-vocabulary half of
`testfiles-are-not-type-checked-testrig-is-broken.md` (R-16: PY-01).
`otos_bench.py` and five bench tools —
`pivot_truth.py`, `truth_check.py`, `rotation_check.py`,
`turn_sweep.py`, `otos_levercal.py` — issue numeric `RUN:<n>` commands
that current firmware's string-keyed `onRun()` dispatch never
registers, so they are silent no-ops. Depends on ticket 003 because
`pivot_truth.py`/`truth_check.py`/`rotation_check.py` are among the
files ticket 003's camera-consolidation touches — landing that first
avoids this ticket's RUN-string edits being redone.

**Confirmed against `test.ts`'s own header comment (its authoritative
named-command list, lines 9-14) during sprint planning** — two of the
five tools already have a real named target and need only a Python-side
rename:

- **`otos_levercal.py`** sends `RUN:8`/`RUN:14`. `test.ts` already has
  `diffDrive.onRun("cal", function (arg) { leverCal(arg != 0) })` —
  `RUN:cal` (arg 0) is the exact equivalent of `RUN:8`, `RUN:cal:1`
  (arg non-zero) of `RUN:14` ("verify" mode, per `leverCal`'s own
  signature). **No firmware change needed for this one** — retarget
  `otos_levercal.py`'s `verb = 'RUN:14' if a.verify else 'RUN:8'` to
  `'RUN:cal:1' if a.verify else 'RUN:cal'` (or `RUN:cal:0` — confirm
  `runArg(0)` treats a bare `RUN:cal` and an explicit `RUN:cal:0`
  identically before choosing).
- `pivot_truth.py`/`truth_check.py`/`rotation_check.py`'s `RUN:10`
  (their `fix()` helper, taking one live OTOS fix) already has a real
  named target too: `diffDrive.onRun("fix", function (arg) {
  logFix("now") })` emits the same `OCAL:now:...` line these three
  tools already parse. Retarget `RUN:10` → `RUN:fix` — **no firmware
  change needed for this piece either.**

The remaining piece **does** need a firmware addition — there is
currently no named verb for a relative pivot-by-degrees or a
parametrized turn rate:

- `pivot_truth.py`/`truth_check.py`/`rotation_check.py`'s
  `PIVOT_VERB = {180: 4, -180: 5, 360: 2}` (commanded relative
  rotation in degrees → dead numeric offset).
- `turn_sweep.py`'s `RUN:{57000 + rate}` (turn-rate) and
  `RUN:{58360 + deg}` (turn-to-degree).

Add **two new named verbs to `test.ts`**, following the exact
`runArg()`-based pattern `goto`/`face` already establish (see
`test.ts:358-399` for that pattern):

- A **relative pivot** verb (e.g. `RUN:pivot:<deg>`) — commands a
  relative in-place rotation of `runArg(0)` degrees, independent of
  world-frame tracking (unlike `face`, which requires
  `worldReady()`/OTOS). Must work on the floor over radio with no OTOS
  requirement, since `rotation_check.py`/`pivot_truth.py`/
  `truth_check.py` are floor+radio-only tools per their own docstrings.
- A **turn-rate** verb (e.g. `RUN:turnrate:<rate>`) — sets the yaw rate
  `turn_sweep.py`'s subsequent pivot verb command uses (mirroring the
  numeric vocabulary's `RUN:57000+rate` then `RUN:58360+deg` two-step
  shape, or combine into one verb taking both args — implementer's
  choice; keep `turn_sweep.py`'s own call shape close to its current
  two-`link.send()` structure to minimize its own edit).

Retarget the five tools' RUN strings once the new verbs exist, and
**update `test.ts`'s own header comment (lines 9-14)** to list them —
it is the authoritative named-command list and becomes a stale-doc
landmine on day one if this ticket skips it.

## Acceptance Criteria

- [x] `test.ts` gains a named relative-pivot verb and a named
      turn-rate verb, both reachable over radio with no OTOS/world-pose
      requirement (confirm by tracing: neither new handler calls
      `worldReady()` or anything gated on it).
- [x] `test.ts`'s header comment (lines 9-14) lists both new verbs
      alongside the existing `cal`/`fix`/`seed`/`probe`/`arm`/`gap`
      list.
- [x] `otos_levercal.py` sends `RUN:cal`/`RUN:cal:1` (or the chosen
      equivalent) instead of `RUN:8`/`RUN:14`.
- [x] `pivot_truth.py`, `truth_check.py`, `rotation_check.py` send
      `RUN:fix` instead of `RUN:10`, and the new pivot verb instead of
      `PIVOT_VERB`'s numeric offsets (2/4/5).
- [x] `turn_sweep.py` sends the new turn-rate/pivot verbs instead of
      `RUN:{57000+rate}`/`RUN:{58360+deg}`.
- [x] Every RUN string these five tools send matches a real,
      documented named verb on current `test.ts` — verified against a
      mocked/fake link (string-level assertion on what `send()`
      receives), no robot required.
- [x] `otos_bench.py` and `testrig.ts` are **unaffected** by this
      ticket — their vocabulary is ticket 005's concern, not this one.
- [x] `uv run pytest` (full suite) passes.

## Implementation Notes

- `pivot_truth.py`/`truth_check.py`/`rotation_check.py`'s pivot
  amounts are exactly `{180, -180, 360}` degrees today — the new named
  verb should accept an arbitrary `runArg(0)` degrees, not hardcode
  those three values, so it is a real relative-pivot primitive rather
  than a renamed 3-way dispatch.
- Reuse existing motion primitives already available to `test.ts`
  (e.g. whatever block-level rotation API `main.ts` exposes) rather
  than hand-rolling a new tick loop — `test.ts`'s existing `tickedMove`
  helper (`startMove` + `driveTick()` loop) is the established pattern
  for this file; follow it if a relative pivot needs one.
- `tools/DESIGN.md`'s overlay already documents this ticket's intended
  shape (named `pivot`/`turnrate` verbs). If the final verb names or
  argument shape differ once implemented, update the overlay copy
  (`clasi/sprints/005-*/design/tools-root-DESIGN.md`,
  `test-root-DESIGN.md`) and regenerate the matching `.diff.md` by
  hand so it stays true after this sprint closes — do not leave the
  overlay describing a shape that was not actually built.

## C++11 Gate Coverage

Not applicable — `test.ts` is TypeScript/PXT, not C++; the five
retargeted tools are Python. Neither is compiled by
`test_cxx11_syntax_gate.py`.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` and the full
  `uv run pytest` — confirm no regression to prior tickets' Python
  changes.
- **New tests to write**: a string-level test per retargeted tool
  (`pivot_truth.py`, `truth_check.py`, `rotation_check.py`,
  `turn_sweep.py`, `otos_levercal.py`) asserting the exact RUN string
  sent against a fake link, matching the documented named verb — no
  robot required.
- **Verification command**: `uv run pytest`, plus this sprint's
  build-checkpoint ticket (007) confirms `test.ts`'s new verbs compile
  clean as part of the flashable hex.
