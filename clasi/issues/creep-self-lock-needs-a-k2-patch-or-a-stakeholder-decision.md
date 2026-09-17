---
status: pending
---

# Creep self-lock below breakaway: confirmed in host-sim; no safe MotionEngine-level fix exists — needs a K2 patch or a stakeholder decision

Follow-up from sprint 039 ticket 006
(`clasi/sprints/039-nudge-mode-sub-floor-micro-moves-for-calibratel/
tickets/done/006-creep-self-lock-host-sim-stiction-plant-investigation.md`),
closing out
`clasi/sprints/039-nudge-mode-sub-floor-micro-moves-for-calibratel/
issues/slow-continuous-creep-self-locks-below-breakaway.md` per that
sprint's own NO-fix fallback ("closes as a documented recommendation
... with a follow-up issue for the kernel-patch decision").

## What ticket 006 found

A host-sim stiction plant (`tests/host/motion_engine_nudge_stiction_
shim.cpp`'s `StictionMotor`, extended with a `withholdStampOnStiction`
mode that mirrors `NezhaMotorPort::collect()`'s real stamp-withholding
behavior — `src/platform/nezha_port.cpp:391-406`) **confirms** the
suspected K2 mechanism
(`tests/host/test_creep_self_lock_stiction_sim.py::
test_creep_below_breakaway_self_locks_with_stamp_withholding`): a
creep commanded below breakaway never moves for the whole hold, and a
**refutation control** in the same file
(`test_creep_recovers_when_stamp_is_not_withheld`) shows the *same*
rig recovers once K2's `advanced` gate is bypassed — isolating the
lock to K2's guard specifically, not the plant, gains, or shaper.

**The sprint plan's own suggested fix location is a dead end**, proven
both by source reading and by a third host-sim test
(`test_hold_vfloor_value_has_no_effect_on_commanded_ramp`): the
continuous-hold branch of `MotionEngine::service()`
(`src/motion/motion_engine.cpp`, the `shaper_.advance(hold_.dominant,
-1.0f, 0.0f, limits_.vMax, dt, limits_, -1.0f)` call) hardcodes
`remain = -1.0f`. `VelocityShaper::advance()`'s floor-snap step is
gated on `remain >= 0.0f` (`src/motion/velocity_shaper.cpp`, step 4),
so the `floor` VALUE passed there is provably inert for a continuous
hold — changing `0.0f` to `limits_.vFloor` would change nothing.

Making a floor genuinely apply to a Hold would need a structural
change (e.g. passing a large sentinel instead of `-1.0f` for `remain`),
and that reverses a **deliberate, pinned design decision from sprint
029 ticket 002**:
`tests/host/test_velocity_shaper.py::
test_continuous_hold_has_no_floor_and_never_arrives` asserts the
opposite property as intentional — "a continuous hold below the floor
is a legitimate request, e.g. a student's own slow WHEELS_V". Ticket
006 had no standing to reverse that decision, so it did not.

## What's left

The only mechanism that would actually make a sub-breakaway creep
MOVE is inside K2 itself (`DifferentialDrive::positionError()`,
`src/core/diffdrive.cpp:955-991`) — vendored, out of scope for a
sprint-039-sized ticket. Two paths forward, not mutually exclusive:

1. **K2 patch** (paired-upstream-patch process, or an explicit
   stakeholder decision per `.claude/rules/fiber-yield-safety.md`'s
   "Related invariants"): let the position reference re-anchor (not
   integrate against a stale measurement, but also not freeze the
   error at exactly its pre-stall value forever) on a driven-but-
   frozen tick, so the I-term still has SOME signal to wind up on. This
   is the durable fix and the one the issue's own source reading
   pointed at from the start.
2. **Stakeholder decision on the sprint-029 trade-off**: is "a
   continuous hold below the floor is legitimate and may simply not
   move" still the right contract now that nudge mode exists
   (sprint 039 tickets 004/005, `MotionEngine::beginNudge()`/
   `serviceNudge()`)? If sub-floor sustained motion is *never* actually
   wanted anymore (nudge mode is the intended tool for exactly that
   case), the fix might not be "make the wheel move" at all, but a
   small MotionEngine-level **fail-fast/observable** improvement: a
   Hold-specific no-progress detector (distinct from the kernel's own
   `stallDemand`, which never arms at creep speed) that ends a
   self-locked hold and reports it, instead of silently spinning to
   the caller's own timeout (30 s in the `calibrateL` capture). This
   does not touch K2 or reverse the pinned floor decision, and is
   worth scoping as its own small ticket if wanted — it was noted but
   not implemented by ticket 006, to keep that ticket's own scope to
   investigation plus a fix ONLY where one was safe and small.

## Evidence

- Hardware anchor (cited exactly, not re-derived):
  `captures/calibratel-vevov-20260915/bench-log.md` run 5 — `i2cf`
  1247 -> 2493 (delta 1246) over `cyc` 1414 -> 2666 (delta 1252) during
  a -4 cm/s / 30 s reverse creep, camera frame `after-back2.jpg`
  showing the robot unmoved.
- Host-sim artifact (SIM, not hardware):
  `tests/host/test_creep_self_lock_stiction_sim.py`, all three tests
  passing as of sprint 039 ticket 006.
