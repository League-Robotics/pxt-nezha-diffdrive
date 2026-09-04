---
id: '001'
title: 'Kernel patches K1-K4: post-floor twist-hold reference, stale-tick freeze,
  anti-windup, rearmReferences()'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on: []
github-issue: ''
issue:
- code-review/kernel-reference-handling-twist-floor-stale-tick-antiwindup.md
- code-review/decide-the-kernel-fork.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Kernel patches K1-K4: post-floor twist-hold reference, stale-tick freeze, anti-windup, rearmReferences()

## Description

`src/core/diffdrive.cpp` has four independently-justifiable bugs in its
reference handling, each MEASURED against the real kernel with ideal
wheels (`docs/code-review/2026-09-02/raw/profile_probe.out`), detailed
in design §4.5 and issue
`kernel-reference-handling-twist-floor-stale-tick-antiwindup.md`:

- **K1** — `controlStep()` integrates `twistRef_.reference` from
  `lambda·cmd.twist` (pre-floor) at `diffdrive.cpp:599`, then
  `applySpeedFloor()` rescales both wheels up to `vMin` at line 617.
  Whenever the floor binds, the reference lags the wheels and the trim
  brakes the turn (−11% reverse duty on a cruise-100 pivot). Move the
  reference-integration line to after `applySpeedFloor()` and compute
  headroom from `0.5·(speedRight − speedLeft)` (the post-floor
  half-differential).
- **K2** — `positionError()` advances `ref.reference` by `speed·dt` even
  on a tick whose `sample.position` didn't change (a frozen encoder
  read), producing a +6 duty-point kick. Take `fresh` as an argument;
  when false, return the last error without advancing the reference.
- **K3** — `ref.reference` accumulates without bound; only the returned
  error is clamped. After updating, clamp `ref.reference` to
  `(position − origin) ± posErrMax`.
- **K4** — Add `rearmReferences()`, a deferred request (same shape as
  the existing `rebasePosition()`) that disarms both position
  references and the twist reference at the start of the next `step()`.
  This retires the engine's `awaitingHandoffNeutral` flag (ticket 003)
  and lets a segment boundary re-anchor without sacrificing a neutral
  tick.

**K5** (`cfg.vMin = 0` in `shims.cpp:ensure()`) is explicitly **not**
part of this ticket — it lands in ticket 003, once `MotionEngine` owns
the floor via `MotionLimits` and can safely absorb the kernel no longer
providing one.

**The kernel-fork open question gates how this ticket ships.**
`.claude/rules/fiber-yield-safety.md` currently documents
`src/core/diffdrive.{h,cpp}` as "do not edit" under the byte-identical-
to-upstream rule, and this ticket edits it. Per design §12 and issue
`decide-the-kernel-fork.md`, write these four patches as a **paired
change** against `radio-robot-elite/src/firm/diffdrive/` (the safer
default until the stakeholder rules otherwise) — implement the same
four patches in both trees, run both trees' fidelity/host-test suites,
and update `.claude/rules/fiber-yield-safety.md`'s "do not edit"
language to carve out "except via a paired upstream PR, see
`decide-the-kernel-fork.md`". If the stakeholder has by this point
decided to drop the byte-identical rule in favor of a local fork with a
behavioral fidelity test instead, do that version: edit only this
repo's copy, add the fidelity test pinning the control law's behavior
on the probe's scenarios, and relax the "do not edit" language
accordingly. Either way, update `src/DESIGN.md` §2's "Vendored, synced
copy" invariant bullet to state which regime is in effect and list the
four patches — this is a real edit to the actual file (not the
sprint's `design/` overlay: `seed_sprint_design_overlay` collided
`src/DESIGN.md`'s and `tools/DESIGN.md`'s overlay slugs this planning
session — see sprint.md's Open Question notes — so `src/DESIGN.md`'s
architecture updates are direct ticket-time edits to the real file for
this sprint, not overlay-mediated).

## Acceptance Criteria

- [x] K1: a floored command produces a twist reference equal to the
      floored half-differential (host test).
      `tests/host/test_kernel_reference_handling.py::test_k1_floored_twist_reference_tracks_post_floor_half_differential`.
- [x] K2: a frozen tick leaves the position reference unchanged (host
      test).
      `tests/host/test_kernel_reference_handling.py::test_k2_frozen_sample_leaves_reference_unchanged_and_does_not_kick_duty`.
