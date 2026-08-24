---
source_file: DESIGN.md
source_hash: d67e1726421a7b8f39abfe82b7c7b1b482eacb5d864c082cda848beb44fa74a4
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 004, currently in review, not yet merged; sprint 005 roadmapped, not yet detail-planned)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 004, closed and merged; sprint 005 roadmapped, not yet detail-planned; sprint 006 detail-planned — motion correctness: goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W — not yet executed)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -20,10 +20,12 @@
 |---|---|---|
 | Kernel | `diffdrive.h/.cpp` | `<cstdint>`/`<cmath>`/`<algorithm>` only — **no I2C, no CODAL, no MakeCode, no geometry** |
 | Motion engine | `motion_engine.h/.cpp` | `diffdrive.h` + libc only — host-portable |
+| Encoder glitch armor (sprint 006) | `encoder_glitch_armor.h` | libc only — host-portable, no project includes at all |
+| Encoder pose source (sprint 006) | `encoder_pose_source.h` | `motion_engine.h` + libc only — host-portable |
 | Wire grammar | `wire_handler.h/.cpp` | libc only — host-portable, no project includes at all |
 | Wire adapter | `wire_adapter.h/.cpp` | `wire_handler.h` + libc — host-portable; reaches hardware only through forward-declared `shims.cpp` free functions |
 | Transports | `serial_transport.*`, `radio_transport.*` | CODAL (`pxt.h` in the .cpp) — know bytes and framing, **nothing** about verbs, grammar, or motion |
-| Hardware ports | `nezha_port.*`, `otos_port.*`, `platform_ports.h` | `pxt.h` + the port interfaces they implement — know I2C/CODAL, nothing about blocks or the wire |
+| Hardware ports | `nezha_port.*`, `otos_port.*`, `platform_ports.h` | `pxt.h` + the port interfaces they implement — know I2C/CODAL, nothing about blocks or the wire; `nezha_port.cpp` additionally calls into `encoder_glitch_armor.h` above (a dependency on a lower, host-portable layer, not membership in this one) |
 | Protocol composition | `protocol.h/.cpp` | everything above — the CODAL fiber that plumbs transports into the wire stack |
 | Shim + blocks | `shims.cpp`, `main.ts` | everything — the composition root and the student-facing API |
 
@@ -96,10 +98,25 @@
   |rotation| ≥ 50° with nonzero distance splits into pivot-then-
   straight, one caller-visible call, one shared deadline);
   `moveV(vx, omega, duration)`; `goToR(x, y, speed, arrive, timeout)`
