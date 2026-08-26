---
status: done
split_from: arc-moves-abort-distance-never-driven.md
sprint: '015'
tickets:
- 015-005
---

# A split move unwinds its own pivot at the phase handoff — the kernel's twist-hold reference is never re-armed

Priority: **High** — deterministic, mechanism identified in code, and the fix is
a one-liner in project-owned code. Affects every `move()` that splits.

Split from `arc-moves-abort-distance-never-driven.md`. Retitled twice as the
diagnosis moved: "stops short" -> "lost in the leg" -> **lost at the handoff**.

## The mechanism

`DifferentialDrive`'s twist-hold servo keeps an integrated reference of
commanded differential and trims the wheels toward it
(`diffdrive.cpp:585-612`). It arms once:

```cpp
if (!twistRef_.armed || twistRef_.epoch != epoch_) {
    twistRef_.reference  = 0.0f;
    twistRef_.originLeft = sampleLeft_.position;
    twistRef_.originRight= sampleRight_.position;
    ...
}
if (dt > 0.0f) twistRef_.reference += scaledTwist * dt;
const float twistError = twistRef_.reference - measuredTwistPosition;
trim = clampf(active_.twistHoldGain * twistError, -headroom, headroom);
```

**`twistRef_.armed` is cleared in exactly two places** — `kModeNeutral`
(`:528`) and `kModeRawDuty` (`:556`). A velocity-mode `drive()` call does **not**
disarm it, and `epoch_` bumps only on a cycle-gap re-anchor (`:466`).

Now compare the two paths:

- **Two separate commands.** The first move ends, `serviceMove()` calls
  `kernel_.neutral()`, the next `step()` runs `kModeNeutral`, `twistRef_` is
  **disarmed**, and the next `drive()` re-arms with a fresh origin. No unwind.
- **A split move's phase 1 -> phase 2.** `serviceMove()` calls `startSegment()`
  directly, which calls `kernel_.drive()`. **There is no `neutral()` between the
  phases**, so `twistRef_` survives with its *pre-pivot* origin and its
  accumulated pivot reference. Phase 2 commands `twist = 0`, so the reference
  stops growing — but `measuredTwistPosition` still carries the whole pivot.
  `twistError` is large and negative, and the trim actively drives the wheels to
  **unwind the pivot**, at `twistHoldGain` (2.0) times the error, clamped to
  headroom — which is *large* at that moment because phase 2's velocity is still
  ramping from 25%.

Fast, active, at the transition, with the robot essentially in place. Which is
exactly what the trajectory shows.

## Measured — tovez, one serial session, clears between

**A) Two-command control:** `RUN:turn:180` -> h = 180.7 deg (correct). Then
`RUN:go` -> heading moved **+0.3 deg** during the standalone leg. Total
181.0 deg. **Heading holds across the pair.**

**B) Single split move `arc:180`, full h(t) trajectory:**

| point | Δh from start | reading |
|---|---:|---|
| max during move | **+185.5 deg** | the pivot *overshoots* |
| at leg-start (first frame >20 mm displacement) | **+168.3 deg** | **−17.2 deg unwound, robot in place** |
| final | +168.7 deg | +0.4 deg during the actual leg |

