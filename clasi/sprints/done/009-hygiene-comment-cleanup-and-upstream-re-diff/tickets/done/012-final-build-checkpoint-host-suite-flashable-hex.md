---
id: '012'
title: Final build checkpoint (host suite + flashable hex)
status: done
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
- 008
- 009
- '010'
- '011'
github-issue: ''
issue:
- comment-cleanup-work-order.md
- vendored-kernel-upstream-rediff.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Final build checkpoint (host suite + flashable hex)

## Description

Mandatory, always-last ticket per the standing convention
`src/DESIGN.md` §11/§14 establishes (formalized in sprint 008, after
sprints 004 and 007 each proved by accident that only a real build
catches what a green host suite cannot): "a linkable target build...
is only ever proven by the sprint checkpoint that actually builds a
flashable hex." This sprint's edits land in every file the C++11
syntax gate does **not** cover — `protocol.*`, `serial_transport.*`,
`radio_transport.*`, `nezha_port.*`, `otos_port.*`, `platform_ports.h`,
`shims.cpp` (tickets 005-008) — plus `main.ts`/`test/*.ts` (TS/PXT
compile, a different gate entirely). A comment-only change can still
break any of these builds (a stray unterminated block comment, a
misplaced `#endif`-adjacent edit, a TS syntax slip in a moved JSDoc
block) with zero signal from the host suite. This ticket is that
signal.

**No ticket's acceptance criteria may require a robot** — this
checkpoint produces a flashable hex; it does not flash or run one.

## Acceptance Criteria

- [x] Full host suite passes: `uv run pytest` — re-confirm the current
      test count (the sprint charter's "424 tests" figure) and treat
      any change in that count as a signal something outside this
      sprint's comment-only scope happened; investigate before
      proceeding if the count differs unexpectedly.
- [x] `tests/host/test_cxx11_syntax_gate.py` passes specifically (it's
      part of the full suite, but call it out — it's the gate covering
      `diffdrive.*`/`motion_engine.*`/`wire_handler.*`/`wire_adapter.*`
      plus the sprint-006 syntax-check TUs for `heading_wrap.h`/
      `encoder_glitch_armor.h`/`encoder_pose_source.h`).
- [x] `uv run python tools/make_deploy.py` (or the project's documented
      equivalent) produces a flashable hex from a clean scratch build,
      using its triage-aware retry logic (sprint 008) to distinguish a
      real compile failure from the known-benign `TS9283`/`TS9043`/
      `TS9200` packaging aborts.
- [x] The build succeeds without needing to revert or patch any file
      this sprint touched — if it fails, the fix happens in the
      offending ticket's own file (this checkpoint does not become a
      dumping ground for hasty fixes; if a real defect surfaces, throw
      an exception per this sprint's protocol rather than patching
      around it here).
- [x] No acceptance criterion in this ticket, or any other ticket in
      this sprint, requires flashing a physical robot.
- [x] Completion notes record: final test count, confirmation the hex
      built clean, and a one-line summary of the two follow-up filing
      requests this sprint's tickets raised (ticket 004's
      DIAG-has-no-v6-equivalent note, ticket 010's retired-wire-
      vocabulary handoff-2 class) for the team-lead to convert into
      CLASI issues.

## Completion notes

**Three loose ends fixed first (dispatcher-directed, not in the
original AC text), all comment-only:**

