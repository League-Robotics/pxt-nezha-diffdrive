---
id: "008"
title: "Build checkpoint: confirm a flashable hex from the sprint's final combined state"
status: open
use-cases: [SUC-001, SUC-002, SUC-003, SUC-004]
depends-on: ["005", "006", "007"]
github-issue: ""
issue: ""
# completes_issue: Controls whether linked issues are archived when this ticket
# is moved to done. Default: true (archive when all referencing tickets are done).
# Set to false (scalar) to suppress archival for ALL linked issues on this ticket.
# Set to a mapping {filename.md: false} to suppress archival per issue filename.
# Use false for tickets that partially address a multi-sprint umbrella issue.
completes_issue: true
# exception: Written by a lower agent when it cannot proceed (see architecture §exception-protocol).
# exception:
#   thrown_by: "programmer"          # "programmer" | "sprint-planner"
#   thrown_at: "2026-05-07T14:23:00Z"
#   attempted: |
#     Description of what was attempted before giving up.
#   conflict: "architecture-update.md §3 — reason the agent is blocked"
#   surface: "internal"              # "user-visible" | "internal"
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: confirm a flashable hex from the sprint's final combined state

## Description

The mandatory, always-last build-checkpoint ticket, per the standing
convention in `docs/design/design.md`'s "Host-vs-target language
standard" section and `src/DESIGN.md` §11: this sprint touches
build-eligible source (`src/core/`, `src/motion/`, `src/shims.cpp`,
`src/comms/`, `src/blocks/`) across seven prior tickets at
`-std=c++11`-vs-`-std=c++20` risk (the host suite compiles at C++20;
both real targets compile at C++11), so a green host suite alone is
never evidence the sprint's final state actually compiles for the
robot. Depends on every ticket that touches `src/` or `test/test.ts`
(001-004 transitively through 007; 005 and 006 are the two remaining
independent branches).

Run `tools/make_deploy.py` against this sprint's own final combined
state (all eight tickets' changes merged, not a single ticket's diff in
isolation) and confirm a flashable hex results, using the triage
`build()` already implements (`tools/DESIGN.md`'s "Build checkpoint
triage" section): hard compile failures reported immediately; the
documented benign packaging-abort shape retried once automatically;
anything else reported as a failure requiring investigation, not
silently retried.

## Acceptance Criteria

- [ ] `uv run python tools/make_deploy.py` (default `--robot vevov`,
      or the robot this sprint's bench acceptance ticket used) produces
      a `built/binary.hex` that passes all of `build()`'s existing
      checks: zero universal-hex block-start markers, size at or above
      `MIN_HEX_SIZE_BYTES`, all ten `nezha-diffdrive` `.cpp` files
      present as `Building CXX object` lines.
- [ ] If the first attempt hits the documented benign packaging-abort
      shape, the automatic retry succeeds; if it hits a hard compile
      failure, that failure is fixed (not worked around) before this
      ticket is marked done — a compile error at this stage means an
      earlier ticket's change does not actually build for the target,
      which is exactly the gap this ticket exists to catch.
- [ ] The resulting hex is confirmed flashable (bench-flash it, or note
      why a flash confirmation wasn't performed this session).
- [ ] This ticket's own test run is the **full** test suite (host +
      tools), not a scoped subset — `.claude/rules/source-code.md`
      reserves the full-suite run for `close_sprint` itself, but this
      ticket's build check is a distinct, additional gate `close_sprint`
      does not perform on its own.

## Implementation Plan

**Approach**: Run the build against the sprint branch's own tip
(after ticket 007 lands), not a synthetic combination — this is
specifically checking what will actually merge.

**Files to create/modify**: None expected (this ticket verifies, it
does not implement) — unless the build surfaces a real defect, in
which case fix it in the file(s) it names, per the triage's own hard-
failure guidance (`tools/DESIGN.md`).

**Testing plan**: `uv run python tools/make_deploy.py`; read the
triage verdict; if `UNKNOWN`/`HARD_FAILURE`, investigate per
`tools/DESIGN.md`'s "Build checkpoint triage" section before retrying
by hand.

**Documentation updates**: None expected, unless a real defect is found
and fixed, in which case document the fix the same way any other
ticket would.
