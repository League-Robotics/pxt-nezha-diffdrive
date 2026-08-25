---
source_file: src-root-DESIGN.md
source_hash: 699bc413426f167a3e88b466eb2f36fcf48959c08390bc634f5718622b6d4327
---
# Diff: src-root-DESIGN.md

Replaces the "Known inert surfaces" note on `WireAdapter::lastDone()`/
`lastDoneReason()` with a description of the real completion channel
sprint 005 builds (one new `shims.cpp` bridge read plus the existing
diagnostic-flags path, no new `MotionEngine` reference), and marks the
two now-resolved "Open questions" bullets (the telemetry-gap retrofit
and the inert completion channel) resolved, following this doc's own
established `~~struck~~` convention for closed items.

```diff
--- src-root-DESIGN.md (pristine)
+++ src-root-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 005, closed and merged — sprint 008: wire hardening and tests that can fail (timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention); sprint 005: `WireAdapter::lastDone()`/`lastDoneReason()` report real motion-completion state for all six verbs instead of the permanently-inert default, backed by one new `shims.cpp` bridge read (`engineMoveActive()`) and a new `Wire::DoneReason::kStall` — see §5 and §10)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -383,18 +383,40 @@
 `status()` and `buildSnapshot()` read, so STATUS's `flags=`/`i2cf=`
 and the telemetry `flags`/`i2cf` columns can never drift apart.
 
-**Known inert surfaces (deliberate, documented):** `lastDone()`/
-`lastDoneReason()` always report `0`/`kNone` — no completion channel
-is threaded back through the void bridge functions; a wire host cannot
-yet observe motion completion through acks.
+**Real completion channel (sprint 005, resolving the prior "known inert
+surfaces" note).** `lastDone()`/`lastDoneReason()` now report real
+values for all six motion verbs rather than the permanently-inert
+`0`/`kNone` default sprint 003 ticket 012 deliberately left in place.
+Two lease-style verbs (WHEELS_V/WHEELS_X/MOVE_V) resolve
+done-vs-timeout-vs-superseded entirely from `WireAdapter`'s own
+pre-existing `motionObligationActive_`/`motionObligationDeadlineMs_`
+bookkeeping — no new dependency. The three goal-directed verbs
+(MOVE_X/GO_TO_R/GO_TO_W) additionally need to know whether the
+underlying `MotionEngine` move is still active when the lease deadline
+is reached, which is the one genuinely new read: `engineMoveActive()`,
+a thin, read-only, forward-declared `shims.cpp` bridge function
+matching the existing `engineWheelsX()`-style convention exactly —
+`WireAdapter` still holds no reference of its own to `MotionEngine`/
+`Rig`. `stall`/`estop` needed no new plumbing at all: both already
+reach `WireAdapter` through the `diagValue()`/`computeFlags()` path
+this class already uses for STATUS's `flags=`/telemetry's `flags`
+column (`stall_halted` and `estopped` are already two of its eight
+diagnostic booleans). `Wire::DoneReason` (`wire_handler.h`) gained one
+new enumerator, `kStall`, for this; `kAborted` ("the caller abandoned
+it") is read as "superseded" — a later motion verb replacing a
+still-live one — since `kStop` already covers both "reached its own
+stop condition" and an explicit `stop()` call. See sprint 005's
+`sprint.md` Design Rationale for the alternatives this ruled out (a
+live `MotionEngine` reference on `WireAdapter`; a stateful return value
+on all six bridge functions instead of the one needed).
 
 **Dependencies.** `wire_handler.h`; `shims.cpp` free functions by
 forward declaration only (`stopAll`, `estopAll`, `setWheelsTimed`,
 `setKernelValue`, `getConfigValue`, `diagValue`, `engineWheelsX`,
 `engineMoveX`, `engineDefaultCruiseMmS`, `engineMoveV`, `engineGoToR`,
-`engineGoToW`, and — sprint 004 ticket 004 — `poseX`, `poseY`,
-`poseHeading`, `otosGet`, `wheelSpeed`). Holds no kernel/engine/Rig
-reference of its own.
+`engineGoToW`, `engineMoveActive` (sprint 005), and — sprint 004 ticket
+004 — `poseX`, `poseY`, `poseHeading`, `otosGet`, `wheelSpeed`). Holds
+no kernel/engine/Rig reference of its own.
 
 ## 6. Transports — `serial_transport.*`, `radio_transport.*`
 
@@ -881,12 +903,18 @@
 
 ## 10. Open questions / known limitations
 
-- `tools/`'s bench scripts still parse the old cleartext `TLM:`
-  prefix (see §8's Telemetry gap paragraph); the v6 `thdr`/`t` frames
-  sprint 004 built are real but nothing in `tools/` consumes them yet
-  — that retrofit is sprint 005 (roadmapped, not yet detail-planned).
-- `WireAdapter::lastDone()`/`lastDoneReason()` permanently inert —
-  hosts cannot observe motion completion via the reliability channel.
+- **(Resolved, sprint 005)** ~~`tools/`'s bench scripts still parse
+  the old cleartext `TLM:` prefix; the v6 `thdr`/`t` frames sprint 004
+  built are real but nothing in `tools/` consumes them yet.~~ Retrofit
+  complete: `tools/tlm.py` is the one shared parser, with fail-loud
+  guards (a dead instrument, a header-only CSV, and a zero-frame plot
+  all now abort loudly). See `tools/DESIGN.md`.
+- **(Resolved, sprint 005)** ~~`WireAdapter::lastDone()`/
+  `lastDoneReason()` permanently inert — hosts cannot observe motion
+  completion via the reliability channel.~~ Real values for all six
+  motion verbs and all five terminal reasons (done/superseded/timeout/
+  stall/estop), host-tested against the real `WireAdapter`. See §5's
+  "Real completion channel" note above.
 - Radio RX is a single 64-byte fragment slot with no multi-fragment
   reassembly (unchanged this sprint — sprint 004 closed the *grammar*
   question, not the *capacity* one). An inbound line longer than one
```
