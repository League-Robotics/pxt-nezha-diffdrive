---
id: '007'
title: 'Final build checkpoint: hex and block-surface parity, flashable hex, handoff
  notes'
status: exception
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

- [ ] A real, final build (all six new modules, `main.ts` gone)
      succeeds via the project's existing `tools/make_deploy.py` /
      scratch-build workflow.
- [ ] Resulting `.hex` compared against ticket 001's archived
      pre-split baseline; outcome (byte-identical, or the specific
      differences found and why they're judged harmless) stated
      explicitly in this ticket's completion notes — not asserted, not
      omitted.
- [ ] Generated block-surface listing (captions, `group=` values,
      parameter ranges, toolbox order) compared against ticket 001's
      archived baseline listing; any difference is a finding this
      ticket must explain or treat as a sprint-blocking regression, not
      wave through.
- [ ] `test/test.ts` and `test/testrig.ts` simulator runs match the
      baseline exactly.
- [ ] Full `tests/host/` suite passes (regression fence).
- [ ] `test_pxt_manifest_completeness.py` passes.
- [ ] A flashable `.hex` is produced and named as this sprint's
      handoff artifact; **not flashed or run on hardware as part of
      this ticket's acceptance** — that's out of scope here (sprint
      011's job).
- [ ] Handoff notes written per the Description's item 5, including an
      explicit statement of whether the cross-file non-exported-
      reference question (overlay §15's central Open Question) needed
      its export fallback anywhere, and if so, exactly which symbols.
- [ ] No acceptance criterion above requires a robot.

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
- **New tests to write**: none.
- **Verification command**: real PXT build via
  `tools/make_deploy.py` (or equivalent); `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`;
  manual hex/block-surface diff against ticket 001's archived
  baseline.
