---
id: "002"
title: "motion/ and core/ boil-down and factual fixes"
status: open
use-cases: [SUC-001]
depends-on: ["001"]
github-issue: ""
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# motion/ and core/ boil-down and factual fixes

## Description

Comment text only in `src/motion/` and `src/core/`. **No behaviour
change** — no signature, no control flow, no constant, no `//%` pragma.

### Files this ticket owns (no other ticket touches them)

- `src/motion/motion_engine.h` (ratio **4.75**, 508 comment / 107 code)
- `src/motion/motion_engine.cpp` (0.75)
- `src/motion/velocity_shaper.h` (2.15), `src/motion/segment.h` (1.38),
  `src/motion/motion_limits.h` (1.26), `src/motion/odometry.h` (1.33)
  — secondary scope, see "High-ratio files not in the annex"
- `src/core/heading_wrap.h` (4.00), `src/core/fiber_identity.h` (4.14),
  `src/core/bus_guard.h` (4.00), `src/core/motion_owner.h` (3.67),
  `src/core/encoder_glitch_armor.h` (2.84)
- `src/core/diffdrive.h`, `src/core/diffdrive.cpp` — **line 1 only**,
  see the naming fix below. Vendored kernel; nothing else in these two
  files is in scope for any ticket in this sprint.

### Rules of engagement (binding, every item)

- **Re-anchor by quoted content, never by line number.** Every line
  number in the review and its annexes is stale; `motion/` was rewritten
  by sprint 031 and `motion_engine.h` is now 673 lines, not the ~750 the
  annex measured.
- **A replacement whose premise changed is a recorded no-op, never
  forced.** Write it in the completion notes with the reason.
- **`.claude/rules/measurement-citations.md`**: a boil-down must not
  delete the artifact path from a `MEASURED` claim. The board, the date
  and the capture/log path survive the cut; the narrative around them is
  what goes. A boiled-down `MEASURED` line with no artifact left in it
  is a regression.
- **`.claude/rules/no-units-in-identifiers.md`**: units live in trailing
  `// [unit]` comments. **This sprint renames nothing** — CH-04 is
  triage #24 and the motion-profile design's ticket 3, both out of
  scope. Never delete a trailing `// [mm]` / `// [counts/s]` to lower a
  ratio; ticket 001's counting rule does not count them anyway.

### Boil-down items (motion-and-kernel annex —
`docs/code-review/2026-09-02/raw/motion-and-kernel.md`, "Boil-down list")

Verified live at planning time. Replacement text is in the annex row
unless noted.

| annex # | anchor (quoted content, current file) | status |
|---|---|---|
| 1 | `motion_engine.h`'s leading block, from `// motion_engine.h -- diffDrive::MotionEngine: the two-primitive reduction` down to the end of the `SPRINT 029 ("motion profile unification"...)` narrative — **72 lines today**, not the annex's 120 | LIVE, reduced. Target ~10 lines: the two primitives, the canonical spec pointer (`radio-robot-lib/docs/design/motion-api.md` §2/§2.1), the CCW-positive sign convention and `b = trackWidth/rotationalSlip`, and the host-portability constraint (which is real and load-bearing — `tests/host/` depends on it). Drop the sprint-029 narrative. |
| 2 | the `settleToRest()` block containing `settleToRest()'s own bound/threshold (sprint 008 ticket 004` and `byte-for-byte shims.cpp's former loop cap and its former local` | LIVE. Use the annex's replacement; **keep** the measured claim and its commit reference. |
| 3 | `// REPLACES 1.040, which came from a single camera pivot on 2026-08-19` and the lines under it | LIVE. Keep the derivation above it (it explains why 0.915 is not the slip — that is exactly the kind of thing a comment must say); delete the `REPLACES 1.040` paragraph. |
| 4 | the seven per-knob blocks near the end of `motion_engine.h`, including the `0.8102 * (1 - 0.027608) = 0.7878` arithmetic | LIVE, reduced. One paragraph per knob: unit, what 0 means, the one measured number **with its artifact path**. |
| 5 | in `motion_engine.cpp`, the `6.4: the pivot->straight handoff goes through rest.` block (~14 lines) | LIVE at reduced scope — 031 already cut the two essays the annex names. Trim to ~5 lines: what the flag waits for, and that the twist reference disarms only on a neutral step. |
| 6 | the twist-hold handoff essay the annex places at `motion_engine.cpp:806-836` | **MOOT** — the file is 575 lines and the essay is gone (031). Record as a no-op; do not invent a substitute. |
| 7 | the yaw-axis shaped-mode history with the `800/400/100` sweep | **MOOT** — no such text in `motion_engine.cpp` (031 replaced shaped mode). Record as a no-op. |
| 18b | `core/heading_wrap.h`'s 21-line header over a 6-line body, containing `sprint 006 ticket 004` and the `otos_port.h includes pxt.h unconditionally` layering paragraph | LIVE. Target ~6 lines: contract, unit, wrap convention, and why it is a separate host-portable file. |

(Annex item 18's other half, `platform/encoder_pose_source.h`, is
**moot** — the file was deleted in sprint 033. Record it.)

### Factual fixes