-  (plain arc reduction, `arrive` accepted but unused — single-shot,
-  no supervisory re-solve); `goToW(pose, …)` (reads a caller-supplied
-  `PoseSource` **once**, rotates world delta into the body frame,
-  delegates to `goToR`).
+  (single-shot, no supervisory re-solve). **Sprint 006**: `goToR` now
+  owns its own split decision instead of inheriting `moveX`'s generic
+  one — `moveX`'s pivot-then-straight split reissues the arc's own
+  `(s, theta)` as pivot-then-straight, which reaches a different
+  endpoint than the blended arc whenever the split threshold fires
+  (the arc-length `s` is not the chord length except in the limit);
+  `goToR` above the threshold instead issues pivot = `atan2(y, x)`
+  (the line-of-sight bearing) then chord = `hypot(x, y)` straight,
+  which reaches `(x, y)` exactly by construction. `theta` is
+  normalized to the short arc (±180°) before the split decision, so a
+  behind-the-robot target pivots at most ~180° instead of the long way
+  around. `arrive` is now honored as a radial no-op gate
+  (`hypot(x, y) <= arrive` returns without issuing a segment) — still
+  single-shot, no supervisory re-solve; a caller wanting repeat-until-
+  arrival re-issues `goToR()` itself, unchanged from before.
+  `goToW(pose, …)` (reads a caller-supplied `PoseSource` **once**,
+  rotates world delta into the body frame, delegates to `goToR`) is
+  unaffected by this change other than inheriting `goToR`'s corrected
+  geometry.
 - Move servicing: `serviceMove()` — one advance per control cycle
   while active: rescales taper/ramp, re-issues `kernel_.drive()`
   **every tick** with a rolling 500 ms lease (gating on scale change
@@ -114,10 +131,22 @@
   `effectiveTrackWidth() = trackWidth / rotationalSlip`, a method,
   deliberately never cached.
 - `PoseSource` — the three-read world-pose port (`x()/y()/heading()`),
-  implemented by `OtosPort` on hardware and `FakePoseSource` in tests.
-  `MotionEngine` holds no `PoseSource` of its own; it is passed per
-  `goToW()` call, which is what makes the class host-testable with no
-  OTOS in the link.
+  implemented by `OtosPort` on hardware, `EncoderPoseSource` on
+  hardware without an OTOS (sprint 006, §7/§9), and `FakePoseSource`
+  in tests. `MotionEngine` holds no `PoseSource` of its own; it is
+  passed per `goToW()` call, which is what makes the class
+  host-testable with no OTOS in the link. **Sprint 006**: the
+  interface's `heading()` contract can no longer state a single wrap
+  convention now that two hardware implementations disagree by
+  construction — `OtosPort` reports heading wrapped to (−π, π] (the
+  chip's own int16 register), `EncoderPoseSource` reports the same
+  unwrapped heading `shims.cpp`'s odometry already carries. Both are
+  contractually valid because `goToR()`/`goToW()` consume `heading()`
+  only through `cos()`/`sin()` (wrap-invariant); the header comment now
+  says so explicitly instead of asserting one universal convention —
+  a caller that ever *differences* two `heading()` reads (rather than
+  taking their cos/sin) must not assume a shared wrap convention across
+  implementations.
 
 **Key state.** `MoveState` (segment targets in counts, ramp start,
 pending second phase, one `deadline` spanning both phases). Geometry
@@ -226,9 +255,11 @@
 `engineXxx()` forwards onto the `MotionEngine` singleton. `cruise`/
 `speed` handling is uniform: negative → `kRange`; zero → the
 configured default via `engineDefaultCruiseMmS()` (full-duty velocity
-in mm/s), refused `kRange` if that too is unconfigured. GO_TO_W with
-no connected OTOS answers `kUnimplemented` (recognized, not wired on
-this build) rather than driving toward a garbage pose. `mradToRad()`
+in mm/s), refused `kRange` if that too is unconfigured. **Sprint 006**:
+GO_TO_W no longer answers `kUnimplemented` for "no OTOS connected" —
+`engineGoToW()` now falls back to `EncoderPoseSource` on any robot
+without a live OTOS (§7/§9), so this handler always dispatches to
+`MotionEngine::goToW()`. `mradToRad()`
 here is the **single** place wire milliradians become radians.
 GET/SET map 15 snake_case wire names 1:1 onto the `ConfigField`
 ordinals (`kFields` table); STATUS packs diag booleans into a local
@@ -344,7 +375,7 @@
 no semantics. Siblings under Protocol, deliberately uncoupled from
 each other.
 
-## 7. Hardware ports — `nezha_port.*`, `otos_port.*`, `platform_ports.h`
+## 7. Hardware ports — `nezha_port.*`, `otos_port.*`, `encoder_glitch_armor.h`, `platform_ports.h`
 
 **NezhaMotorPort** (`DiffDrive::Motor` over I2C 0x10). The
 write-shaping pipeline is not styling — each stage guards a measured
@@ -356,9 +387,31 @@
 discarded on zero so a stopped wheel cannot creep; min-write throttle
 + slew, both bypassed for stops. Encoder sampling is split-phase
 (select 0x46 → 4 ms settle → read), counts never device-reset —
-rebaseline is a software offset. Carries the wedge detector
-(identical-read streaks; `wedgeSuspect` = streak while driven) and
-glitch armor (two-strike rejection of implausible reads).
+rebaseline is a software offset (`rebaseline()`, offset-only, no bus
+traffic).
+
+**`EncoderGlitchArmor` (`encoder_glitch_armor.h`, sprint 006 — new
+host-portable module).** The raw-counts plausibility decision that used
+to live entirely inside `NezhaMotorPort::collect()` — implausible-jump
+rejection, two-strike accept — extracted into a small header with no
+`pxt.h`/I2C dependency, alongside `motion_engine.h` in spirit: a pure
+function of `(rawCounts, lastGoodRaw, rejectPending)` returning one of
+three decisions (`kAccept` — plausible, integrate as motion;
+`kAcceptAsRebaseline` — a second consecutive self-consistent reading
+after an implausible jump, but now treated as *the counter restarted*,
+not *the wheel teleported*; `kRejectPending` — first implausible
+reading, hold and wait for a second). This changes KERN-07/R-07's
+existing two-strike behavior: previously the second consistent reading
+was accepted as a real ~4 m position jump; now that same trigger is
+routed to `kAcceptAsRebaseline`, which `NezhaMotorPort::collect()` (the
+thin, hardware-only caller) turns into an offset re-anchor
+(`encOffset_ = raw`, matching the existing manual `rebaseline()`'s own
+software-offset technique) instead of an integrated jump — position
+stays continuous, velocity reads as the (small) real motion during the
+gap rather than a multi-m/s spike. `NezhaMotorPort` is the only
+caller; the class is otherwise unaware of I2C, CODAL, or the kernel.
+Host-tested directly (no fakes needed — it has no hardware dependency
+to fake); see §11 for this module's C++11 syntax-gate coverage.
 
 **OtosPort** (SparkFun OTOS, I2C 0x17; implements `PoseSource`).
 Ported verbatim from the reference firmware: register map, distinct
@@ -368,7 +421,40 @@
 and silently inherits a previous session's values — measured 42.7 mm
 pivot circle from a stale arm). The lever arm is applied in
 **software** on every read/seed; the chip's own offset register is
