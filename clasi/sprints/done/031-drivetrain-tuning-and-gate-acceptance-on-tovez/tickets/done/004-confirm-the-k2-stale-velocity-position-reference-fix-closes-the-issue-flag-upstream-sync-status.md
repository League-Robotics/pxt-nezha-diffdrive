---
id: '004'
title: Confirm the K2 stale-velocity/position-reference fix closes the issue; flag
  upstream sync status
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Confirm the K2 stale-velocity/position-reference fix closes the issue; flag upstream sync status

**Type: (c) analysis of existing code and captured data — no hardware,
likely no new code.**

## Description

The issue's own CORRECTION section (code review 2026-09-02, MK-03)
identifies the real mechanism as `positionError()` advancing
`ref.reference` by `speed*dt` even on a tick whose encoder sample did
not advance, not a raw PID velocity-error problem — and names the fix
as "K2" in
`docs/code-review/2026-09-02/kernel-reference-handling-twist-floor-stale-tick-antiwindup.md`
(sprint 029 ticket 001, corrected by ticket 010).

Reading the CURRENT vendored kernel (`src/core/diffdrive.cpp`) shows
K2 already landed: `positionError()` takes an `advanced` parameter and
only integrates the reference when the previous step's own collect
moved the wheel's cached sample
(`sampleAdvancedLeft_`/`sampleAdvancedRight_`), with a comment citing
the exact MEASURED result (+6 duty points off one frozen tick,
`profile_probe.cpp` E5) this issue described. This ticket is
**verification, not implementation**:

1. Confirm `core/diffdrive.cpp`'s current `positionError()` matches the
   patch described in the review finding.
2. Check `tests/host/test_kernel_reference_handling.py` and
   `tests/host/test_frozen_encoder_hold.py` (or equivalent) actually
   exercise the frozen-tick-then-resume scenario the issue describes,
   with an assertion bounding the post-fault duty/velocity transient.
   If a gap exists, write the missing assertion (a small (b)-shaped
   addition) rather than leaving the claim unverified.
3. Check whether `decide-the-kernel-fork.md`'s paired-PR obligation
   (syncing K1-K4 to `radio-robot-elite`) has actually happened. If not,
   flag it explicitly in the closing note — do NOT perform the upstream
   sync yourself; it is out of this sprint's scope.

## Acceptance Criteria

- [x] Closing note cites the exact lines in `core/diffdrive.cpp` that
      implement K2's freshness gate, confirming they match the review
      finding's description.
- [x] Closing note states, with test file names and test function
      names, whether existing host tests cover the described transient;
      any gap found is closed with a new assertion in this ticket.
- [x] Closing note states the upstream (`radio-robot-elite`) sync status
      as either "confirmed synced, see `<commit/PR>`" or "not yet
      synced — flagged, out of scope for sprint 031."
- [x] This issue is only marked resolved if the above confirms K2 is
      both landed and tested; if the analysis instead finds a real gap
      requiring new kernel behavior, say so and do NOT claim the issue
      closed.

## Testing

- **Existing tests to run**:
  `uv run pytest tests/host/test_kernel_reference_handling.py
  tests/host/test_frozen_encoder_hold.py`
- **New tests to write**: only if step 2 above finds a coverage gap.
- **Verification command**: `uv run pytest tests/host/`

## Closing note (verification, no kernel code changed)

**1. K2's freshness gate is landed and matches the review finding.**
`src/core/diffdrive.h:294-296` declares `positionError(speed, wheel,
ref, dt, advanced)` with a per-wheel `advanced` bool, backed by
`sampleAdvancedLeft_`/`sampleAdvancedRight_` (`diffdrive.h:343-351`,
default `true` so the very first `step()` behaves like an ordinary
fresh tick). `diffdrive.cpp:528-535` sets those flags at the END of
`step()` by comparing each wheel's `sampleTime` before/after that
cycle's own `refreshSample()` call — the same before/after comparison
`i2cFaultCount_` already uses — so the flag consumed by the NEXT
`step()`'s `controlStep()` genuinely reflects "did the collect that
just ran move this wheel's cached sample." `controlStep()` passes
those exact per-wheel flags into `positionError()` at
`diffdrive.cpp:701-704`.