1. **`src/core/diffdrive.h` line 1 and `src/core/diffdrive.cpp` line 1
   self-name the wrong files.** They read `// differential_drive.h — ...`
   and `// differential_drive.cpp — ...`; the files are
   `diffdrive.{h,cpp}` (the `.cpp`'s own `#include "diffdrive.h"` proves
   it). Also in the `.h`, the clause `ONE class, TWO files (this header
   + differential_drive.cpp)` names **this tree's** sibling and is wrong
   the same way.

   **Change only the self-naming words.** Do **not** touch
   `Vendored from League-Robotics/radio-robot ... src/firm/diffdrive/
   differential_drive.cpp` in either file, nor `src/DESIGN.md`'s or
   `docs/design/specification.md`'s references to that path: those name
   the **upstream** file correctly. The header already declares the
   local divergence policy ("namespace/include changes only"), and
   correcting a self-name is within it — but say so in the completion
   notes, since this is the only vendored-kernel edit in the sprint.

2. **`motion_engine.h`'s header claims both call paths arrive "via the
   same forwards".** The clause reads `the TypeScript block API
   (\`blocks/\`) via shims.cpp's engine* forwards, and the wire adapter
   (wire_adapter.cpp) via the same forwards`. Blocks reach
   `startMove()`/`engineGoToRArmed()`; the wire reaches `engineMoveX()`
   and friends — different forwards onto one implementation. Fix the
   clause while boiling item 1 down; the point worth keeping is *one
   implementation, two callers*.

### Factual errors to record as no-ops (verified already fixed or moot)

State each in the completion notes, naming the sprint. Do not "fix"
them; do not re-introduce the claim.

- `vMaxMmS_`/`brakeFrac_` "not consulted by anything yet" — **moot**,
  031 deleted the text.
- `goToWorld` is a "capped-curvature" path — **resolved**; no
  occurrence in `src/` or `docs/design/`.

### High-ratio files not in the annex (judgement pass)

`core/fiber_identity.h` (4.14), `core/bus_guard.h` (4.00),
`core/motion_owner.h` (3.67), `core/encoder_glitch_armor.h` (2.84),
`motion/velocity_shaper.h` (2.15). These are not on any annex list.
Apply the guidelines' write-time standard and cut what is clearly
archaeology (sprint/ticket narration, diff restatement,
justification-to-reviewer). **Do not cut a header whose length is
contract, unit, invariant and one measured fact** — a 29-line header
over a 7-line pure function can be entirely correct, and
`fiber_identity.h` and `bus_guard.h` document safety invariants that a
reader genuinely cannot recover from the code. Where you decide a file
stays as it is, say so in the completion notes; ticket 008 will record
its baseline unchanged.

### Capture citations in this ticket's files

`motion/segment.h` cites `captures/bench-acceptance-029-20260904d/`
(`lag-measure.log`). That directory is **fully tracked** (69 files) —
no action. Nothing else under `motion/` or `core/` cites `captures/`;
every citation the annex's CH-03 listed from `motion_engine.{h,cpp}`
was rewritten away by sprint 031.

## Acceptance Criteria

- [ ] Annex items 1, 2, 3, 4, 5 and 18b are applied, each re-anchored
      by quoted content.
- [ ] Annex items 6, 7 and 18a are recorded as no-ops with reasons.
- [ ] `src/core/diffdrive.h` and `src/core/diffdrive.cpp` name
      themselves correctly; the upstream `src/firm/diffdrive/
      differential_drive.cpp` provenance line is **unchanged** in both.
- [ ] `motion_engine.h` no longer claims blocks and the wire adapter
      arrive "via the same forwards".
- [ ] Every surviving `MEASURED` claim in the edited files still names
      its board, date and artifact path.
- [ ] No trailing `// [unit]` comment was deleted; no identifier was
      renamed.
- [ ] `motion_engine.h`'s ratio is materially below 4.75 and
      `heading_wrap.h`'s below 4.00; both recorded in the completion
      notes.
- [ ] Ticket 001's volume ratchet still passes (it must — ratios only
      go down here).
- [ ] No `//%` pragma and no line of code changed. `git diff --stat`
      shows only comment lines.

## Testing

Foreground only, never `run_in_background`.

- **Existing tests to run**:

      uv run pytest tests/host/test_archaeology_marker_budget.py \
                    tests/host/test_cxx11_syntax_gate.py \
                    tests/host/test_kernel_harness.py -q
      uv run pytest tests/host/ -k source_pin -q
      uv run pytest tests/host/ -q

  The C++ syntax gate and the kernel harness matter here: a mangled
  `/* */` delimiter or a stray `*/` inside an edited block turns a
  comment edit into a compile error, and these are the two host tests
  that actually compile `motion/` and `core/`.

- **New tests to write**: none. This ticket asserts nothing new; ticket
  001 already supplies the ratchet.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Sources for replacement text:
  `docs/code-review/2026-09-02/raw/motion-and-kernel.md`, section
  "Boil-down list (my scope; replacement text is the whole comment)",
  rows 1-7 and 18; and section "CH-02 — comments that are wrong today".
- Read `sprint.md`'s "Verification pass" section first — it records
  which annex rows are live, which are moot, and why.
- Do not run the full repo suite; the sprint's one full run is inside
  `close_sprint`.