-held at zero — applying both double-corrects.
+held at zero — applying both double-corrects. **Sprint 006**:
+`setPose()` now wraps the heading channel into (−π, π] before handing
+it to `writePoseMm()`'s quantizer — the chip's heading register is a
+wrap-mandatory quantity (full scale ±π) that `writePoseMm()` was
+clamping like a length (x/y keep the clamp; only the heading channel
+gains a wrap). A seed heading of 350° (a 0–360° convention source, or
+the deliberately-unwrapped odometry heading echoed back through
+`seedPose()`) now lands at the equivalent −10° instead of clamping to
++179.89°, keeping the OTOS and encoder pose sources agreed at seed
+time — the disagreement `seedPose()`'s own drift-measurement contract
+depends on not existing yet.
+
+**`EncoderPoseSource` (`encoder_pose_source.h`, sprint 006 — new
+host-portable module).** A second `PoseSource` implementation over
+`shims.cpp`'s existing dead-reckoned odometry (`Rig::x/y/heading`), for
+robots with no OTOS fitted — most of the fleet (the OTOS is on vevov
+only). Three-method port, same shape as `OtosPort`: holds const
+references to the Rig's already-computed `x`/`y`/`heading` floats and
+returns them verbatim — it does not compute odometry itself. It is
+constructed as a `Rig` member (or otherwise lifetime-tied to `Rig`'s
+own lazy-singleton, process-lifetime instance) so the references it
+holds never outlive their target — the same lifetime relationship
+`MotionEngine`'s own `kernel_`/`clock_` references already have to
+their `Rig`-owned targets; this is not a dangling-reference risk so
+long as no `EncoderPoseSource` is ever constructed with a shorter
+lifetime than `Rig` itself. It does not need its own epoch-tracking for the "epoch-guarded rebaseline"
+motion-api.md §3.6 calls for, because it reads the same Rig-local state
+`odomUpdate()` already produces, and `EncoderGlitchArmor` above already
+makes that state continuous across a detected brick-reset — the
+guarantee is inherited, not re-implemented. Heading is reported
+unwrapped, matching `shims.cpp`'s existing odometry contract (§3's
+`PoseSource` note on the two implementations' differing wrap
+conventions). Host-portable and host-tested the same way
+`FakePoseSource` already is.
 
 **Bus discipline (system invariant).** The Nezha brick and the OTOS
 share one I2C bus. Every OTOS transaction must run on the same fiber
