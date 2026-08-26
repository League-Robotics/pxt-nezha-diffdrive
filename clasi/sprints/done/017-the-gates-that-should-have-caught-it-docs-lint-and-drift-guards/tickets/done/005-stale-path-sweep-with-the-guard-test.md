---
id: '005'
title: Stale-path sweep WITH the guard test
status: done
use-cases:
- SUC-002
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

- [x] Zero `main.ts` references remain in live source (`src/**/*.{h,cpp,ts}`,
      `tools/*.py`) except inside a deliberately-kept historical section, if
      any survives ticket 004's cleanup.
- [x] The 6 pre-013 include-path comment references are corrected.
- [x] The 5 dangling function-name references are corrected or removed.
- [x] A new host test under `tests/host/` greps `src/` and `docs/` for
      `src/<path>` references and fails if any named path doesn't exist on
      disk. It passes against the corrected tree.
- [x] The new test is added to the suite `close-sprint`/CI would run (no
      special exclusion).
- [x] No firmware behavior is changed -- only comments, doc prose, and the
      new test file.

## Completion notes (2026-08-26)

Re-measured against the current tree (post tickets 001-004) rather than
trusting the briefing's line numbers, per its own instruction.

- **`main.ts` in live source**: found 17 (briefing said "16"; the extra
  was `motion/motion_engine.cpp:255`, apparently missed in the original
  count) across `shims.cpp` (x5), `comms/protocol.h` (x2),
  `comms/protocol.cpp` (x3), `comms/wire_adapter.cpp` (x2),
  `motion/motion_engine.h` (x2), `motion/motion_engine.cpp` (x1),
  `blocks/sim.ts` (x1), `tools/tour_square.py` (x1). All corrected --
  most rewritten to name the current file (`blocks/motion.ts`,
  `blocks/run.ts`, `blocks/world.ts`, `blocks/stop.ts` as appropriate,
  confirmed by grepping each referenced symbol's actual current
  location rather than guessing); the two describing a specific
  historical event (a compiler-error report, a prior TS-side formula)
  were reworded to drop the literal `main.ts` token while keeping the
  historical fact intact.
- **`src/DESIGN.md`**: 5 `main.ts` mentions remain, all inside
  legitimately historical framing ("sprint 012: split from a single
  `main.ts`", "formerly `main.ts`'s") in sections 1 and 9 -- these
  describe the sprint-012 split in past tense and were left alone, per
  the ticket's own guidance to only fix S1-S11 mentions that are NOT
  already historical.
- **6 pre-013 include paths**: all 6 corrected as specified
  (`src/otos_port.h` -> `src/platform/otos_port.h` x3,
  `src/wire_adapter.{h,cpp}` -> `src/comms/wire_adapter.{h,cpp}` x3)
  plus `tools/DESIGN.md`'s `src/heading_wrap.h` ->
  `src/core/heading_wrap.h`.
- **5 dangling function references**: all corrected.
  `formatDiag()` (3 sites) -- the wire_adapter.cpp:163 site was the
  "live defect" the briefing called out (asserted as current); reworded
  to point at `probe()`, the actual current TS-facing diagValue()
  exposure, and to note the DIAG verb itself was retired (confirmed by
  grep: no `"DIAG"` string handler exists anywhere in `src/`, and
  `tools/tour_watch.py`'s own comment independently confirms "the
  firmware no longer emits that verb at all"). `parseLine()`,
  `sendDebug()`, `sendTelemetry()`/`sendDeviceBanner()` -- already
  framed as historical ("the old X"); the dangling names were dropped
  in favor of describing the pattern/role generically, per the
  ticket's "otherwise just remove the dangling pointer" guidance.
- **The guard**: `tests/host/test_no_stale_src_paths.py`, two
  assertions. (1) `src/<path>.{h,cpp,ts}` existence check across
  `src/`, `docs/`, `tools/` (including their `.md` files). (2) bare
  `main.ts` mention check, scoped to live source only
  (`src/**/*.{h,cpp,ts}`, `tools/*.py`) since `docs/**/*.md` may
  legitimately narrate the sprint-012 split historically -- verified
  this scoping choice is right by confirming `src/DESIGN.md`'s 5
  remaining mentions above are exactly that. Three false-positive
  shapes handled and documented in the test's own docstring: dated
  audit snapshots under `docs/code-review/<YYYY-MM-DD>/` (excluded by
  a directory-name-shaped regex, not a blanket exclusion --
  `docs/code-review/guidelines.md` itself, undated, stays in scope for
  ticket 006), two external-repo path prefixes (`src/firm/`, from the
  upstream `radio-robot` kernel repo; `src/protocol/`, from
  `radio-robot-lib`) that this project's own `src/` structurally never
  uses, and fenced (` ``` `) code blocks in markdown, stripped before
  scanning since an illustrative multi-line example isn't a claim of
  existence. Verified the guard actually catches regressions by
  injecting a temporary stale reference, confirming the test failed
  with the exact offending path and line, then reverting and
  re-confirming green.
- **Dangling-function-reference guard (stretch goal): attempted, not
  shipped.** Prototyped a comment-stripped-corpus version (name
  followed by `()` in a comment, with no matching `name(` anywhere in
  real code). Out of 240 distinct call-like names mentioned in
  comments across `src/` and `tools/`, only 5 had zero code
  occurrences -- but all 5 were false positives, each a different
  class: `poseX()/Y()/heading()` shorthand (regex catching mid-
  abbreviation `Y`, not a name), `uBit.init()` and
  `NRF52I2C::waitForStop()` (real CODAL/nrf52 platform API this repo
  doesn't define), `onXxx()` (a deliberate generic placeholder for
  "any of the six `onWheelsV()`-shaped handlers"), and this ticket's
  own reworded `formatDiag()` note (correctly past-tense, "was
  retired"). A workable allowlist would have to keep growing exactly
  when an engineer writes the kind of comment ticket 006's standard
  wants more of -- a measured hardware/vendor-API fact
  (`nezha_port.cpp`'s bus-hang guard citing
  `NRF52I2C::waitForStop()` is literally the keep-list example). Not
  shipped; the two checks above are.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full host suite,
  since this ticket touches comments across many `src/` files and a
  compile-affecting typo in a comment edit, while unlikely, is worth
  catching) and `uv run pytest tests/tools/test_tour_square.py` or
  equivalent if `tour_square.py` has its own tests.
- **New tests to write**: the stale-path guard test described above --
  name it something like `tests/host/test_no_stale_src_paths.py`.
- **Verification command**: `uv run pytest tests/host/`.
