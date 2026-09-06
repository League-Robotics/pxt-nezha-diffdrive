---
source_file: DESIGN.md
source_hash: a11e260411e0dabea2521c5b2a3a2ac3cb1a78d342ffcf8af9d58a30238f2e27
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -31,7 +31,7 @@
 | Motion engine | `motion/motion_engine.h/.cpp` | `diffdrive.h` + libc only — host-portable |
 | Heading wrap (sprint 006) | `core/heading_wrap.h` | libc only — host-portable, no project includes at all |
 | Encoder glitch armor (sprint 006) | `core/encoder_glitch_armor.h` | libc only — host-portable, no project includes at all |
-| Encoder pose source (sprint 006) | `platform/encoder_pose_source.h` | `motion_engine.h` + libc only — host-portable |
+| Odometry (sprint 033) | `motion/odometry.h` | `motion_engine.h` + libc only — host-portable |
 | Wire grammar | `comms/wire_handler.h/.cpp` | libc only — host-portable, no project includes at all |
 | Wire adapter | `comms/wire_adapter.h/.cpp` | `wire_handler.h` + libc — host-portable; reaches hardware only through forward-declared `shims.cpp` free functions |
 | Transports | `comms/serial_transport.*`, `comms/radio_transport.*` | CODAL (`pxt.h` in the .cpp) — know bytes and framing, **nothing** about verbs, grammar, or motion |
@@ -153,6 +153,40 @@
   Everything else in the kernel — the FF+I law, lambda, bias, stall/
   deficit latches, lease, e-stop, output publication — is untouched by
   this ticket.
+  - **straight_trim** (sprint 031 ticket 019,
+    `docs/sprint-031-postmortem.md` §2.2) — a new `Config::straightTrim`
+    field ([1], default 0, wire ordinal 38): every tick the twist-hold
+    block is active, `straightTrim · cmd.velocity · dt` is added to
+    `twistRef_.reference` directly, alongside (not instead of) K1's own
+    `scaledTwist · floorScale · dt` term — an independent additive bias,
+    not scaled by `floorScale` (it is not a commanded twist the speed
+    floor ever touches). **Positive `straightTrim` makes the RIGHT
+    wheel travel further than the LEFT in encoder space.** It exists
+    because tovez's forward legs curve by a per-robot amount that
+    §2.2's own re-analysis found splits roughly in half: MEASURED tovez
+    2026-09-05 (`captures/session-b-20260905/discriminator-20260905/
+    legs.json`, two 600 mm legs with `TLM FULL`), camera dh
+    −1.37/+1.65 deg vs encoder-integrated dh −0.75/+0.63 deg — so the
+    curvature is **not** purely encoder-invisible (§2.2's original
+    hypothesis (A)); roughly half reaches the encoders and is left as
+    steady-state error by a proportional-only twist hold (gain 4 [1/s])
+    against a constant disturbance (hypothesis (B)), and roughly half
+    never reaches the encoders at all (a ground-side wheel-radius/scrub
+    mismatch — twist hold's own measured error is genuinely zero for
+    this half, which is why retuning `twist_hold_gain` alone, sprint
+    031 tickets 012/015, could never close it). A single bias on the
+    REFERENCE (not the feedback) cancels the total of both components
+    in steady state: it deliberately drives the encoders to twist by
+    the fraction that cancels the invisible half, and the nonzero
+    target it gives the proportional hold also relieves that hold's own
+    residual on the visible half. Measured afterwards (postmortem §2.2a,
+    `captures/session-b-20260905/discriminator-20260905{,-v2}/`),
+    tovez's leg yaw turned out to be a variable, sign-inconsistent
+    breakaway on direction reversal, not a constant curvature, so
+    tovez's trim stays 0 and is NOT to be sized; the field is the right
+    tool only for a robot with a CONSTANT ground-side mismatch.
+    Host-proved (no hardware needed to validate the mechanism) in
+    `tests/host/test_straight_trim.py`.
 - Each `step()` runs split-phase encoder sampling:
   `requestSample()` → 4 ms settle sleep → `tick()` per wheel. Anything
   that lands other I2C traffic inside that settle window destroys the
@@ -256,21 +290,22 @@
   had a getter but no setter (API-06: the doctrine already named
   `rotationalSlip` as the only correct turn-calibration knob, but no
   caller anywhere could reach it). Reachable from `shims.cpp` through
-  the existing generic `ConfigField`/`kFields` mechanism (§5, §9), not
+  the existing generic config-field mechanism (§5, §9), not
   a new dedicated `setGeometry()`-style shim — this field is a
   one-time chassis-calibration constant for a non-reference kit, not a
   value tuned as routinely as `trackWidth`/`travelCalib`.
 - `PoseSource` — the three-read world-pose port (`x()/y()/heading()`),
