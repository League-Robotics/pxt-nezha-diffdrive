---
id: '005'
title: Encoder glitch-armor rebaseline-on-discontinuity (host-testable)
status: in-progress
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: brick-reset-odometry-teleport.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Encoder glitch-armor rebaseline-on-discontinuity (host-testable)

## Description

`NezhaMotorPort::collect()`'s glitch armor (`src/nezha_port.cpp:196-239`)
rejects an implausible raw-counts jump (`|delta| > kMaxDeltaCounts`,
5000 counts) on its first appearance, then **accepts** it as truth if
a second, mutually-consistent reading follows (the documented
hand-rotation re-sync path). If the Nezha brick's MCU resets
mid-session (brownout, wiring blip), its encoder counter restarts near
zero; `encOffset_` is captured once at `begin()` and never
re-baselined by any production path. The two-strike rule then accepts
the post-reset counter as reality: `position()` jumps by the full
delta (~4 m at a typical ~50k-count reset), `refreshSample()` computes
a multi-M-counts/s velocity spike from the jump, and `odomUpdate()`
folds the teleport straight into pose (code review R-07, KERN-07 —
code path CONFIRMED statically; the hardware premise that a brick
reset actually zeroes the 0x46 counter is UNVERIFIABLE without a bench
run, tracked separately by ticket 006).

**This ticket is the host-testable half only.** The defect it fixes —
the two-strike rule accepting *any* implausible-then-consistent jump
as truth — is real and worth fixing independent of what causes the
jump; a brick reset is the named hypothesis, not the only possible
trigger. Do not gate this ticket's completion on ticket 006's bench
result. `completes_issue: false` is set deliberately in this ticket's
frontmatter — the issue's bench-only half remains open until ticket
006 completes it.

**Fix, at the module level** (see `design/DESIGN.md` §7 for the full
write-up): extract the raw-counts plausibility decision into a new,
host-portable `encoder_glitch_armor.h` (no `pxt.h`/I2C dependency at
all — a pure function of `(rawCounts, lastGoodRaw, rejectPending)`
returning one of three outcomes: accept as motion, accept as
rebaseline, or hold pending). The existing two-strike trigger now
routes to "accept as rebaseline" instead of "accept as motion":
`NezhaMotorPort::collect()` (the thin, hardware-only caller) re-anchors
`encOffset_` to the new raw value (the same software-offset technique
the existing, currently-uncalled-in-production `rebaseline()` already
uses) instead of integrating the jump — position stays continuous,
velocity reflects real motion during the sample gap rather than a
multi-m/s spike — and a DIAG counter increments so the event is
visible. The existing behavior for an ordinary implausible-then-
plausible-consistent second reading (e.g. a genuine hand-rotation
re-sync) is a **new third outcome**, not a replacement of today's
accept-as-motion path for cases where the second reading is NOT the
same kind of implausible-jump-then-consistent pattern — read
`collect()`'s existing logic carefully before changing it; this ticket
adds a branch, it does not remove the existing one wholesale.

**C++11 gate coverage:** `encoder_glitch_armor.h` has no `pxt.h`
dependency and should be added to
`tests/host/test_cxx11_syntax_gate.py`'s coverage via a small
dedicated syntax-check translation unit. `nezha_port.cpp` itself (the
caller) is **not** covered by that gate and cannot be made so — it
includes `pxt.h` unconditionally for I2C. A green host suite proves
`encoder_glitch_armor.h`'s decision logic is correct and syntax-valid
at C++11; it does not prove `nezha_port.cpp`'s call site compiles for
either real embedded target.

## Acceptance Criteria

- [x] A host test drives `EncoderGlitchArmor` directly (no I2C fake
      needed — it has no hardware dependency) with a scripted
      implausible-then-consistent raw-counts sequence (e.g. simulating
      a ~50k-count reset-like jump) and asserts an "accept as
      rebaseline" decision, not "accept as motion."
      — `tests/host/test_encoder_glitch_armor.py::
      test_reset_like_jump_then_consistent_reading_is_accepted_as_rebaseline`
      (prime(50_000), evaluate(30) -> kRejectPending, evaluate(75) ->
      kAcceptAsRebaseline).
