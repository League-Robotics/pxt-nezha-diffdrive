---
source_file: DESIGN.md
source_hash: 717179b52ed99288d78ba18adbc8569ecb077b49a3bf2cd7b01439cf608ccdd4
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -130,7 +130,17 @@
   `setRampMs`).
 - Geometry: `countsPerMm() = 10 / travelCalib`;
   `effectiveTrackWidth() = trackWidth / rotationalSlip`, a method,
-  deliberately never cached.
+  deliberately never cached. **Sprint 007**: `rotationalSlip` gains
+  `setRotationalSlip(float)`, validated `>0` exactly like
+  `setTrackWidth()`/`setTravelCalib()` (invalid values silently
+  ignored, prior value retained) — closing the one geometry field that
+  had a getter but no setter (API-06: the doctrine already named
+  `rotationalSlip` as the only correct turn-calibration knob, but no
+  caller anywhere could reach it). Reachable from `shims.cpp` through
+  the existing generic `ConfigField`/`kFields` mechanism (§5, §9), not
+  a new dedicated `setGeometry()`-style shim — this field is a
+  one-time chassis-calibration constant for a non-reference kit, not a
+  value tuned as routinely as `trackWidth`/`travelCalib`.
 - `PoseSource` — the three-read world-pose port (`x()/y()/heading()`),
   implemented by `OtosPort` on hardware, `EncoderPoseSource` on
   hardware without an OTOS (sprint 006, §7/§9), and `FakePoseSource`
@@ -180,7 +190,17 @@
 allocation, no `std::string`), enforces case-as-direction (commands
 UPPERCASE, replies lowercase), and dispatches an 18-entry verb table:
 HELLO, PING, ID, VER, STATUS, HELP, GET, SET, TLM, WHEELS_X, WHEELS_V,
-MOVE_X, MOVE_V, GO_TO_R, GO_TO_W, STOP, ESTOP, RUN.
+MOVE_X, MOVE_V, GO_TO_R, GO_TO_W, STOP, ESTOP, RUN. **Sprint 007**:
+`kCommandTable`'s size is now derived (`static const VerbEntry
+kCommandTable[];`, defined with a deduced size plus a `static_assert`
+pinning the expected count) instead of the size being hand-written
+twice (declaration and definition both said `[18]`) — closing WIRE-09:
+removing a verb without updating both `[18]`s used to compile silently
+and zero-fill the vacated slot, which `strcmp()`s a `nullptr` on the
+first lookup that reaches it (a hard fault on the robot, for every
+command). No verb is added, removed, or reordered by this change — the
+18 names above are unchanged; only how the array's size is spelled
+changes.
 
 **Reliability layer.** Every sequenced verb carries a mandatory
 trailing `#<id>`, strictly incrementing from 1. Handler state is
@@ -255,15 +275,42 @@
 a runaway"); WHEELS_X/MOVE_X/MOVE_V/GO_TO_R/GO_TO_W → the
 `engineXxx()` forwards onto the `MotionEngine` singleton. `cruise`/
 `speed` handling is uniform: negative → `kRange`; zero → the
