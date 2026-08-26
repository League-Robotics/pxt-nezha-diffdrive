---
id: '006'
title: Enumerate remaining mirrored constants; drift-test or merge each
status: done
use-cases: []
depends-on:
- '002'
- '005'
github-issue: ''
issue: duplicated-constants-across-the-shim-boundary.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Enumerate remaining mirrored constants; drift-test or merge each

## Description

This is the sprint's real deliverable: not a fix to one constant, but a
**checkable enumeration** of every mirrored constant left in the repo, so the
answer to "is this repo's mirrored-constant hygiene good?" is a list anyone
can verify, not an assertion. The rule this acts on, established by the
review and restated in both linked issues:

> Every mirrored constant in this repo that has a drift test -- `kVersion`,
> the four 240-byte line-cap constants, `RUN_EVENT_SOURCE`, the `kDiag*`
> ordinals -- has held across five sprints without drifting. Every one
> without a drift test has drifted, or is structurally able to. **Every
> mirrored constant gets a drift test, or gets merged.**

Depends on tickets 002 and 005 because both retire specific mirrors (`0x5F`;
the cdeg<->rad conversion) that this enumeration needs to treat as
already-resolved, not as open findings to re-litigate.

## What "mirrored constant" means here

A value that two or more independently-editable sites (different files,
different languages, or both) each carry their own literal copy of, where the
two copies are supposed to represent the same fact. This is NOT the same as
"the same numeric literal appears twice by coincidence" (e.g. two unrelated
`0` or `1` literals) -- it specifically means: if one site changes and the
other does not, something silently becomes wrong. The dutl/dutr percent scale
that ticket 003 documents is a related-but-distinct category (one number
observed through two derivations, not two independently-settable copies) and
is out of scope here -- it is already handled by ticket 003.

## Known starting set (verify and extend by grep sweep -- do not stop here)

**Already guarded (drift-tested, confirm still true, no action needed)**:

| Constant | Sites | Test |
|---|---|---|
| `kVersion` | `protocol.cpp` vs `pxt.json` | `test_wire_constants_drift.py::test_k_version_matches_pxt_json_version` |
| 240-byte line cap | `serial_transport.h`, `wire_handler.h`, `radio_transport.h` (x2) | same file, capacity-constants test |
| `RUN_EVENT_SOURCE` / `kRunEventSource` | `run.ts` vs `protocol.cpp` | same file |
| `kDiag*` ordinals | `wire_adapter.cpp` vs `shims.cpp`'s `diagValue()` switch | same file |

**Resolved by this sprint's earlier tickets (confirm the merge landed cleanly,
no action needed beyond verification)**:

| Constant | Resolution |
|---|---|
| `kExpectedProductId` (`0x5F`) | Ticket 002 -- merged to a single site in `otos_port.h` |
| cdeg<->rad conversion | Ticket 005 -- merged to `kCdegToRad`/`kRadToCdeg` in `shims.cpp` |

**Explicitly tracked elsewhere -- do NOT fix in this ticket (cross-reference
only, so the enumeration is honest about what exists without duplicating
another sprint's work)**:

- **`travelCalib` (0.7878 mm/deg)** -- mirrored across `src/DESIGN.md`,
  `docs/design/specification.md`, `docs/design/usecases.md`,
  `tools/tour_watch.py`, `tools/tour_chart.py`. Already has a dedicated
  ticket: sprint 017 ticket 002 (`clasi/sprints/017-.../tickets/002-propagate-travelcalib-0-7878-to-three-docs-and-two-tools-drift-test-or-delete-the-mirrors.md`),
  not yet executed as of this sprint's planning (sprint 017 phase:
  `ticketing`). List it in this ticket's enumeration output with a status of
  "tracked by sprint 017 ticket 002" -- do not re-implement its fix here, and
  do not mark it done in this ticket's own bookkeeping.