The leg is innocent (+0.4 deg, matching the standalone leg's +0.3 deg). The
pivot overshoots by ~5.5 deg. **The loss is a 17.2 deg unwind at the handoff.**

Unwind exceeding overshoot is expected: `reference` integrates the *commanded*
scaled twist while `measured` is actual, so the taper phase — commanded twist
scaled down while the wheels coast — leaves `measured` running ahead of
`reference`. All of that mismatch is corrected at once when phase 2 opens the
headroom.

## Hypotheses tested and refuted, in order

1. **Stall latch / wrong-way abort** — refuted. `probe(2)` and `probe(25)` flat
   at baseline and after every arc.
2. **The deadline cutting the move short** — refuted. 2688 ms and 2625 ms
   against a 3500 ms budget; both ended ~800 ms early.
3. **The yaw taper crawling below breakaway** — refuted. With
   `setTaperWindows(400, 1)` (no yaw taper at all) the move still ended 6.9 deg
   short.
4. **Slow heading drift during the straight leg** — refuted by the h(t)
   trajectory. The leg contributes +0.4 deg.

## The fix

**In project-owned code, one line**: make the phase 1 -> phase 2 handoff in
`serviceMove()`/`queuePivotThenStraight()` issue `kernel_.neutral()` before
`startSegment()` for the pending phase — reproducing exactly the state the
two-command control proves is correct.

Do **not** fix this in `diffdrive.cpp`. That file is a vendored, byte-stable
copy of the radio-robot control kernel; a kernel-side change (re-arming
`twistRef_` when the commanded twist changes materially) would have to land
upstream in both repos. It may still be the right long-term fix — the stale
reference is a latent trap for *any* caller that changes twist without passing
through neutral — but it is an upstream conversation, not this ticket.

Second, smaller finding for whoever takes this: **the pivot overshoots by
~5.5 deg** before the unwind. Separate from the handoff bug and still open.

`serviceMove()`'s heading-blindness during phase 2 (`yawTarget == 0`, so the
whole yaw block is skipped) is the **enabling condition** — nothing measures or
corrects heading once phase 2 starts, so the unwind goes unobserved and the move
reports complete. Worth fixing too, but it is not the cause.

## Relationship to `rotation-error-is-injected-by-the-legs-not-the-pivots.md`

Weakened, not confirmed. That issue infers from camera truth that the residual
enters during the straight legs. This bench work shows the *split move's* loss
is at the handoff and the leg contributes ~0.3-0.4 deg. Those are compatible
only if the tour's leg-injected error comes from something other than this. The
two should be re-examined together once this fix lands — a tour whose corners
stop unwinding may simply not have a leg problem.

**Credit**: measured by the `blocks-local-codeserver-test` session on tovez
across three campaigns; mechanism identified in `diffdrive.cpp` by this session.

---

## OPEN — hardware confirmation, deferred to 2026-08-26 morning

The fix landed in sprint 015 ticket 005 (merged, v0.20260826.1): `serviceMove()`
now defers `startSegment()` by one service call at the phase 1 -> phase 2
handoff, so the caller's own `step(); serviceMove();` cadence delivers a real
~24 ms neutral tick and the kernel's `twistRef_` re-arms.

Note the naive fix does NOT work and was caught in implementation: a bare
`kernel_.neutral()` immediately followed by `startSegment()` changes nothing,
because both merely overwrite the kernel's `command_` and delivery happens on
the next `step()` — which `MotionEngine` never calls itself.

**Not yet confirmed on hardware.** No flash was attempted: a peer session's
instrumented rig was on tovez and flashing would have destroyed it. That session
has since ended.

**The check**, when someone has the board: flash master's current hex, run a
split move of the `move(20, 180)` shape, and capture the h(t) trajectory.

| measure | before the fix (tovez, measured) | prediction after |
|---|---:|---:|
| peak heading during move | +185.5 deg | ~ +185 deg (overshoot is a separate, still-open finding) |
| peak -> leg-start | **−17.2 deg** | **~0 deg** |
| final heading | +168.7 deg | ~ +180 deg |

The peer's `RUN:arc:<deg>` verbs in `projects/blocktest` are the right
instrument; this repo's `test/test.ts` has no split-move verb (`RUN:pivot` is a
pure pivot and the tours use separate commands), so either re-flash that rig or
add an equivalent verb first.

Still open regardless of this fix: the **~5.5 deg pivot overshoot** before the
unwind, and `serviceMove()`'s heading-blindness during phase 2 (`yawTarget == 0`
skips the whole yaw block), which is the enabling condition rather than the
cause.