-  implemented by `OtosPort` on hardware, `EncoderPoseSource` on
-  hardware without an OTOS (sprint 006, §7/§9), and `FakePoseSource`
-  in tests. `MotionEngine` holds no `PoseSource` of its own; it is
+  implemented by `OtosPort` on hardware, `Odometry`
+  (`motion/odometry.h`) on hardware without an OTOS (§9), and
+  `FakePoseSource` in tests. `MotionEngine` holds no `PoseSource` of its own; it is
   passed per `goToW()` call, which is what makes the class
   host-testable with no OTOS in the link. **Sprint 006**: the
   interface's `heading()` contract can no longer state a single wrap
   convention now that two hardware implementations disagree by
   construction — `OtosPort` reports heading wrapped to (−π, π] (the
-  chip's own int16 register), `EncoderPoseSource` reports the same
-  unwrapped heading `shims.cpp`'s odometry already carries. Both are
+  chip's own int16 register), the dead-reckoned source reports its
+  heading unwrapped (`EncoderPoseSource` then, `Odometry` since sprint
+  033). Both are
   contractually valid because `goToR()`/`goToW()` consume `heading()`
   only through `cos()`/`sin()` (wrap-invariant); the header comment now
   says so explicitly instead of asserting one universal convention —
@@ -467,6 +502,24 @@
 start 30 ms apart, `g2-run.log`, `probe-arc.log`); the margin now
 scales with the yaw target (this session's commit); on the reflashed board 6 of 6 arcs ran (`g2-run-b.log`, endpoint mean 10 mm). `omegaFloor`: no hard floor with `vMin = 0` -- full commanded rotation down to 30 mm/s per wheel, ~50 % at 10 (`omega-floor.log`); the compiled 20 deg/s stays.
 
+**Sprint 031: the yaw-scaled margin still false-positives in the first
+minutes after a cold boot.** The wheels' own start-up skew — before the
+drivetrain has settled to its steady-state per-wheel response — can
+still cross the yaw-scaled margin on the very first commanded segments
+after a power cycle, tripping `wrongWay()` on a segment that is not
+actually running backwards
+(`segment-moves-end-early-just-after-boot.md`; two of four early-ending
+segments captured on tovez 2026-09-04 were confirmed wrong-way aborts
+by `wrongWayCount()`). The fix evaluates `wrongWay()` only after the
+dominant axis has progressed a minimum distance, so a brief start-up
+skew cannot trip the check before real motion begins — the yaw-scaled
+margin itself is unchanged once that minimum is reached. The
+stall-latch window (`updateLatch`, §2) is the separate candidate
+mechanism for this sprint's other two (straight-line, `yawTarget == 0`)
+early-end cases, which have no `wrongWay()` path at all; see this
+sprint's ticket 005 for which mechanism the cold-boot capture actually
+confirms.
+
 **Dependencies.** Holds references to a caller-owned kernel and
 `Clock` (the shaper's `dt` and the deadline backstop need wall time
 independent of kernel stepping). Owns **no odometry** — pose stays a
@@ -576,6 +629,55 @@
 the frame cadence (protocol.cpp, 50 ms) for a TLM-subscribed host
 (see §8's Fiber loop).
 
+**Result codes and the write-only answer (sprint 033).** `Result` maps
+1:1 onto the wire's own error numbers: `kUnknown` 1, `kBadArg` 2,
+`kRange` 3, `kFull` 4, `kUnimplemented` 6, `kNotReady` 8, `kBusy` 10,
+and — new — **`kWriteOnly` 12** (`Wire::kErrWriteOnly`), "that name
+exists and cannot be read." The reference grammar numbers its own codes
+1–11 (11, `ERR_DUPLICATE_ID`, is deleted but spent), so 12 is the first
+number free of that range rather than one of the 5/7/9 holes inside it,
+which an older host may already have an opinion about. Its one producer
+today is `GET rebase` (§5). `Adapter::onGet()` returns a `Result`
+rather than a bool so the two refusals are distinguishable at all;
+`resultCode()` names `kErrWriteOnly` rather than re-typing the number,
+pinned by `test_wire_constants_drift.py`.
+
+**Telemetry lines reserve their terminator (sprint 033).**
+`emitHeader()`/`emitFrame()` stop appending content at
+`sizeof(emitBuf_) - 2` and write `'\n'` plus the NUL unconditionally,
+through one shared `terminateEmitBuf()`. They used to share a single
+bound between content and terminator, so once the content reached the
+last writable byte the `append("\n")` silently did nothing and the line
+went out unterminated. Every sink downstream then dropped a byte on the
+assumption a terminator was there, taking a real digit instead: `t …
+-12345` reaching the host as `t … -1234` — a plausible wrong number,
+not a parse error. The widest projected FULL frame this project emits
+is 239 bytes *including* the terminator, one byte inside the buffer, so
+the next column added to FULL would have crossed it. Content truncates
+instead, which is visibly wrong to a host. `buildHelpLine()` always did
+it this way; the two telemetry emitters now match it, and
+`test_wire_telemetry_frame.py` sweeps the boundary a byte at a time
+rather than pinning one length.
+
+**The sequence space reserves its ceiling (sprint 033).**
+`WireHandler::kMaxSequenceId` is `UINT32_MAX`; legal inbound ids are
+`[1, kMaxSequenceId − 1]`. `expectedNext_` may *reach* the ceiling —
+that is what "the last legal id has been accepted" looks like — but no
+line may *carry* it, so `expectedNext_ = id + 1` can never wrap.
+Without the reservation, accepting `#4294967295` set `expectedNext_`
+to 0: a value no id can equal or fall below, so every later line
+nacked asking for id 0 (not legal either) while
+`replyAck(expectedNext_ − 1)` underflowed on top — a session
+unrecoverable except by HELLO, having said nothing about why. A line
+carrying the reserved id is a decode failure (`nack` plus `err 3`,
+`ERR_RANGE`: the shape is fine, the one number in it is out of bounds)
+and does not advance the sequence. `sequenceIdIsExecutable()` is
+public and static so a host test can drive the boundary, since walking
+`expectedNext_` there for real means sending four billion commands.
+Reaching the ceiling legitimately is a terminal state for the session:
+every later line falls below it and re-acks without executing, and
+HELLO — the reset a reconnecting host already sends — is the cure.
+
 **`Adapter` seam.** The pure-virtual contract behind every verb:
 identity/now/status, the six motion verbs (angles arrive as float
 milliradians), estop/stop, GET/SET field delegation, TLM mode,
@@ -636,21 +738,89 @@
 The four verb handlers' refusal-on-`<=0` logic above is **unchanged**;
 only the value it reads changed. **Sprint 006**:
 GO_TO_W no longer answers `kUnimplemented` for "no OTOS connected" —
-`engineGoToW()` now falls back to `EncoderPoseSource` on any robot
-without a live OTOS (§7/§9), so this handler always dispatches to
+`engineGoToW()` now falls back to the dead-reckoned `Odometry` on any
+robot without a live OTOS (§9), so this handler always dispatches to
 `MotionEngine::goToW()`. `mradToRad()`
 here is the **single** place wire milliradians become radians.
-GET/SET map snake_case wire names 1:1 onto the `ConfigField` ordinals
-(`kFields` table) — 15 through sprint 006, 18 as of sprint 007, 19 as
-of 2026-08-29, and **34, as of sprint 029 ticket 004** (design
-`motion-profile-unification.md` §4.7): the ten shaping-related fields
+GET/SET map snake_case wire names 1:1 onto config ordinals — 15 names
+through sprint 006, 18 as of sprint 007, 19 as of 2026-08-29, 34 as of
+sprint 029 ticket 004, and 32 rows today.
+
+**The config surface is one list, in one file.** `comms/config_fields.h`
+holds `kConfigFields[]` — `{name, ordinal, unit}`, one row per name a
+host can `SET`/`GET`, in the order a bare `GET` dumps them.
+`wire_adapter.cpp` includes that header and keeps no copy of its own
+(`kFields`, its old hand-kept copy, is gone). `shims.cpp` carries the
+matching BEHAVIOUR in two tables keyed by the same ordinals —
+`kLimitsFields` (the ten shaping fields, over `MotionLimits`) and
+`kConfigAccessors` (`{ordinal, get, set}`, everything else) — and has
+no per-field `switch` left: `setKernelValue()`/`getConfigValue()` are
+each four lines over those two tables. The behaviour half cannot live
+in the header because every accessor reaches into `Rig`, the kernel or
+the motion engine and therefore needs `pxt.h`, while the header must
+stay host-portable (it is compiled into the host wire tests and
+syntax-checked at the target's own C++11). The split is by portability,
+not preference, and `tests/host/test_config_surface_single_source.py`
+fails if the two halves name different ordinal sets, if an ordinal
+appears in both `shims.cpp` tables, or if `wire_adapter.cpp` grows a
+name table again.
+
+`blocks/motion.ts`'s `ConfigField` enum is **generated** from that same
+header by `tools/gen_config_field_enum.py` and committed — PXT compiles
+a fixed TypeScript file set and cannot read a C++ table at build time,
+so generation plus a drift test is the closest reachable equivalent to
+including it. Each row in the header carries a
+`// ConfigField.<Name>: "<label>"` annotation supplying that row's TS
+member name and `//% block=` dropdown label; a row without one stops
+the generator rather than being skipped. **Re-run
+`uv run python tools/gen_config_field_enum.py` and commit the result
+whenever a row is added, renamed, renumbered, or removed**;
+`tests/tools/test_gen_config_field_enum.py` regenerates and compares,
+so a forgotten run fails the suite instead of shipping a block layer
+that addresses a different field than the wire does. `rebase` (32) and
+`estop_clear` (33) are enum members like any other row as of sprint 033
+ticket 003 — previously they were wire-only names with no member, which
+is why the enum and the wire table were not even the same length.
+
+**`goto_timeout` (39): a field that was private state.** Sprint 033
+ticket 004 added the go-to deadline as an ordinary row of this same
+table, backed by `Rig::goToDeadline`. It is new to the WIRE only. The
+value already existed, as a `shims.cpp`-local field written by
+`engineSetGoToDeadline()` and read by `engineGoToRArmed()` — a
+pre-arming pair that exists because every `//%` shim in this file stays
+at four parameters or fewer (a five-parameter `engineGoToR()` shim
+reproduced PXT's "TS9200: Assertion failed" deterministically, sprint
+015 ticket 006), so `goToR()`'s fifth argument has to reach the shim
+through `Rig` rather than through its own parameter list. That
+constraint is unchanged, and so are both shims' signatures and every
+`blocks/motion.ts` caller; only the storage moved. What the move buys
+is that the deadline is now readable and settable like any other
+config field (`GET goto_timeout` / `SET goto_timeout`), where a private
+field was neither. It was never one-shot: nothing zeroes it after a
+go-to consumes it, and `startGoTo()` sets it immediately before every
+`_goToR()`, so a block-issued go-to overwrites whatever a bench host
+set. That ordering is the contract; the storage never was.
+
+Before this consolidation there were four hand-synchronised lists of
+the same surface (`kFields`, both `shims.cpp` switches, and the enum).
+The visible cost was `protocol.h`'s comment citing "diagValue ordinal
+30" for the RUN-queue drop counter: the real reader is
+`diagValue()`'s ordinal 28, ordinal 30 does not exist in `diagValue()`
+at all, and 30 in the *config* ordinal space — a different namespace
+entirely — is `omega_max`. Corrected to 28. `diagValue()` itself stays
+a separate, read-only table and is deliberately NOT folded into
+`kConfigFields`: its ordinals have no `SET` counterpart and no natural
+unit, and merging them would force every consumer of the config table
+to handle a "no setter" case for the benefit of neither.
+
+Within that one list, the ten shaping-related fields
 (`v_floor`, `stop_distance`, `accel`, `decel`, `v_max`, `jerk`,
 `omega_max`, `omega_floor`, `arrive_dist`, `arrive_yaw`) are no longer
 individually switched in `shims.cpp` — one small descriptor table
 (`kLimitsFields`, `{ordinal, setter, field}` rows over
 `MotionLimits`' own "positive, else keep" setters and public members,
 `motion_limits.h`) is consulted by `setKernelValue()`/`getConfigValue()`
-BEFORE either function's own per-field switch runs, replacing what used
+BEFORE `kConfigAccessors`, replacing what used
 to be up to thirteen independently-maintained `MotionEngine` shaping
 setters with one small, additive table (review CO-05, scoped to this
 design). `v_floor` keeps ordinal 8 (previously `speed_floor`, the
@@ -666,7 +836,7 @@
 name. Eight OLD ordinals (22, 23, 24, 25, 26, 27, 29, 31 —
 `brake_frac`, `dist_taper`, `yaw_taper`, `dist_floor`, `turn_floor`,
 `ramp_ms`, `plateau_min_s`, `profile_exit`) are **removed** outright:
-no row exists for them in `kFields` any more, so both GET and SET
+no row exists for them in `kConfigFields` any more, so both GET and SET
 answer `err 1` (`Wire::Result::kUnknown`, the same reply any
 unrecognized wire name gets) for one release — a stale bench script
 fails loudly instead of silently setting nothing. The
@@ -687,9 +857,10 @@
 latch's state). `stall_clear` is deliberately **not** a new top-level
 wire verb and is **not** folded into `clearEmergencyStop()`/`ESTOP`
 (§9) — the stall latch and the e-stop latch are semantically distinct
-fault classes, same principle sprint 006 established for
-`deliverStopNow()` deliberately not touching `estopLatch_`. **Sprint
-028**: `kFields` gains `rebase` (ordinal 32, backed by
+fault classes, same principle sprint 006 established for the soft
+stop (`Rig::softStop()` since sprint 033) deliberately not touching
+`estopLatch_`. **Sprint
+028**: the table gains `rebase` (ordinal 32, backed by
 `kernel.rebasePosition()` plus, on an OTOS-equipped chassis, the
 platform-layer pose-seed path `seedPose()` already uses so both pose
 sources stay agreed at the zero point) and, riding in the same ticket,
@@ -705,7 +876,28 @@
 ignored) while a motion obligation or RUN job is live, the same
 commandable-state gate other state-changing SET actions already check
 — zeroing the frame or clearing e-stop out from under an active move
-would corrupt in-flight position-error math. STATUS
+would corrupt in-flight position-error math.
+
+**`GET rebase` answers `err 12` (`ERR_WRITE_ONLY`), not `err 1`
+(sprint 033).** `rebase` is the one name in `kConfigFields` with
+nothing readable behind it: no stored value, and no live latch worth
+mirroring the way `estop_clear`'s GET mirrors the estop flag and
+`stall_clear`'s mirrors `stallHalted`. `onGet()` refuses it rather
+than manufacture a reading that would always answer 0 — that part was
+always right. What was wrong was refusing it with the SAME code a
+misspelled name gets: `rebase` is advertised by `fieldName()`, so a
+host that read the field list and then asked for one of its entries
+was told the name does not exist, and its only recourse was to re-send
+it hunting for a typo that was never there. `Adapter::onGet()` now
+returns a `Wire::Result` instead of a bool for exactly this reason —
+a bool cannot distinguish "no such name" from "nothing to read" — and
+`Wire::Result::kWriteOnly` maps to wire code 12 (`Wire::kErrWriteOnly`,
+§4). A bare `GET` dump is unchanged: it lists what can be read, so
+`rebase` stays absent from it. `estop_clear` is deliberately NOT given
+this treatment; it has a real read path and answers `kOk` like any
+stored field.
+
+STATUS
 packs diag booleans into a local
 `flags` word and, since sprint 004 ticket 004, an honest `otos=`
 (`otosGet(7) != 0`, replacing a hardcoded `false` that predated any
@@ -829,6 +1021,24 @@
 call `resolvePendingIfDue()` before returning, so polling either one
 alone is enough to notice a completion.
 
+**Sprint 031: the `kStop`-vs-`kTimeout` split was decided at the wrong
+time.** `resolvePendingReason()`'s "was the wire-side lease still live"
+check reads `now_()` at the moment `resolvePendingIfDue()` happens to
+run — not at the moment `engineMoveActive()` actually went false. A
+segment that finishes well inside its lease still reads `kTimeout` if
+nothing polls STATUS/`lastDone`/`lastDoneReason` before the lease's
+deadline passes, even though the engine went idle long before that
+deadline (MEASURED tovez 2026-09-04: the same pivot read `stop` when
+polled at 8 Hz and `timeout` when polled slower,
+`wire-done-reason-is-resolved-lazily.md`). The fix latches the
+lease-was-still-live boolean at the tick where the protocol fiber's
+existing per-tick hook (§8) observes `engineMoveActive()` transition to
+false, rather than deferring that comparison to whenever
+`resolvePendingIfDue()` next runs. `resolvePendingReason()`'s two
+possible outputs (`kStop`/`kTimeout`) are unchanged — only when the
+decision is made moves earlier, from poll time to the engine's own
+inactive transition.
+
 **Dependencies.** `wire_handler.h`; `shims.cpp` free functions by
 forward declaration only (`stopAll`, `estopAll`, `setWheelsTimed`,
 `setKernelValue`, `getConfigValue`, `diagValue`, `engineWheelsX`,
@@ -859,23 +1069,45 @@
 calls. `kMaxLineBytes` = 240 is deliberately kept equal to
 `WireHandler::kMaxLineBytes` so this transport is never the tighter
 cap (a 201–239-byte line would otherwise be truncated one layer below
-the tested discard-whole-line guarantee). `writeLine()`'s two-writer
-guard (sprint 004 ticket 006) is a **bounded retry inside the call
-itself**: a second caller finding the guard held sleeps `fiber_sleep(2)`
-and checks again, up to `kMaxSendAttempts = 5`, before giving up and
-counting a drop — deliberately a *different* policy from
-`RadioTransport::sendLine()`'s drop-and-retry-once below (the sprint's
-architecture review explicitly approved keeping the two distinct:
-serial has no caller whose loss is "fine" the way telemetry's
-self-healing `seq` gap makes radio's drop acceptable). The drop
-counter is exposed at diag ordinal 26 (`probe(26)`/`diagValue(26)`,
-`shims.cpp`).
+the tested discard-whole-line guarantee). **Single writer: the protocol
+fiber.** `writeLine()` claims and releases nothing. Its two
+`uBit.serial.send(…, SYNC_SLEEP)` calls do yield (once CODAL's TX ring
+fills), but a yield only corrupts a line if a *second* writer can
+interleave into it, and none can: every caller — a v6 reply, a
+telemetry frame, a line another fiber handed to `Protocol::emitLine()`
+and this fiber later drained off the emit ring — reaches it from
+`Protocol::serviceOnce()`, on `Protocol`'s own fiber. The `sending_`
+bool and its bounded `kMaxSendAttempts` retry that used to guard
+against a TS-fiber writer are **deleted**: that writer stopped existing
+when the emit ring shipped, and a guard describing a caller that cannot
+occur is worse than none — it reads as live protection. The drop
+counter stays (a `uBit.serial.send()` that itself reports a failure) and
+is exposed at diag ordinal 26 (`probe(26)`/`diagValue(26)`,
+`shims.cpp`): "did a line ever fail to go out" is a real, still-open
+question, unrelated to how many fibers write.
 
 **RadioTransport.** Frames wire lines for the fleet's RADIOBRIDGE
 relay: `[SEQ][FLAGS][LEN][payload]` fragments (START/MORE/END flags),
-a TX-only port of the fleet's robot-side radio driver. Radio enable is
-lazy (group 10 by default, channel 4 — vevov's fleet assignment —
-power 7). Group is the one field a student program can change, via
+a TX-only port of the fleet's robot-side radio driver. **The v6 radio
+link is opt-in, and this class owns that decision**: `enable()` sets
+it, `enabled()` answers it, and `sendLine()`/`tryReceiveLine()` return
+`false` — touching no hardware — until `enable()` has been called.
+That gate used to be a `Protocol::radioEnabled_` bool checked at three
+call sites the source itself numbered "Gate 1/2/3 of 3" (the RX poll,
+`emitLineNow()`'s radio mirror, and the radio telemetry emission);
+every path into this class has to be gated, not just the poll, because
+BOTH entry points lazily call `ensureRadioReady()` — so a caller-side
+gate is a rule each new call site must remember, while one on the
+object cannot be forgotten. `Protocol` now asks
+`radioTransport_.enabled()` at the one place the answer still buys
+something (skipping `wireHandlerRadio_.emitTelemetry()`, which would
+otherwise format frames and advance its own header state for a link
+that cannot carry them) and lets the transport refuse everywhere else.
+`enable()` does not bring the radio up: bring-up stays
+lazy-on-first-use (group 10 by default, channel 4 — vevov's fleet
+assignment — power 7), so a program that enables the link and never
+sends or polls still never pays `uBit.radio.enable()`'s RAM/softdevice
+cost. Group is the one field a student program can change, via
 `setGroup()`/the blocks layer's "set radio group" block (sprint 021
 ticket 005). The supported path is calling it from `on start`, before
 the radio has come up: `setGroup()` just stores the value, and
@@ -891,15 +1123,39 @@
 **only** called inside that handler because polling an empty queue
 kills the program within two polls (measured; CODAL EmptyPacket
 refcounting). Multi-fragment inbound reassembly is deliberately out of
-scope. Send-path scratch buffers are members, not stack locals — the
+scope.
+
+**RX counters (sprint 033).** `onDatagram()`'s remaining decision —
+accept this line, drop it as over-length, or drop it because the single
+RX slot is still full — is one call to `radioRxClassify()`, which also
+records it in `RadioRxCounters` (`frames`, `accepted`,
+`oversizeDropped`, `overrunDropped`; all saturating). Both live in
+`radio_transport.h` beside `radioRxLineFits()`, for the same reason:
+the header has no CODAL dependency, so the decision worth testing is
+host-testable (`test_radio_transport_rx_capacity.py`) even though its
+one call site is not. `frames − accepted == oversizeDropped +
+overrunDropped` on any healthy build. Before this, `rxFrames_` and
+`rxAccepted_` were public members nothing ever incremented and nothing
+ever read — "did the radio drop anything" had a permanent, confident
+answer of zero — and the single-slot drop, the one that actually
+happens whenever two datagrams land inside one servicing window, was
+not counted at all. The four are surfaced through `Protocol`'s
+`radioRx*Count()` at diag ordinals **31–34** (`probe(31..34)` /
+`diagValue(31..34)`, in that order). The raw fields are gone; a
+read-only `rxCounters()` accessor replaces them, since the fields that
+sat public were exactly the ones nothing maintained. Send-path scratch buffers are members, not stack locals — the
 protocol fiber's 2 KB stack overflowed and hard-faulted with them on
-the stack (measured). Those buffers are no longer single-fiber-only
-(sprint 004 ticket 002): the protocol fiber (via `RadioSink::write()`)
-and the TS fiber (via `Protocol::emitLine()`) both call `sendLine()`
-now, guarded by a `sending_` bool — the second caller in returns
-`false` untouched. `emitLine()` retries once after `fiber_sleep(2)`;
-`RadioSink::write()` ignores the drop by design (a lost `t` frame
-self-heals via the next `seq` gap). Not host-testable (this file
+the stack (measured). Those buffers are **single-fiber use**: the
+protocol fiber is `sendLine()`'s only writer, so they are shared in the
+sense of "reused every call", not "reached concurrently". The
+`sending_` re-entrancy guard, and `emitLineNow()`'s
+`fiber_sleep(2)`-and-retry that existed only to answer it, are
+**deleted** — the TS-fiber writer they guarded against went away when
+`emitLine()` became a ring enqueue drained by this same fiber, and a
+`false` return now means one thing only: the link is disabled. Retrying
+a disabled radio achieves nothing. A telemetry frame or reply that does
+not go out is still accepted silently (a lost `t` frame self-heals via
+the next `seq` gap). Not host-testable (this file
 includes `pxt.h`); verified by code review, first exercised live at
 the bench. **Sprint 008**: `kMaxPayloadBytes`'s own doc comment
 previously claimed it was "sized the same as SerialTransport's bound"
@@ -1124,28 +1380,20 @@
 (350° → −10°) the real register write would produce without needing
 I2C in the link.
 
-**`EncoderPoseSource` (`encoder_pose_source.h`, sprint 006 — new
-host-portable module).** A second `PoseSource` implementation over
-`shims.cpp`'s existing dead-reckoned odometry (`Rig::x/y/heading`), for
-robots with no OTOS fitted — most of the fleet (the OTOS is on vevov
-only). Three-method port, same shape as `OtosPort`: holds const
-references to the Rig's already-computed `x`/`y`/`heading` floats and
-returns them verbatim — it does not compute odometry itself. It is
-constructed as a `Rig` member (or otherwise lifetime-tied to `Rig`'s
-own lazy-singleton, process-lifetime instance) so the references it
-holds never outlive their target — the same lifetime relationship
-`MotionEngine`'s own `kernel_`/`clock_` references already have to
-their `Rig`-owned targets; this is not a dangling-reference risk so
-long as no `EncoderPoseSource` is ever constructed with a shorter
-lifetime than `Rig` itself. It does not need its own epoch-tracking for the "epoch-guarded rebaseline"
-motion-api.md §3.6 calls for, because it reads the same Rig-local state
-`odomUpdate()` already produces, and `EncoderGlitchArmor` above already
-makes that state continuous across a detected brick-reset — the
-guarantee is inherited, not re-implemented. Heading is reported
-unwrapped, matching `shims.cpp`'s existing odometry contract (§3's
-`PoseSource` note on the two implementations' differing wrap
-conventions). Host-portable and host-tested the same way
-`FakePoseSource` already is.
+**`EncoderPoseSource` — RETIRED in sprint 033, replaced by `Odometry`
+(`motion/odometry.h`, §9).** Sprint 006 added it here as a second
+`PoseSource` implementation for robots with no OTOS fitted — most of the
+fleet (the OTOS is on vevov only). It computed nothing: it held `const
+float&` references to `shims.cpp`'s already-computed `Rig::x/y/heading`
+and returned them verbatim, which bought a ~45-line header comment
+explaining why those references could not dangle. Sprint 033 deleted it
+along with the loose fields it pointed at. The pose *is* an object now
+(`Odometry`), it integrates the kernel `Output` itself, and it
+implements `PoseSource` directly, so the fallback `goToW()` selects is
+the same object that computes the number — no adapter, no bound
+references, no lifetime essay. Its unwrapped-heading contract and its
+inherited `EncoderGlitchArmor` continuity guarantee carried over
+unchanged; see `motion/odometry.h`'s own header comment and §9.
 
 **Bus discipline (system invariant; structural as of sprint 030).** The
 Nezha brick and the OTOS share one I2C bus. Every OTOS transaction must
@@ -1194,9 +1442,11 @@
 points against the guard) rather than by three-plus call sites each
 independently remembering a documented rule.
 
-**Staged stop under a live guard (sprint 030).** `deliverStopNow()`
-and the starvation watchdog write the motor register from whichever
-fiber calls them, by design (sprint 006) — a genuine safety path that
+**Staged stop under a live guard (sprint 030).** The soft stop
+(`deliverStopNow()` then; `Rig::softStop()` since sprint 033 folded
+that free function into it) and the starvation watchdog write the
+motor register from whichever fiber calls them, by design
+(sprint 006) — a genuine safety path that
 must not wait on anything. That is still true when the bus is idle.
 When `BusGuard` is held, sprint 030 changes this to a *staged* stop:
 the caller sets a `pendingStop_` flag on the Rig instead of writing
@@ -1243,9 +1493,11 @@
 
 **Responsibility.** The CODAL fiber that plumbs bytes between the
 transports and the v6 wire stack — it knows nothing of the grammar
-itself. Composition by NSDMI in declaration order: `SerialSink`/
-`RadioSink` (each strips the trailing `\n` WireHandler supplies,
-because its own transport appends its own), a single `WireAdapter`
+itself. Composition by NSDMI in declaration order: one
+**`TransportSink`** per transport — all three instantiations of the
+same class (`comms/transport_sink.h`), not three hand-copied `Wire::Sink`
+subclasses as before — each pairing a transport with a one-line writer
+function; a single `WireAdapter`
 (constructed with a placeholder identity; `run()` installs the real
 one via `setIdentity()` once the fiber is executing — the proven-safe
 time to call `microbit_friendly_name()`/`microbit_serial_number()`),
@@ -1259,13 +1511,35 @@
 
 **Fiber loop (`run()`).** Sends the boot banner unsolicited
 (byte-identical to HELLO's reply), then forever: poll serial
-`tryReadLine()` — lines with the literal `RUN:` prefix go to the
-legacy MessageBus bridge, everything else is `feed()`'d to
-`wireHandler_`; poll radio RX the same way (sprint 004 ticket 001,
-closing sprint 003's own Open Question 4) — lines with the literal
-`RUN:` prefix go to the same legacy bridge, preserved unchanged as a
-fallback, everything else — the full v6 grammar — is `feed()`'d to
-`wireHandlerRadio_` instead; every 50 ms, if
+`tryReadLine()`, poll radio RX, poll WiFi — and hand whatever each one
+produced to **`routeLine(handler, data, len)`**, the one inbound path.
+A line carrying the literal `RUN:` prefix goes to the cleartext RUN
+bridge; everything else — the full v6 grammar, including its own
+space-separated `RUN <name> … #<id>` verb — is `feed()`'d to the
+`handler` the caller passed, followed by the separate `"\n"` feed that
+completes the line. Which `WireHandler` that is (`wireHandler_` /
+`wireHandlerRadio_` / `wireHandlerWifi_`, each with its own
+`expectedNext_`) is the ONLY thing that ever differed between the three
+poll branches — which is exactly why the `RUN:` carve-out used to be
+written out three times to stay true on all three wires.
+
+**Each transport drains up to `kRxDrainPerPass` = 4 lines per pass
+(sprint 033), not one.** One per pass meant one per ~24 ms while a
+dispatched job ran, because the tick hook is then this loop's only
+caller — and serial at 115200 delivers ~276 bytes into a 255-byte ring
+in that window, so a host writing two commands back-to-back overflowed
+CODAL's ring, which drops the overflow with no signal whatsoever.
+Four, not more: each routed line can emit several reply lines into an
+8-slot emit ring, and an unbounded drain would starve
+`drainEmitQueue()` and the telemetry cadence, both of which only run
+*between* passes. Four is also what the WiFi branch already bounded
+itself at, so all three transports now answer to one named constant
+instead of three independently spelled numbers. Radio holds a single
+inbound line at a time, so its second iteration usually finds nothing
+— but its datagram handler fires on its own event, so consuming
+promptly is a slot freed before the next arrival finds it busy (and
+that drop is now counted, §6). Then, every
+50 ms, if
 `wireAdapter_.telemetryEnabled()`, call `wireAdapter_.buildSnapshot()`
 **once** and hand that same `Snapshot` reference to both handlers'
 `emitTelemetry(snapshot)` (sprint 004 tickets 003/004) — building it
@@ -1277,7 +1551,29 @@
 any path; §"Reliability layer" above); and while
 `wireAdapter_.hasLiveMotionObligation()`, call `tickDrive()` itself
 (the fiber is the tick source for wire-issued motion), else
-`fiber_sleep(5)`.
+`fiber_sleep(5)`. Every millisecond reading this loop takes comes from
+one method, `clockNow()` — the single place `clock_`'s microsecond
+counter is reduced to the scale the telemetry cadence, the WiFi debug
+period, the RUN dedupe window and `wireNow()` all work in; it replaced
+four separate `nowMicros() / 1000` conversions.
+
+**One sink, `comms/transport_sink.h`.** Outbound, the mirror of
+`routeLine()`. Every reply, ack and telemetry frame leaves through a
+`TransportSink<Transport>`: it decides how much of the written line is
+content and hands those bytes to the transport, which appends its own
+single delimiter. That decision — `wireLineContentLength()` — is why a
+sink drops a byte at all: `WireHandler::writeLine()` terminates every
+line it writes, and passing that byte through as well would double it.
+It is dropped only after being **checked for**, which the three
+hand-copied sinks this replaces did not do: they took the last byte off
+blind, so a line arriving without its terminator lost a real byte
+instead — a plausible, wrong number rather than a visibly truncated
+one. The header has no `pxt.h` dependency (only `wire_handler.h`'s
+`Sink` interface), so unlike the sinks it replaces it is executable
+under `tests/host/test_transport_sink.py`, terminated / unterminated /
+CRLF / empty / maximum-width lines included; the transport a sink is
+paired with, and everything below it, remains review-verified and
+bench-exercised.
 
 **Sprint 028: one execution model, not three.** Before this sprint,
 wire motion ticked on this fiber (above) while `RUN:` motion ticked on
@@ -1358,11 +1654,17 @@
 
 ```mermaid
 graph TD
-    Wire[Serial / Radio transport] --> Protocol
+    Wire[Serial / Radio / WiFi transport] -->|one line| RouteLine[routeLine -- one inbound path]
+    RouteLine --> Protocol
+    Protocol -->|every reply, ack, telemetry frame| Sink[TransportSink -- one Sink class]
+    Sink --> Wire
+    Radio[RadioTransport] -->|enable / enabled -- owns its own gate| Radio
     Protocol -->|drainEmitQueue, then serviceOnce: read/telemetry| Protocol
-    Protocol -->|enqueue on RUN: prefix| RunQueue[run_queue.h ring]
-    RunQueue -->|dropped counter| DiagValue[shims.cpp diagValue ordinal table]
-    Protocol -->|dispatchJob: dequeue + runAction0| TSDispatch[run.ts dispatch via _registerRunDispatch]
+    Protocol -->|offer on RUN: prefix| RunBridge[comms/run_bridge.h -- sanitize, dedupe, park]
+    RunBridge -->|run_queue.h ring| RunQueue[8 x 48 slot ring]
+    RunBridge -->|dropped 28, malformed 30| DiagValue[shims.cpp diagValue ordinal table]
+    Radio -->|rx frames/accepted/overrun/oversize 31-34| DiagValue
+    Protocol -->|dispatchJob: dispatchOne + runAction0| TSDispatch[run.ts dispatch via _registerRunDispatch]
     TSDispatch -->|student onRun handler, nested on protocol fiber -- not forked| StudentCode[Student RUN / button handler]
     StudentCode -->|startMove/driveTwist/startDrive: takes kBlock| MotionOwner
     Protocol -->|motionOwner_ arbitration: kNone/kWire/kJob/kBlock| MotionOwner{motionOwner_}
@@ -1378,18 +1680,52 @@
     NezhaPort -->|EncoderGlitchArmor: raw==0 rejected explicitly| Kernel
 ```
 
-**RUN bridge.** `RUN:<name>[:<arg>…]` parks the payload in an 8-slot
-ring (sprint 026 ticket 002's `run_queue.h`, superseding the original
-4-slot MessageBus-events ring this paragraph used to describe — a real
-queue with occupancy and a saturating drop counter, diag ordinal 30,
-rather than a fixed cursor that could silently overwrite a still-live
-slot). **Sprint 028**: dequeuing no longer raises a MessageBus event at
-all — see the fiber-loop paragraph above for `dispatchJob()`'s direct
-call into `run.ts`'s dispatcher via `_registerRunDispatch()`. 3 s same-
-text dedupe (at arrival, not at handling, so it is immune to any
-queueing) still absorbs hosts repeating commands to survive the
-single-slot radio buffer (measured pre-028: one 3×-repeated RUN ran
-three consecutive pivots) — unchanged by this sprint. **Sprint 008's
+**RUN bridge.** `RUN:<name>[:<arg>…]` is handled by **`RunBridge`**
+(`comms/run_bridge.h/.cpp`), a host-portable object composed into
+`Protocol` — the same extraction shape `run_queue.h` itself already
+has, and host-tested on its own by `tests/host/test_run_bridge.py` with
+no `Protocol`, no fiber and no radio in the link. Its surface is
+`offer(data, len, now)` → one of `kMalformed`/`kSuppressed`/`kBypass`/
+`kQueued`/`kDropped`, `dispatchOne()` (stage the oldest parked payload
+and release its slot), and `currentText()` (what is staged right now).
+It owns sanitizing, repeat suppression, and the 8-slot ring
+(`run_queue.h`, superseding the original 4-slot MessageBus-events ring
+this paragraph used to describe — a real queue with occupancy and a
+saturating drop counter, diag ordinal 28, rather than a fixed cursor
+that could silently overwrite a still-live slot). It does **not** call
+TypeScript and does **not** arbitrate the drivetrain: `Protocol` keeps
+both, because only `Protocol` can see a wire request, a dispatched job
+and a block-program move together. **Sprint 028**: dequeuing no longer
+raises a MessageBus event at all — see the fiber-loop paragraph above
+for `dispatchJob()`'s direct call into `run.ts`'s dispatcher via
+`_registerRunDispatch()`. A **400 ms** same-text dedupe (at arrival,
+not at handling, so it is immune to any queueing) absorbs hosts
+repeating commands to survive the single-slot radio buffer (measured
+pre-028: one 3×-repeated RUN ran three consecutive pivots). The window
+was 3000 ms until it was cut: that was far wider than any retransmit
+burst and made sending one command twice in a row impossible, which is
+exactly the shape a parameter sweep sends.
+
+**Sprint 033 — the bypass names are exempt from the dedupe, and every
+sanitizer refusal is counted.** `abort`/`clearestop` skip the window
+along with the queue. Suppression exists to stop a *host's own
+retransmit* executing twice; an operator hammering `abort` is not
+retransmitting, and the whole point of the bypass is that nothing may
+stand between those two names and the drivetrain — a window that ate
+the second press was the one drop this bridge must never make. It is
+safe because both bypass handlers are idempotent (stop what is
+running; clear a latch that may already be clear), the same property
+that made them safe to invoke reentrantly inside a running job. And
+`offer()`'s four refusal shapes (empty, overlong, non-printable, empty
+name) now increment `malformedCount()`, surfaced at diag ordinal
+**30** — deliberately separate from the ring's capacity count at
+ordinal 28, since a malformed line and a full ring are different
+failures calling for different fixes. Each refusal used to be a bare
+`return`: a 48-character `RUN:tour:…` line with several numeric
+arguments simply vanished, and from the relay that was
+indistinguishable from radio loss.
+
+**Sprint 008's
 own note here is now historical**: the literal event source `0x2001`
 this paragraph used to describe, and `run.ts`'s matching
 `RUN_EVENT_SOURCE` constant, along with the drift test that pinned the
@@ -1417,14 +1753,14 @@
 moved: nothing outside the class needs to name the others, so widening
 them would be access-loosening without a caller to justify it).
 Single-sourcing the name, not the value, closes the drift risk without
-touching radio's actual capacity (sprint 010's scope, §6). Since
-sprint 004 ticket
-002, the radio half checks `RadioTransport::sendLine()`'s bool return:
-`false` means its re-entrancy guard fired against the protocol fiber's
-own concurrent `RadioSink::write()`, and — because this is the one
-caller whose loss is user-visible (a test's own recorded result) —
-this retries once after `fiber_sleep(2)` before giving up silently,
-not in a loop.
+touching radio's actual capacity (sprint 010's scope, §6). The radio
+half no longer checks `sendLine()`'s bool return or retries: `false`
+used to mean "the re-entrancy guard fired against a concurrent writer",
+which is why it was worth one `fiber_sleep(2)`-and-retry; with the emit
+ring making this fiber the sole writer, `false` means "the link is
+disabled", and sending the same line twice to a disabled radio achieves
+nothing. `emitLineNow()` also no longer gates on a radio-enable flag of
+its own — `RadioTransport` refuses on its own behalf (§6).
 
 **Lifecycle.** Lazy singleton `protocol()`, started by a top-level
 `_startProtocol()` call the moment the extension's compiled code loads
@@ -1473,10 +1809,29 @@
 
 Pieces the kernel deliberately does not contain:
 
-- **Odometry** (`odomUpdate`): differential dead-reckoning from
-  kernel `Output` positions using the engine's geometry
-  (`countsPerMm`, `effectiveTrackWidth`), midpoint-heading
-  integration into Rig-local `x/y/heading`. **Sprint 006**: `tickDrive()`
+- **Odometry** (`Rig::odometry`, `motion/odometry.h`): differential
+  dead-reckoning from kernel `Output` positions using the engine's
+  geometry (`countsPerMm`, `effectiveTrackWidth`), midpoint-heading
+  integration into the object's own `x/y/heading`. **Sprint 033** made
+  this one object: the frame, the wheel baseline, the rebase-epoch
+  guard (the codebase's only reader of `Output.positionEpochLeft/Right`
+  now), `reset()`/`seed()`, and the `PoseSource` face `goToW()` falls
+  back to when no OTOS is fitted — where `Rig` used to carry five loose
+  fields, a free `odomUpdate()` over them, and a separate
+  `EncoderPoseSource` adapter bound to them by `const float&` (§7). The
+  integration math moved unchanged, and `shims.cpp` keeps a one-line
+  `odomUpdate(r)` helper that does nothing but hand
+  `kernel.output()` to `Odometry::update()` — the object deliberately
+  holds no kernel, which is what makes it host-testable against a
+  scripted wheel path (`tests/host/test_odometry.py`, the first host
+  coverage this math has ever had). **Reads mutate odometry**:
+  `poseX()`/`poseY()`/`poseHeading()` each call `update()` before
+  reading, and that is load-bearing — between moves nothing else
+  advances the frame, so a host's 50 ms telemetry poll is what keeps
+  pose current. Sprint 033 considered making the reads pure and
+  deliberately kept the contract, documenting it on `Odometry` itself
+  rather than leaving it implicit across three call sites.
+  **Sprint 006**: `tickDrive()`
   now folds `odomUpdate()` into **every** tick unconditionally, not
   only while a move-engine move is (was) active — continuous-mode
   driving (`setWheels`/`driveTwist` under a `while (tickDrive())` loop)
@@ -1548,11 +1903,12 @@
   `isStalled()` (returns `kernel.output().stallHalted`), each reachable
   from a dedicated Drive-group block (`clearStallLatch()`,
   `isStalled()`) parked next to `emergencyStop()`/`clearEmergencyStop()`
-  — and, on the wire, `stall_clear`'s new `kFields`/`ConfigField`
+  — and, on the wire, `stall_clear`'s own config-table/`ConfigField`
   ordinal (§5) reaches the same `clearStallLatch()` call via
   `setKernelValue()`'s ordinal 17. Deliberately **not** folded into
   `clearEmergencyStop()`/`ESTOP` — same principle sprint 006 established
-  for `deliverStopNow()` deliberately not touching `estopLatch_`: the
+  for the soft stop (`Rig::softStop()`) deliberately not touching
+  `estopLatch_`: the
   stall latch and the e-stop latch are semantically distinct fault
   classes, and blurring their clear paths would reintroduce the
   ambiguity that decision fixed for a different pair.
@@ -1588,8 +1944,9 @@
 - **Wire bridges**: `setWheelsTimed`/`driveTwistTimed` (duration =
   lease), the six `engineXxx()` forwards, `engineDefaultCruise()`,
   `diagValue()` (the DIAG/STATUS ordinal table),
-  `getConfigValue`/`setKernelValue` (the ×1000 table, 34 ordinals as of
-  sprint 029 ticket 004's descriptor-table rewrite — see §5), `probe()`,
+  `getConfigValue`/`setKernelValue` (the ×1000 surface, 31 named rows,
+  routed through `kLimitsFields`/`kConfigAccessors` with no per-field
+  switch — see §5), `probe()`,
   `setLimits()` (sprint 029 ticket 004: the one shim replacing the now-
   retired `setTaperWindows`/`setTaperFloors`/`setRampMs` no-op shims —
   see §5), `wheelSpeed()`.
@@ -1608,7 +1965,7 @@
   correctly agreed at seed time for any heading, per §7's OTOS heading-
   wrap fix). **Sprint 006**: `engineGoToW()` no longer refuses when the
   OTOS is not connected — it now selects `OtosPort` when connected,
-  `EncoderPoseSource` otherwise (§7), in this one place, and always
+  the Rig's own `Odometry` otherwise (§9), in this one place, and always
   dispatches to `MotionEngine::goToW()`. This closes
   `no-encoder-odometry-posesource-fallback`: GO_TO_W (and the block
   API's world-pose moves that route through it) is no longer a no-op
@@ -1647,7 +2004,9 @@
 24 ms pacing), and the RUN dispatcher. **Sprint 012** split this out of
 a single `main.ts` into six cohesion-sized modules. Current structure:
 
-- **`motion.ts`** — the `ConfigField` enum, the two movement-default
+- **`motion.ts`** — the `ConfigField` enum (GENERATED from
+  `comms/config_fields.h` by `tools/gen_config_field_enum.py`; edit the
+  header and re-run, never the enum — §5), the two movement-default
   `let`s (`defaultSpeed`/`defaultYawRate`) and their Setup-group
   setters (`setDefaultSpeed`, `setDefaultYawRate`, `setTrackWidth`,
   `setWheelCalibration`, `setConfigValue`), continuous-mode drive
@@ -1744,11 +2103,15 @@
 - **Sprint 032 ticket 008**: `cycleStat()` (`shims.cpp`) and its
   simulator stand-in `_cycleStat()` (`sim.ts`) are deleted outright —
   grepped repo-wide, neither had a caller anywhere in `src/`, `test/`,
-  `tests/`, or `tools/`. `r.tickOverrunCount`/`simTickOverrunCount`/
-  `simCycleCount`, the counters `cycleStat()` used to read, are left
-  in place: they are still written every tick by
-  `tickDrive()`/`_tickDrive()`'s own pacing logic, independent of
-  `cycleStat()` ever existing.
+  `tests/`, or `tools/`. **Sprint 033 ticket 001** finished the job:
+  `r.tickOverrunCount`/`simTickOverrunCount`/`simCycleCount`, the
+  counters `cycleStat()` used to read, had gone write-only (still
+  incremented every tick by `tickDrive()`/`_tickDrive()`'s own pacing
+  logic, read by nothing) — they are deleted too, along with their
+  per-tick increments. The kernel's own missed-deadline count
+  (`out.cycleOverrunCount`, `diagValue()` case 19,
+  `src/core/diffdrive.h`/`.cpp`) is a distinct, real quantity with a
+  real reader (`probe(19)`) and is untouched.
 - Continuous-mode commands (`setWheelSpeeds`/`driveTwist`, `motion.ts`)
   only move the robot while a `while (diffDrive.driveTick())` loop
   ticks; blocking moves tick internally. **Sprint 007**: this is now
@@ -1844,7 +2207,11 @@
   own line ceiling (`tests/host/test_wire_constants_drift.py`). The
   239-byte pathological worst case that used to exceed the old 200
   now fits under 240 — with exactly 1 byte of headroom, thin, not
-  comfortable (`tests/host/test_wire_telemetry_frame.py`). Filed as
+  comfortable (`tests/host/test_wire_telemetry_frame.py`). Sprint 033
+  removed the sharp edge under that thin margin: the frame's
+  terminator is now reserved rather than sharing the content bound
+  (§4), so crossing 239 truncates visibly instead of silently
+  mis-terminating a line the sinks then take a real digit off. Filed as
   `clasi/issues/radio-rx-capacity-fragmentation.md`, closed by sprint
   010.
 - **(Resolved, sprint 008)** ~~The post-move settle loop is
@@ -1879,8 +2246,8 @@
   revisiting if a sprint ever ships without its checkpoint ticket.
 - **(Resolved, sprint 006)** ~~The encoder-odometry `PoseSource`
   fallback for OTOS-less robots is explicitly not built; GO_TO_W
-  refuses on such robots.~~ `EncoderPoseSource` (§7) now serves that
-  role; GO_TO_W dispatches on every robot regardless of OTOS presence
+  refuses on such robots.~~ The dead-reckoned `Odometry` (§9) now
+  serves that role; GO_TO_W dispatches on every robot regardless of OTOS presence
   (§9). Remaining caveat: the fallback carries no drift/uncertainty
   signal back to the caller — a GO_TO_W served by encoders is silently
   a weaker promise than one served by the OTOS, distinguishable today
@@ -2014,8 +2381,15 @@
 motion engine, shim/wire); each is individually defensible, but
 nothing previously stated which one a given entry point delivers. That
 gap is exactly why `shims.cpp::endMove()` shipped for several sprints
-calling `deliverStopNow()` alone, unpaired with `kernel.neutral()` — a
-defect this sprint fixed (see the entry-point table below). Two
+calling the port-level zero alone, unpaired with `kernel.neutral()` —
+a defect this sprint fixed (see the entry-point table below). **Sprint
+033 ticket 004 update:** the three-call sequence the fix produced was
+still written out separately at each of four call sites, and
+`updateMove()`'s branch never matched the other three. It now has one
+definition, `Rig::softStop()`, which absorbed the former free function
+`deliverStopNow()`; the rows below name it, and citations to
+`shims.cpp` line numbers are left as of sprint 016 rather than
+re-derived — read them as "this function", not "this line". Two
 properties distinguish the five: **(a)** does it write to the motor
 ports immediately (tick-independent), or only *stage* a command that
 needs a subsequent `kernel.step()` to reach the motors, and **(b)**
@@ -2028,31 +2402,39 @@
 | Mechanism | Immediate or staged? | Entry point(s) | Persists across subsequent `step()`s? | Requires clearing to resume? |
 |---|---|---|---|---|
 | `kernel.neutral()` (`core/diffdrive.cpp:365-369`) | Staged — overwrites `command_`; the motors are zeroed only on the next `step()` | `MotionEngine::endMove()` (`motion/motion_engine.cpp:103-106`, conditional on `move_.active`); `MotionEngine::serviceMove()`'s move-completion branch (`motion/motion_engine.cpp:451`, unconditional — natural end, timeout, stall, wrong-way, or e-stop); `shims.cpp::stopAll()` (`shims.cpp:767`); `shims.cpp::endMove()` free function (`shims.cpp:755`, unconditional as of this sprint); starvation watchdog (`shims.cpp:726`) | Yes, once a `step()` delivers it — holds until a new `drive()`/`driveDuty()` overwrites `command_` | No (not a latch) |
-| `NezhaMotorPort::emergencyStop()` (`platform/nezha_port.cpp:125-130`) | Immediate — writes zero duty straight to the port, tick-independent | `deliverStopNow()` (`shims.cpp:272-275`), called from `stopAll()` (`shims.cpp:771`), `endMove()` (`shims.cpp:758`), and `updateMove()`'s move-end path (`shims.cpp:505`); the starvation watchdog's direct calls (`shims.cpp:728-729`); `DifferentialDrive::emergencyStopMotors()`'s own internal calls (`core/diffdrive.cpp:381-382`) | **No — momentary.** `command_`/the lease are untouched; the very next `step()` re-commands from them unless paired with `kernel.neutral()` or an e-stop latch | N/A (not a latch) |
+| `NezhaMotorPort::emergencyStop()` (`platform/nezha_port.cpp:125-130`) | Immediate — writes zero duty straight to the port, tick-independent | `Rig::softStop()`, called from `stopAll()`, `endMove()`, the starvation watchdog, and `updateMove()`'s move-end path — all four, exclusively, since sprint 033; `tickDrive()`'s own delivery of a stop `softStop()` staged behind `busGuard`; `DifferentialDrive::emergencyStopMotors()`'s own internal calls (`core/diffdrive.cpp:381-382`) | **No — momentary.** `command_`/the lease are untouched; the very next `step()` re-commands from them unless paired with `kernel.neutral()` or an e-stop latch | N/A (not a latch) |
 | `kernel.estop()` (`core/diffdrive.cpp:371-373`) | Staged — sets `estopLatch_ = true` only; no motor write | `DifferentialDrive::estop()`, called from `shims.cpp::estopAll()` (`shims.cpp:778`) — always paired there with `emergencyStopMotors()` | Yes — re-checked on every `step()` (`core/diffdrive.cpp:485`) regardless of `command_` | Yes — `kernel.estopClear()` (`core/diffdrive.cpp:375-377`), forwarded by `shims.cpp::estopClear()` (`shims.cpp:783`) |
 | `kernel.emergencyStopMotors()` (`core/diffdrive.cpp:379-383`) | Both — an immediate port zero on both motors (same primitive as row 2) **and** `estopLatch_ = true` as a side effect, undocumented at the header (`core/diffdrive.h:200`) | `shims.cpp::estopAll()` (`shims.cpp:779`), reached from the `emergency stop` block (`blocks/stop.ts:21-25`) and the wire's ESTOP verb (`WireAdapter::onEstop()`, `comms/wire_adapter.cpp:494-499`) | Yes — same latch as row 3 | Yes — same `estopClear()` path |
 | Lease expiry (`core/diffdrive.cpp:475-483`) | Staged — a passive per-`step()` check (`cmd.validUntil` vs. the kernel clock), not a caller-invoked action | Not an entry point a caller invokes. `MotionEngine::serviceMove()` reissues a rolling 500 ms lease every tick while a move is active (`motion/motion_engine.cpp:388`), so an abandoned move degrades within 500 ms of servicing stopping; the wire's `WHEELS_V`/`WHEELS_X`/`MOVE_V` verbs set the lease to the caller's full requested duration once, at command time (`kWheelsVDurationCeiling`, `comms/wire_adapter.h:59`) | Yes, once triggered — forces `effective = kModeNeutral` on every subsequent `step()` until a new `drive()`/`driveDuty()` call | No explicit clear — a fresh lease-bearing command resumes motion |
 
 **Row 2 is the one that misleads, and it is this sprint's own
-finding.** `deliverStopNow()` alone — an immediate, port-level zero
-write — is momentary, not a stop: it does not touch `command_` or any
+finding.** The port-level zero write alone — immediate, and since
+sprint 033 the third part of `Rig::softStop()` — is momentary, not a
+stop: it does not touch `command_` or any
 latch, so a still-live kernel command (a long continuous-drive lease,
 in particular) re-asserts a nonzero duty on the very next `step()`.
 Every production call site pairs it with `kernel.neutral()` (row 1) or
 an e-stop latch (rows 3/4) for exactly this reason — `shims.cpp::
-endMove()` calling `deliverStopNow()` unpaired was the gap; it now
-also calls `kernel.neutral()` unconditionally (below).
+endMove()` calling it unpaired was the gap. Sprint 016 fixed that by
+adding an unconditional `kernel.neutral()` there; sprint 033 made the
+pairing structural rather than remembered, by putting all three calls
+inside `Rig::softStop()` so no caller can take one without the
+others.
 
 **Entry points:**
 
 | Entry point | Mechanism(s) delivered | Survives the next `step()`? |
 |---|---|---|
-| `stop` block / wire STOP → `stopAll()` (`shims.cpp:764-772`) | `engine.endMove()` + `kernel.neutral()` (staged) + `deliverStopNow()` (immediate) | Yes |
+| `stop` block / wire STOP → `stopAll()` | `Rig::softStop()`: `engine.endMove()` + `kernel.neutral()` (staged) + the port-level zero (immediate) | Yes |
 | `emergency stop` block / wire ESTOP → `estopAll()` (`shims.cpp:775-780`) | `engine.endMove()` + `kernel.estop()` + `kernel.emergencyStopMotors()` (latch + immediate) | Yes, robustly — latched until `estopClear()` |
-| `stop move` block → `endMove()` free function (`shims.cpp:743-759`) | `engine.endMove()` (stages neutral only if a move-engine move was active) + an unconditional `kernel.neutral()` (this sprint's fix) + `deliverStopNow()` | Yes — the unconditional `kernel.neutral()` is what now also stops a continuous-drive command, not only a move-engine move |
-| Starvation watchdog (`watchdogEntry()`, `shims.cpp:718-731`) | `kernel.neutral()` + `engine.endMove()` + an immediate port zero on both motors | Yes, but non-latching — a fresh `drive()`/`tickDrive()` call resumes motion immediately; re-fires every ~50 ms while abandonment persists |
-| `updateMove()`'s move-end path (`shims.cpp:487-507`, via `MotionEngine::serviceMove()`) | `serviceMove()`'s own `kernel.neutral()` on move completion/timeout/stall/wrong-way/e-stop (`motion/motion_engine.cpp:451`) + `deliverStopNow()` when the move was active and just ended (`shims.cpp:505`) | Yes — same staged-plus-immediate pairing as `stopAll()`/`endMove()` |
-
-No structural change — this section is documentation-only. Every
-citation above was checked against this sprint's final source, not
-carried over from planning notes.
+| `stop move` block → `endMove()` free function | `Rig::softStop()` — the same three, and the unconditional `kernel.neutral()` inside it is sprint 016's own fix, now structural | Yes — that unconditional `kernel.neutral()` is what also stops a continuous-drive command, not only a move-engine move |
+| Starvation watchdog (`watchdogEntry()`) | `Rig::softStop()` — it used to spell the same three out itself, in the opposite order, which reaches the same end state | Yes, but non-latching — a fresh `drive()`/`tickDrive()` call resumes motion immediately; re-fires every ~50 ms while abandonment persists |
+| `updateMove()`'s move-end path (via `MotionEngine::service()`) | `service()`'s own `kernel.neutral()` on move completion/timeout/stall/wrong-way/e-stop + `Rig::softStop()` when the move was active and just ended. This is the site that used to take the port write ALONE; since sprint 033 it takes the same soft stop as the other three, and the two calls it gained are inert here (`service()` has already neutralled the kernel and cleared the Segment) | Yes — same staged-plus-immediate pairing as `stopAll()`/`endMove()` |
+
+Sprint 016 made no structural change here — that section was
+documentation-only, and every citation in it was checked against that
+sprint's final source rather than carried over from planning notes.
+Sprint 033 ticket 004 IS a structural change to the same taxonomy: the
+soft stop's three parts now have one definition instead of four, so
+the rows above name `Rig::softStop()` where they used to name three
+calls per site.
```