- **Simulator yaw rate divisor (`blocks/sim.ts:99`'s `/ 115`) vs hardware's
  `effectiveTrackWidth()` (114.2 / 0.952 = 119.96mm)** -- this is a genuine
  ~4.3% VALUE discrepancy (correctness finding C-14 in
  `docs/code-review/2026-08-26/raw/correctness-wire-blocks.md`), not merely
  an unguarded-but-currently-correct duplicate. Neither linked issue for this
  sprint names it, and fixing the simulator's actual physics is a behavior
  change outside a "small, self-contained, hygiene" ticket's scope. List it
  in the enumeration output as a KNOWN, UNRESOLVED discrepancy with a
  one-line note recommending it become its own issue -- do not change
  `sim.ts`'s divisor or add a drift test asserting the two values match
  (they do not match today; a test asserting equality would be asserting
  something false).

**Named by `duplicated-constants-across-the-shim-boundary.md` as the other
merge candidate this ticket must resolve**:

- **Two default speeds in two units**: `src/blocks/motion.ts:55`
  `defaultSpeed = 15` ([cm/s], block-layer move speed, independently settable
  via `setDefaultSpeed`) vs `src/shims.cpp:145` `defaultCruiseMmS_ = 150.0f`
  ([mm/s], wire's `default_cruise` sentinel resolution, independently
  settable over the wire at `kFields` ordinal 15). `shims.cpp:143`'s comment
  currently asserts these "match," seeded from `defaultSpeed` (15 cm/s), and
  cites `main.ts` -- a file retired two sprints ago (see `src/DESIGN.md`'s own
  note flagging this citation as stale). Nothing enforces the match; they
  diverge the moment either is set independently, which the design allows.
  **Resolve this one explicitly** (do not just leave it in a "known
  discrepancy, out of scope" bucket like the sim.ts case above -- it IS in
  scope, named by the linked issue): either (a) find a real way to derive one
  from the other at a shared boundary (a true merge -- only if a mechanism
  exists or is cheap to add; if the two are architecturally independent by
  design, as Q-05's own analysis suggests, a literal merge may not be sound),
  or (b) if they are legitimately independent by design (one is a wire
  sentinel default, the other a block-layer move speed, both deliberately
  separately settable), correct `shims.cpp:143`'s comment to stop asserting a
  coupling that is not maintained -- remove the stale `main.ts` citation and
  state plainly that the 150.0f seed was a one-time planning-time choice
  matched to `defaultSpeed`'s value AT THE TIME, not an enforced invariant.
  Whichever path is taken, record the decision and its reasoning in the
  ticket's implementation (a code comment, at minimum) so a future reader
  does not re-discover this as a bug.

## What to change

1. **Grep sweep**: search `src/`, `blocks/` (if distinct from `src/blocks/`),
   `tools/`, `tests/`, and `docs/design/` for numeric or string literals that
   plausibly represent the same real-world fact in two or more
   independently-editable locations. Use the known starting set above as a
   floor, not a ceiling -- the point of this ticket is that the list is
   checkable, so it must reflect an actual sweep, not just a transcription of
   this ticket's own starting set. Cross-check against
   `docs/code-review/2026-08-26/raw/cohesion-and-tooling.md`'s Q-03/Q-04/Q-05
   findings and its closing "Structural observations" section for anything
   this ticket's own research did not already surface.
2. For each constant found, categorize and act:
   - **Already drift-tested** -- note it, no action.
   - **Resolvable by merge** (one site can defer to the other, or both can
     defer to one new shared definition) -- merge it, following the pattern
     tickets 002 and 005 established in this same sprint.
   - **Not mergeable, but currently consistent** -- add a drift test
     following `tests/host/test_wire_constants_drift.py`'s established
     pattern (regex/text-scan both sides at test time, compare, fail loud
     with a message naming both source files).
   - **Not mergeable and NOT currently consistent** (a real, already-drifted
     discrepancy, like the sim.ts case) -- do not add a false-equality test;
     flag it explicitly as a known discrepancy with a recommendation, and
     leave the value unchanged unless it is the defaultSpeed/defaultCruiseMmS_
     pair named above, which this ticket must resolve one way or the other.
   - **Already tracked by another sprint/ticket** (travelCalib) -- cite it,
     do not duplicate the fix.
3. Produce the enumeration itself somewhere durable and reviewable -- the
   natural home is either a new test file's module docstring (following
   `test_wire_constants_drift.py`'s own docstring, which already enumerates
   its four guarded cases) or a short table in this ticket's own
   implementation notes / commit message. Prefer extending
   `tests/host/test_wire_constants_drift.py`'s docstring with the newly
   resolved cases, keeping ONE canonical list rather than scattering it.
4. Add drift tests for every newly-merged or newly-guarded constant, in
   `tests/host/test_wire_constants_drift.py` (extending the existing file,
   consistent with the sprint's Test Strategy) or a clearly-named sibling
   file if the existing one becomes unwieldy.

## Acceptance Criteria

- [x] A grep-based sweep of `src/`, `blocks/`, `tools/`, `tests/`, and
      `docs/design/` was performed (not just a transcription of this
      ticket's starting set), and its result is recorded somewhere
      reviewable (test file docstring, ticket notes, or commit message).
- [x] Every mirrored constant found has one of: a drift test, a completed
      merge (this ticket or tickets 002/005), a note that it's tracked by
      another sprint/ticket (travelCalib), or an explicit "known,
      unresolved discrepancy" flag with a recommendation (sim.ts's yaw-rate
      divisor) -- none is left silently unaddressed.
- [x] The `defaultSpeed`/`defaultCruiseMmS_` pair is explicitly resolved
      (merged, or the false "match" comment corrected) -- this one may not be
      left as a bare "known discrepancy" note, since the linked issue names
      it as a merge candidate this sprint must act on.
- [x] `travelCalib` is listed with a "tracked by sprint 017 ticket 002" note
      and is NOT modified by this ticket.
- [x] The sim.ts yaw-rate divisor is listed as a known, unresolved
      discrepancy with a recommendation, and its value is NOT changed by
      this ticket.
- [x] Every newly added drift test follows `test_wire_constants_drift.py`'s
      established pattern (source-text scan, pinned comparison, a failure
      message naming both files).
- [x] No change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable).

## Enumeration (the artifact)

Grep sweep performed across `src/` (including `src/blocks/`, which is
this project's `blocks/` -- there is no separate top-level `blocks/`
directory), `tools/`, `tests/`, and `docs/design/`, cross-checked
against `docs/code-review/2026-08-26/raw/cohesion-and-tooling.md`
(Q-03/Q-04/Q-05 and its "Structural observations" closing section) and
`raw/correctness-wire-blocks.md` (C-14). The starting set's four
already-guarded pairs and two tickets-002/005 merges were verified
still true by re-running their tests; three new mirrored constants
this ticket's own sweep found (the 24 ms cadence, `trackWidth`/
`rotationalSlip` vs the spec doc, and the `ConfigField` ordinal
three-way) had no prior guard.

