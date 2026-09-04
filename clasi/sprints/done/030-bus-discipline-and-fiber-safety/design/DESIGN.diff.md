---
source_file: DESIGN.md
source_hash: 7386567a038538778bbfaa8fbf36c42b1c0a8dd4a2c3297a5c4aa374c9e071ea
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -727,6 +727,28 @@
 the moment either one commits a resolution — the natural-completion
 path that was the actual gap.
 
+**Sprint 030: the sprint 016 fix only fires when something polls it.**
+`resolvePendingIfDue()` is reached from exactly two places —
+`lastDone()` and `lastDoneReason()` — both driven by a host explicitly
+asking "are you done" (`replyAck`/`replyNack`/`STATUS`). Nothing calls
+either one from protocol.cpp's own `run()` loop, which instead reads
+`hasLiveMotionObligation()` directly to decide whether to call
+`tickDrive()` — a check that reads `motionObligationActive_` and the
+deadline, but never resolves a completed-but-unpolled motion first. A
+host that sends a timed verb, sees (by any means other than
+`STATUS`/`lastDone`) that it finished early, and immediately sends a
+cleartext `RUN:tour` gets it refused by `dispatchJob()`'s
+`motionOwner_ != kNone` gate for the rest of the original verb's
+declared duration, even though the kernel has been idle since the
+verb's own goal was reached. **Fix:** `hasLiveMotionObligation()` calls
+`resolvePendingIfDue()` first, so the one check `run()`'s loop already
+makes every pass is now also the one place a stale-but-finished
+obligation gets cleared — no second poll site to add, no new call for
+`run()` to make. This is additive to the sprint 016 fix, not a
+replacement for it: `lastDone()`/`lastDoneReason()` still resolve
+eagerly for a host that DOES poll; this closes the case where nothing
+does.
+
 **Telemetry projection (sprint 004 ticket 004).** `buildSnapshot()`
 returns a `const Wire::Snapshot&` into a member (mirroring
 radio-robot-lib's own `DiffDriveAdapter::buildSnapshot()`), built from
@@ -757,6 +779,26 @@
 (wire_adapter.cpp, anonymous namespace) is now the single source both
 `status()` and `buildSnapshot()` read, so STATUS's `flags=`/`i2cf=`
 and the telemetry `flags`/`i2cf` columns can never drift apart.
+
+**Sprint 030: `TLM NOW` actually does something.** Through sprint 029,
+`onTlm(TlmMode::kNow)` fell into the `mode != kNow` guard's else branch
+— i.e. it changed nothing and returned `kOk` — with no code anywhere
+that ever emitted a frame in response (`grep -n kNow src/comms` found
+only the mode-decode path, never a producer). A host with telemetry off
+had no way to ask for a single pose fix without subscribing to a
+stream it would then have to unsubscribe from. `onTlm()` now sets a
+`oneShotDue_` flag on `kNow` (still never writing `mode_`, preserving
+the "does not change the current subscription" contract §"protocol.md
+S6.1" already established); `serviceOnce()` checks `oneShotDue_`
+alongside `telemetryEnabled()` each pass and, when set, builds and
+emits exactly one `thdr`+`t` pair on both handlers and clears the flag
+— the same `buildSnapshot()`/`emitTelemetry()` pair the periodic path
+already uses, called one extra time rather than duplicated. If a later
+ticket's investigation finds emitting mid-stream awkward for some
+`TlmMode` combination not yet exercised, the documented fallback is an
+honest `kUnimplemented` refusal (the same shape `TLM BUFFER` already
+uses above) rather than the silent no-op this replaces — either
+outcome is better than "acks and emits nothing."
 
 **Motion-completion resolution (sprint 005 ticket 004).**
 `lastDone()`/`lastDoneReason()` are the wire's completion channel, not
@@ -863,6 +905,40 @@
 legal `FULL`-mode telemetry frame can itself reach up to 239 bytes,
 above this same cap (§10's Open Questions).
 
+**Sprint 030: `execRun()`'s locals, and the protocol fiber's stack
+margin under the sprint 028 call chain.** The radio scratch-buffer
+overflow just above (measured, pre-sprint-004) is the standing reason
+this fiber's stack gets this much attention: it has already hard-faulted
+from large stack locals once. Since sprint 028 the protocol fiber hosts
+the *entire* TS job call chain — `run()` → `serviceOnce()` →
+`dispatchJob()` → `runAction0()` → the student's handler → `tickDrive()`
+→ the service hook → `serviceOnce()` again → `drainEmitQueue()` (a
+241-byte local) → `emitLineNow()` → `sendLine()` — and every yield in
+that chain pays CODAL's context-switch stack copy for however deep it
+currently is. `WireHandler::execRun()` (`comms/wire_handler.cpp`)
+declares `argv[kMaxRunArgs]` (16 pointers) and `result[kMaxRunResultBytes]`
+(224 bytes) before `adapter_.onRun()` can even return a refusal, then
+`sanitized[kMaxRunResultBytes]` (224 bytes) and `buf[kMaxLineBytes + 1]`
+(241 bytes) before the final write — committed regardless of whether
+the call chain above ever gets deep enough for it to matter. **Fix
+(unconditional, independent of measurement):** move `sanitized`/`buf`
+below the `if (outcome != Result::kOk) return;` / `if (!hasResult)
+return;` early returns they already follow textually but not
+stack-allocation-wise (C++ locals are live for their enclosing scope,
+not from point of first use), and move `result` to a member (`emitBuf_`
+already established that pattern in `WireHandler`) if the "commit
+before the adapter can refuse" ordering can't otherwise be avoided —
+whichever ticket 005 finds actually shrinks the pre-refusal high-water
+mark. **Measurement:** a `DIFFDRIVE_FAULT_SPIN` build with a
+stack-canary fill, one full `RUN:tour` plus a `RUN x #1` over radio
+mid-tour, high-water mark read by pyOCD — hardware-only, no host-test
+substitute (this file, `protocol.cpp`, and the TS dispatch path all
+require `pxt.h`). The buffer relocation ships regardless of what the
+measurement shows; the measurement's job is to say whether more
+headroom is needed beyond that, and is recorded as MEASURED with its
+capture artifact or explicitly left UNVERIFIED with what was tried, per
+`.claude/rules/measurement-citations.md`.
+
 **Layering.** Both know bytes and framing only — no verbs, no COBS,
 no semantics. Siblings under Protocol, deliberately uncoupled from
 each other.
@@ -990,6 +1066,23 @@
 Host-tested directly (no fakes needed — it has no hardware dependency
 to fake); see §11 for this module's C++11 syntax-gate coverage.
 
+**Sprint 030: explicit raw-zero rejection.** The 0x46 counter is never
+device-reset, so a destroyed sample from a bus collision (the "Bus
+discipline" hazard below, or a brick power-up before the first real
+read) reads back as raw `0`. The pre-030 two-strike rule only compared
+magnitudes (`|raw - lastGoodRaw| > kMaxDeltaCounts`), so for the first
+~40 cm of travel after power-up — while `lastGoodRaw` is still small —
+a destroyed `0` reading sits within `kMaxDeltaCounts` of the last good
+value and was silently accepted as `kAccept`, teleporting position
+toward 0 and back. `evaluate()` gains one condition ahead of the
+existing magnitude check: `raw == 0 && lastGoodRaw_ != 0` returns
+`kRejectPending` unconditionally, regardless of magnitude — the
+documented Phase-F signature is now named explicitly rather than
+relying on it happening to also be a large-magnitude jump. A genuine
+counter restart (two consistent implausible non-zero reads, or two
+consistent zero reads) still reaches `kAcceptAsRebaseline` through the
+existing two-strike path, unchanged.
+
 **OtosPort** (SparkFun OTOS, I2C 0x17; implements `PoseSource`).
 Ported verbatim from the reference firmware: register map, distinct
 velocity LSB scales (decoding velocity with the position constants
@@ -1042,10 +1135,64 @@
 conventions). Host-portable and host-tested the same way
 `FakePoseSource` already is.
 
-**Bus discipline (system invariant).** The Nezha brick and the OTOS
-share one I2C bus. Every OTOS transaction must run on the same fiber
-that ticks the kernel; an OTOS read interposed in the encoder's
-select→read settle window destroys the encoder sample.
+**Bus discipline (system invariant; structural as of sprint 030).** The
+Nezha brick and the OTOS share one I2C bus. Every OTOS transaction must
+run on the same fiber that ticks the kernel; an OTOS read interposed in
+the encoder's select→read settle window destroys the encoder sample.
+
+Through sprint 029 this was a documented convention enforced at exactly
+one call site: `tickDrive()`'s own `stepBusy` flag serialized
+`kernel.step()` against a second concurrent `tickDrive()` call, but
+nothing else on the bus took it — every OTOS shim entry
+(`otosBegin/Read/Zero/Calibrate/SetOffset`, `seedPose`, all in
+`shims.cpp`) issued I2C unconditionally, `SET rebase`'s OTOS write ran
+synchronously on the protocol fiber, `test.ts` ran a 10 Hz OTOS sampler
+on its own `control.inBackground` fiber, and the `start drive` block's
+background ticker left `read world position`/`set world pose`/
+`calibrate world sensor` reachable from the main fiber with no
+coordination at all. Four independent holes, one shared failure mode
+(§ above, "the documented Phase-F signature").
+
+**Sprint 030** promotes `stepBusy` from a bare `bool` to `BusGuard`
+(`core/bus_guard.h` — host-portable, no `pxt.h`, alongside
+`encoder_glitch_armor.h`/`heading_wrap.h`): `acquire(Sleeper&)` spins
+`while (busy_) sleeper.sleepMillis(1)` then sets `busy_ = true`
+(byte-identical logic to the old inline loop, extracted so
+`tests/host/test_bus_guard.py` can script it against `FakeSleeper::
+onSleep`), `release()` clears it. `Rig::stepBusy` (`shims.cpp`) becomes
+`Rig::busGuard`; `tickDrive()` and every OTOS entry point above acquire
+it — three lines per entry, matching the issue's own estimate. `SET
+rebase`'s OTOS write becomes a deferred `pendingOtosZero` flag on the
+Rig, performed inside `tickDrive()` after the guard clears, the same
+deferred-request shape `kernel.rebasePosition()` already uses.
+`test.ts`'s sampler moves into the job's own tick loop (sampled every
+k-th tick, inside the already-guarded `tickDrive()` call) instead of a
+free-running background fiber. `startDrive`'s background loop
+(`blocks/motion.ts`) now owns its own periodic `readWorld()` call
+inside the same loop that calls `_tickDrive()` — one guarded fiber, one
+list of things it does per pass — rather than leaving `read world
+position` a separate, ungated block a student could call from any
+fiber; that block's own doc comment now says explicitly that it is a
+live bus transaction (the file-level comment already said so; the
+per-function one did not).
+
+The result: every I2C caller on this bus reaches it through
+`BusGuard::acquire()`/`release()`, provably (a source-pin test greps
+`otos_port.cpp`'s `uBit.i2c` callers and `shims.cpp`'s OTOS entry
+points against the guard) rather than by three-plus call sites each
+independently remembering a documented rule.
+
+**Staged stop under a live guard (sprint 030).** `deliverStopNow()`
+and the starvation watchdog write the motor register from whichever
+fiber calls them, by design (sprint 006) — a genuine safety path that
+must not wait on anything. That is still true when the bus is idle.
+When `BusGuard` is held, sprint 030 changes this to a *staged* stop:
+the caller sets a `pendingStop_` flag on the Rig instead of writing
+across the guard, and the busy fiber delivers it itself in the same
+place `tickDrive()` already delivers a post-move settle stop (§ above),
+milliseconds later at worst. The not-busy case (the overwhelming
+majority) is unchanged — an immediate write, no staging, no added
+latency for the common path.
 
 **Yield discipline (system invariant).** The build enables the hardware
 FPU (`-mfpu=fpv4-sp-d16 -mfloat-abi=softfp`) and **CODAL's context
@@ -1153,9 +1300,49 @@
 issue, because the second fiber ran concurrently) as a deliberate fast
 path instead.
 
+**Sprint 030: the service hook checks fiber identity, and the block
+program's fiber becomes a third `motionOwner_` value.** Two gaps
+survived sprint 028's collapse, both from the same root cause — a
+CODAL `MessageBus` handler (a button press, in `test.ts`) runs on its
+**own** fiber, a THIRD executor `motionOwner_`'s two-way `kWire`/`kJob`
+split never accounted for:
+
+1. `serviceHookEntry()` gated on `protocol().motionOwner_ ==
+   MotionOwner::kJob` — a piece of STATE — not on which fiber was
+   calling `tickDrive()`. A button-handler fiber calling `tickDrive()`
+   while a `RUN:tour` job is live on the protocol fiber satisfied that
+   state check and ran `serviceOnce()` a second time, concurrently,
+   corrupting the wire dispatcher's shared `lineBuf_` mid-yield (the ack
+   write yields; the other fiber's `feed()` overwrote the buffer during
+   that yield). Fixed by capturing the protocol fiber's own identity
+   (an injectable "current fiber" accessor, so a host test can pin a
+   fake value) the first time `run()` executes, and checking THAT
+   instead of `motionOwner_`: `serviceHookEntry()` now returns unless
+   `currentFiber() == protocolFiberId_`, full stop — no fiber but the
+   protocol fiber's own `tickDrive()` calls ever run `serviceOnce()`,
+   regardless of what `motionOwner_` says.
+2. `motionOwner_` had no value for "the block program's own fiber is
+   driving" — `startMove()`/`driveTwist()`/`startDrive()` (`shims.cpp`,
+   reached from any TS fiber) called the engine unconditionally, so a
+   button-handler tour could supersede a still-live wire move with no
+   arbitration at all; the wire's own completion channel then resolved
+   that superseded move as `kStop`, indistinguishable from a normal
+   stop. **Decision:** `motionOwner_` gains `kBlock`, not a blanket
+   refusal — test.ts's existing button-triggered tours are a real,
+   working, idle-time use of the robot and refusing them outright would
+   regress that, so the block-motion entry points
+   (`startMove`/`startGoTo`/`driveTwist`/`startDrive`) take `kBlock`
+   ownership the same way `dispatchJob()` takes `kJob`, releasing it
+   back to `kNone` when their own move ends. A wire motion verb arriving
+   while `motionOwner_ == kBlock` is refused the same `kBusy` a
+   `kJob`-held drivetrain already answers with — one arbitration rule,
+   three owners, not two special cases plus a hole. `motionOwner_`/
+   `jobOwnsMotion_`'s pre-existing duplication (CM-14) is folded into
+   this same one-owner field as a byproduct, not a separate change.
+
 Component diagram (target shape, reused from sprint 026's own
-Architecture section, drawn there before this collapse was
-implemented):
+Architecture section and extended here for the bus guard and the third
+motion owner):
 
 ```mermaid
 graph TD
@@ -1164,14 +1351,19 @@
     Protocol -->|enqueue on RUN: prefix| RunQueue[run_queue.h ring]
     RunQueue -->|dropped counter| DiagValue[shims.cpp diagValue ordinal table]
     Protocol -->|dispatchJob: dequeue + runAction0| TSDispatch[run.ts dispatch via _registerRunDispatch]
-    TSDispatch -->|student onRun handler| StudentCode[Student RUN handler]
-    Protocol -->|motionOwner_ arbitration| MotionOwner{wire vs job}
-    MotionOwner -->|tickDrive after stepBusy=false| Rig[shims.cpp Rig / DifferentialDrive kernel]
+    TSDispatch -->|student onRun handler, own MessageBus fiber| StudentCode[Student RUN / button handler]
+    StudentCode -->|startMove/driveTwist/startDrive: takes kBlock| MotionOwner
+    Protocol -->|motionOwner_ arbitration: kNone/kWire/kJob/kBlock| MotionOwner{motionOwner_}
+    MotionOwner -->|tickDrive, guard held only inside step| Rig[shims.cpp Rig / DifferentialDrive kernel]
+    Rig -->|acquire/release, every OTOS + kernel.step caller| BusGuard[core/bus_guard.h]
+    Protocol -->|serviceHookEntry: fiber identity check, not motionOwner_| ServiceHook{currentFiber == protocolFiberId_?}
+    ServiceHook -->|only the protocol fiber's own tickDrive call| Protocol
     Protocol -->|every yield| VfpGuard[vfp_guard.h]
     Rig -->|encoder settle sleeps, via CodalSleeper| VfpGuard
     Rig -->|SET rebase / SET estop_clear| WireAdapter[wire_adapter.cpp SET handler]
     WireAdapter -->|rebasePosition / estopClear| Kernel[core/diffdrive.cpp, byte-identical]
     NezhaPort[platform/nezha_port.cpp collect] -->|held sampleTime_ on frozen-but-acked read| Kernel
+    NezhaPort -->|EncoderGlitchArmor: raw==0 rejected explicitly| Kernel
 ```
 
 **RUN bridge.** `RUN:<name>[:<arg>…]` parks the payload in an 8-slot
```
