---
source_file: DESIGN.md
source_hash: 7cec66b921e155932c4a0b55ef4b236661ee8b877e8e5cce9a78005da9e725c0
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 007, closed and merged 2026-08-24 — student API: stall-latch clear and readback, the `driveTick()` continuous-drive contract, the wire `cruise == 0` sentinel, simulator turn-rate and e-stop parity, a `rotationalSlip` setter, and the `pxt.json` manifest fix that had been blocking every hex build; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -200,7 +200,24 @@
 first lookup that reaches it (a hard fault on the robot, for every
 command). No verb is added, removed, or reordered by this change — the
 18 names above are unchanged; only how the array's size is spelled
-changes.
+changes. **Sprint 008**: the six motion verbs' `timeout`/`duration`
+fields (`WHEELS_X`/`WHEELS_V`/`MOVE_X`/`MOVE_V`/`GO_TO_R`/`GO_TO_W`) now
+pass through one shared decode-time clamp before any verb-specific
+decode logic runs: `0` is rejected (`kRange`), and any value above
+2^31−1 is silently clamped to 2^31−1. This closes WIRE-02/KERN-06
+(R-06 — `WHEELS_X`/`MOVE_X` disagreeing about what `0` means, and a
+`WHEELS_X … timeout 0` leaving a stale kernel lease armed with no
+motion obligation tracking it) and WIRE-10/KERN-10-adjacent (R-18 — a
+timeout above 2^31 wrapping the deadline arithmetic negative and
+re-triggering the ticket-011 starvation-kill pattern for an input class
+no prior test reached). Enforcing this once, at decode, in
+`wire_handler.cpp`, rather than six times in each `wire_adapter.cpp`
+handler, is deliberate: every downstream consumer (`WireAdapter`'s own
+obligation-window math, `MotionEngine::wheelsX()`'s lease-clamp
+arithmetic, the kernel's `drive()` lease) now only ever sees an
+in-range value, so none of them individually needs to reason about `0`
+or overflow — see this sprint's Design Rationale (§14) for why reject
+(not clamp) was chosen for the `0` case specifically.
 
 **Reliability layer.** Every sequenced verb carries a mandatory
 trailing `#<id>`, strictly incrementing from 1. Handler state is
@@ -328,7 +345,12 @@
 armed it and every other verb's move starved and was watchdog-stopped
 almost immediately). The clock arrives as a plain C function pointer
 (`NowMsFn`), nullptr on hosts with no clock (obligation then always
-false — honest).
+false — honest). **Sprint 008**: the `duration`/`timeout` value every
+handler reads here is now guaranteed already in-range (nonzero, ≤
+2^31−1) by `wire_handler.cpp`'s shared decode-time clamp (§4) — no
+handler here changed its own logic; the values arriving at
+`motionObligationDeadlineMs_ = nowMs_() + timeout` simply can no longer
+be `0` or large enough to matter for wraparound.
 
 **Telemetry projection (sprint 004 ticket 004).** `buildSnapshot()`
 returns a `const Wire::Snapshot&` into a member (mirroring
@@ -344,7 +366,17 @@
 centidegrees — do not also divide it); and `wheelSpeed`. POSE's 12
 columns (`seq now flags x y h ox oy oh vl vr i2cf`) are always
 present; FULL adds 8 more (`cyc posl posr dutl dutr lexc wrng cycovr`)