- [x] A host test confirms the existing behavior for a plausible
      single reading (no jump) is unchanged: "accept as motion."
      — `test_plausible_single_reading_is_accepted_as_motion`
      (parametrized deltas including the exact kMaxDeltaCounts
      boundary) and `test_a_run_of_plausible_readings_stays_accepted`.
- [x] A host test confirms the existing behavior for an implausible
      first reading with **no** consistent second reading is
      unchanged: "hold pending" (the existing reject-and-wait path).
      — `test_implausible_first_reading_with_no_second_holds_pending`
      and `test_implausible_first_reading_followed_by_an_inconsistent_second_still_holds`.
- [x] `NezhaMotorPort::collect()`'s integration with
      `EncoderGlitchArmor` is exercised indirectly if any existing
      `nezha_port.cpp`-adjacent test exists; if none does (likely,
      given `nezha_port.cpp` is not host-testable), state so explicitly
      rather than silently skipping this check.
      — Stated explicitly: no `nezha_port.cpp`-adjacent host test
      exists (`nezha_port.h` includes `pxt.h` unconditionally;
      `tests/host/DESIGN.md` S6 already lists `nezha_port` under "not
      covered, by design"). The `collect()`/`begin()`/`rebaseline()`
      wiring to `EncoderGlitchArmor` (offset re-anchor formula, DIAG
      counter increment) is **review-verified only** — see this
      ticket's own report to team-lead for the exact diff reasoning.
- [x] A DIAG counter increments when a rebaseline fires, 0 across a
      normal session with no discontinuities (add to the existing
      DIAG ordinal table alongside the other glitch/wedge counters).
      — `shims.cpp::diagValue()` ordinal 27 (sum of
      `left.rebaselineCount_ + right.rebaselineCount_`); wiring is
      review-verified only (same host-testability limit as above).
- [x] `encoder_glitch_armor.h` is added to
      `tests/host/test_cxx11_syntax_gate.py`'s covered-files list.
      — via `tests/host/encoder_glitch_armor_syntax_check.cpp`.
- [x] `completes_issue: false` remains set in this ticket's frontmatter
      (do not change it — ticket 006 completes the issue).

## Implementation Plan

**Approach:**
1. Design `encoder_glitch_armor.h`'s pure decision function/class,
   preserving the exact numeric behavior of the existing two-strike
   rule (`kMaxDeltaCounts = 5000`) for its two existing outcomes, and
   adding the third ("accept as rebaseline," when the same trigger
   that used to mean "accept as motion" fires).
2. Refactor `NezhaMotorPort::collect()` to call into it, replacing the
   inline two-strike logic with a call to the extracted decision plus
   a branch on its three-way result: "accept as motion" (existing
   path, unchanged), "hold pending" (existing path, unchanged),
   "accept as rebaseline" (new — re-anchor `encOffset_`, do not update
   `lastPosition_`/`velocity_` as if real motion occurred).
3. Add the DIAG counter for rebaseline events, following the existing
   pattern for `glitchCount_`/similar counters already exposed via
   `diagValue()`.
4. Add `encoder_glitch_armor.h` to the C++11 syntax gate.

**Files to modify:**
- `src/encoder_glitch_armor.h` (new) — the pure decision logic.
- `src/nezha_port.cpp` — `collect()` refactored to call it; new DIAG
  counter.
- `src/nezha_port.h` — expose the new counter if needed for `diagValue()`.
- `src/shims.cpp` — wire the new counter into `diagValue()`'s ordinal
  table if not already reachable.
- `tests/host/test_cxx11_syntax_gate.py` — add `encoder_glitch_armor.h`.
- `tests/host/` — new tests exercising `EncoderGlitchArmor` directly.

**Testing plan:** host-only, against `encoder_glitch_armor.h` directly
— it has no hardware dependency, so this is fully testable without a
robot, unlike most of `nezha_port.cpp`.

**Documentation updates:** none beyond `design/DESIGN.md`'s existing
overlay content, which this ticket implements. Do **not** edit
`brick-reset-odometry-teleport.md`'s bench-result section — that is
ticket 006's job, after the bench experiment actually runs.