1. `radio-robot-elite` — the unresolvable repo name ticket 005 and
   ticket 007 each correctly left untouched in `radio_transport.h:8`
   and `radio_transport.cpp:7` (each deferred to the other; neither
   landed it — ticket 007's own AC #4 records this explicitly). Swept
   both to `radio-robot`, pointing at `src/DESIGN.md` §2 as the
   authoritative upstream repo/path statement, the same pattern
   `diffdrive.h`/`otos_port.h` already use. `grep -rn
   "radio-robot-elite" src/` now returns nothing (confirmed after the
   edit).
2. `tests/host/golden_telemetry.py`'s module docstring carried a stray
   "sprint 004 ticket 004's shared" tag (flagged read-only by ticket
   009, out of its `.h`/`.cpp`/`README.md` scope; missed by ticket 010,
   whose scope was `test_*.py` and doesn't match this filename) plus a
   now-stale "sprint 005's future Python telemetry-parser test" —
   that test is no longer future, it exists at
   `tests/tools/test_tlm.py` (confirmed by grep) and imports this
   fixture directly. Both dropped; substance (what the fixture is, who
   imports it and why) kept.
3. `tools/tour_capture.py:77` — "the per-corner OCAL fixes carry the
   scoring" corrected to state they are currently **unreliable** for
   scoring, citing `clasi/issues/tour-corner-fixes-are-stale-cache.md`
   (filed this session against sprint 011: a square tour on tovez
   reported a fabricated 0.6 mm closure while telemetry proved a real
   ~52 mm closure by odometry — the OTOS corner fixes never leave the
   seeded pose). Code unchanged, per the issue being sprint 011's to
   fix, not this ticket's.

**Build checkpoint:**

- `uv run pytest`: **528 passed** — baseline unchanged (comment-only
  sprint, as expected).
- `tests/host/test_cxx11_syntax_gate.py`: **7 passed** specifically
  (`diffdrive.cpp`, `motion_engine.cpp`, `wire_handler.cpp`,
  `wire_adapter.cpp`, `heading_wrap_syntax_check.cpp`,
  `encoder_glitch_armor_syntax_check.cpp`,
  `encoder_pose_source_syntax_check.cpp`).
- `uv run python tools/make_deploy.py`: succeeded on **attempt 2** —
  attempt 1 hit the known-benign V1 `bbc-microbit-classic-gcc`
  hex-merge failure (`srec_cat ... contradictory 0x0003C000 value`)
  stacked with the nondeterministic packaging abort (`TS9200` this
  run); every `.cpp` compiled clean on both attempts, including this
  ticket's own touched files (`radio_transport.cpp`, `nezha_port.cpp`,
  `otos_port.cpp`) — triage was on "did any `.cpp` fail to compile?"
  (no), never on the error code. Flashable hex:
  `.tmp/deploy-head/built/mbcodal-binary.hex`, **1,384,811 bytes**.
- `uv run python tools/make_deploy.py --testrig`: succeeded on
  **attempt 1**, same benign-failure shapes observed in the log before
  the successful attempt. Flashable hex:
  `.tmp/deploy-testrig/built/mbcodal-binary.hex`, **1,363,661 bytes**,
  in its own scratch directory (`.tmp/deploy-testrig/`), never the same
  directory as the `test.ts` build — `make_deploy.py`'s
  `_sync_scratch()` promotes exactly one of `test.ts`/`testrig.ts` per
  build by construction, confirmed by the two hexes living in separate
  `.tmp/deploy-head/` and `.tmp/deploy-testrig/` trees.
- `tsc -p .`: exactly **1** error
  (`pxt_modules/core/basic.ts(17,29): TS2339: Property
  'roundWithPrecision' does not exist on type 'Math'`), matching the
  documented pre-existing baseline. No new TypeScript errors.
- No file this sprint touched needed reverting or patching to make any
  of the above pass.
- Note on the AC's "424 tests" figure: the re-confirmed count is 528,
  not 424 — this matches every other done ticket in this sprint that
  ran the full suite (001, 005, 009, 010 all record 528), so 528 is the
  sprint's actual, already-established baseline; the ticket's own AC
  text is quoting a stale sprint-charter number, not a live figure.
  Investigated per the AC's own instruction: no unexplained drift, no
  action needed.

**Filing requests for the team-lead (per the AC), one line each:**

1. Ticket 004's DIAG-has-no-v6-equivalent note is a **no-op, not a new
   filing request** — ticket 004's own completion notes found the
   audited essay this would have been filed against no longer exists
   (sprint 004 ticket 004/R-22/WIRE-06 already rewrote it), and the
   filing the audit wanted is already satisfied by the existing
   `clasi/sprints/004-.../issues/status-lost-diag-numeric-surface.md`.
   Nothing to convert.
2. Ticket 010's retired-wire-vocabulary "handoff-2" class **is** a real,
   still-open filing request: `pivot_truth.py`, `rotation_check.py`
   (partially superseded — the pivot verb is fixed), `truth_check.py`,
   `turn_sweep.py`, `tour_capture.py`/`tour_watch.py`/`tour_run.py`/
   `practice_chart.py` all speak the retired numeric
   `RUN:<n>`/`TLM:`/`DIAG` vocabulary that current firmware's
   named-verb dispatch does not answer (`tour_capture.py`'s bare
   `RUN:{run}` would silently no-op against the deployed `test.ts`
   build, per ticket 010's confirmation) — worth a CLASI issue.

**Behaviour-neutral sprint — what this proves and what it does not:**

- The host suite staying at 528 is **necessary but not sufficient**:
  most files this sprint touched (`shims.cpp`, `main.ts`, `protocol.*`,
  `serial_transport.*`/`radio_transport.*`, `nezha_port.*`,
  `otos_port.*`) are outside the C++11 syntax gate and reached by no
  host test at all (see each ticket's own "C++11 gate coverage"
  section — 005, 006, 007, 008 all state this explicitly). The two
  real builds above (`test.ts` and `testrig.ts`, both compiling every
  touched `.cpp` clean) are the other half of the evidence, and the
  only evidence for those files in this sprint.
- **No robot was flashed and no hardware validation was performed** as
  part of this sprint's completion. Both hexes above are unflashed,
  untested-on-hardware build artifacts only.
- Worth recording for whoever reads this next: across eleven tickets,
  blind application of the comment work order would have introduced
  wrong information at least six times (ticket 005's TX-only/no-RX-
  listener false claim and stale kMaxPayloadBytes-already-fixed no-op;
  ticket 007's `nezha_port.h` R7 correction that would have clipped a
  load-bearing sentence; ticket 009's stale "wire_handler/wire_adapter/
  motion_engine don't exist yet" README claim and the settle-loop
  README text superseded by sprint 008 ticket 004; ticket 010's stale
  `otos_levercal.py`/`rotation_check.py` audit items already fixed by
  sprint 005) — the audit's verdicts were anchored to a code state five
  merged sprints out of date. Ticket 011 encoded that lesson into
  `docs/code-review/guidelines.md`.

**Design docs**: none edited by this ticket (comment-only fixes in
`.h`/`.cpp`/`.py` source files; no `docs/design/*` or `*/DESIGN.md`
touched). Nothing found this ticket that needs a design-doc update.

## C++11 gate coverage

This ticket **is** the coverage for everything the syntax gate misses
— it is the terminal check, not a gated file itself.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite).
- **New tests to write**: none.
- **Verification command**: `uv run pytest && uv run python tools/make_deploy.py`