-only in `TlmMode::kFull`. `telemetryEnabled()` (`mode_ !=
+only in `TlmMode::kFull`. **Sprint 008**: `TlmMode::kAuto` and
+`TlmMode::kBuffer`'s previously-undocumented fall-through to POSE's
+column set is now a stated decision, not an accident:
+`TlmMode::kAuto` is a documented alias for `TlmMode::kPose` (same 12
+columns, same cadence — matches the pre-existing de facto behavior
+exactly, so no wire-visible change), while `TlmMode::kBuffer` refuses
+at the `TLM` verb itself (`kUnimplemented`) rather than silently
+emitting POSE's columns — no buffering mechanism exists anywhere in
+this codebase to give "buffer" real, narrower semantics yet, and
+refusing is more honest than emitting a column set no one specified
+(see §14's Design Rationale). `telemetryEnabled()` (`mode_ !=
 TlmMode::kOff`) lets protocol.cpp skip building a Snapshot at all for
 a session with no subscriber (see §8's Fiber loop). `computeFlags()`
 (wire_adapter.cpp, anonymous namespace) is now the single source both
@@ -417,7 +449,21 @@
 `RadioSink::write()` ignores the drop by design (a lost `t` frame
 self-heals via the next `seq` gap). Not host-testable (this file
 includes `pxt.h`); verified by code review, first exercised live at
-the bench.
+the bench. **Sprint 008**: `kMaxPayloadBytes`'s own doc comment
+previously claimed it was "sized the same as SerialTransport's bound"
+— false since ticket 005 (sprint 004) raised `SerialTransport`'s
+`kMaxLineBytes` to 240 while this constant stayed 200; the comment now
+states the true relationship: `kMaxPayloadBytes` is deliberately the
+**tighter** of the two transports' caps, and `protocol.cpp`'s
+`emitLine()` (§8) now names this constant directly instead of
+re-declaring its own bare `200` literal, so the two can never drift
+apart silently again the way they already had (WIRE-05/R-21). The
+*value* is unchanged — still 200, still radio's real capacity ceiling
+— this sprint single-sources the constant, it does not raise radio's
+capacity: that is `radio-rx-capacity-fragmentation.md`'s scope (sprint
+010), which also already tracks the adjacent, still-open finding that a
+legal `FULL`-mode telemetry frame can itself reach up to 239 bytes,
+above this same cap (§10's Open Questions).
 
 **Layering.** Both know bytes and framing only — no verbs, no COBS,
 no semantics. Siblings under Protocol, deliberately uncoupled from
@@ -569,12 +615,38 @@
 `main.ts` reads it back via `runCommandText()` and dispatches by name
 on the handler's own fiber. 3 s same-text dedupe absorbs hosts
 repeating commands to survive the single-slot radio buffer (measured:
-one 3×-repeated RUN ran three consecutive pivots).
+one 3×-repeated RUN ran three consecutive pivots). **Sprint 008**: the
+literal event source `0x2001` above and `main.ts`'s own
+`RUN_EVENT_SOURCE = 0x2001` are two independent hand-typed copies of
+the same MessageBus event id (WIRE-01-adjacent minor, R-21) — now
+pinned by a drift test that reads both source files as text and fails
+if they diverge, rather than single-sourced across the TS/C++ boundary
+(no shared-constant mechanism crosses that boundary today; a drift test
+is the same shape sprint 004/006/007 already use for cross-language
+pairs like this).
 
 **`emitLine()`** writes one caller-supplied line to **both**
 transports — test results must come back over radio because USB only
-reaches the bench stand, where the wheels are off the ground. Note it
-caps at 200 bytes (predates the 240 raise). Since sprint 004 ticket
+reaches the bench stand, where the wheels are off the ground.
+**Sprint 008**: its cap now names `RadioTransport::kMaxPayloadBytes`
+directly instead of re-declaring its own bare `200` literal (WIRE-05/
+R-21) — this constant is deliberately the **tighter** of the two
+transports' caps (radio's, not serial's 240), chosen so a line this
+call clips never depends on which transport happens to carry it; the
+previous bare literal was numerically correct but disconnected from
+that rationale, which is what let it read as merely stale once ticket
+005 raised serial's own cap independently. `kMaxPayloadBytes` itself
+moves from `private` to `public` on `RadioTransport` to make this
+reference possible — a one-line access-specifier change with no
+encapsulation cost (it stays a compile-time constant, still used
+in-class to size `payloadBuf_`. Note that `RadioTransport`'s other
+size/framing constants — `kFrameHeaderBytes`, `kGroup`, `kChannel`,
+`kTransmitPower` — remain `private`, and only `kMaxPayloadBytes` was
+moved: nothing outside the class needs to name the others, so widening
+them would be access-loosening without a caller to justify it).
+Single-sourcing the name, not the value, closes the drift risk without
+touching radio's actual capacity (sprint 010's scope, §6). Since
+sprint 004 ticket
 002, the radio half checks `RadioTransport::sendLine()`'s bool return:
 `false` means its re-entrancy guard fired against the protocol fiber's
 own concurrent `RadioSink::write()`, and — because this is the one
@@ -585,8 +657,15 @@
 **Lifecycle.** Lazy singleton `protocol()`, started by `main.ts`'s
 top-level `_startProtocol()` the moment the extension's compiled code
 loads — never a global constructor (uBit.init ordering). Identity
-constants: drivetrain "diffdrive", profile "tovez", version — a
-manually-synced mirror of `pxt.json`'s version.
+constants: drivetrain "diffdrive", profile "tovez", version. **Sprint
+008**: `kVersion` no longer hand-mirrors `pxt.json`'s version as a
+literal that can silently drift (it had, by ten version bumps —
+WIRE-01/MOD-01/BLK-09, R-17) — it is now single-sourced or drift-tested
+against `pxt.json` (the specific mechanism is a build-time-feasibility
+call made during ticket execution, per this sprint's Design Rationale,
+§14) so `ID`/`VER`'s wire reply can no longer misreport the build a
+host is actually talking to, restoring the `mbdeploy` → `VER`
+deploy-verification flow's own precondition.
 
 **Telemetry gap (closed, sprint 004).** The old periodic cleartext
 `TLM:` line was retired with v5 and had no v6 replacement through
@@ -631,18 +710,32 @@
   `serviceMove()` on the caller's fiber, then absolute-deadline
   self-pacing to the kernel's configured 24 ms cadence (re-anchored
   after gaps). A cooperative-fiber `stepBusy` flag serializes
-  concurrent tickers. On the tick that ends a move it runs up to 12
-  extra settle steps until the wheels measure at rest, folding coast
-  counts into odometry before the final read — without this the
+  concurrent tickers. **Sprint 008**: on the tick that ends a move,
+  `tickDrive()` now calls a new `MotionEngine` settle helper instead of
+  running its own inline loop — the helper steps the kernel up to 12
+  times, breaking early once both wheels measure at rest, identical
+  behavior to the loop it replaces (measured: without this step, the
   neutral never reached the motors before the `while (tickDrive())`
-  caller exited (measured: +9–13° per turn). This settle loop is
-  **not host-testable** (bolted to Rig-local odometry) — a known,
-  accepted gap; only hardware exercises it. **Sprint 006 leaves this
-  loop's shape untouched deliberately** — the follow-up issue
-  `settle-tick-loop-is-not-host-testable` (sprint 008) plans to extract
-  its logic into a host-portable helper, and this sprint's own stop-
-  delivery fix (below) is placed elsewhere specifically so it does not
-  collide with that future extraction. **Sprint 007**: `tickDrive()`'s
+  caller exited, +9–13° per turn). `tickDrive()` still calls
+  `odomUpdate(r)` once, itself, immediately after the helper returns —
+  folding coast counts into Rig-local odometry stays a `shims.cpp`
+  concern, unmoved by this extraction; only the settle/rest *decision*
+  (how many steps, when to stop) crossed into `motion_engine`, which
+  needed nothing more than the already-host-portable
+  `kernel.step()`/`kernel.output()` surface to make that decision. This
+  is a narrower cut than sprint 003 ticket 013's own note anticipated
+  ("extracting cleanly would mean moving odometry ownership into
+  motion_engine too") — that concern applies to extracting the whole
+  settle-then-integrate behavior as one unit; it does not apply once the
+  settle decision and the odometry fold are kept as two separate calls,
+  which is what this sprint does. The extracted helper is now
+  **host-tested directly** (a new `tests/host/` shim exercises it via
+  `kernel_shim.cpp`/`fake_ports.h`, reusing the `FakeSleeper::onSleep`
+  hook sprint 006 added) — closing the gap sprint 003's own regression
+  test could only argue for by proxy. No new fiber or ticker is
+  introduced; the one-fiber-ticks-a-move constraint (§4/§8) is
+  unaffected — `tickDrive()` is still the loop's only caller.
+  **Sprint 007**: `tickDrive()`'s
   return value changes from raw post-`serviceMove()` move-engine state
   to `commandLooksActive(r)` (the same helper the starvation watchdog
   below already used and proved correct in production — move-engine
@@ -798,10 +891,36 @@
   telemetry frame (up to 239 bytes measured). Filed as
   `clasi/issues/radio-rx-capacity-fragmentation.md`, claimed by sprint
   010.
-- The post-move settle loop is hardware-only-tested (unchanged this
-  sprint; see §9's stop-delivery note on why the fix landed elsewhere).
-- `protocol.cpp`'s `kVersion` is a manual mirror of `pxt.json` and
-  can drift.
+- **(Resolved, sprint 008)** ~~The post-move settle loop is
+  hardware-only-tested.~~ Its bounded-iteration/break-on-rest decision
+  is now a `MotionEngine` helper, host-tested directly (§9). Remaining,
+  narrower gap: `odomUpdate(r)` itself and the loop's actual
+  `kernel.step()` calls against real hardware are still only ever
+  exercised by flashing — this sprint host-tests the *decision logic*,
+  not the physical settle behavior, which is the same boundary every
+  other host-portable extraction in this document draws.
+- **(Resolved, sprint 008)** ~~`protocol.cpp`'s `kVersion` is a manual
+  mirror of `pxt.json` and can drift.~~ Single-sourced or drift-tested
+  against `pxt.json` (§8) — ten version bumps had drifted at the time
+  this was fixed (WIRE-01/R-17).
+- **(New, sprint 008)** `TlmMode::kBuffer` now refuses
+  (`kUnimplemented`) rather than falling through to POSE's columns
+  (§5) — a real behavior change for any host that was unknowingly
+  relying on the old fall-through, though none is known to exist. A
+  future sprint that gives BUFFER real, narrower semantics changes this
+  refusal into an implementation, not a widening of an existing
+  contract.
+- **(New, sprint 008)** The target-viability gap
+  (`host-tests-compile-newer-standard-than-target.md`) is addressed by
+  a standing per-sprint build-checkpoint-ticket *convention* (§11, §14;
+  `docs/design/design.md`'s matching update), not by a hard automated
+  gate in `close_sprint` — that tool is CLASI-server code outside this
+  project's own source tree, so no ticket here can wire a gate into it.
+  This closes the gap procedurally (every future sprint's own planner
+  is expected to include the ticket) rather than mechanically
+  (nothing currently prevents a sprint from being planned without one);
+  flagged for the team-lead/stakeholder as a process decision worth
+  revisiting if a sprint ever ships without its checkpoint ticket.
 - **(Resolved, sprint 006)** ~~The encoder-odometry `PoseSource`
   fallback for OTOS-less robots is explicitly not built; GO_TO_W
   refuses on such robots.~~ `EncoderPoseSource` (§7) now serves that
@@ -900,6 +1019,33 @@
 not evidence they compile for the robot — only the sprint's own
 flashable-hex checkpoint proves that.
 
+**Sprint 008** closes the *centerpiece* gap this section documents —
+not by widening the syntax gate further (the settle-loop extraction's
+new logic lands as a method on the already-gate-covered `MotionEngine`
+class, defined in `motion_engine.cpp`, so no new file and no new gate
+registration are needed — a deliberately simpler choice than sprint
+006's three new headers, since `motion_engine.cpp` already composes the
+kernel reference the new method needs and was already portable, unlike
+`otos_port.cpp`/`nezha_port.cpp`, which had no portable home to extract
+into without building one) — but by formalizing what this section has
+said all along in different words: "a *linkable* target build... is
+only ever proven by the sprint checkpoint that actually builds a
+flashable hex." Sprints 004 and 007 each proved that sentence true by
+accident (their own last ticket happened to run `make_deploy.py`, and
+each time that accident is what caught the sprint's own defect). This
+sprint makes the accident a rule: every sprint that touches
+build-eligible source now includes a mandatory, always-last
+build-checkpoint ticket (see `docs/design/design.md`'s matching update
+and §14 below), and `tools/make_deploy.py` itself gains the triage
+this section's own "known-benign, tolerate a retry" caveats needed —
+distinguishing a real `.cpp` compile failure from the legacy V1
+hex-merge failure and the nondeterministic `TS9283`/`TS9043`/`TS9200`
+packaging abort, retrying only the latter automatically. This still
+does not turn the syntax gate into something it isn't: the gate proves
+syntax validity for four portable files plus their extracted-header
+siblings; the checkpoint proves the whole package actually links for
+both real targets. Both are needed; neither substitutes for the other.
+
 ## 12. Sprint 006 — architecture diagram and change summary
 
 Substantial-tier sprint update (see `sprint.md`'s Architecture section
@@ -1165,3 +1311,244 @@
 `tests/host/wire_motion_verb_shim.cpp`'s mirror leaves a fully green
 host suite that has stopped testing the real contract — called out
 above and in the corresponding ticket's acceptance criteria.
+
+## 14. Sprint 008 — architecture diagram and change summary
+
+Substantial-tier sprint update (see `sprint.md`'s Architecture section
+for the sizing decision). Six issues from the 2026-08-23 code review's
+"tests must be able to fail" cluster, spanning the wire layer, the host
+test harness, and the project's own build-verification process. No new
+module is introduced in the sense sprint 006's three headers were (new
+files with no prior home); the settle-loop extraction (issue 4) adds a
+new *method* to the existing `MotionEngine` class instead. The vendored
+kernel (`diffdrive.{h,cpp}`) stays byte-unchanged throughout, so no
+cross-repo resync is triggered.
+
+**Sprint Changes (recap — module level; see §4/§5/§6/§8/§9/§11 above
+for detail):**
+
+- `wire_handler.h`/`.cpp` — one shared decode-time clamp for all six
+  motion verbs' `timeout`/`duration` fields: reject `0` (`kRange`),
+  clamp values above 2^31−1 down to it.
+- `wire_adapter.cpp`/`.h` — no handler-level logic change for timeout
+  (the values they read are now pre-bounded); `TlmMode::kAuto` is
+  documented as a `TlmMode::kPose` alias, `TlmMode::kBuffer` refuses
+  (`kUnimplemented`) instead of falling through to POSE's columns.
+- `protocol.cpp` — `kVersion` single-sourced or drift-tested against
+  `pxt.json`; `emitLine()`'s cap now names
+  `RadioTransport::kMaxPayloadBytes` instead of a bare `200` literal;
+  the `0x2001` RUN event-source literal is drift-tested against
+  `main.ts`'s `RUN_EVENT_SOURCE`.
+- `radio_transport.h` — `kMaxPayloadBytes`'s doc comment corrected
+  (deliberately the tighter cap, not "equal" to serial's); value
+  unchanged.
+- `main.ts` — no functional change; `RUN_EVENT_SOURCE` is now the
+  drift-tested half of the `0x2001` pair above.
+- `motion_engine.h`/`.cpp` — new settle-to-rest method consuming only
+  the existing `kernel_` reference and `DiffDrive::DifferentialDrive`'s
+  already-portable `step()`/`output()` surface; no geometry, no
+  odometry.
+- `shims.cpp` — `tickDrive()`'s inline settle loop replaced by a call to
+  the new `MotionEngine` method, followed by the existing, unmoved
+  `odomUpdate(r)` call; no other behavior change.
+- `tools/make_deploy.py` — `build()` gains triage: distinguishes a real
+  `.cpp` compile failure from the two documented benign abort shapes
+  and retries the latter once automatically, instead of only checking
+  "does a hex exist."
+- `tests/host/` — boundary-value timeout tests across all six motion
+  verbs; a `kVersion`/`pxt.json` drift test; an `emitLine`/transport
+  line-cap test; a `RUN_EVENT_SOURCE` drift test; the `WaHandle` wedge/
+  `setWheelsTimed`/config-rounding re-sync plus a demonstrated drift
+  test; a new settle-helper shim (`kernel_shim.cpp`/`fake_ports.h`
+  extension, reusing `FakeSleeper::onSleep`) and its host test; `TLM
+  AUTO`/`BUFFER` `thdr`/`err` pinning tests.
+
+```mermaid
+flowchart LR
+    HOST["Wire host"] -->|"6 motion verbs"| WH["WireHandler<br/>wire_handler.cpp<br/>NEW: shared timeout clamp"]
+    WH -->|"decoded, bounded fields"| WA["WireAdapter<br/>wire_adapter.cpp<br/>NEW: TLM AUTO/BUFFER semantics"]
+    WA -->|"engineWheelsX() / engineMoveX() / ..."| RIG["Rig<br/>shims.cpp composition root"]
+    RIG -->|composes| ME["MotionEngine<br/>motion_engine.cpp<br/>NEW: settleToRest()"]
+    ME -->|"kernel_.drive() / step() / output()"| KERNEL["DifferentialDrive<br/>diffdrive.cpp — unchanged"]
+    RIG -->|"tickDrive(): calls settleToRest(), then odomUpdate()"| ME
+    HOSTTEST["tests/host new shim<br/>NEW"] -->|"exercises settleToRest() directly"| ME
+```
+
+The new edge worth naming explicitly: `tests/host/`'s new shim becomes
+a direct consumer of `MotionEngine`'s new method — the same kind of
+edge `WaHandle`'s existing shims already have to `wire_adapter.cpp`, not
+a new *kind* of dependency, but a genuine new instance of one, which is
+why this sprint clears the "new cross-module dependency" substantial-tier
+signal on its own even before counting module totals.
+
+No entity-relationship diagram: no persistent data model exists in this
+embedded package, and none of the six issues introduces one — the wire
+protocol's field set (`kFields`, `TlmMode`, the six motion verbs' own
+fields) is unchanged; only field-level *semantics* (timeout 0, `TLM
+AUTO`/`BUFFER`) are defined more precisely. No separate dependency-
+direction graph beyond the diagram above: dependency direction is
+unchanged (Presentation/wire → MotionEngine → Kernel/ports, kernel at
+the bottom); the one new edge (`tests/host` → the new `MotionEngine`
+method) travels the same direction test shims already travel toward
+production code, and the settle-helper's own dependency
+(`MotionEngine` → `DifferentialDrive`, via the existing `kernel_`
+reference) already existed — no cycle is introduced.
+
+**Migration concerns.** Three real wire-behavior changes, all detailed
+in `sprint.md`'s own Architecture section and repeated here for the
+overlay's own completeness: (1) every motion verb refuses `timeout`/
+`duration` `0` instead of the two disagreeing prior behaviors (a strict
+behavior change, but both prior meanings were bugs the review confirmed,
+not features anything should depend on); (2) a `timeout`/`duration`
+above 2^31−1 is now clamped and the move runs, instead of wrapping
+negative and dying early (a strict improvement); (3) `TLM BUFFER` now
+refuses instead of silently emitting POSE's columns (a behavior change
+for any host relying on the undocumented fall-through — none known to
+exist in-tree). No data persists across power cycles anywhere in this
+system, so none of the three carries a data-migration question beyond
+the behavior changes themselves.
+
+**Risk (known, not newly introduced by this sprint).** The settle-loop
+extraction's call-site change in `shims.cpp::tickDrive()` is, like every
+`shims.cpp` change, invisible to the C++11 syntax gate and every host
+test by construction (§1's layering table) — only this sprint's own
+build-checkpoint ticket proves that call site still compiles and links
+against the new `MotionEngine` method signature. This is not a new risk
+class; it is this sprint's own riskiest single change landing exactly
+in the gap issue 6 exists to describe, which is why the build-checkpoint
+ticket is ordered last and depends on every other ticket in this
+sprint — it is meant to catch exactly this kind of change, not only
+future sprints' changes.
+
+**Design Rationale (selected decisions):**
+
+*Decision: reject `timeout`/`duration == 0`, don't clamp it to a small
+minimum.* Alternatives were (a) reject outright [chosen], (b) clamp `0`
+up to some small nonzero minimum (e.g. 1 ms), (c) keep two different
+per-verb meanings but document them explicitly. (a) needs no new
+"minimum" constant to invent and justify, matches the existing
+precedent that a nonsensical input is refused rather than silently
+reinterpreted (`cruise <= 0` already refuses this way on every
+X/GO_TO verb), and gives a host an unambiguous signal (`err 3`) instead
+of a magic-number substitution it would have to know about out of band.
+(c) was rejected because the review's own finding is that today's two
+meanings are *both* bugs — WHEELS_X's stale-lease lurch and MOVE_X's
+silent no-op are not two intentional designs worth preserving side by
+side. Consequence: any host that was deliberately sending `timeout 0`
+to mean "instant no-op" (MOVE_X's old behavior) must send a very small
+positive value instead; no in-tree tool does this today.
+
+*Decision: clamp (not reject) values above 2^31−1.* A host sending an
+oversized timeout is asking for "a very long time," and the practical
+intent — run for as long as it takes, bounded generously — is served by
+capping rather than refusing. Rejecting would force every host that
+uses a sentinel-like "very large number" pattern for "no real timeout"
+to learn this project's specific ceiling; clamping serves that intent
+transparently. Consequence: `GET`/wire replies never need a new error
+code for this case, and 2^31−1 ms (~24.8 days) is generous enough that
+no legitimate caller's intent is frustrated by the clamp.
+
+*Decision: `TLM AUTO` becomes an alias for `TLM POSE`; `TLM BUFFER`
+becomes a refusal, not a narrower column set.* Alternatives for AUTO
+were (a) alias to POSE [chosen], (b) build real "robot chooses cadence"
+semantics. (b) is a real feature with its own design surface (what
+signal picks the cadence? does it change mid-session?) that this
+Low-priority housekeeping issue does not warrant opening in a hardening
+sprint — (a) matches today's actual behavior exactly, so it is a
+zero-risk documentation fix, not a feature. Alternatives for BUFFER were
+(a) refuse until real semantics exist [chosen], (b) also alias to POSE,
+(c) invent a narrower column set now. (b) was rejected because "buffer"
+implies a distinct transport-level behavior (accumulating frames before
+a batched send) that does not exist anywhere in this codebase today —
+aliasing it to POSE would document a lie, not a decision. (c) was
+rejected because inventing column semantics with no consumer or
+transport mechanism to validate them against is exactly the kind of
+speculative generality this project's own architecture principles warn
+against. (a) is honest about the gap and matches the issue's own stated
+preference ("answering err is better than emitting a column set no one
+specified"). Consequence: a future sprint that builds real buffering
+gets to define BUFFER's semantics without inheriting an accidental
+column-set contract nobody chose.
+
+*Decision: the settle-loop's extracted logic becomes a `MotionEngine`
+method, not a new standalone header.* Alternatives were (a) a new
+header in the `heading_wrap.h`/`encoder_glitch_armor.h`/
+`encoder_pose_source.h` mold [rejected], (b) a method on the existing
+`MotionEngine` class [chosen]. Those three sprint-006 precedents were
+extracted *from* CODAL-bound files (`otos_port.cpp`, `nezha_port.cpp`)
+that had no portable home at all — a new header was the only way to
+gain any host-test coverage. The settle loop's situation is different:
+`motion_engine.cpp` is already host-portable, already gate-covered, and
+already composes the exact `kernel_` reference the settle decision
+needs (§3's Dependencies) — there is no missing home to build. Adding a
+method to an existing, already-correct-layer class is simpler than
+inventing a new file and gains gate coverage for free (no new syntax-
+check translation unit to register). Consequence: `shims.cpp::tickDrive()`
+calls one new `MotionEngine` method instead of running its own loop;
+`odomUpdate(r)` stays exactly where it was, called once, immediately
+after, by `shims.cpp` itself — the fold-coast-counts-into-odometry
+concern this extraction deliberately does not move.
+
+*Decision: close the target-viability gap with a mandatory per-sprint
+build-checkpoint ticket, not a hard gate in `close_sprint`.* Covered in
+full in `sprint.md`'s own Architecture section (the centerpiece
+decision) and `docs/design/design.md`'s matching convention update;
+restated here in Design Rationale form. Alternatives were (a) compile
+the whole host suite at `-std=c++11` [Option 1 in the issue], (b) widen
+the existing syntax gate further [Option 2, already partially done by
+sprint 004/006 and this sprint's shared-clamp addition to `wire_handler.cpp`
+in §4], (c) a hard automated build gate wired into `close_sprint`
+[Option 3, hard-gate variant], (d) a mandatory per-sprint
+build-checkpoint ticket [Option 3, ticket variant — chosen]. (a) was
+not attempted this sprint: the issue itself flags "existing test-side
+code... may use newer features deliberately, so this may not be a
+one-line change — measure before committing to it," and this sprint's
+own scope is already substantial without absorbing that measurement and
+its fallout. (b) narrows one defect class (language-standard mismatches)
+but the issue's own evidence table shows it is structurally incapable
+of catching class 2 (`-Woverflow`-only defects) or class 3 (`pxt.json`
+manifest omissions) — no amount of widening the syntax gate closes
+those, because the gate never reads `pxt.json` and never runs the real
+target's warning set. (c) was rejected because `close_sprint` is
+CLASI-server code outside this project's own repository, so no ticket
+here can implement it, and because the two documented benign-abort
+shapes make a naive pass/fail gate unreliable in exactly the way that
+would erode trust in it over time. (d) is what sprints 004 and 007
+already did *by accident* — this sprint's contribution is making it a
+named, written-down convention (`design.md`, `src/DESIGN.md` §11) plus
+giving `tools/make_deploy.py` the triage logic that was missing (today
+it only checks "does a hex exist," with no distinction between "the
+compiler rejected a `.cpp`" and "packaging aborted for a known, benign,
+retriable reason"). Consequence: target viability is now proven once
+per sprint by construction of the planning process (every future
+sprint-planner is expected to include this ticket), not by which ticket
+happened to run a real build first — but it remains a *process*
+guarantee, not a *mechanical* one, since nothing currently prevents a
+sprint from being planned without its checkpoint ticket. Flagged as an
+open question for the team-lead/stakeholder below.
+
+**Open Questions (sprint 008):**
+
+- Should the mandatory build-checkpoint-ticket convention be enforced
+  mechanically (e.g., a CLASI-level check that a sprint cannot close
+  without a ticket that ran `make_deploy.py`) rather than relying on
+  every future sprint-planner remembering to include one? This sprint
+  cannot answer that — enforcing it would mean changing CLASI's own
+  `close_sprint`/`sprint-planner` behavior, outside this project's
+  authority — but flags it as the natural next escalation if a sprint
+  ever does ship without its checkpoint.
+- The `kVersion`/`pxt.json` single-sourcing mechanism (build-time
+  substitution vs. a drift test) is left to ticket-execution-time
+  measurement of what the pxt/yotta build toolchain actually allows —
+  this sprint's architecture states the requirement (never drift again)
+  without pre-committing to a mechanism that might not survive contact
+  with the actual build pipeline.
+- The `kDiag*` ordinal set shared, by convention only, between
+  `wire_adapter.cpp`'s named constants and `shims.cpp`'s raw numeric
+  `case` labels is a softer instance of the same "single source of
+  truth" problem as `kVersion` — this sprint pins it with a drift test
+  (§4/§8's pattern) rather than restructuring `shims.cpp` to include
+  `wire_adapter.h` for the shared constants, since that coupling change
+  is a real design choice (see `src/DESIGN.md` §1's deliberate
+  `shims.cpp`-has-no-header convention) better made deliberately in its
+  own review than folded into a Minor here.
```