-configured default via `engineDefaultCruiseMmS()` (full-duty velocity
-in mm/s), refused `kRange` if that too is unconfigured. **Sprint 006**:
+configured default via `engineDefaultCruiseMmS()`, refused `kRange` if
+that too is unconfigured. **Sprint 007**: `engineDefaultCruiseMmS()`
+no longer derives from `fullDutyVelocity` (the kernel's ~875 mm/s
+100%-duty rail) — it now reads a new, independently configured
+`defaultCruiseMmS_` field (`shims.cpp` Rig state, seeded 150 mm/s to
+match the block layer's own `defaultSpeed`), closing R-11/BLK-03/API-03:
+the wire's "0 = configured default" convenience sentinel and the
+kernel's unrelated "0 = uncalibrated, refuse" sentinel on
+`fullDutyVelocity` were two different meanings of zero collapsed onto
+one field — a spec-following host sending `cruise 0` got the fastest,
+least-controlled move the robot can make instead of a sane default.
+The four verb handlers' refusal-on-`<=0` logic above is **unchanged**;
+only the value it reads changed. **Sprint 006**:
 GO_TO_W no longer answers `kUnimplemented` for "no OTOS connected" —
 `engineGoToW()` now falls back to `EncoderPoseSource` on any robot
 without a live OTOS (§7/§9), so this handler always dispatches to
 `MotionEngine::goToW()`. `mradToRad()`
 here is the **single** place wire milliradians become radians.
-GET/SET map 15 snake_case wire names 1:1 onto the `ConfigField`
-ordinals (`kFields` table); STATUS packs diag booleans into a local
+GET/SET map snake_case wire names 1:1 onto the `ConfigField` ordinals
+(`kFields` table) — 15 through sprint 006, **18 as of sprint 007**:
+`default_cruise` (ordinal 15, backed by the new `shims.cpp` Rig field
+above, not `kernel.config()`), `rotational_slip` (ordinal 16, backed
+by `MotionEngine::setRotationalSlip()`/`rotationalSlip()`, §3), and
+`stall_clear` (ordinal 17, a write-triggered action wearing a
+config-field's clothes: `SET stall_clear <nonzero>` calls
+`DifferentialDrive::clearStallLatch()`, already existed, previously
+had no caller anywhere in the package outside a test shim; its GET
+side is a convenience readback of `stallHalted`, not a stored value —
+alongside the pre-existing STATUS `flags` bit 2 and `probe(2)`, now
+documented, this is the third independent way to read the stall
+latch's state). `stall_clear` is deliberately **not** a new top-level
+wire verb and is **not** folded into `clearEmergencyStop()`/`ESTOP`
+(§9) — the stall latch and the e-stop latch are semantically distinct
+fault classes, same principle sprint 006 established for
+`deliverStopNow()` deliberately not touching `estopLatch_`. STATUS
+packs diag booleans into a local
 `flags` word and, since sprint 004 ticket 004, an honest `otos=`
 (`otosGet(7) != 0`, replacing a hardcoded `false` that predated any
 wire-reachable OTOS check — R-22/WIRE-06) plus a decimal `i2cf=` fault
@@ -595,7 +642,38 @@
   `settle-tick-loop-is-not-host-testable` (sprint 008) plans to extract
   its logic into a host-portable helper, and this sprint's own stop-
   delivery fix (below) is placed elsewhere specifically so it does not
-  collide with that future extraction.
+  collide with that future extraction. **Sprint 007**: `tickDrive()`'s
+  return value changes from raw post-`serviceMove()` move-engine state
+  to `commandLooksActive(r)` (the same helper the starvation watchdog
+  below already used and proved correct in production — move-engine
+  active **or** nonzero applied duty), closing R-10/API-01: the
+  documented `while (diffDrive.driveTick())` continuous-drive idiom
+  (README, spec §4.2, UC-002) exited on its first iteration, because
+  `wheelsV()`/`wheelsX()` clear the move planner before `tickDrive()`
+  is ever called, so raw move-engine state read `false` immediately.
+  `commandLooksActive()`'s existing "or nonzero applied duty" clause is
+  exactly what a continuous-mode command needs; for a position-mode
+  move's final tick, the settle loop just above already drives
+  `appliedDutyLeft/Right` to zero before this function returns, so the
+  documented "a move's final tick still returns false, ending the loop
+  on the same call that finishes the move" behavior is preserved with
+  no new logic. No doc site's prose changes meaning — see §13's Design
+  Rationale.
+- **Stall latch clear + readback** (new, sprint 007): the kernel's
+  `clearStallLatch()` and `Output.stallHalted` already existed and were
+  already correct (R-01/API-02's finding was a **missing caller**, not
+  missing kernel logic) — `clearStallLatch()`'s only caller anywhere in
+  the package was a host-test shim, and the only readback was an
+  undocumented `probe(2)`. Two thin new `shims.cpp` forwards close
+  this: `clearStall()` (calls `kernel.clearStallLatch()`) and
+  `isStalled()` (returns `kernel.output().stallHalted`), each reachable
+  from a dedicated `main.ts` Drive-group block (`clearStallLatch()`,
+  `isStalled()`) parked next to `emergencyStop()`/`clearEmergencyStop()`
+  — and, on the wire, `stall_clear`'s new `kFields`/`ConfigField`
+  ordinal (§5) reaches the same `clearStallLatch()` call via
+  `setKernelValue()`'s ordinal 17. Deliberately **not** folded into
+  `clearEmergencyStop()`/`ESTOP` — see §13's Design Rationale for why
+  the two latches stay separate.
 - **Stop delivery** (sprint 006, new): `stopAll()`/`endMove()`
   (`stop`/`stop move`) and `updateMove()`'s own move-completion branch
   (the `isMoving()`/`move progress` poller's path, which can end a move
@@ -628,8 +706,16 @@
 - **Wire bridges**: `setWheelsTimed`/`driveTwistTimed` (duration =
   lease), the six `engineXxx()` forwards, `engineDefaultCruiseMmS()`,
   `diagValue()` (the DIAG/STATUS ordinal table),
-  `getConfigValue`/`setKernelValue` (the ×1000 table), `probe()`,
-  taper/ramp setters, `wheelSpeed()`.
+  `getConfigValue`/`setKernelValue` (the ×1000 table, 15→18 ordinals as
+  of sprint 007 — see §5), `probe()`, taper/ramp setters, `wheelSpeed()`.
+  **Sprint 007**: `engineDefaultCruiseMmS()` no longer derives from
+  `fullDutyVelocity`; it returns a new `defaultCruiseMmS_` Rig field
+  (seeded 150 mm/s), settable/gettable through `setKernelValue`/
+  `getConfigValue` ordinal 15 (§5). `diagValue(2)` (`stallHalted`,
+  already existed) gains a name in `probe()`'s doc comment instead of
+  staying an undocumented magic index. `diagValue()`'s own switch has
+  its spliced `case 25` (between the "23/24" comment and cases 23/24)
+  reordered — a reader trap, no behavior change.
 - **OTOS surface**: a lazy singleton **separate from Rig** (usable
   without starting the drive), `otosBegin/otosRead/otosGet/otosZero/
   otosCalibrate/otosSetOffset`, `seedPose()` (writes **both** pose
@@ -655,8 +741,31 @@
 
 - Continuous-mode commands (`setWheelSpeeds`/`driveTwist`) only move
   the robot while a `while (diffDrive.driveTick())` loop ticks;
-  blocking moves tick internally. `startMove`/`startGoTo` + polling
-  does **not** advance a move by itself — a documented tick-model gap.
+  blocking moves tick internally. **Sprint 007**: this is now true in
+  fact, not only in prose — `driveTick()`'s return contract fix above
+  is what makes it true; the simulator's own `_tickDrive()` gets the
+  same fix (returns "does anything still look commanded" — sim move
+  active, or nonzero `simVel`/`simYawRate` — instead of raw sim
+  move-engine state) so the browser and hardware idioms match.
+  `startMove`/`startGoTo` + polling does **not** advance a move by
+  itself — a documented tick-model gap, unchanged this sprint.
+- **Sprint 007, simulator/hardware parity**: `_setWheels`' sim body
+  drops a stray `/10` in its yaw-rate term (`(right-left)/10/track`
+  → `(right-left)/track`) that made simulator turns 10× slower than
+  hardware for the same `set wheel speeds` call (R-12/BLK-06) — the
+  formula now matches `_driveTwist`'s own, already-correct sim math. A
+  new `simEstopped` flag, set in `_estopAll()` and cleared in
+  `_estopClear()`, gates `_setWheels`/`_driveTwist`/`_startMove`
+  (checked, no-op while set) — mirroring hardware's intake-time
+  refusal (`checkCommandable()`'s `estopLatch_` gate) so
+  `emergency stop` now refuses further motion in the browser exactly
+  as it does on hardware (R-13/BLK-07); previously the simulator
+  refused nothing, so the UC-011 "forgot to clear" trap was invisible
+  exactly where students develop.
+- **Sprint 007**: `runArgCount()` gains the null guard its sibling
+  `runArgText()` already had (`if (!runParts) return 0`) — closing
+  R-15/BLK-02, a documented silent-boot-death (panic 980) class for any
+  call before the first RUN event registers a handler.
 - `goToWorld()` is this project's own TS-level closed-loop heuristic
   (one pass, pivot-first beyond 12°, curvature capped at 25°,
   residual error inherited by the next hop) — deliberately a separate
@@ -708,6 +817,33 @@
   restarts the 0x46 counter near zero — remains unconfirmed absent a
   bench run; see `brick-reset-odometry-teleport.md` and sprint 006's
   bench-checklist ticket.
+- **(New, sprint 007)** The review's Design assessment names a broader
+  opportunity this sprint deliberately does not build: e-stop, the
+  stall latch, the starvation watchdog's soft-stop, and lease expiry
+  are four distinct "robot is off" states a student currently
+  distinguishes only by reading separate readbacks; a single unified
+  "why won't it move" surface could retire the whole class. Excluded
+  this sprint because the watchdog's soft-stop is **deliberately
+  non-latching** (§9) while the other three latch/expire — a unified
+  reporter needs to represent that asymmetry correctly, which is a new
+  design question (enum? bitmask? which ordinals feed it?) this
+  sprint's research did not narrow down enough to ticket safely. Three
+  of the four states are now independently readable after this sprint
+  (e-stop: STATUS flags bit 1; stall: STATUS flags bit 2 / DIAG
+  ordinal 2 / `stall_clear` GET, §5/§9; the settle loop's own
+  stop-delivery fix, sprint 006) — a future sprint would design the
+  aggregation, not invent readbacks from scratch.
+- **(New, sprint 007)** `default_cruise`'s seed value (150 mm/s,
+  matching the block layer's `defaultSpeed`) is a planning-time choice,
+  not a measured one — if a bench host's own idea of a sane default
+  differs from the block layer's, this is the constant to revisit.
+- **(New, sprint 007)** `pxt.json`'s `microphone` dependency's true
+  purpose is genuinely unknown — two independent code-review passes
+  found no reference to it anywhere in `src/`/`test/`, and disagreed
+  with each other on whether that means it is dead. Documented, not
+  deleted (`specification.md` §2); flagged here in case the stakeholder
+  has out-of-band knowledge this review process cannot see from source
+  alone.
 
 ## 11. Host-vs-target language standard (a standing build-gate constraint)
 
@@ -866,3 +1002,166 @@
 change than this sprint's scope); ticket 002 should add a host test
 confirming a corrupted collect during this window is counted, not
 silently accepted as a valid sample.
+
+## 13. Sprint 007 — architecture diagram and change summary
+
+Substantial-tier sprint update (see `sprint.md`'s Architecture section
+for the sizing decision). Six issues from the 2026-08-23 code review's
+API-contract cluster, sharing one boundary: student-observable surface
+(blocks, wire verbs, the browser simulator, and the doc sites that
+describe all of it). No new module is introduced; the vendored kernel
+(`diffdrive.{h,cpp}`) stays byte-unchanged throughout, so no cross-repo
+resync is triggered.
+
+**Sprint Changes (recap — module level; see §3/§4/§5/§9/§10 above for
+detail):**
+
+- `shims.cpp` — two new thin kernel forwards (`clearStall()`,
+  `isStalled()`); a new `defaultCruiseMmS_` Rig field + accessors
+  replacing `engineDefaultCruiseMmS()`'s old `fullDutyVelocity`
+  derivation; `tickDrive()`'s return expression changes to
+  `commandLooksActive(r)`; three new `setKernelValue()`/
+  `getConfigValue()` ordinals (15/16/17); `diagValue()`'s spliced
+  `case 25` reordered; two wire-boundary casts clamped (WIRE-08).
+- `motion_engine.h` — `MotionEngine::setRotationalSlip(float)`,
+  validated `>0`.
+- `wire_adapter.cpp`/`.h` — `kFields` grows 15→18
+  (`default_cruise`/`rotational_slip`/`stall_clear`); no forward
+  declarations added.
+- `wire_handler.h`/`.cpp` — `kCommandTable`'s size becomes derived
+  (`kVerbCount` + `static_assert`) instead of hand-counted; no verb
+  added, removed, or reordered.
+- `main.ts` — two new Drive-group blocks (`clearStallLatch`,
+  `isStalled`); three new `ConfigField` entries; `runArgCount()`'s
+  null guard; `_setWheels`'s corrected yaw-rate formula; a new
+  `simEstopped` latch gating three sim bodies; `_tickDrive()`'s return
+  expression fixed in step with `tickDrive()`'s; `maxNudges` deleted;
+  `goToWorld()`'s JSDoc corrected.
+- `tsconfig.json` — gains `pxt_modules/core/serial.ts`.
+- `tests/host/wire_motion_verb_shim.cpp` — `engineDefaultCruiseMmS()`'s
+  test double updated in lockstep with the real one (required, not
+  optional — see Migration Concerns).
+
+**No new component/module diagram.** Every edge this sprint uses
+already exists and is already drawn in §1 (`wire_adapter.cpp` →
+`shims.cpp` forward declarations; `shims.cpp` → `MotionEngine`;
+`main.ts` → `shims.cpp` via `//%` shims). Nothing new is composed —
+three named fields join an existing flat table, one return expression
+changes, one array becomes derived-size. A diagram would redraw the
+current module graph with no new nodes or edges, which clarifies
+nothing beyond what §1 already shows (the same reasoning sprint 020's
+own architecture doc used to omit its diagram).
+
+**No entity-relationship diagram** — no persistent data model exists
+in this embedded package (nothing survives a power cycle), and this
+sprint doesn't change that. The wire protocol's *field* model does
+change; shown as a table instead of an ERD, since `kFields`/
+`ConfigField` is a flat name→ordinal list, not an entity graph:
+
+| Ordinal | Wire name | Enum member | Backing store | New? |
+|---|---|---|---|---|
+| 0–14 | (existing 15) | (existing) | `kernel.config()` | no |
+| 15 | `default_cruise` | `DefaultCruise` | `shims.cpp` Rig field | **yes** |
+| 16 | `rotational_slip` | `RotationalSlip` | `MotionEngine` field | **yes** |
+| 17 | `stall_clear` | `StallClear` | kernel action (no storage) | **yes** |
+
+Ordinal 17's GET side is a convenience readback of `stallHalted`, not
+a stored value — it is an action wearing a config-field's clothes (see
+Design Rationale below).
+
+**No dependency-direction graph** beyond the statement above:
+dependency direction is unchanged (Presentation/wire → MotionEngine →
+Kernel/ports, kernel at the bottom); every new call this sprint adds
+travels an edge that already existed in that direction.
+
+**Migration concerns.** One real wire-behavior change, not internal:
+a bench host or Python tool that has learned to send `cruise 0`
+*because* it wants full-duty speed will get ~150 mm/s instead once
+`default_cruise` ships — the entire point of the fix. No in-tree tool
+sends a literal `cruise 0` for that reason today (not exhaustively
+checked — grepping `tools/` for a literal `0` fourth-field pattern is
+cheap due diligence before merging, not a blocker). No other verb's
+wire-visible behavior changes: the four motion verbs' refusal-on-`<=0`
+logic is untouched, only the value it reads changed.
+`tests/host/wire_motion_verb_shim.cpp`'s `engineDefaultCruiseMmS()`
+test double **must** be updated in the same ticket that changes the
+real one, or `test_wheels_x_cruise_zero_uses_configured_default` and
+its `MOVE_X`/`GO_TO_R` siblings keep silently validating the OLD,
+wrong contract forever — the single highest-risk item in this sprint,
+because a missed test-double update produces a fully green suite that
+proves nothing about the actual fix. No data persists across power
+cycles anywhere in this system today, so the two new configured fields
+carry no migration question beyond "what do they default to" (answered
+above).
+
+**Design Rationale (selected decisions — see `sprint.md`'s own
+Architecture section for the condensed version a reader of that file
+alone would need):**
+
+*Decision: `tickDrive()`'s contract is "return whether anything still
+looks commanded," not a new `driveHold()` idiom.* Alternatives were (a)
+redefine the return to `commandLooksActive()` [chosen] or (b) add a
+`driveHold()`/similar idiom and leave `driveTick()`'s return as
+move-progress-only, rewriting all four doc sites. (a) requires zero
+doc-text rewrites — the README, spec §4.2, and UC-002 already describe
+this exact contract; they were aspirational, not wrong, before the
+code caught up — and reuses a helper already proven correct in
+production by the starvation watchdog, with the settle loop (§9)
+already driving `appliedDuty` to zero exactly when a position-mode
+move's final tick needs the loop to end. (b) would add a second
+continuous-mode idiom to teach and contradict `testrig.ts`'s existing
+bare-tick usage, for no behavioral gain over (a). Consequence: doc
+sites need confirmation edits (a cross-reference to the new regression
+test), not content rewrites.
+
+*Decision: the stall latch gets a dedicated block + a SET-able wire
+field, not a new top-level verb, and is not folded into
+`clearEmergencyStop()`.* Folding in is rejected on the same principle
+sprint 006 established for `deliverStopNow()` deliberately not
+touching `estopLatch_` — the stall latch and the e-stop latch are
+semantically distinct fault classes; blurring their clear paths
+reintroduces exactly the ambiguity that decision fixed for a different
+pair. A brand-new top-level wire verb is rejected because this project
+has no existing precedent for a wire-level "clear a latch" verb at all
+(even `estopClear()` is block-only today), and this sprint is already
+resizing `kCommandTable` for WIRE-09 in the same sprint — adding a row
+to a table this sprint is simultaneously trying to make less fragile
+is avoidable risk for no gain over the SET-action route the review's
+own remedy text names as sufficient. Consequence: `stall_clear` shows
+up in the generic `set config` dropdown alongside the dedicated block
+— a minor, accepted UI redundancy, not a defect.
+
+*Decision: `default_cruise` is a new, independent field, not a
+reinterpretation of `fullDutyVelocity`.* The wire's "0 = configured
+default" convenience sentinel and the kernel's unrelated "0 =
+uncalibrated, refuse" sentinel on `fullDutyVelocity` are two different
+meanings of zero that never need to coexist in one read — they're
+consumed in unrelated code paths (`checkCommandable()`'s calibration
+gate vs. `engineDefaultCruiseMmS()`'s substitution). Splitting them is
+the review's own stated remedy and requires no change to the four verb
+handlers' existing, already-correct refusal-on-`<=0` logic — only the
+value `engineDefaultCruiseMmS()` returns changes.
+
+*Decision: `rotationalSlip` gets the generic `ConfigField` escape
+hatch, not a dedicated "set turn slip" block.* This is a one-time
+chassis-calibration constant for a teacher/builder setting up a
+non-reference kit, not a value tuned as routinely as
+`trackWidth`/`travelCalib` (which chose the dedicated-block route
+precisely because they are the common case). The review's own text
+accepts "at minimum... `ConfigField`" as sufficient. Consequence: the
+measurement-derivation comment travels with the field, corrected per
+`verify-comments.md`'s CHALLENGE (the 0.915 ratio → 120.0 mm effective
+track → 0.952 slip bridge, previously missing from the in-tree
+comment) so a future re-measurer does not "fix" 0.952 back to 0.915.
+
+**Risk (known, not newly introduced):** none specific to this sprint's
+own changes — every kernel primitive this sprint reaches
+(`clearStallLatch()`, `Output.stallHalted`, `checkCommandable()`)
+already existed and was already correct, and `tickDrive()`'s settle
+loop (sprint 006) already produces the exact zero-duty state the new
+return expression depends on. The one item worth tracking is
+procedural, not architectural: a ticket that changes
+`engineDefaultCruiseMmS()` without also updating
+`tests/host/wire_motion_verb_shim.cpp`'s mirror leaves a fully green
+host suite that has stopped testing the real contract — called out
+above and in the corresponding ticket's acceptance criteria.
```