@@ -473,9 +559,17 @@
 - **Odometry** (`odomUpdate`): differential dead-reckoning from
   kernel `Output` positions using the engine's geometry
   (`countsPerMm`, `effectiveTrackWidth`), midpoint-heading
-  integration into Rig-local `x/y/heading`. Updated lazily on pose
-  reads and while a move is active. Odometry ownership staying here
-  (not in MotionEngine) is a known, accepted architectural seam.
+  integration into Rig-local `x/y/heading`. **Sprint 006**: `tickDrive()`
+  now folds `odomUpdate()` into **every** tick unconditionally, not
+  only while a move-engine move is (was) active — continuous-mode
+  driving (`setWheels`/`driveTwist` under a `while (tickDrive())` loop)
+  previously updated pose only on the next explicit pose read, which
+  integrated the whole driven interval as one straight chord regardless
+  of actual curvature (UC-009's "pose is always live-updated from
+  odometry regardless of command mode" was aspirational, not true,
+  before this fix). `updateMove()`'s own odometry gate (only while a
+  move is active) is unchanged — that path is move-engine polling, not
+  continuous-mode driving, and stays correct as-is.
 - **Tick engine** (`tickDrive()`): one `kernel.step()` +
   `serviceMove()` on the caller's fiber, then absolute-deadline
   self-pacing to the kernel's configured 24 ms cadence (re-anchored
@@ -486,13 +580,41 @@
   neutral never reached the motors before the `while (tickDrive())`
   caller exited (measured: +9–13° per turn). This settle loop is
   **not host-testable** (bolted to Rig-local odometry) — a known,
