---
id: "003"
title: "platform/ and shims.cpp boil-down and factual fixes"
status: open
use-cases: [SUC-001]
depends-on: ["001"]
github-issue: ""
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# platform/ and shims.cpp boil-down and factual fixes

## Description

Comment text only in `src/platform/` and `src/shims.cpp`. **No
behaviour change.** `src/shims.cpp` carries 37 `//%` PXT pragma lines
and `src/comms/protocol.cpp` another 4 — **do not disturb a single
one**; a mangled pragma is the one way a comment-only edit in this file
breaks a real firmware build.

### Files this ticket owns (no other ticket touches them)

- `src/shims.cpp` (ratio **1.71**, 1215 comment / 710 code — the
  largest single comment body in the tree)
- `src/platform/nezha_port.cpp` (0.96), `src/platform/nezha_port.h`
  (0.80), `src/platform/vfp_guard.h` (3.85),
  `src/platform/otos_port.{h,cpp}`, `src/platform/platform_ports.h`

### Rules of engagement (binding, every item)

Identical to ticket 002 — re-anchor by quoted content never line
number; a replacement whose premise changed is a recorded no-op never
forced; `.claude/rules/measurement-citations.md` (never strip the
artifact path out of a `MEASURED` claim); `.claude/rules/
no-units-in-identifiers.md` (this sprint renames nothing, and never
delete a trailing `// [unit]`).

### Boil-down items (motion-and-kernel annex, rows 8-15)

| annex # | anchor (quoted content, current file) | status |
|---|---|---|
| 8 | `nezha_port.cpp`'s fault-handler forensics block plus its two dated updates: `UPDATE 2026-09-01 -- the "memory corruption" above is probably not` and `UPDATE 2026-09-02 -- RESOLVED. The VFP-register-clobber theory above` | **LIVE.** This is the canonical example of guidelines anti-pattern 6, which ticket 001 writes up — collapse all three paragraphs into the annex's replacement, which states the current truth in four lines. **Keep the `MEASURED tigez 2026-08-30, captures/tigez-cal-20260830/` citation**, and see the citation repoint below. |
| 9 | the bus-hang guard essay around `codal-nrf52 commit 1fbb724` / `NRF52I2C::waitForStop() bounds one stuck` | LIVE. Use the annex's two-line replacement; keep the commit hash and the ~11 s bound — both are facts a reader cannot recover from the code. |
| 10 | the `sampleTime_` hold block: `discarded: position/velocity/sampleTime all HOLD`, `Hold sampleTime_ here instead of falling through to the`, `cannot be trusted as motion -- so withhold sampleTime_` | LIVE, reduced. Use the annex's replacement; note the field is `sampleTime_`, not the annex's `sampleTimeUs_`. Keep the `MEASURED gopiv 2026-09-02, captures/gopiv-frozen-encoder-fix-20260902/notes.md` citation (that directory is fully tracked — no action needed). |
| 11 | `shims.cpp`'s block around `deliverStopNow(), which this method absorbs` and `Rig::softStop()` | **LIVE, but not as written.** Sprint 033 absorbed `deliverStopNow()` into `Rig::softStop()` and replaced the old essay with *fresh sprint-033 narration at the same spot*. Boil the new narration down to the annex's target content — immediate port-level zero on both motors; `neutral()` is only staged; a stop from a non-ticker fiber would otherwise wait ~100-150 ms for the watchdog; never `emergencyStopMotors()`, which latches the e-stop. |
| 12 | `shims.cpp`'s `tickDrive()` header and its two inline histories | LIVE. Annex target: 8 lines total — one step + serviceMove per call on the caller's fiber, absolute-deadline pacing, returns `commandLooksActive()`, settle before reporting done. |
| 13 | `shims.cpp`'s wire-forward rationales (the blocks above the `engine*` forwards that narrate *why* each forward exists, e.g. `this used to read MotionEngine::aDecelMmS2()`) | LIVE. One line each: what the forward returns and who calls it. |
| 14 | the three-block go-to shim split saga: `single five-parameter engineGoToR() reproduced "TS9200: Assertion` and `version reproduced "TS9200: Assertion failed" deterministically --` | LIVE. Collapse to the annex's two-line replacement, once. (`src/blocks/motion.ts`'s and `src/blocks/sim.ts`'s copies of the same story belong to **ticket 006** — do not touch them; `src/DESIGN.md`'s copy belongs to **ticket 008**.) |
| 15 | `shims.cpp`'s per-case commentary in `setKernelValue()`/`getConfigValue()` | **LIVE, reduced.** Sprint 033 moved the ten shaping ordinals into `kLimitsFields` (`comms/config_fields.h`, `motion/motion_limits.h`), which already makes those self-describing. What survives is the per-case commentary on the remaining `kConfigAccessors` rows and the `diagValue()` case block (`case 20`-`case 34`). Cut narration; **keep** each case's one-line statement of what the counter means and what a nonzero value indicates — those are facts a reader cannot get from the ordinal. |