| Constant | Sites | Verdict | Action taken |
|---|---|---|---|
| `kVersion` | `protocol.cpp` vs `pxt.json` | Already guarded | None; `test_k_version_matches_pxt_json_version` re-run, still passing |
| 240-byte line cap | `serial_transport.h`, `wire_handler.h`, `radio_transport.h` (x2) | Already guarded | None; four-way equality test re-run, still passing |
| `RUN_EVENT_SOURCE`/`kRunEventSource` | `run.ts` vs `protocol.cpp` | Already guarded | None; drift test re-run, still passing |
| `kDiag*` ordinals | `wire_adapter.cpp` vs `shims.cpp`'s `diagValue()` | Already guarded | None; both pinned-snapshot tests re-run, still passing |
| `kExpectedProductId` (`0x5F`) | `otos_port.h` (single site) | Merged (ticket 002, this sprint) | None; `test_otos_product_id_single_source.py` re-run, still passing |
| cdeg<->rad conversion (`kCdegToRad`/`kRadToCdeg`) | `shims.cpp`, 8 sites | Merged (ticket 005, this sprint) | None further; ticket 005's own new drift test (section 5 of `test_wire_constants_drift.py`) re-run, still passing |
| `travelCalib` (0.7878 mm/deg) | `motion_engine.h` (source), `tools/tour_chart.py` (mirror, drift-tested), `src/DESIGN.md`, `docs/design/specification.md`, `docs/design/usecases.md` (doc mentions) | Tracked by sprint 017 ticket 002 -- verified, not re-implemented | Confirmed already executed: `tour_chart.py`'s `--travel-calib` default is 0.7878 and guarded by `tests/tools/test_travel_calib_drift.py`; `tour_watch.py`'s old `k = 0.8102/100` mirror was deleted outright (not merely updated -- the dead branch it fed was removed); all three docs currently state 0.7878. **Not modified by this ticket.** |
| `defaultSpeed` (`blocks/motion.ts`, 15 cm/s) vs `defaultCruiseMmS_` (`shims.cpp`, 150.0f mm/s) | `src/blocks/motion.ts:57`, `src/shims.cpp`'s `Rig::defaultCruiseMmS_` | Resolved explicitly -- NOT merged (legitimately independent by design: one is a wire sentinel default settable over `default_cruise`, the other a block-layer move speed settable via `setDefaultSpeed()`; Q-05's own analysis reached the same conclusion) | Corrected `shims.cpp`'s seed comment: removed the archaeology markers (sprint/ticket/finding-ID/`.md` citations) and the assertion that the 150.0f/15 cm/s match is maintained; states plainly it was a one-time implementation-time snapshot, explains why the two are free to diverge. Two new drift tests pin the corrected comment's honesty (no stale `main.ts` citation; explicit "not an enforced invariant" + "independently settable" language present) |
| 24 ms tick cadence | `shims.cpp`'s `cfg.cyclePeriod = 24` vs `blocks/sim.ts`'s `kSimTickPeriodMs = 24` | Not mergeable (TS vs C++, no shared boundary); currently consistent | New drift test added (`test_sim_tick_period_matches_hardware_cycle_period`) |
| `trackWidth` (114.2) / `rotationalSlip` (0.952) | `motion_engine.h`'s defaults vs `docs/design/specification.md`'s constants table | Not mergeable (code vs. doc); currently consistent | Two new drift tests added, one per value |
| `ConfigField` ordinals (0-17) | `blocks/motion.ts`'s `ConfigField` TS enum vs `wire_adapter.cpp`'s `kFields` name/ordinal table vs `shims.cpp`'s `setKernelValue()`/`getConfigValue()` switches | Not mergeable (TS vs C++, same deliberate choice the existing `kDiag*` test already documents for this exact ordinal space); currently consistent; **previously unguarded** -- found by this ticket's own sweep, not in the starting set | Two new drift tests added: ordinal equality (TS enum vs `kFields`) and case-coverage (every ordinal has a `setKernelValue()`/`getConfigValue()` case) |
| Simulator yaw-rate divisor (`blocks/sim.ts:99`'s `/ 115`) vs hardware's `effectiveTrackWidth()` (114.2 / 0.952 = 119.96) | `blocks/sim.ts:99` vs `motion_engine.h`'s `effectiveTrackWidth()` | **Known, unresolved discrepancy** (~4.3% VALUE mismatch, not an unguarded-but-correct duplicate) -- out of this ticket's hygiene scope by design | Filed `clasi/issues/simulator-yaw-rate-divisor-diverges-from-hardware-track-width.md` (did not previously exist) with the C-14 evidence and a suggested direction. **`sim.ts`'s value is NOT changed by this ticket.** No false-equality test added. |

All nine drift tests new to this ticket (5-9, `test_wire_constants_drift.py`)
plus ticket 005's own section-5 tests were run together with the
pre-existing ones: `uv run pytest tests/host/test_wire_constants_drift.py`
-- 19 passed. Full `tests/host/ tests/tools/` suite: 677 passed. Archaeology
marker ratchet re-checked after the comment correction (it removes
markers, adds none): still within budget.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_constants_drift.py`
  (confirm the four already-guarded cases still pass unchanged), plus the
  full host and tools suites (`uv run pytest tests/host/ tests/tools/`) since
  this ticket touches `shims.cpp`'s comment (the `defaultCruiseMmS_` case) and
  potentially `motion.ts`/`sim.ts`.
- **New tests to write**: one drift test per newly-merged-or-guarded constant
  discovered by the sweep, added to `tests/host/test_wire_constants_drift.py`
  following its own established pattern. If the `defaultSpeed`/
  `defaultCruiseMmS_` pair is resolved via merge, add a test pinning the
  relationship; if resolved via corrected documentation instead, no
  "equality" test is appropriate (they are legitimately independent) -- but
  do add a test confirming the corrected comment no longer cites the retired
  `main.ts`, and no longer asserts a match that isn't enforced (the "test
  that fails against today's code" here is one that checks the *comment
  text itself* no longer contains the stale claim, which fails against
  today's actual comment and passes once corrected).
- **Verification command**: `uv run pytest tests/host/ tests/tools/`
