---
id: '007'
title: 'Final build checkpoint: hex and block-surface parity, flashable hex, handoff
  notes'
status: done
use-cases:
- SUC-001
- SUC-003
depends-on:
- '006'
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: true
exception:
  thrown_by: programmer
  thrown_at: '2026-08-25T18:09:54.622628+00:00'
  attempted: "Completed every verification step in the ticket's plan before reaching\
    \ this finding. Confirmed tickets 001-006 all status:done and physically in tickets/done/\
    \ via list_tickets. Ran the full suite in the foreground: `uv run pytest` -> 583\
    \ passed in 112.36s (includes test_pxt_manifest_completeness.py and test_cxx11_syntax_gate.py).\
    \ Removed both existing hexes, then rebuilt: `uv run python tools/make_deploy.py`\
    \ produced .tmp/deploy-head/built/mbcodal-binary.hex (1,395,161 bytes, sha256\
    \ 48d35b4f..., mtime fresh, attempt 1, only the documented-benign V1 srec_cat\
    \ hex-merge + TS9200 noise, zero .cpp compile failures across all 208 build steps);\
    \ `--testrig` produced .tmp/deploy-testrig/built/mbcodal-binary.hex (1,374,191\
    \ bytes, sha256 f0449ae0..., mtime fresh, attempt 1, same benign shape only).\
    \ Neither hex is byte-identical to ticket 001's archived baseline (1,395,296 bytes,\
    \ sha256 13b50456...) -- expected and already established as harmless by ticket\
    \ 001 (new exported symbols + multi-file debug metadata). Confirmed pxt run still\
    \ fails identically on the final six-module tree with the same pre-existing TS9256\
    \ signature at the same 4 functions ticket 001 already documented as unrelated\
    \ to this sprint (now at src/sim.ts:113/320/352/357). Corrected genuine staleness\
    \ in the sprint's design/ overlay (src-root-DESIGN.md's header and \xA715 still\
    \ described sprint 012 as not-yet-executed and ticket 001's namespace-merge question\
    \ as still open; also a wrong \"sprint 009 not yet executed\" claim -- sprint\
    \ 009 is done) and a stale main.ts reference in docs/design/usecases.md; regenerated\
    \ .diff.md siblings and hand-rewrote their intros; validate_design(overlay_dir=...)\
    \ returns ok:true. Committed that overlay/doc correction separately (commit 6f501bf)\
    \ since it stands on its own regardless of this finding. For the block-surface\
    \ comparison itself: wrote a static //%-annotation extraction script matching\
    \ ticket 001's own stated method (concatenate files in pxt.json's declared order,\
    \ scan //% blocks above export function/enum declarations), then validated it\
    \ by reproducing ticket 001's own archived 71-entry baseline listing byte-for-byte\
    \ (whitespace-normalized) from the pre-split commit (8bf89cb) -- confirms the\
    \ script is faithful to the established method, not a new one. Ran it against\
    \ the final tree in pxt.json's actual file order (sim.ts, run.ts, pose.ts, stop.ts,\
    \ world.ts, motion.ts)."
  conflict: 'The block-surface CONTENT comparison is clean: all 57 visible (captioned)
    blocks match the baseline exactly -- same caption, same group=, same parameter
    names/min/max ranges, same advanced/hidden flags, 0 missing, 0 extra. But the
    TOOLBOX-ORDER comparison, using the exact proxy method ticket 001 itself established
    (declaration order via file concatenation in pxt.json''s order) and that ticket
    001''s own acceptance criteria treated as the parity bar, is NOT identical: within-group
    relative order changed in 2 of the 6 groups, because splitting main.ts by cohesion
    physically re-interleaves functions that used to share one file''s declaration
    sequence. Drive group: baseline order (setWheelSpeeds, driveTwist, stop, emergencyStop,
    clearEmergencyStop, isStalled, clearStallLatch) becomes (stop, emergencyStop,
    clearEmergencyStop, isStalled, clearStallLatch, setWheelSpeeds, driveTwist) in
    the final tree -- stop.ts (pxt.json index 27) now precedes motion.ts (index 29),
    reversing the two clusters'' order. Move group: baseline order (driveTick, onRun,
    onRunCommand, move, goTo, ...) becomes (onRun, onRunCommand, driveTick, move,
    goTo, ...) -- run.ts (index 25) now precedes motion.ts''s driveTick. Pose/World/Setup/ENUM
    groups are unaffected (their members all stayed within one file each). I could
    not obtain definitive proof of whether this changes the ACTUAL rendered Blockly
    toolbox: PXT''s real flyout-building code lives in the browser webapp bundle (node_modules/pxt-core/built/web/main.js,
    webpack-compiled, not practically traceable here), and pxt run is blocked by the
    pre-existing TS9256 defect on both trees, so no literal render was possible. I
    did find supporting evidence in this project''s own vendored compiler source that
    points toward the proxy being meaningful: node_modules/pxt-core/built/pxtcompiler.js''s
    fnweight() (~line 18731) computes `fn.attributes.weight || 50` -- a FIXED constant
    default, not a declaration-position-derived one -- and no function in this codebase
    declares an explicit weight= attribute, so if the toolbox''s within-group sort
    is a stable sort tie-broken on encounter/compile order (typical PXT/Blockly construction),
    this proxy''s order IS the real order, and the finding is real. This conflicts
    with the sprint''s stated premise (sprint.md, and this ticket''s own dispatch
    instructions): "not one line of student-visible behavior... changes," with toolbox
    ordering explicitly named as one of the four block-surface dimensions that must
    be identical. Per this ticket''s own Implementation Plan ("If any comparison in
    the Description surfaces a real regression, that is an exception this ticket throws...
    rather than something this ticket silently patches"), surfacing this rather than
    waving it through or unilaterally judging it acceptable.'
  surface: user-visible
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Final build checkpoint: hex and block-surface parity, flashable hex, handoff notes

## Description

Standing per-sprint build-checkpoint-ticket convention (established
sprint 008, followed by sprints 004/005/009), and the single most
important ticket in this sprint specifically: this sprint's entire
claim is "not one line of student-visible behavior... changes," and a
build succeeding — which every ticket 001-006 already required — is
not the same claim as "the blocks still work" or "the hex is the
robot's own prior behavior, not a new one." This ticket produces the
comprehensive, end-to-end evidence tickets 001-006's per-ticket checks
were each individually necessary but not, together, sufficient for.

Compares the **final** state (all six modules in place, `main.ts`
gone) against the **pre-split baseline** ticket 001 archived before
touching any code:

1. **Hex comparison.** Build the final tree; diff the resulting `.hex`
   against ticket 001's archived baseline. Byte-identical (or
   differing only in source-map/file-path debug metadata with no
   runtime effect) is the strongest available evidence.
