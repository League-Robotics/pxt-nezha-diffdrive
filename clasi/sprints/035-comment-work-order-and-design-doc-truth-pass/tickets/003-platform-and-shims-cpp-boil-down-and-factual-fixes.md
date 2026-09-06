---
id: '003'
title: platform/ and shims.cpp boil-down and factual fixes
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
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

- [x] Annex items 8-15 are applied, each re-anchored by quoted content;
      any judged a no-op is recorded with its reason.
- [x] `nezha_port.cpp` no longer carries a stacked `UPDATE <date>`
      chain; the surviving text states the current truth (the VFP
      clobber, fixed by `vfp_guard.h`; the handler stays as the last
      line of defence) and keeps its `MEASURED` citation.
- [x] `shims.cpp`'s header no longer says the move engine is added by
      this file; the ODOMETRY bullet's `live HERE` is untouched.
- [x] `nezha_port.cpp`'s tigez citation points at
      `captures/tigez-cal-20260830/notes.md`.
- [x] `nezha_port.h`'s ordinal-27 claim is recorded as a verified
      no-op.
- [x] All 37 `//%` pragma lines in `src/shims.cpp` are byte-identical
      to before (`git diff` shows no `//%` line).
- [x] Every surviving `MEASURED` claim names its board, date and
      artifact path.
- [x] `shims.cpp`'s ratio is materially below 1.71; recorded in the
      completion notes.
- [x] No trailing `// [unit]` deleted, no identifier renamed, no line
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

## Completion notes

### Annex rows 8-15