Inside `positionError()` (`diffdrive.cpp:911-946`), the reference
advance is now gated: `if (advanced) { ref.reference += speed * dt;
... }` (line 933 onward). When `advanced` is false, `ref.reference` is
left untouched and the function falls through to recompute `error =
ref.reference - (wheel.position - ref.origin)` against the SAME
(unchanged) reference and the SAME (unchanged, because the sample
never advanced) `wheel.position` — reproducing the previous call's
error exactly rather than integrating a phantom tick. This is
precisely the mechanism the issue's CORRECTION section and review
finding MK-03 describe ("skip the reference advance for a wheel whose
sample did not advance") and matches the K2 patch description in
`clasi/sprints/done/029-motion-profile-unification-one-shaper-one-floor-predictive-arrival/issues/done/kernel-reference-handling-twist-floor-stale-tick-antiwindup.md`
verbatim. Source reading, not a hardware measurement.

Interaction with sprint 030's glitch armor
(`src/core/encoder_glitch_armor.h`, gained explicit raw-zero rejection
this sprint): the armor operates upstream of this gate, inside
`Motor`/`Rig::tick()`-level sample collection — it decides whether a
raw encoder delta is trusted enough to update the cached
position/sampleTime at all. K2's `sampleAdvancedLeft_`/`Right_` flags
are computed from whether that collect (armor included) actually moved
`sampleTime`, so a sample the armor rejects (including now a rejected
raw-zero) is exactly the kind of tick K2 already treats as
"not advanced" — the two mechanisms compose correctly: the armor
decides freshness at the sensor layer, K2 protects the position
reference from integrating against whatever the armor did not accept.
No K2 code touches `encoder_glitch_armor.h` and no armor code touches
`positionError()`, so there is no double-counting or ordering hazard
between them. This is a source-reading conclusion (both files reviewed
side by side); it has not been exercised together on hardware or in a
combined host test in this ticket.

**2. Test coverage: no gap found.**
`tests/host/test_kernel_reference_handling.py::test_k2_frozen_sample_leaves_reference_unchanged_and_does_not_kick_duty`
already reproduces `profile_probe.cpp`'s own E5 scenario (300 counts/s
cruise, `kp == 0`) with LEFT's collect failing for exactly one tick
after settling, and asserts both halves of the transient the issue
describes: (a) `ref_after == pytest.approx(ref_frozen_tick, abs=1e-6)`
— the reference the tick immediately after the freeze sees is
unchanged from the freeze tick itself (K2's own claim), and (b)
`abs(duty_after - duty_frozen_tick) < 0.006` — duty does not step
toward the rail (the historical unfixed magnitude was ~+6 duty points
= 0.06 in this [-1,1] fraction; the test requires staying under a
tenth of that).

To confirm this test is not vacuous, I temporarily reverted K2's gate
in a scratch copy (`if (advanced)` -> `if (true)` in
`positionError()`, `src/core/diffdrive.cpp`, not committed) and reran
just that test: it failed exactly as expected, `ref_after`
295.1999816894531 vs expected 287.9999694824219 (a jump of ~7.2 counts
on the tick right after the freeze — the phantom-advance mechanism the
issue describes). The change was then reverted (`git diff` against
`src/core/diffdrive.cpp` is empty; nothing from this experiment is
committed). This is a source-level experiment run in this session, not
a hardware measurement.

`tests/host/test_frozen_encoder_hold.py`'s three tests cover the
adjacent, PLATFORM-layer fix (sprint 028: `NezhaMotorPort::collect()`
withholding the sample-time stamp so a frozen-but-acked read holds the
prior velocity instead of manufacturing a zero) — a different
mechanism (velocity PID chasing a phantom zero-velocity error) than
K2's position-reference integration, but the same "frozen tick"
family the issue's original (pre-CORRECTION) diagnosis named. Both
files together cover the two distinct frozen-encoder mechanisms in
play; no coverage gap was found and no new test was written for this
ticket.

Existing tests run in the foreground this session (both files, 11
tests, all passing):

```
uv run pytest tests/host/test_kernel_reference_handling.py tests/host/test_frozen_encoder_hold.py -v
...
11 passed in 4.58s
```

**3. Upstream (`radio-robot-elite`) sync status: not yet synced —
flagged, out of scope for sprint 031.**
`src/DESIGN.md` §2 (and the sprint 030 and sprint 031 design overlays,
which both carry the identical text with no revision since) state the
K1-K4 patches were "each implemented here with a diff staged for
upstream at
`docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`
(not yet opened as an upstream PR as of this ticket's own close)" —
referring to sprint 029 ticket 001's close. That staged patch file is
present in this repo's tree
(`docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`).
I found no reference anywhere in `clasi/sprints/done/030-*` or the
current `clasi/sprints/031-*` design overlays, tickets, or issues to
an opened upstream PR or a landed sync commit in `radio-robot-elite` —
grepped for `radio-robot-elite` and `kernel-patches-k1-k4` across
`clasi/`, `docs/`, and `src/`, and every hit points back at the same
staged-patch/not-yet-opened language. I have no access to the
`radio-robot-elite` checkout itself from this worktree to check its
history directly, so this is a source-reading conclusion within this
repo, not a check of the upstream repo. Per the ticket's own
instruction, I did not attempt the sync — flagging it here as
outstanding, same status as at sprint 029's close: the paired-PR
obligation from
`clasi/sprints/done/029-.../issues/done/decide-the-kernel-fork.md` has
not been discharged.

**Conclusion: K2 is confirmed landed and tested; the issue is closed.**
The stale-position-reference mechanism the issue's CORRECTION section
names cannot occur in the current kernel — `positionError()`'s
`advanced` gate structurally prevents the reference from ever
integrating against a wheel position that did not move — and an
existing, non-vacuous host test pins that behavior. The one open item
(upstream sync) is a process/coordination gap, not a code defect in
this repo, and is explicitly out of sprint 031's scope per the ticket
description.