- [x] K3: a 50 mm lag yields a reference backlog of exactly
      `posErrMax` (host test).
      `tests/host/test_kernel_reference_handling.py::test_k3_anti_windup_bounds_the_stored_reference_backlog`
      (uses counts, the kernel's own unit, in place of an mm
      conversion diffdrive.cpp never performs itself; see the test's
      own docstring).
- [x] K4: `rearmReferences()` zeroes both the position and twist
      references at the next `step()`, and the twist error is zero on
      the tick after a phase change (host test).
      `tests/host/test_kernel_reference_handling.py::test_k4_rearm_references_zeroes_twist_error_on_the_next_tick`
      and `::test_k4_rearm_references_zeroes_position_references_too`.
- [x] Probe-as-test: no negative right duty during a cruise-100 pivot
      with the twist servo on; the frozen-tick duty kick (E5) is zero.
      `tests/host/test_profile_probe_kernel.py` (via
      `tests/host/profile_probe_kernel_check.cpp`, a duplicated copy of
      `profile_probe.cpp`'s own `Rig` run as a standalone check binary
      — ticket 003 owns the full `test_profile_probe.py`). MEASURED
      against the patched kernel, this same probe binary run directly:
      E3d most-negative right duty +0.0% across cruise 60/100/200 with
      twist-hold gain 2 (was −13.0%/−11.0%/0% before this ticket); E5
      duty step +0.85 points on the tick after the freeze (was ~+6).
- [x] Shipped as a paired change against
      `radio-robot-elite/src/firm/diffdrive/` (default) or as a locally
      owned fork with a new behavioral fidelity test — whichever the
      stakeholder has decided by ticket start; if undecided, proceed
      under the paired-PR default per design §12.
      Proceeded under the paired-PR default (undecided at ticket
      start). The four patches are implemented here; the equivalent
      diff for upstream is staged at
      `docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`,
      including the manual-application note (upstream's own comments
      have already diverged from this repo's vendored copy, so the
      hunks will not `git apply` cleanly). **The upstream PR against
      `radio-robot-elite` has NOT been opened as of this ticket's own
      close** — that repository is read-only from this worktree and
      opening a PR there is out of this ticket's reach; the patch file
      is the artifact that unblocks it. Tracked as an open follow-up.
- [x] `.claude/rules/fiber-yield-safety.md`'s "do not edit
      diffdrive.{h,cpp}" note is updated to reflect whichever regime
      was used.
- [x] `src/DESIGN.md` §2's kernel invariants bullet is updated in the
      real file to describe the four patches and the fork regime in
      effect.
- [x] Everything else in the kernel (FF+I law, lambda, bias, stall/
      deficit latches, lease, e-stop, output publication) is untouched.
      Confirmed by the existing pinned host-test suite staying green
      unchanged (no pinned expectation needed updating): see the
      ticket's own "Testing plan" / this session's final report.

## Implementation Plan

**Approach**: Implement K1-K4 as four small, separable diffs to
`controlStep()`/`positionError()`, each individually justifiable as a
bug fix (per the issue's own framing) rather than as one large rewrite.
Write the host tests first against `WaHandle`/`FakeMotor`-style test
doubles already used in `tests/host/`, confirming each fails against
today's code and passes after the patch.

**Files to create/modify**:
- `src/core/diffdrive.cpp` — the four patches.
- `src/core/diffdrive.h` — new `rearmReferences()` public method
  declaration and its deferred-request counter field, matching
  `rebasePosition()`'s existing shape.
- `tests/host/test_kernel_reference_handling.py` (new) — K1-K4's four
  scenarios per design §9.3.
- `.claude/rules/fiber-yield-safety.md` — update the "do not edit"
  language.
- `src/DESIGN.md` §2 — real-file edit describing the patches and the
  fork regime (see Description above for why this bypasses the sprint
  overlay).
- If paired-PR: the corresponding diff against
  `radio-robot-elite/src/firm/diffdrive/` (coordinate with that repo's
  own process; note the dependency in this ticket's own status if the
  upstream PR is still pending at ticket close).

**Testing plan**: `tests/host/test_kernel_reference_handling.py` (new,
scoped run per `.claude/rules/source-code.md`); confirm the existing
kernel host-test suite (`tests/host/test_diffdrive_*.py` or equivalent)
stays green — this ticket must not change the FF+I control law's
observable behavior outside the four named defects.

**Documentation updates**: `src/DESIGN.md` §2 (real file, see above);
`.claude/rules/fiber-yield-safety.md`.