| row | outcome |
|---|---|
| 8 | **applied.** `nezha_port.cpp`'s fault-handler block: original forensics + the two dated `UPDATE` paragraphs collapsed into one statement of the current truth (weak handler = infinite loop, so the brick keeps its last command; root cause was the VFP clobber `vfp_guard.h` closes; handler stays as the last line of defence). Both `MEASURED` citations kept, the 2026-08-30 one repointed per factual fix 2. The "decode BFAR as ASCII and as a float" advice was kept — it is guidance for the next fault, not archaeology. |
| 9 | **applied.** Bus-hang guard essay 38 → 9 lines. Kept commit `1fbb724`, the codal-microbit-v2 v0.3.5 pin, the ~11 s bound with its 10 s + 1 s derivation, the 3-per-motor multiplication, and the stated trade-off (a single transient NACK now reports `connected() == false`). Dropped the "not confirmed which path an unpowered brick takes / ticket 005 should watch for it" speculation. |
| 10 | **applied.** `sampleTime_` hold block 32 → 18 lines. Field name is `sampleTime_` (the annex's `sampleTimeUs_` does not exist). The `MEASURED gopiv 2026-09-02, captures/gopiv-frozen-encoder-fix-20260902/notes.md` citation and its "five tours in six, all this branch" number kept. The annex's "PID chased to 420 mm/s" number was **not** used — that figure belongs to the *other* gopiv 2026-09-01 citation further down the file, not this branch, so importing it would have been a fabricated attribution. |
| 11 | **applied, to the sprint-033 narration actually present** (not the pre-033 text the annex quotes). 83 → 41 lines, carrying the annex's four target facts plus the two the current code cannot do without: the unconditional `kernel.neutral()`, and the `pendingStop_` staging while `busGuard` is held. `deliverStopNow` still appears on exactly one comment line, as `test_soft_stop_source_pin.py` requires. |
| 12 | **applied.** `tickDrive()`'s header 30 → 17, the `isDriving()` history 27 → 11, the `odomUpdate()` history 22 → 11, and the move-completion + settle pair 28 → 13. Kept every invariant (absolute-deadline pacing and its re-anchor rule, why raw `moveActive` is the wrong read, why a Hold needs `isDriving()`, the arc-vs-chord error, the +9-13°/+15-22 mm watchdog cost, why one extra step is not enough). |
| 13 | **applied.** Six wire-forward blocks reduced to what each returns and who calls it: `engineDefaultCruise` 22 → 11, `engineADecel`/`engineDefaultCruiseForDistance` 25 → 9, `engineDominantAxisTravel` 6 → 5, `engineMoveActive` 15 → 8, `engineMoveEndedByDeadline` 12 → 6, `engineWheelsX`/`engineMoveX` 11 → 8. The annex's specific anchor (`this used to read MotionEngine::aDecelMmS2()`) is gone; the behavioural consequence it existed to explain (`engineADecel() > 0` always takes the distance-aware branch) is kept. |
| 14 | **applied, told once.** The saga now lives only on `engineSetGoToDeadline()` (17 → 10 lines): PXT rejects a `//%` shim with more than four parameters, TS9200, and this setter supplies the fifth. `Rig::goToDeadline` (32 → 12) and `Rig::pendingGoToYawRate_` (13 → 8) now point at it; `engineSetGoToYawRate()` (9 → 6) likewise. `blocks/motion.ts`, `blocks/sim.ts` and `src/DESIGN.md` untouched (tickets 006/008). |
| 15 | **applied at the reduced scope the ticket describes.** `kLimitsFields`' section header 16 → 9 and its table comment 7 → 3, with the three inline row notes (8/18/37) trimmed but each keeping its ordinal-provenance fact. `kConfigAccessors`' header 26 → 20 (the C++11-vs-C++17 lambda reason and the config_fields.h split are both load-bearing). Per-accessor: `rebase` 19 → 12, `goto_timeout` 15 → 10. `diagValue()` cases 26-34: narration cut, each case keeping one line for what the counter means and what nonzero indicates, and 31-34 keeping the `31 - 32 == 33 + 34` invariant. |

### Factual fixes

1. **Applied.** The header's `MOVE ENGINE` bullet now says the moves
   live in `motion/motion_engine.{h,cpp}` and that what this file adds
   is the composed `MotionEngine` member and the forwards onto it. The
   `ODOMETRY` bullet's `live HERE` above it is byte-unchanged
   (`grep -n "live HERE" src/shims.cpp` still returns the one line).
2. **Applied.** Both `captures/tigez-cal-20260830` citations in
   `nezha_port.cpp` now read `captures/tigez-cal-20260830/notes.md`
   (lines 23 and 85). **Depends on ticket 007's `git add -f`** — the
   path does not resolve in a fresh clone until that lands. Both facts
   cited (CFSR 0x8200 / BFAR 0x474E4988 at notes.md:134; the
   `uBit.serial.printf()` block with IPSR=3 at notes.md:178-179) were
   verified present in that file before repointing.

### Verified no-op

- **`nezha_port.h`'s ordinal-27 claim.** Confirmed correct and left
  alone: `Exposed via diagValue() ordinal 27.` closes the
  `rebaselineCount_` comment, and `shims.cpp`'s `case 27:` returns
  `ensure().left.rebaselineCount_ + ensure().right.rebaselineCount_`.
- **The optional clarity improvement WAS taken**: `maxDrivenStreak_`
  now carries `Exposed via diagValue() ordinals 21 (left) and 22
  (right).`, matching `case 21:`/`case 22:` in `shims.cpp`.

### Two `MEASURED` claims given their artifact

Acceptance criterion "every surviving `MEASURED` claim names its board,
date and artifact path" was not met by two pre-existing claims in this
ticket's own files: `vfp_guard.h` and `platform_ports.h` each carried
`MEASURED gopiv 2026-09-01 (pyOCD…)` with no path (`platform_ports.h`
said only "the knowledge article under docs/"). Both now name
`docs/knowledge/2026-09-01-codal-does-not-save-fpu-registers-across-fibers.md`,
which is tracked and contains the cited CFSR 0x8200 / `float -25.0` /
s16-s31 forensics. Nothing was invented.

### Two files boiled down to absorb those additions

The ratchet from ticket 001 is per file and down-only, so the two added
citation lines had to be paid for in the same files:

- `platform_ports.h` restated `vfp_guard.h`'s hazard and measurement
  verbatim while including that header — the "provenance belongs in one
  authoritative place" standard. It now points at `vfp_guard.h` and
  keeps its own distinct fact (this class is the vendored kernel's only
  yield path).
- `vfp_guard.h`'s header was tightened without dropping a fact: the
  hazard, the measurement, all three properties of the fix, the
  `noinline` rationale and the `general-regs-only` ICE warning all
  survive.
- `nezha_port.h`'s `glitchArmor_` comment lost its "state this member
  used to hold inline" diff restatement (anti-pattern 4).

### Ratios (counting rule: `tests/host/test_archaeology_marker_budget.py`)

| file | before | after |
|---|---|---|
| `src/shims.cpp` | 1215 / 710 = **1.7113** | 1007 / 710 = **1.4183** |
| `src/platform/nezha_port.cpp` | 244 / 255 = **0.9569** | 189 / 255 = **0.7412** |
| `src/platform/vfp_guard.h` | 50 / 13 = **3.8462** | 46 / 13 = **3.5385** |
| `src/platform/platform_ports.h` | 27 / 27 = **1.0000** | 20 / 27 = **0.7407** |
| `src/platform/nezha_port.h` | 59 / 74 = **0.7973** | 58 / 74 = **0.7838** |

`src/platform/otos_port.{h,cpp}` were read and judged **no-ops** — no
annex row anchors in them, no factual error, and both already sit well
under baseline (0.75 and 0.27).

### Comment-only proof (mechanical)

`shims.cpp` includes `pxt.h` and is not host-compiled, so the edit was
proved comment-only by text rather than by a build:

1. **Every added/removed line in `git diff -- src/` is a comment.**
   `git diff -U0` filtered to `^[+-]` (headers excluded) leaves nothing
   after dropping lines matching `^[+-][[:space:]]*//` — output empty.
   No `/* */` block was touched anywhere in this ticket.
2. **No `//%` pragma line appears in the diff.** The same filtered diff,
   with leading whitespace stripped, has no line matching `^[+-]//%` —
   output empty. Counts are byte-stable: `src/shims.cpp` 37 before and
   37 after, `src/comms/protocol.cpp` 4 before and 4 after (that file
   was not touched at all).
3. **Code-line count per file identical before and after**, applying the
   ratchet's own counting rule to `git show HEAD:<file>` vs the working
   copy: `shims.cpp` 710 → 710, `nezha_port.cpp` 255 → 255,
   `nezha_port.h` 74 → 74, `platform_ports.h` 27 → 27, `vfp_guard.h`
   13 → 13.
4. **No trailing `// [unit]` deleted**: the sorted multiset of
   `// [...]` annotations in `shims.cpp` is identical before and after,
   and the trailing-bracket line count is unchanged in all four
   `platform/` files.

A desk firmware build is still the team-lead's post-sprint step.

### Tests (foreground, this turn)

    uv run pytest tests/host/test_archaeology_marker_budget.py \
                  tests/host/test_cxx11_syntax_gate.py \
                  tests/host/test_wire_constants_drift.py -q
    -> 58 passed in 1.19s

    uv run pytest tests/host/ -k source_pin -q
    -> 85 passed, 1082 deselected in 0.27s

    uv run pytest tests/host -q
    -> 1167 passed in 28.65s

No source pin needed restoring — no pin failed at any point.