### Factual fixes

1. **`shims.cpp`'s header claims the move engine lives here.** The
   leading block lists, among "the application-layer pieces the kernel
   deliberately does not contain" that *this file* adds:
   `- MOVE ENGINE: position-mode moves (distance+yaw, and goto via the`.
   The engine moved to `src/motion/motion_engine.{h,cpp}` in sprint 003;
   `shims.cpp` holds a `MotionEngine engine{kernel, clock};` member and
   a set of forwards. Rewrite the bullet to say what is true: the move
   engine is `motion/motion_engine.{h,cpp}`, and this file composes it
   and forwards to it. **ODOMETRY's `live HERE` in the bullet above it
   is still correct** — track width and travel calibration genuinely do
   live in this file. Do not "fix" that one.

2. **`nezha_port.cpp`'s `captures/tigez-cal-20260830/` citation must be
   repointed at a tracked file.** That directory is 2.6M and mostly
   large JSON blobs; **ticket 007** force-tracks only its small evidence
   files. Change the citation from the bare directory to
   `captures/tigez-cal-20260830/notes.md`. **Coordinate:** ticket 007
   does the `git add -f`; this ticket does the text. If you reach this
   before 007 has run, make the edit anyway and note the dependency —
   007's acceptance criteria include verifying every repointed path
   resolves.

### Factual error to record as a no-op (verified already correct)

- `nezha_port.h`'s ordinal-27 claim. The review reads it as saying the
  encoder *streaks* are exposed via `diagValue()` ordinal 27. In the
  current file the sentence `Exposed via diagValue() ordinal 27.` sits
  at the end of the **`rebaselineCount_`** comment, and `shims.cpp`'s
  `case 27:` returns `left.rebaselineCount_ + right.rebaselineCount_`.
  It is correct. Record it as a no-op.

  *Optional clarity improvement, at your discretion:* the
  `maxDrivenStreak_` comment above it cites no ordinal at all, and the
  streaks are ordinals 21 and 22. Adding that is a one-line
  improvement, not a fix; if you add it, say so in the notes.

## Acceptance Criteria

- [ ] Annex items 8-15 are applied, each re-anchored by quoted content;
      any judged a no-op is recorded with its reason.
- [ ] `nezha_port.cpp` no longer carries a stacked `UPDATE <date>`
      chain; the surviving text states the current truth (the VFP
      clobber, fixed by `vfp_guard.h`; the handler stays as the last
      line of defence) and keeps its `MEASURED` citation.
- [ ] `shims.cpp`'s header no longer says the move engine is added by
      this file; the ODOMETRY bullet's `live HERE` is untouched.
- [ ] `nezha_port.cpp`'s tigez citation points at
      `captures/tigez-cal-20260830/notes.md`.
- [ ] `nezha_port.h`'s ordinal-27 claim is recorded as a verified
      no-op.
- [ ] All 37 `//%` pragma lines in `src/shims.cpp` are byte-identical
      to before (`git diff` shows no `//%` line).
- [ ] Every surviving `MEASURED` claim names its board, date and
      artifact path.
- [ ] `shims.cpp`'s ratio is materially below 1.71; recorded in the
      completion notes.
- [ ] No trailing `// [unit]` deleted, no identifier renamed, no line
      of code changed.

## Testing

Foreground only.

- **Existing tests to run**:

      uv run pytest tests/host/test_archaeology_marker_budget.py \
                    tests/host/test_cxx11_syntax_gate.py \
                    tests/host/test_wire_constants_drift.py -q
      uv run pytest tests/host/ -k source_pin -q
      uv run pytest tests/host/ -q

  The source-pin family is the one that breaks here: several pins match
  text in `shims.cpp` and `nezha_port.cpp`
  (`test_soft_stop_source_pin.py`, `test_staged_stop_source_pin.py`,
  `test_dispatched_job_motion_source_pin.py`, `test_vfp_guard_
  source_pin.py`, `test_bus_guard_source_pin.py`,
  `test_exec_run_stack_footprint_source_pin.py`). If a pin fails, the
  correct response is almost always to restore the text the pin matches
  — a pin exists because that exact wording is load-bearing — not to
  loosen the pin.

- **New tests to write**: none.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Replacement text source:
  `docs/code-review/2026-09-02/raw/motion-and-kernel.md`, "Boil-down
  list", rows 8-15; and its "CH-02" table.
- Read `sprint.md`'s "Verification pass" section first.
- Do not run the full repo suite.