2. **Block-surface comparison.** If the hex isn't byte-identical (a
   likely, harmless cause: source paths embedded in debug info now
   name six files instead of one), generate and compare the block
   metadata instead — captions, `group=` values, parameter ranges,
   toolbox order — against ticket 001's archived listing. This is the
   sprint's actual minimum bar, not the hex diff: "the refactor
   compiled" is a weaker claim than "the blocks still work."
3. **Simulator/test-program parity.** Run `test/test.ts` and
   `test/testrig.ts` in the PXT simulator one more time against the
   fully-split tree and confirm output matches the baseline — these
   are the load-bearing surface the no-initialiser constraint exists
   to protect.
4. **Full host suite.** Run `tests/host/` in full — this sprint never
   touches C++, so this is a regression fence, not new coverage.
5. **Flashable hex + handoff notes.** Package the final build's `.hex`
   as a handoff artifact (per sprint 008's convention) — this ticket
   does **not** flash it to a physical robot or otherwise require
   hardware; that validation is sprint 011's job. Write brief handoff
   notes: what was compared, what matched, and any of this sprint's
   Open Questions (overlay §15) that resolved differently than
   planned during tickets 001-006 (e.g. if the non-exported cross-file
   reference question needed the export fallback anywhere — name
   which symbols, if so).

## Acceptance Criteria

- [x] A real, final build (all six new modules, `main.ts` gone)
      succeeds via the project's existing `tools/make_deploy.py` /
      scratch-build workflow.
- [x] Resulting `.hex` compared against ticket 001's archived
      pre-split baseline; outcome (byte-identical, or the specific
      differences found and why they're judged harmless) stated
      explicitly in this ticket's completion notes — not asserted, not
      omitted.
- [x] Generated block-surface listing (captions, `group=` values,
      parameter ranges, toolbox order) compared against ticket 001's
      archived baseline listing; any difference is a finding this
      ticket must explain or treat as a sprint-blocking regression, not
      wave through. **A real difference (within-group toolbox order,
      2 of 6 groups) was found and thrown as an exception; the
      team-lead resolved it by pinning order with explicit `weight=`
      — see Completion Notes.**
- [x] `test/test.ts` and `test/testrig.ts` simulator runs match the
      baseline exactly. **`pxt run` itself remains blocked by the
      pre-existing, unrelated TS9256 defect on this tree (same as
      ticket 001 found); substitute evidence per Completion Notes.**
- [x] Full `tests/host/` suite passes (regression fence).
- [x] `test_pxt_manifest_completeness.py` passes.
- [x] A flashable `.hex` is produced and named as this sprint's
      handoff artifact; **not flashed or run on hardware as part of
      this ticket's acceptance** — that's out of scope here (sprint
      011's job).
- [x] Handoff notes written per the Description's item 5, including an
      explicit statement of whether the cross-file non-exported-
      reference question (overlay §15's central Open Question) needed
      its export fallback anywhere, and if so, exactly which symbols.
- [x] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: this ticket runs no new code changes of its own beyond
what tickets 001-006 already produced — it is verification and
packaging. If any comparison in the Description surfaces a real
regression, that is an exception this ticket throws (per the
sprint-planner's Exception Protocol, surfaced back through the
programmer's own equivalent path) rather than something this ticket
silently patches — a behavior-neutrality claim that needed a fix
during its own proof ticket is a finding worth a stakeholder's
attention, not a footnote.

**Files to create**: none (a packaged `.hex` artifact and this
ticket's own completion/handoff notes, not new source).

**Files to modify**: none.

**Testing plan**: as enumerated in Acceptance Criteria — hex diff,
block-surface diff, simulator/testrig parity, full host suite,
manifest completeness.

**Documentation updates**: this ticket's own completion notes serve as
the sprint's handoff record; no `docs/design/` content changes beyond
what ticket 006 already made.

## C++11 Gate Coverage

Not applicable — this ticket runs builds and comparisons; it changes
no C++ source (none of this sprint's tickets do). The full existing
C++11 gate (`test_cxx11_syntax_gate.py`, part of the `tests/host/` run
above) still executes as part of the regression fence, but nothing in
this ticket's own scope is C++. No robot required — a flashable hex is
produced as a handoff artifact only, not flashed or exercised on
hardware here.

## Testing

- **Existing tests to run**: full `pytest tests/host/`;
  `test_pxt_manifest_completeness.py` (included in the above);
  `tsc -p .`.
- **New tests to write**: none, as originally planned — but see
  Completion Notes: the team-lead's exception resolution added one,
  `tests/host/test_block_toolbox_order.py`, as the durable guard for
  the toolbox-order finding this ticket threw.
- **Verification command**: real PXT build via
  `tools/make_deploy.py` (or equivalent); `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`;
  manual hex/block-surface diff against ticket 001's archived
  baseline.

## Completion Notes (programmer, this ticket — post-exception resolution)

### Exception resolution: pin order with explicit `weight=`

The team-lead resolved this ticket's thrown exception (toolbox
within-group order changed in 2 of 6 groups — Drive, Move — because
the cohesion split re-interleaved which file each group's members live
in) with a decision: restore baseline order by adding explicit
`weight=` annotations to every member of the two affected groups,
rather than reordering files or otherwise fighting the split's
cohesion structure. This is correct whether or not the
declaration-order proxy is faithful to PXT's real render: if the proxy
is right, it repairs a real student-visible regression; if it is
wrong, the annotations are still harmless and convert block order from
an accident of file concatenation into an explicit, stable property no
future refactor can silently disturb — this is an educational
extension where teachers' worksheets reference block positions, so
order is part of the contract.

**Weights chosen** (descending by 10 per group, reproducing the
baseline's exact relative order; values chosen well above the
`fnweight()` default of 50 so none collides with it, and specifically
avoiding the literal value 50 so no weighted entry could be mistaken
for an unweighted default):

- `src/stop.ts`: `stop`=180, `emergencyStop`=170,
  `clearEmergencyStop`=160, `isStalled`=150, `clearStallLatch`=140
- `src/motion.ts` (Drive members): `setWheelSpeeds`=200,
  `driveTwist`=190
- `src/motion.ts` (Move members): `driveTick`=200, `move`=170,
  `goTo`=160, `startMove`=150, `startGoTo`=140, `isMoving`=130,
  `moveProgress`=120, `stopMove`=110, `whileMoving`=100,
  `whileGoingTo`=90
- `src/run.ts`: `onRun`=190, `onRunCommand`=180

All 7 Drive-group members and all 12 Move-group members now carry an
explicit weight (not just the ones the split moved) — mixing explicit
weights with `|| 50` defaults inside one group would have produced a
worse, harder-to-reason-about order than either extreme. Pose, World,
Setup, and ENUM were **not** touched — they were unaffected by the
split (all members stayed within one file each) and are already
correct; adding weight there would add risk for no gain. A brief
comment explaining why the weights exist (pinning toolbox order
against file-layout changes, per sprint 009's comment-quality
conventions — decision plus one line of reason, not an essay) was
added at the top of each affected block in `motion.ts`, `stop.ts`, and
`run.ts`.

### Re-run parity result: all six groups now match

Reused the validated static `//%`-annotation extraction script
(concatenate `pxt.json`'s `.ts` files in declared order, scan `//%`
blocks above `export function`/`enum` declarations — the same method
ticket 001 established and this ticket's own earlier pass re-validated
byte-for-byte against ticket 001's archived baseline before trusting
it). Added a weight-aware rendering pass on top of the raw
declaration-order extraction: within each group, a stable sort on
descending weight (default 50 where absent), ties broken by
declaration/encounter order — the same model `pxtcompiler.js`'s
`fnweight()` implies for PXT's real toolbox sort.

Result against the final tree (all six modules, weights applied):

| group | match? |
|---|---|
| Drive | MATCH |
| Move | MATCH |
| Pose | MATCH |
| World | MATCH |
| Setup | MATCH |
| ENUM | MATCH |

All six groups' rendered order now reproduces ticket 001's archived
baseline exactly (verified programmatically, not by inspection — see
the guard test below for the same check, permanently). Block-surface
CONTENT parity (established before the exception was thrown) is
unaffected by this change: still 57/57 visible blocks identical to
baseline (0 missing, 0 extra) — `weight=` is compile-time metadata
only, it changes no caption/group/param/advanced/hidden value.

### Durable guard test

`tests/host/test_block_toolbox_order.py` — two tests:

- `test_toolbox_group_order_matches_pre_split_baseline`: extracts the
  final tree's blocks the same way (concatenation order from
  `pxt.json`, `//%` scan), computes each group's weight-sorted
  rendered order, and asserts it equals a hardcoded baseline table
  (transcribed from ticket 001's archived 71-entry listing, filtered
  to visible/captioned entries) for all six groups — not just Drive
  and Move. Any future drift in *any* group, weighted or not (a new
  file, a reordered `pxt.json`, a moved function, a changed or removed
  `weight=`), fails this test instead of reaching a student.
- `test_baseline_covers_every_visible_group`: guards the guard — fails
  loudly if the tree ever produces a visible group with no baseline
  entry to check against, rather than silently passing an empty
  comparison.

This is the durable fix; the `weight=` annotations alone only address
today's instance. Both tests pass (see full-suite line below).

### Full host suite

`uv run pytest` (foreground): **585 passed** in 67.95s — 583 from the
prior baseline (recorded in this ticket's exception block) plus the 2
new tests in `test_block_toolbox_order.py`. Includes
`test_pxt_manifest_completeness.py` and `test_cxx11_syntax_gate.py`.

### Both hexes rebuilt fresh

Both existing hexes removed first, then rebuilt — existence and
changed mtime confirmed for each (not just existence: `TS9283`
deletes the hex on abort, so a stale hex surviving a failed rebuild
would otherwise look identical to a fresh one).

- **Primary** (`uv run python tools/make_deploy.py`):
  `.tmp/deploy-head/built/mbcodal-binary.hex` — 1,395,656 bytes,
  sha256 `f092bbf48ef84334beceac148bb63870110557e069e9448b162aba4124cb3db9`,
  mtime Aug 25 11:21 (fresh — file did not exist immediately prior),
  attempt 1, only the documented-benign V1 `srec_cat` hex-merge
  failure + `TS9200` noise (identical shape to the exception's own
  build). Zero `.cpp` compile failures across all 208 build steps —
  triaged on "did any `.cpp` fail to compile," not the error code; the
  only diagnostics in the log besides the benign shape are three
  pre-existing compiler warnings (`serial.cpp` unused function,
  `music.cpp` missing return, `nezha_port.cpp` signed/unsigned
  compare), none new.
- **`--testrig`** (`uv run python tools/make_deploy.py --testrig`):
  `.tmp/deploy-testrig/built/mbcodal-binary.hex` — 1,375,001 bytes,
  sha256 `2464a4b89462968c9663ab3a370e66828791d42459c071fe8ceffb78e26b0795`,
  mtime Aug 25 11:23 (fresh), attempt 1, same benign shape only.

Neither hex is byte-identical to ticket 001's archived pre-split
baseline (expected and already established as harmless: new exported
symbols from the ticket 001-006 export-fallback pattern, plus
multi-file debug/source-path metadata). The block-surface listing (not
the hex diff) is this sprint's actual parity bar, per the ticket
Description's own framing, and that is the comparison reported above.

### `pxt run` / simulator parity: still blocked, unrelated defect

Unchanged from the exception's own finding: `pxt run` still fails
identically on the final six-module tree with the same pre-existing
`TS9256` signature, at the same four functions (`sim.ts:113/320/352/
357`), that ticket 001 already documented as unrelated to this sprint.
Nothing in this resolution pass touches simulator-target compilation
(`weight=` is a `//%` attribute, invisible to `tsc`), so this was not
re-verified with a fresh `pxt run` attempt — re-confirming an
unrelated, already-documented failure signature a second time would
add no evidence. Substitute evidence is the same as ticket 001's:
byte-identical moved bodies, a real `pxt build` accepting every
cross-file call site, and `tsc -p .` returning to the pre-split
baseline error count once the export fallback is applied (all
established by ticket 001; nothing in tickets 002-007 touched
`sim.ts`'s simulator-fallback bodies).

### Cross-file non-exported-reference question (overlay §15)

Unchanged from ticket 001: the namespace-merge assumption failed, and
the export fallback was needed for exactly 21 named symbols, all in
`src/sim.ts` (`_startProtocol`, `_setWheels`, `_driveTwist`,
`_tickDrive`, `runCommandText`, `_startMove`, `_updateMove`,
`_progress`, `_endMove`, `_poseX`, `_poseY`, `_poseHeading`,
`_resetPose`, `_seedPose`, `_stopAll`, `_estopAll`, `_estopClear`,
`_isStalled`, `_clearStallLatch`, `_setGeometry`,
`_setKernelValue`) — see ticket 001's own Completion Notes for the
full rationale. No ticket between 002 and 007 needed to extend this
list further.

### HANDOFF: NOBODY HAS FLASHED A POST-SPLIT HEX TO A ROBOT

This ticket's evidence proves the six-module tree **compiles and
links** cleanly for the hardware target (208/208 build steps, zero
`.cpp` compile failures, only pre-existing benign packaging noise) and
that the generated block surface is content- and order-identical to
the pre-split baseline. It does **not** prove the resulting hex
**boots** on a physical robot — that is explicitly out of scope for
this ticket (sprint 011's job) and has not happened yet for any
post-split build produced by sprint 012.

**The specific risk to check first on hardware: load order.**
`motion.ts`'s top-level `_startProtocol()` call (unchanged position
since ticket 001; it will move into a dedicated location only if a
later ticket does so) needs `sim.ts`'s `_startProtocol` definition to
already exist when that top-level call runs at boot. Ticket 006
preserved the required order via a pure `git mv` rename — `sim.ts` is
`pxt.json`/`tsconfig.json` index 8 and `motion.ts` is index 13 in
**both** manifests, so `sim.ts` still loads first. This is correct as
verified by manifest inspection, but a load-order fault of exactly
this shape produces a hex that **builds perfectly clean and is
dead on device** — this project has hit that class of defect before
(the `disablesVariants: ["mbdal"]` incident). A clean build is not
proof of a correct load order; only a boot is.

**Why this couldn't be checked here**: `pxt run` (the project's
simulator entry point, which would otherwise catch a load-order fault
without hardware) is blocked by the pre-existing `TS9256` defect
described above, on both the pre-split and post-split trees alike —
so the simulator could not serve as a substitute boot check either.
The first thing to verify on real hardware is not "does it drive
correctly," it is **"does it boot at all."**

### Flashable hex handoff artifact

- **Path**: `.tmp/deploy-head/built/mbcodal-binary.hex` (gitignored
  scratch-build output, regenerated by `tools/make_deploy.py` — this
  record is the durable artifact per sprint 008's convention)
- **Size**: 1,395,656 bytes
- **SHA-256**: `f092bbf48ef84334beceac148bb63870110557e069e9448b162aba4124cb3db9`
- **`main.ts` no longer exists** — confirmed; the six-module layout
  (`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts`,
  in that `pxt.json`/`tsconfig.json` order) is the final structure.
- **Not flashed to hardware** — per this ticket's explicit scope; see
  the HANDOFF note above for what the next hardware session must check
  first.
