---
id: '012'
title: Final build checkpoint (host suite + flashable hex)
status: open
use-cases: []
depends-on: ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011"]
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

- [ ] Full host suite passes: `uv run pytest` — re-confirm the current
      test count (the sprint charter's "424 tests" figure) and treat
      any change in that count as a signal something outside this
      sprint's comment-only scope happened; investigate before
      proceeding if the count differs unexpectedly.
- [ ] `tests/host/test_cxx11_syntax_gate.py` passes specifically (it's
      part of the full suite, but call it out — it's the gate covering
      `diffdrive.*`/`motion_engine.*`/`wire_handler.*`/`wire_adapter.*`
      plus the sprint-006 syntax-check TUs for `heading_wrap.h`/
      `encoder_glitch_armor.h`/`encoder_pose_source.h`).
- [ ] `uv run python tools/make_deploy.py` (or the project's documented
      equivalent) produces a flashable hex from a clean scratch build,
      using its triage-aware retry logic (sprint 008) to distinguish a
      real compile failure from the known-benign `TS9283`/`TS9043`/
      `TS9200` packaging aborts.
- [ ] The build succeeds without needing to revert or patch any file
      this sprint touched — if it fails, the fix happens in the
      offending ticket's own file (this checkpoint does not become a
      dumping ground for hasty fixes; if a real defect surfaces, throw
      an exception per this sprint's protocol rather than patching
      around it here).
- [ ] No acceptance criterion in this ticket, or any other ticket in
      this sprint, requires flashing a physical robot.
- [ ] Completion notes record: final test count, confirmation the hex
      built clean, and a one-line summary of the two follow-up filing
      requests this sprint's tickets raised (ticket 004's
      DIAG-has-no-v6-equivalent note, ticket 010's retired-wire-
      vocabulary handoff-2 class) for the team-lead to convert into
      CLASI issues.

## C++11 gate coverage

This ticket **is** the coverage for everything the syntax gate misses
— it is the terminal check, not a gated file itself.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite).
- **New tests to write**: none.
- **Verification command**: `uv run pytest && uv run python tools/make_deploy.py`
