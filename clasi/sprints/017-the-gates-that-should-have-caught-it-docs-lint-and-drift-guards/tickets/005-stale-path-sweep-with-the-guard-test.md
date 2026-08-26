---
id: '005'
title: Stale-path sweep WITH the guard test
status: open
use-cases: [SUC-002]
depends-on: []
github-issue: ''
issue: stale-paths-survived-the-sprint-013-sweep.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Stale-path sweep WITH the guard test

## Description

Sprint 013 ticket 006 was scoped as "final sweep -- DESIGN.md, doc/tool
prose, repo-wide stale-path verification," and 40+ stale references
survived it anyway. This ticket redoes the sweep and, this time, pairs it
with a mechanical guard so it can't silently regress again -- fixing
without guarding is explicitly incomplete for this sprint.

**Fix the guard first, then use it to drive the fix list** -- writing the
test before the cleanup means the fix list is whatever the test reports,
not a hand-curated list that might miss something.

### Known offenders (from the 2026-08-26 review; re-verify against current
tree since sprint 015/016 may have moved things further)

**16 `main.ts` references in live source** -- `main.ts` was retired in
sprint 012:
`shims.cpp` (x5: comments at roughly lines 143, 389, 742, 745, 1035),
`comms/protocol.h` (x2: ~100, 234), `comms/protocol.cpp` (x3: ~61, 63,
374), `comms/wire_adapter.cpp` (x2: ~91, 96), `motion/motion_engine.h`
(x2: ~13, 70), `motion/motion_engine.cpp` (~229), `blocks/sim.ts` (~162),
plus `tools/tour_square.py:5`. `protocol.cpp:374` is the one most likely
to cost someone real debugging time -- it claims `startProtocol()` is
"called once from a top-level statement in main.ts's `diffDrive`
namespace"; the actual call is in `src/blocks/motion.ts:66`.

**23 more `main.ts` references in `src/DESIGN.md`** -- these may
substantially overlap with or be subsumed by ticket 004's S12-S16 removal
(S15 in particular is about the `main.ts` split and is full of `main.ts`
references that become moot once that section is deleted). **Coordinate
with ticket 004**: if this ticket runs after 004, re-count `main.ts`
references in `src/DESIGN.md` first -- most may already be gone. If
several remain in S1-S11, fix those directly.

**6 pre-sprint-013 include paths in live headers**:

| File:line | Says | Is |
|---|---|---|
| `motion/motion_engine.h:135, :148` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `platform/encoder_pose_source.h:10` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `comms/wire_handler.h:144, :168` | `src/wire_adapter.cpp` | `src/comms/wire_adapter.cpp` |
| `comms/wire_handler.h:276` | `src/wire_adapter.h` | `src/comms/wire_adapter.h` |

Plus `tools/DESIGN.md:110` -> `src/heading_wrap.h` (should be
`src/core/heading_wrap.h`). These are comment-prose references to paths,
**not** actual `#include` directives -- do not confuse this with ticket
009's include-path work, which is about the compiler's actual `-I` search
behavior. This ticket only fixes what the comments *say*.

**5 comment references to functions that don't exist**: `formatDiag()`
(`comms/radio_transport.h:196, 240`; `comms/wire_adapter.cpp:163` --
the live defect, since it's asserted as a current cross-reference, not
flagged as historical), `parseLine()` (`comms/protocol.cpp:130`),
`sendDebug()` (`comms/wire_handler.cpp:1138`), `sendTelemetry()` and
`sendDeviceBanner()` (`comms/protocol.h:57`). These are historical/dangling
references -- either delete the reference or replace it with the current
equivalent if one exists (e.g. `formatDiag()` -> whatever function now
does that job, if any; otherwise just remove the dangling pointer).

## The guard: a host test that greps for dead `src/<path>` references

Add a test under `tests/host/`, modeled directly on
`test_pxt_manifest_completeness.py` (no compiler, reads files as text,
milliseconds): scan `src/` and `docs/` for text matching a `src/<path>`
pattern (e.g. `src/[\w/.-]+\.(h|cpp|ts)` or similar -- tune the regex to
catch real path references without false-positiving on prose that merely
contains the word "src"), and assert every matched path exists on disk
relative to the repo root. This is the single mechanical guard that would
have caught every finding in this ticket and in `design-doc-set-fails-
validation.md`'s D-07 finding.

Scope the regex carefully -- it needs to catch `src/otos_port.h` (wrong,
should be `src/platform/otos_port.h`) and `main.ts` bare references (no
`src/` prefix, since they're mid-sentence file mentions) without
false-positiving on things like `src/DESIGN.md` itself (which exists) or
code identifiers that happen to contain slashes. Decide explicitly whether
`main.ts` bare mentions (no path prefix) need their own pattern separate
from the `src/<path>` grep, since the issue's two categories (stale
`src/<path>` includes vs. bare `main.ts` mentions) are structurally
different checks. It's fine to implement them as two assertions in one
test file if that's cleaner than one regex trying to do both jobs.

The function-name-reference class (`formatDiag()` etc.) is a different
kind of check (identifier existence, not path existence) -- a stretch
goal if time allows, but the ticket's must-have guard is the path check;
call out in the ticket's completion notes if the function-reference check
was or wasn't added, so it's not silently assumed done.

## Acceptance Criteria

- [ ] Zero `main.ts` references remain in live source (`src/**/*.{h,cpp,ts}`,
      `tools/*.py`) except inside a deliberately-kept historical section, if
      any survives ticket 004's cleanup.
- [ ] The 6 pre-013 include-path comment references are corrected.
- [ ] The 5 dangling function-name references are corrected or removed.
- [ ] A new host test under `tests/host/` greps `src/` and `docs/` for
      `src/<path>` references and fails if any named path doesn't exist on
      disk. It passes against the corrected tree.
- [ ] The new test is added to the suite `close-sprint`/CI would run (no
      special exclusion).
- [ ] No firmware behavior is changed -- only comments, doc prose, and the
      new test file.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full host suite,
  since this ticket touches comments across many `src/` files and a
  compile-affecting typo in a comment edit, while unlikely, is worth
  catching) and `uv run pytest tests/tools/test_tour_square.py` or
  equivalent if `tour_square.py` has its own tests.
- **New tests to write**: the stale-path guard test described above --
  name it something like `tests/host/test_no_stale_src_paths.py`.
- **Verification command**: `uv run pytest tests/host/`.