-  accepted gap; only hardware exercises it.
+  accepted gap; only hardware exercises it. **Sprint 006 leaves this
+  loop's shape untouched deliberately** — the follow-up issue
+  `settle-tick-loop-is-not-host-testable` (sprint 008) plans to extract
+  its logic into a host-portable helper, and this sprint's own stop-
+  delivery fix (below) is placed elsewhere specifically so it does not
+  collide with that future extraction.
+- **Stop delivery** (sprint 006, new): `stopAll()`/`endMove()`
+  (`stop`/`stop move`) and `updateMove()`'s own move-completion branch
+  (the `isMoving()`/`move progress` poller's path, which can end a move
+  at its deadline without ever calling `tickDrive()`) now each also
+  call a small shared helper that pushes an immediate, port-level
+  zero write to both motors — the exact same primitive the starvation
+  watchdog already uses (`Motor::emergencyStop()`, tick-independent,
+  never touches the kernel's e-stop latch) — in addition to staging
+  `kernel.neutral()` as before. This closes R-08/BLK-01: previously a
+  stop/move-completion issued from a fiber other than the one currently
+  inside `kernel.step()`'s ~8 ms settle window staged a neutral that
+  was not delivered to the motors until that settle window's step()
+  returned *and* another tick ran — which, if the tick loop had already
+  exited (exactly the case when the completing/stopping call is what
+  ended it), meant no further step() ran at all until the ~100–150 ms
+  starvation watchdog fired. The fix adds no new fiber/ticker (the
+  "one ticker per move" invariant, `settle-tick-loop-is-not-host-
+  testable`, is unaffected) and does not touch the vendored kernel
+  (`diffdrive.{h,cpp}` stay byte-unchanged, so no cross-repo resync is
+  needed) — it is entirely a `shims.cpp`-level composition reusing an
+  existing, already-proven primitive.
 - **Starvation watchdog**: every ~50 ms, if something looks active
   (`isMoveActive()` or nonzero applied duty) and no tick has run for
   ~100 ms, it calls `kernel.neutral()`, `engine.endMove()`, and
   port-level `emergencyStop()` on both motors — a *resumable soft
   stop* that never touches the e-stop latch, so a fresh tick resumes
-  motion with no clear step.
+  motion with no clear step. Unchanged this sprint; the stop-delivery
+  fix above reuses this same port-level primitive rather than adding a
+  new mechanism.
 - **Wire bridges**: `setWheelsTimed`/`driveTwistTimed` (duration =
   lease), the six `engineXxx()` forwards, `engineDefaultCruiseMmS()`,
   `diagValue()` (the DIAG/STATUS ordinal table),
@@ -501,9 +623,19 @@
 - **OTOS surface**: a lazy singleton **separate from Rig** (usable
   without starting the drive), `otosBegin/otosRead/otosGet/otosZero/
   otosCalibrate/otosSetOffset`, `seedPose()` (writes **both** pose
-  sources so their later divergence is the drift being measured), and
-  `engineGoToW()` which refuses (returns false) when the OTOS is not
-  connected.
+  sources so their later divergence is the drift being measured — now
+  correctly agreed at seed time for any heading, per §7's OTOS heading-
+  wrap fix). **Sprint 006**: `engineGoToW()` no longer refuses when the
+  OTOS is not connected — it now selects `OtosPort` when connected,
+  `EncoderPoseSource` otherwise (§7), in this one place, and always
+  dispatches to `MotionEngine::goToW()`. This closes
+  `no-encoder-odometry-posesource-fallback`: GO_TO_W (and the block
+  API's world-pose moves that route through it) is no longer a no-op
+  on the fleet's OTOS-less robots (tovez, gopiv, zeguz) — it drives on
+  dead-reckoned odometry instead, a materially weaker (drifting)
+  promise than the OTOS gives, which the ticket's own documentation
+  update states plainly rather than leaving the two verbs looking
+  identical.
 
 **main.ts** owns the student units and the block API (groups Drive,
 Move, Pose, World, Setup), the browser-simulator fallback bodies (a
@@ -547,11 +679,25 @@
   telemetry frame (up to 239 bytes measured). Filed as
   `clasi/issues/radio-rx-capacity-fragmentation.md`, claimed by sprint
   010.
-- The post-move settle loop is hardware-only-tested.
+- The post-move settle loop is hardware-only-tested (unchanged this
+  sprint; see §9's stop-delivery note on why the fix landed elsewhere).
 - `protocol.cpp`'s `kVersion` is a manual mirror of `pxt.json` and
   can drift.
-- The encoder-odometry `PoseSource` fallback for OTOS-less robots is
-  explicitly not built; GO_TO_W refuses on such robots.
+- **(Resolved, sprint 006)** ~~The encoder-odometry `PoseSource`
+  fallback for OTOS-less robots is explicitly not built; GO_TO_W
+  refuses on such robots.~~ `EncoderPoseSource` (§7) now serves that
+  role; GO_TO_W dispatches on every robot regardless of OTOS presence
+  (§9). Remaining caveat: the fallback carries no drift/uncertainty
+  signal back to the caller — a GO_TO_W served by encoders is silently
+  a weaker promise than one served by the OTOS, distinguishable today
+  only by reading STATUS's `otos=` flag before calling, not by
+  anything GO_TO_W itself returns.
+- `EncoderGlitchArmor`'s rebaseline-on-discontinuity path (§7) is
+  built and host-tested against the *code path* KERN-07 identified,
+  but the *hardware premise* — whether a Nezha brick MCU reset actually
+  restarts the 0x46 counter near zero — remains unconfirmed absent a
+  bench run; see `brick-reset-odometry-teleport.md` and sprint 006's
+  bench-checklist ticket.
 
 ## 11. Host-vs-target language standard (a standing build-gate constraint)
 
@@ -585,3 +731,116 @@
 need `pxt.h` and are not covered by this gate at all, and a *linkable*
 target build — not merely syntax-valid C++11 — is only ever proven by
 the sprint checkpoint that actually builds a flashable hex.
+
+**Sprint 006** adds two new host-portable headers with no `pxt.h`
+dependency of their own — `encoder_glitch_armor.h` and
+`encoder_pose_source.h` (§7) — to this same gate, via a small dedicated
+syntax-check translation unit each (neither has a natural `.cpp` of its
+own the way `motion_engine.h` rides along with `motion_engine.cpp`).
+This is the gate's coverage growing by the two files this sprint adds
+that are eligible for it; it does **not** narrow the gap for the files
+this sprint actually changes that remain ineligible — `shims.cpp` (stop
+delivery, continuous-mode odometry fold, `EncoderPoseSource`/
+`OtosPort` selection wiring) and `nezha_port.cpp`/`otos_port.cpp`
+(the hardware-port callers of the two new headers) all still include
+`pxt.h` and stay outside this gate, exactly as `src/DESIGN.md`'s
+pre-sprint-006 text already said. A green host suite for this sprint's
+`shims.cpp`/port changes is, as always, not evidence they compile for
+the robot — only the sprint's own flashable-hex checkpoint proves that.
+
+## 12. Sprint 006 — architecture diagram and change summary
+
+Substantial-tier sprint update (see `sprint.md`'s Architecture section
+for the sizing decision and rationale). Six issues from the 2026-08-23
+code review's motion-correctness cluster, five CONFIRMED defects plus
+one capability gap sharing the same `PoseSource`/heading-wrap seam.
+Two new host-portable modules are introduced (`EncoderGlitchArmor`,
+`EncoderPoseSource`); the kernel (`diffdrive.{h,cpp}`) stays
+byte-unchanged throughout, so no cross-repo (radio-robot firmware)
+resync is triggered by this sprint.
+
+**Sprint Changes (recap — module level; see §3/§7/§9 above for detail):**
+
+- `motion_engine.cpp` — `goToR()` owns its own pivot-split decision
+  (bearing-pivot + chord, not inherited from `moveX`'s generic split);
+  theta normalized to the short arc; `arrive` honored as a radial
+  no-op gate.
+- `shims.cpp` — `tickDrive()` folds `odomUpdate()` unconditionally
+  into every tick (continuous-mode odometry fix); `stopAll()`/
+  `endMove()`/`updateMove()`'s completion branch each add an immediate
+  port-level stop (cross-fiber settle-window fix); `engineGoToW()`
+  selects `OtosPort` or `EncoderPoseSource` in one place instead of
+  refusing without an OTOS.
+- `otos_port.cpp` — `setPose()` wraps the heading channel before
+  quantizing (seed-heading clamp fix).
+- `nezha_port.cpp` — `collect()`'s two-strike acceptance now routes
+  through `EncoderGlitchArmor` and rebaselines on a detected
+  discontinuity instead of integrating it as motion.
+- `encoder_glitch_armor.h` (new) — extracted, host-portable
+  plausibility/rebaseline decision.
+- `encoder_pose_source.h` (new) — `PoseSource` over existing Rig
+  odometry, for OTOS-less robots.
+- `motion_engine.h` — `PoseSource::heading()` contract comment
+  clarified (wrap convention is implementation-defined; consume only
+  via cos/sin).
+
+```mermaid
+flowchart LR
+    WA[WireAdapter<br/>wire_adapter.cpp] -->|"engineGoToW() / engineGoToR()"| RIG
+    RIG[Rig<br/>shims.cpp composition root] -->|composes| KERNEL[DifferentialDrive<br/>diffdrive.cpp — unchanged]
+    RIG -->|composes| ME[MotionEngine<br/>motion_engine.cpp]
+    RIG -->|"odomUpdate() every tick (NEW: unconditional)"| RIG
+    KERNEL -->|Motor port| NEZHA[NezhaMotorPort<br/>nezha_port.cpp]
+    NEZHA -->|"NEW: delegates plausibility decision"| GLITCH[EncoderGlitchArmor<br/>encoder_glitch_armor.h — NEW]
+    RIG -->|"NEW: wraps Rig x/y/heading as PoseSource"| ENCPOSE[EncoderPoseSource<br/>encoder_pose_source.h — NEW]
+    RIG -->|"selects: OTOS if connected, else encoder"| OTOS[OtosPort<br/>otos_port.cpp]
+    ME -->|"goToW() reads pose.x/y/heading()"| OTOS
+    ME -->|"goToW() reads pose.x/y/heading()"| ENCPOSE
+    RIG -->|"stopAll()/endMove()/updateMove():<br/>NEW immediate port-level stop"| NEZHA
+```
+
+No entity-relationship diagram: no persistent data model exists in
+this embedded package, and none of the six issues introduces one. No
+separate dependency-direction graph beyond the diagram above: dependency
+direction is unchanged (Presentation/wire → MotionEngine → Kernel/ports,
+Kernel at the bottom); the two new modules sit at the bottom of the
+stack (host-portable, zero outward dependencies) with exactly one
+caller each (`NezhaMotorPort` for `EncoderGlitchArmor`, `Rig` for
+`EncoderPoseSource`) — no cycle is introduced.
+
+**Migration concerns.** None requiring data migration or a deployment
+sequencing change. Two behavior changes are visible to an existing
+caller and worth flagging explicitly rather than treating as purely
+internal: (1) GO_TO_W becomes more permissive — a caller that
+previously received `kUnimplemented` on an OTOS-less robot now receives
+`kOk` and an encoder-driven move; this is a strict widening (nothing
+that worked before stops working), but any caller-side logic that
+specifically branched on `kUnimplemented` to mean "this robot has no
+world-pose capability at all" will observe different behavior. (2)
+`stop`/`stop move` now deliver a hardware-level zero write immediately
+in addition to the pre-existing staged neutral, which changes worst-case
+stop latency (better) but not documented behavior (UC-011's postcondition
+already promised "further Drive/Move commands work normally" — this
+sprint makes that true sooner, not differently).
+
+**Risk (known, pre-existing, not newly introduced by this sprint):**
+the new immediate port-level write in `stopAll()`/`endMove()`/
+`updateMove()` shares the same I2C bus as the Nezha brick's encoder
+settle window (§7's bus discipline note) — if it lands on a *different*
+fiber than the one currently inside `kernel.step()`'s ~4 ms-per-wheel
+settle sleep, it is exactly the kind of "other I2C traffic during the
+settle window" `diffdrive.h`'s own kernel invariant warns can corrupt a
+sample. This exposure already exists today in the starvation
+watchdog's own port-level writes (same primitive, same bus, no
+fiber coordination); this sprint's fix increases how *often* the
+collision window can be hit (any cross-fiber stop, not only a fully
+abandoned tick loop), not its consequence. Consequence, if it happens:
+`refreshSample()`'s existing fault path already treats a corrupted
+collect as a failed sample — position/velocity hold at their last good
+value and `i2cFaultCount_` increments — precisely because the robot is
+stopping in that same tick, a stale encoder reading for one cycle is
+low-consequence. No design change is proposed to close this fully (that
+would mean serializing all port writes through the tick fiber, a larger
+change than this sprint's scope); ticket 002 should add a host test
+confirming a corrupted collect during this window is counted, not
+silently accepted as a valid sample.
```
