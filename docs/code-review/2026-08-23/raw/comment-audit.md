# Comment-hygiene audit — 2026-08-23

Charter: guidelines.md dimension 6 — comments are aids to future readers, **not
historical documents**. This is the delete/rewrite work order that reduces the
comment base to the minimal set that earns its place.

Counting convention: one **block** = a contiguous run of full-line comment
lines, one doc comment (JSDoc/docstring), or one group of same-line trailing
annotations on a single declaration list (a struct's unit tags count as one
block). `//%` pxt annotations, shebangs, and encoding lines are excluded.
KEEP blocks are counted, not itemized. Counts are by-block, hand-tallied
(±1–2 on the large files); the DELETE/REWRITE itemization is complete.

Verdicts: **D** = delete outright. **R** = rewrite; replacement text or the
load-bearing content to keep is given. **A** = add (missing doc on a public
surface). "Noise %" = (D+R)/total.

---

## 1. Summary table

| File | Blocks | D | R | A | KEEP | Noise |
|---|---|---|---|---|---|---|
| src/diffdrive.h | 15 | 0 | 5 | 0 | 10 | 33% |
| src/diffdrive.cpp | 22 | 0 | 1 | 0 | 21 | 5% |
| src/motion_engine.h | 28 | 0 | 8 | 0 | 20 | 29% |
| src/motion_engine.cpp | 20 | 0 | 1 | 0 | 19 | 5% |
| src/nezha_port.h | 14 | 0 | 1 | 0 | 13 | 7% |
| src/nezha_port.cpp | 15 | 0 | 0 | 0 | 15 | 0% |
| src/otos_port.h | 13 | 1 | 1 | 0 | 11 | 15% |
| src/otos_port.cpp | 8 | 0 | 0 | 0 | 8 | 0% |
| src/platform_ports.h | 5 | 0 | 0 | 0 | 5 | 0% |
| src/protocol.h | 15 | 0 | 6 | 0 | 9 | 40% |
| src/protocol.cpp | 20 | 0 | 7 | 0 | 13 | 35% |
| src/radio_transport.h | 13 | 0 | 5 | 0 | 8 | 38% |
| src/radio_transport.cpp | 8 | 0 | 2 | 0 | 6 | 25% |
| src/serial_transport.h | 6 | 1 | 4 | 0 | 1 | 83% |
| src/serial_transport.cpp | 6 | 0 | 2 | 0 | 4 | 33% |
| src/wire_adapter.h | 17 | 0 | 12 | 0 | 5 | 71% |
| src/wire_adapter.cpp | 24 | 4 | 8 | 1 | 12 | 50% |
| src/wire_handler.h | 30 | 0 | 7 | 0 | 23 | 23% |
| src/wire_handler.cpp | 35 | 0 | 3 | 0 | 32 | 9% |
| src/main.ts | 55 | 1 | 5 | 0 | 49 | 11% |
| src/shims.cpp | 40 | 3 | 12 | 0 | 25 | 38% |
| test/test.ts | 25 | 0 | 2 | 0 | 23 | 8% |
| test/testrig.ts | 8 | 0 | 0 | 0 | 8 | 0% |
| tests/host/README.md | 5 (sections) | 0 | 3 | 0 | 2 | 60% |
| tests/host/fake_ports.h | 10 | 0 | 0 | 0 | 10 | 0% |
| tests/host/fake_pose_source.h | 3 | 0 | 1 | 0 | 2 | 33% |
| tests/host/wire_mock_adapter.h | 11 | 0 | 2 | 0 | 9 | 18% |
| tests/host/kernel_shim.cpp | 8 | 0 | 0 | 0 | 8 | 0% |
| tests/host/motion_engine_shim.cpp | 12 | 0 | 3 | 0 | 9 | 25% |
| tests/host/wire_grammar_shim.cpp | 11 | 0 | 1 | 0 | 10 | 9% |
| tests/host/wire_motion_verb_shim.cpp | 18 | 1 | 5 | 0 | 12 | 33% |
| tests/host/test_kernel_harness.py | 14 | 0 | 1 | 0 | 13 | 7% |
| tests/host/test_motion_engine_primitives.py | 22 | 0 | 2 | 0 | 20 | 9% |
| tests/host/test_motion_engine_reductions.py | 30 | 0 | 2 | 0 | 28 | 7% |
| tests/host/test_motion_engine_gotow.py | 20 | 0 | 2 | 0 | 18 | 10% |
| tests/host/test_regression_post_move_neutral.py | 12 | 0 | 1 | 0 | 11 | 8% |
| tests/host/test_regression_yaw_taper_pure_turn.py | 12 | 0 | 1 | 0 | 11 | 8% |
| tests/host/test_wire_grammar.py | 38 | 0 | 3 | 0 | 35 | 8% |
| tests/host/test_wire_motion_verbs.py | 50 | 0 | 3 | 0 | 47 | 6% |
| tests/host/test_wire_reliability.py | 19 | 0 | 1 | 0 | 18 | 5% |
| tools/camlink.py | 8 | 0 | 0 | 0 | 8 | 0% |
| tools/robotlink.py | 7 | 0 | 0 | 0 | 7 | 0% |
| tools/make_deploy.py | 7 | 0 | 0 | 0 | 7 | 0% |
| tools/otos_bench.py | 4 | 0 | 0 | 0 | 4 | 0% |
| tools/otos_levercal.py | 10 | 0 | 1 | 0 | 9 | 10% |
| tools/pivot_truth.py | 6 | 0 | 0 | 0 | 6 | 0% |
| tools/practice_chart.py | 7 | 0 | 0 | 0 | 7 | 0% |
| tools/reposition.py | 5 | 0 | 0 | 0 | 5 | 0% |
| tools/rotation_check.py | 8 | 0 | 1 | 0 | 7 | 13% |
| tools/tour_capture.py | 6 | 0 | 0 | 0 | 6 | 0% |
| tools/tour_chart.py | 9 | 0 | 0 | 0 | 9 | 0% |
| tools/tour_closedloop.py | 6 | 0 | 0 | 0 | 6 | 0% |
| tools/tour_practice.py | 10 | 0 | 0 | 0 | 10 | 0% |
| tools/tour_run.py | 10 | 0 | 0 | 0 | 10 | 0% |
| tools/tour_square.py | 9 | 0 | 2 | 0 | 7 | 22% |
| tools/tour_watch.py | 8 | 0 | 0 | 0 | 8 | 0% |
| tools/truth_check.py | 8 | 0 | 0 | 0 | 8 | 0% |
| tools/turn_sweep.py | 7 | 0 | 0 | 0 | 7 | 0% |
| **Total** | **~854** | **11** | **123** | **1** | **~719** | **~16%** |

Worst files by noise ratio: **serial_transport.h (83%)**, **wire_adapter.h
(71%)**, **tests/host/README.md (60%)**, then wire_adapter.cpp (50%),
protocol.h (40%).

---

## 2. Per-file work order

### src/diffdrive.h
- `1-26` — R — "differential_drive.h — DiffDrive::DifferentialDrive…" — keep the ports summary + vendoring invariant in ~8 lines: *"Vendored from radio-robot-elite (src/firm/control); control law byte-identical to upstream — fix bugs in both trees. Self-contained: only include is <cstdint>. Ports the host implements: Motor (staged duty, split-phase encoder, e-stop), Clock (monotonic us), Sleeper, FiberLauncher (optional — a host owning its loop calls step() directly)."* Drop the manifesto phrasing and the other repo's test-path reference.
- `81-82` — R — "kRefusedNotBegun // command before begin(). NOT before start(): the" — **truncated mid-sentence.** Complete: `// command before begin(); start() is NOT required — step() may be caller-driven.`
- `84` — R — "kCadencePreserved // post-begin setConfig with a differing cyclePeriod:" — truncated. Complete: `// post-begin setConfig with a different cyclePeriod: cadence kept, rest applied.`
- `90-91` — R — "maxDuty // [%] authority rail (lambda scales to" — truncated. Complete: `// [%] authority rail; lambda scales demand down to it.`
- `125` — R — "cycleOverrunCount // cycles that missed their absolute" — truncated. Complete: `// cycles that missed their absolute deadline.`
- KEEP ×10: all unit/sign annotations, the cycleGapCount blocks (119-124, 314-318), seqlock/constants comments.

### src/diffdrive.cpp
- `1-6` — R — "EXTRACTED from src/firm/control/…" — keep the both-trees invariant but name the repo: `// Vendored from radio-robot-elite src/firm/control/differential_drive.cpp (namespace/include changes only). Fix bugs in both trees until the firmware consumes this package.`
- KEEP ×21: this file is the exemplar — the kMaxCycleGapUs measured-runaway block (423-440), seqlock odd/even, "stop is stop; never offset it", "fail closed, never inject NaN", all unit tags.

### src/motion_engine.h
- `1-113` — R — 113-line header brain-dump — compress to ~20 lines keeping ONLY: spec pointer (radio-robot-lib motion-api.md S2/S2.1 — read first); host-portable constraint (no pxt.h/CODAL anywhere in .h/.cpp); the two primitives + move engine one-liners; geometry doctrine (*trackWidth is caliper-measured and never "corrected"; ALL rotational scrub lives in rotationalSlip — keeping them apart is what lets a bad turn be diagnosed*); sign convention (*CCW+; positive twist turns LEFT; left wheel slower in a left turn; never re-derived from cable order — this project shipped that bug and patched it four times downstream*). Delete: every "sprint 003 ticket NNN", the per-method restatements (each method already carries its own doc comment), the shims.cpp extraction narrative.
- `122-132` — R — PoseSource comment — 3 lines: pluggable pose port for goToW(); OtosPort implements for hardware, FakePoseSource for tests; no CODAL dependency.
- `144-157` — R — constructor comment — keep 3 lines: caller owns kernel/clock (references only, like the kernel's own ports); engine needs its own Clock because ramp/timeout need wall time and the kernel's clock_ is private. Drop ticket refs.
- `191-198` (wheelsV doc) — R — drop "Byte-for-byte the math shims.cpp's setWheels()/… already perform" sentence; keep contract + units + clears-planner.
- `214-215` — R — section banner: drop "sprint 003 ticket 007".
- `265-267` — R — taper-knobs banner: drop "shims.cpp's setTaperWindows()… forward to these" (call-graph narration).
- `335-346` — R — rotationalSlip_ comment — keep the measurement + the sign lesson in 3 lines: `// [1] wheel-contact scrub, camera-measured 2026-08-20: six 180-deg pivots turned 164-166 deg physical -> slip 0.952. CAUTION: an earlier single-pivot value (1.040) had the SIGN of the effect backwards (robot under-rotates, it doesn't over-rotate); OTOS agreed with camera to 1.005.`
- `348-349` — R — "(extracted from shims.cpp's former Rig fields, sprint 003 ticket 007)" — drop parenthetical.
- KEEP ×20: geometry method docs, primitive/move-engine method contracts, kTurnFirstAngleRad, MoveState (single-deadline invariant), startSegment/cancelMove, travelCalib_/trackWidth_ measured provenance, shaping-default trade-off block (357-362).

### src/motion_engine.cpp
- `62` — R — "---- move engine (motion-api.md S3.3-S3.5), sprint 003 ticket 007 ----" — drop the ticket ref.
- KEEP ×19: taper/ramp comments, wrong-way SIGNED-progress comment, yaw-taper-double-count block (237-243, measured), rolling-lease reissue rationale (261-267), phase-transition abort rules — all load-bearing.

### src/nezha_port.h
- `1-28` — R (light) — header — keep the failure-mode list verbatim (it is exactly what dimension-6 says to keep); compress lines 3-7 to one provenance line: `// Ported from radio-robot-elite nezha_motor.cpp + motor_armor.h's wedge detector.`
- KEEP ×13: every shaping-stage gotcha, split-phase encoder contract, lastNonzeroSign_/zeroSinceMs_ wedgelab annotations, maxDrivenStreak_ semantics.

### src/nezha_port.cpp — KEEP ×15, no changes. (The writeShapedDuty stage comments, wedgelab (20,50]ms 12/12 measurement, glitch-rejection phantom-teleport capture, commit-only-on-ACK — all exemplary.)

### src/otos_port.h
- `17-19` — R — "NOT ported (yet): the software lever-arm transform (sensorToCentre/centreToSensor)…" — **STALE: contradicted by this same header** (setOffset/sensorToCentre/centreToSensor are declared below and implemented in otos_port.cpp). Delete the paragraph; the setOffset() doc comment (71-77) already covers the lever arm.
- `27-33` — D — "Sprint 003 ticket 010: implements motion_engine.h's PoseSource port… additive only, no behavioral change" — diff narration; the class declaration `: public PoseSource` says it.
- KEEP ×11: LSB-scale trap (measured 2x/11.1x), boot zeroing (phantom 42.7 mm circle), bus discipline (Phase F), begin()/read()/setOffset()/setPose() contracts, register map, kBusClearanceMs.

### src/otos_port.cpp — KEEP ×8, no changes (silent-discard-during-calibration block 92-102 is a model comment).

### src/platform_ports.h — KEEP ×5, no changes.

### src/protocol.h
- `1-16` — R — v5-retirement inventory ("retires the ENTIRE v5 wire format… all of it deleted, not merely unused") — replace with 3 lines: *"Protocol: the CODAL protocol fiber and byte plumbing between SerialTransport/RadioTransport and the v6 wire stack (wire_handler/wire_adapter). Knows nothing of the grammar, reliability layer, or verbs."*
- `18-33` — R — RUN carve-out paragraph — keep the invariant in 4 lines: legacy cleartext `RUN:<name>[:<arg>…]` coexists with v6 on the same wire, detected by literal `RUN:` prefix before the v6 stack sees the line; it is the only path that feeds the MessageBus test-trigger bridge; radio RX accepts ONLY this form.
- `35-45` — R — radio carve-out paragraph — keep 2 lines (radio RX is RUN-only; emitLine() mirrors to both transports); drop the mirror-rationale essay.
- `47-61` — R — retired-TLM note — keep as a crisp 4-line KNOWN GAP: *"v6 has no data-bearing telemetry frame yet: emitTelemetry() sends only ack/nack keepalives. tools/tour_*.py's TLM: parsers silently never fire on this build. Restored by a future thdr/t projection (protocol.md S5.2)."* (Also listed under handoff notes.)
- `144-165` — R — identity NSDMI/timing essay — keep the invariant in 4 lines: identity is read in run() (the fiber body), never at construction — microbit_friendly_name()/serial_number() are not proven safe before uBit.init(); serialBuf_ is a member because WireAdapter borrows a pointer into it.
- `210-216` — R — NSDMI comment — 2 lines: members initialize in declaration order; serialSink_/wireAdapter_/wireHandler_ each depend only on members above them. Placeholder Identity until run() calls setIdentity().
- `227-240` — R — protocol() comment — keep 3 lines: lazy singleton — a global constructor would run before uBit.init() brings up the fiber scheduler; started from main.ts's top-level `_startProtocol()` so the boot banner goes out with no host request.
- KEEP ×9: start()/emitLine()/runText() docs (emitLine's bench-stand rationale is good), RUN slot-ring and dedupe comments, SerialSink newline-strip contract, clock_ note, rxLineBuf_ note.

### src/protocol.cpp
- `4-7` — R — cstdio comment — 1 line: `// plain snprintf: newlib-nano's <cstdio> does not put snprintf in namespace std (same in wire_handler.cpp).`
- `12-26` — R — tickDrive() fwd-decl essay — 3 lines: this fiber calls tickDrive() while a wire motion obligation is live (the kernel has no background fiber of its own); reached by same-package forward declaration — shims.cpp has no header; keep signatures compatible.
- `30-63` — R — identity-constants essay — keep 5 lines: name = microbit_friendly_name() (mbdeploy keys its registry off it — a fixed string would stomp the registry); serial = microbit_serial_number(); kVersion is a manually-synced mirror of pxt.json's "version" — bump together. Drop acceptance-criteria narration. **See handoff: the sync is currently broken (1.0.0 vs 1.0.10).**
- `71-79` — R — poll/emit-cadence comment — drop "carried over from the retired v5 loop… acceptance heritage"; keep the two-sided bound rationale (1 line each).
- `195-200` — R — "No analogous radioTransport_.begin()…" — 1 line: `// RadioTransport self-enables on first use (see ensureRadioReady()).`
- `236-245` — R — v6-feed comment — 2 lines: whole lines go to feed(); the trailing '\n' is fed as a second call (feed() reassembles regardless of chunking).
- `314-321` — R — startProtocol comment — drop "(ticket 002)"; keep the top-level-statement / idempotence explanation (2 lines).
- KEEP ×13: kOldRunPrefix, kRunEventSource must-match, protocolEmitLine PXT-radio-dependency trap, handleRun sanitize + measured dedupe block, runText, wireNowMs safety note, run()'s banner/carve-out/reliability-cadence/obligation comments, fiber_sleep note, gProtocol.

### src/radio_transport.h
- `1-33` — R — header — keep ~10 lines: role (thin CODAL leaf; knows uBit.radio + RadioRelay framing, nothing else); the on-air fragment layout table `[SEQ:1][FLAGS:1][LEN:1][payload]`, flags START/MORE/END, single-fragment = START|END; TX-only: no datagram listener, no reassembly, FLAG_ACK never used; provenance one-liner (MicroBitRadioLink, RadioRelay wire spec §5). Delete the sprint.md quotation block.
- `43-59` — R — sendLine doc — **stale**: "COBS here is keyed on 0x0A… see protocol.h" (v5/COBS retired). Keep: appends one trailing 0x0A; truncates, never overflows; lazily enables radio on first call (enable() has RAM/softdevice cost a serial-only user shouldn't pay).
- `84-93` — R — sendFragmented doc — drop sprint.md Open Question refs; keep MTU derivation from MICROBIT_RADIO_MAX_PACKET_SIZE + always-emit-one-fragment rule.
- `106-115` — R — kGroup/kChannel comment — 2 lines: `// Fleet RADIOBRIDGE convention. Channel 4 = vevov's assigned channel (zavaz relay matches: !CG 4 10); group 10; power 7.`
- `118-125` — R — kMaxPayloadBytes essay — 1 line: `// Local truncation bound; equals SerialTransport's only because both carry the same lines.`
- KEEP ×8: tryReceiveLine doc, onDatagram (bench-measured recv-on-empty kill — critical), member-scratch stack-overflow measurement (128-132), flag constants, FLAG_ACK note, kFrameHeaderBytes, RX diagnostics, txSeq_.

### src/radio_transport.cpp
- `1-12` — R — header — 3 lines (role + provenance one-liner); drop the "trimmed to exactly what a sender needs" essay (the .h now says it).
- `127-132` — R — sendLine comment — drop "(see this module's header for why that's safe for binary content)" — stale COBS cross-ref; keep terminator + truncation lines.
- KEEP ×6: ensureRadioReady call-order + band-must-be-set-explicitly, reference-style RX, kMaxFrame locality, multi-frag drop, member-scratch pointers.

### src/serial_transport.h  (worst file — 83% noise)
- `1-12` — R — header — **stale**: "for the Protocol v5 wire link", "COBS here is keyed on 0x0A, not 0x00 — see protocol.h" (protocol.h no longer documents any of that). Replace with 4 lines: thin CODAL leaf owning uBit.serial + 0x0A line delimiting; carries (buffer, length) pairs, never NUL-terminated strings — line content may legally contain 0x00.
- `20-32` — R — kMaxLineBytes essay — 2 lines: `// One wire line's content, excluding the trailing 0x0A. MUST stay == Wire::WireHandler::kMaxLineBytes (240): if this layer is the tighter cap it truncates overlong lines into still-parseable prefixes one layer below WireHandler's tested discard-whole-line guarantee.`
- `36-47` — D — begin()'s first paragraph — **describes readLine(), a method that no longer exists on this class** (the doc was left behind when the method was removed; four more readLine() references at lines 58, 60, 67, 77 and serial_transport.cpp:60).
- `48-50` — KEEP (the actual begin() doc: ring-sizing) — but reword "full binary v5 frame" → "a full line arriving as one burst".
- `54-56` — KEEP — writeLine.
- `58-72` — R — tryReadLine doc — keep the contract (never sleeps; drains buffered bytes; true iff a full line completed; outCap-truncation) minus "counterpart to readLine()" and "(ticket 005: …)".
- `75-80` — R — partial_ comment — drop the readLine() comparison; 1 line: `// Accumulation is fixed at kMaxLineBytes; outCap only bounds the copy-out.`

### src/serial_transport.cpp
- `18-23` — R — begin() comment — **stale** "one binary v5 frame (WHEELS is ~27 wire bytes)". Keep: `// codal's rx ring defaults to ~20 bytes; a line arriving as one burst at 115200 overflows it between protocol-fiber polls (measured: mangled frames, eaten delimiters). Size both rings for a few full lines.`
- `59-61` — R — "mirrors readLine()'s own truncate-not-overrun behavior" — readLine() is gone; say `// past kMaxLineBytes: keep consuming so the stream stays framed; stop copying.`
- KEEP ×4: ASYNC semantics, drained-break, delimiter handling, retained-partial note.

### src/wire_adapter.h  (71% noise)
- `1-108` — R — the 108-line header is the largest single brain-dump in the repo: three sprint-ticket chronicles, a bug-and-fix history (ticket 011's missing obligation arming), and justification-to-reviewer throughout. Replace with ~12 lines: concrete Wire::Adapter for this robot; all six motion verbs have real effect; STOP/ESTOP/GET/SET and the engine* calls reach shims.cpp via same-package forward declarations (shims.cpp has no header — wire_adapter.cpp's block must stay signature-compatible); holds no kernel/engine reference of its own; host-portable — no pxt.h/CODAL anywhere (host tests supply their own definitions of the forwarded functions); Identity fields are borrowed pointers; now() comes from a NowMsFn supplied at composition (nullptr ⇒ now()==0 and hasLiveMotionObligation() always false); every ACCEPTED motion verb arms a motion-obligation deadline (duration for V-forms, timeout for X/GO_TO forms — a conservative overestimate, harmless) that protocol.cpp's fiber polls to keep ticking the kernel.
- `120-129` — R — kWheelsVDurationCeiling — 2 lines: `// [ms] WHEELS_V/MOVE_V duration ceiling (motion-api.md S1): duration IS the lease — a dead host cannot mean a runaway. Enforced here; the handler holds no bounds table.`
- `155-162` — R — setIdentity — 2 lines: placeholder-at-construction, real identity later — a CODAL identity read is unsafe before uBit.init() (protocol.cpp calls this from its fiber body). Same borrowed-pointer contract.
- `167-176` — R — onWheelsV doc — 2 lines: forwards to setWheelsTimed() (velocity=(l+r)/2, twist=(r-l)/2 CCW+, duration = lease); only the ceiling is enforced here — no kernel refusal is observable (setWheelsTimed returns void).
- `180-194` — R — onWheelsX doc — keep: wire fields already mm/mm/mm-per-s/ms; cruise<0 refused kRange (a ceiling has no sign); cruise==0 → configured default via engineDefaultCruiseMmS(), refused kRange if that too is unconfigured. Drop citations/ticket refs (~4 lines).
- `198-209` — R — onMoveX doc — keep: same cruise handling; `rotation` is THE mrad→rad seam (mradToRad(), tested both signs). 3 lines.
- `211-225` — R — onMoveV doc — 2 lines: plain wheelsV reduction; omega through the same mrad seam; duration shares kWheelsVDurationCeiling.
- `227-240` — R — onGoToR doc — 2 lines: speed plays cruise's role (same <0/==0 handling); arrive passes through unused (single-shot reduction); timeout is moveX's backstop.
- `242-265` — R — onGoToW doc — keep the DECISION in 3 lines: *no encoder-odometry fallback exists, so "no OTOS fitted/begun/connected" is a real state; answers kUnimplemented ("recognized, not wired on this build") rather than kRange/kNotReady — this is what keeps it from driving toward a garbage pose.* Drop the citation pile.
- `270-277` — R — config section banner — 2 lines: field-name table replacing the old ordinal verbs 1:1; see wire_adapter.cpp's kFields for the mapping.
- `286-292` — R — hasLiveMotionObligation banner — 2 lines: true iff the most recent accepted motion verb's window has not elapsed; always false with no clock wired.
- `295-317` — R — the 23-line lastDone() DECISION essay — 3 lines: *No completion channel yet: the engine* bridge functions return void/availability-only and this class deliberately holds no MotionEngine reference, so 0/kNone (wire-correct, inert) is returned. Revisit when a host actually consumes lastDone().*
- `336-337` — R — private banner: drop ticket tag.
- KEEP ×5: NowMsFn rationale (plain fn ptr, no heap/CODAL), constructor borrowed-pointer contract, onEstop/onStop tags, onRun no-registration-table comment, motionObligationDeadlineMs_ unit tag.

### src/wire_adapter.cpp
- `1-4` — R — file comment — **STALE**: "why five motion verbs answer kUnknown" — all six have real effect (this very file dispatches them). Replace: `// wire_adapter.cpp -- see wire_adapter.h for the class contract.`
- `12-21` — R — forward-decl block 1 — 2 lines: `// shims.cpp entry points (no header of its own): plain same-namespace forward declarations, must stay signature-compatible with shims.cpp's definitions.`
- `29-48` — R — forward-decl block 2 — fold into one comment with block 1; keep the one invariant: rotationRad/omegaRad arrive ALREADY converted (mradToRad below); the cruise-0 sentinel is resolved BEFORE these are called.
- `50-70` — R — forward-decl block 3 — fold in; keep engineGoToW()'s bool = "a live PoseSource was available", not a dispatch failure.
- `74-82` — R — kFields comment — 2 lines: 15 wire names onto setKernelValue()/getConfigValue() ordinals; declaration order matches main.ts's ConfigField so a bare GET dumps in that order.
- `195-211` — R — status() preamble — this 17-line "flagged here for whoever picks this up next" essay is real content in the wrong home. 3 lines: *"Deliberate narrowing: v6 has no DIAG verb; flags carries only the 8 boolean diagValue() reads. The old DIAG's numeric bench fields (i2c fault counter, per-wheel pos/duty/vel, counters) have NO v6 equivalent."* — and file it as an issue (see handoff).
- `228-231` — R — "active" comment — **stale** "this robot's WHEELS_V-only, planner-free command surface". Replace: `// "active": ready, not halted, and a wheel is measurably moving.`
- `259-261` — R — onWheelsV obligation comment — 2 lines (record deadline so protocol.cpp keeps ticking; no-op without a clock); drop ticket tag.
- `286-293` — R — onWheelsX obligation comment — keep only: `// timeout is a backstop, not the real duration -- conservative deadline; ticking a little past completion is harmless.`
- `313` — D — "// sprint 003 ticket 012: see onWheelsX()'s identical comment above." (onMoveX)
- `331-332` — D — same repeated tag (onMoveV; keep the "duration IS the lease" half-line if wanted).
- `351` — D — same repeated tag (onGoToR).
- `377-378` — D — same repeated tag (onGoToW; keep "only armed on the path that dispatched").
- `392-396` / `409` — R — onEstop/onStop obligation comments — keep the rationale once (e-stop must revert the fiber to idle poll immediately), drop ticket tags; onStop's may say "see onEstop".
- `367-373` — R — onGoToW comment — 2 lines (fallback not built → real reachable state; kUnimplemented per header).
- **A** — onGet/onSet (`422-436`) — the ×1000 fixed-point convention is uncommented at the one place it is applied on the wire path. Add: `// config values cross the shim boundary as x1000-scaled ints (shims.cpp convention).`
- KEEP ×12: flags-layout comment, kDiag ordinals, tlmModeWireName kNow note, **mradToRad (159-173 — keep verbatim; the off-by-1000 failure narrative is exactly a dimension-6 keeper)**, now() comment, exact-narrowing-cast note, hasLiveMotionObligation wraparound idiom, onTlm kNow note, onRun comment.

### src/wire_handler.h
- `1-87` — R — header — the reliability-layer summary (14-68) is genuine wire-format documentation: KEEP it. Delete/replace lines 70-87: "Sprint 003 ticket 004 adds… WHEELS_V gets real effect there; **the other five answer Result::kUnknown, a deliberate 'no planner yet'**" — STALE (all six are real in wire_adapter.cpp) and ticket archaeology. Keep only: angles are milliradian integers on the wire (degrees-at-API conversion is a binding's job) + the host-portable constraint.
- `95-100` — R — Sink comment — drop "so a later ticket wiring this onto SerialTransport… has nothing to redesign here" (the ticket landed); keep the one-write-per-line-including-'\n' contract.
- `107-113` — R — Identity comment — drop "(ticket 003; ticket 002 only needed name/serial…)" tail.
- `169-174` — R — DoneReason comment — **stale** "Carried here even though this ticket wires up no motion verb yet". Keep: wire spellings + "every sequenced ack/nack piggybacks this pair (S8.8)".
- `183-198` — R — Adapter comment — drop the "This is NOT sprint.md's own src/wire_adapter…" meta-clarification; 3 lines: the seam behind every verb; production impl = diffDrive::WireAdapter; test double = WireMockAdapter.
- `423-430` — R — kCommandTable comment — keep the HELP-cannot-drift rationale; drop "Ticket 004 inserted the six motion verbs…" sentence.
- `482-490` — R — motion decode/exec banner — drop "(motion-api.md S9.1's wire mapping, sprint 003 ticket 004)" and the WHEELS_V-history tail; keep the decode/exec shared-contract line.
- KEEP ×23: StatusFields, Result (incl. the deleted-kDuplicateId note), TlmMode, motion-method unit annotations, onStop `now` note, completion-channel contract, onRun contract, kMaxLineBytes, **feed() doc (272-318 — the NUL characterization and overflow rule are exactly right)**, sendBanner, emitTelemetry (keep the no-telemetry-frame-yet gap note), malformedCount, tokenizeLine, dispatch, handleDecodeFailure, DecodeFn/ExecuteFn contracts, kMaxFieldTokens/kMaxRunArgs/kMaxRunResultBytes, stand-ins note, reliability-state note.

### src/wire_handler.cpp
- `10-22` — R — cstdio/strtof comment — 2 lines: `// plain snprintf/strtof: newlib-nano's headers declare them globally but not in namespace std; every other std:: function this file uses genuinely is.` Drop the discovery story.
- `433-437` — R — "Unrecognized verb (including every motion verb this ticket does not yet wire up)" — **stale** (all six are in kCommandTable). Replace: `// Unrecognized verb: a decode failure exactly like bad arity -- the sequence does NOT advance.`
- `741-749` — R — motion section banner — drop "(sprint 003 ticket 004)" and the pre-history tail; keep the mrad-integers + wire-int→float note.
- KEEP ×32: parse-helper strictness comments, formatConfigValue NaN-UB analysis, sanitizeLineText, overflow/blank-line/embedded-NUL guards, case-is-direction, ESTOP/PING/HELLO handling, three-way id classification comments, -Wswitch note, execRun's kMaxLineBytes+1 subtlety, emitTelemetry.

### src/main.ts
- `52-72` — R — **jumbled triple comment above the run-state variables**: (a) lines 52-59 document `_startProtocol()` but sit 27 lines away from that statement (line 86) — move them to it; (b) lines 60-63 (runParts semantics) stay; (c) lines 64-72 (no-initialiser PXT init-order trap, measured panic 980) stay — that one is a top-tier keeper. Mechanical split + move.
- `143-153` — R — RUN comment — keep must-match-kRunEventSource + slot mechanism; drop the "the way the old numbered vocabulary had to (RUN:30000+us…)" tail.
- `266-276` — R — startMove doc — drop "This sprint does not supply that tick source"; say "nothing supplies that tick automatically".
- `546` — D — `let maxNudges = 6  // bounded arrival retries` — comment (and variable) describe the pre-one-pass goToWorld that no longer exists; goToWorld never reads it. (See handoff — delete the dead variable with it.)
- `740-748` — R — sim tick comment — drop "(sprint 002)".
- `756-767` — R — simIntegrate clip comment — keep the fraction-clip rationale (2 lines); drop the 10 ms→24 ms cadence history and "caught by this ticket's own net-zero-pose simulator check".
- KEEP ×49: file header (units/conventions), all student-facing block JSDoc (checked against implementations — accurate and crisp; the repeated tick-model warnings on startMove/isMoving/moveProgress/stopMove are justified for students), world-pose doctrine + I2C fiber constraint, goToWorld one-pass/curvature-cap measured blocks, turnFirstDeg measured rationale, emitLine's "do not write the word r-a-d-i-o" PXT trap, otosGet unit table, `// [rad/s] over track`, _cycleStat, OTOS section.
- Public-API bar check: every exported block has a doc comment; none missing. (probe()'s doc lives in shims.cpp's misplaced block — see shims.cpp 898-912.)

### src/shims.cpp
- `1-27` — R — header — keep the four-bullet composition summary and the integer-boundary convention (25-27, load-bearing); drop "(sprint 002)" tags inside bullets.
- `29-53` — R — "Second caller (ticket 003)… Third caller (ticket 011)… Fourth caller (ticket 012)…" — three paragraphs of caller-history. Replace with 3 lines: *"Also called directly by protocol.cpp and wire_adapter.cpp via same-package forward declarations (this file has no header): tickDrive/stopAll/estopAll/setWheelsTimed/setKernelValue/getConfigValue/diagValue and the engine* wire forwards. Keep signatures compatible with their forward-declaration blocks."*
- `77-85` — D — orphaned fragment: "Excludes the first one or two pivots of a session, which over-rotate grossly (262 and 233 deg…)" has **no referent** (its subject — the slip measurement — moved to MotionEngine; the sentence now dangles at the top of Rig), plus moved-fields archaeology. The init-order invariant it mentions is restated at 119-123 which stays.
- `130-137` — D — "Move-engine state … moved into `engine` itself, sprint 003 ticket 007 … below are now thin forwards" — restatement of a diff.
- `139-141` — R — drop "(sprint 002)"; keep "caller-driven stepping replaces the kernel's own unwired fiber pacer".
- `201-205` — R — watchdog-launch comment — drop "this sprint"; 2 lines.
- `237-244` — D — "setWheels()/driveTwist() and their two timed variants below are now thin forwards into MotionEngine::wheelsV() (sprint 003 ticket 006) -- the math is unchanged…" — diff narration; the four-line bodies say it.
- `264-279` — R — setWheelsTimed banner — keep 3 lines: duration is the kernel lease (expiry auto-neutralizes on the next step; no timer needed); deliberately not `//%`-annotated — not block-facing; protocol.cpp is the only caller.
- `299-317` — R — engineWheelsX banner — keep 3 lines: wire-shaped units throughout; rotationRad arrives already converted (wire_adapter.cpp's mradToRad); cruise<=0 is MotionEngine's no-op — the 0-means-default substitution happens in wire_adapter before these; not `//%`-annotated.
- `415 (418-421)` — R — updateMove comment — drop "matching the pre-extraction free-function serviceMove()'s own early-return gate"; keep "odomUpdate only while a move was active — pose stays lazily updated otherwise".
- `427-447` — R — tickDrive banner — keep the pacing contract + always-steps + returns-post-service state (all load-bearing); drop "(sprint 002)"/sprint.md citations. ~8 lines.
- `501-519` — R — the 19-line "Sprint 003 ticket 013 note, carried over from ticket 009's own report" essay — 3 lines: *"KNOWN GAP: this settle loop is exercised only on hardware — it is welded to Rig-local odometry (odomUpdate), which no host build links. Extracting it means moving odometry into motion_engine (a real architectural change). test_regression_post_move_neutral.py mirrors the loop's shape but cannot execute this body."*
- `570-603` — R (light) — watchdog section — keep essentially all of it (it is the best long comment in the file); delete the two "this sprint" phrases and the sprint.md citation.
- `674-678` — R — diagValue comment — **three stale claims**: "for the wire protocol's DIAG verb" (retired), "protocol.cpp is the only caller" (wire_adapter.cpp and probe() also call it), "floats are scaled x100" (only duty is; positions/velocities return raw counts). Replace: `// Kernel Output accessor, one int per field: booleans 0/1, duty x100, positions/velocities raw counts. Callers: wire_adapter.cpp status(), probe() (TS).`
- `700-712` — R — the case-20..25 comments — fine content, but case 25 sits between the "23/24" comment and cases 23/24. Reorder the cases (or move the comment) so comments sit above what they describe.
- `788-809` — R — getConfigValue 22-line essay — **stale**: "(ticket 004: Protocol's GET_CONFIG verb handler)" and "protocol.cpp's handleGetConfig() validates the field range itself" (both retired; wire_adapter.cpp's kFields is the caller now). Replace with 3 lines: read-back counterpart to setKernelValue() — same ordinals, same x1000 scaling; reads config() (staged_, written synchronously by every setter, so always current); not `//%`-annotated — C++-internal, wire_adapter.cpp is the caller; unknown field → 0.
- `850-863` — R — engineMoveV banner — 3 lines (same fold as 299-317; keep the placed-after-otosRef() ordering note).
- `875-888` — R — engineGoToW comment — keep the honest-refusal rationale in 3 lines; drop ticket/spec citation pile.
- `898-912` — R — **two unrelated comments concatenated**: lines 898-904 are probe()'s doc (probe() is at line 946 — move them there; the per-tick-recording/radio-round-trip measurement is a keeper); lines 905-907 are setTaperWindows's doc (stay); lines 908-912 (PXT TS9200 five-arg shim failure + `//%`-adjacency trap) are a top-tier keeper — stay, but as their own block.
- KEEP ×25: vevov wiring block (87-111 — measured sign-convention forensics, keep verbatim), init-order (119-123), tovez kernel defaults + twist-hold rationale, TICK MODEL block with the deliberate commented-out `rig->kernel.start()` (reason stated — allowed to stay), move-completion stop delivery (472-481) and settle ticks (483-489), startMove dual-rate reconciliation algebra (359-376), cycleStat, watchdog constants/commandLooksActive/watchdogEntry, odometry tags, wheelSpeed, emitLine/runCommandText forward-decl notes, seedPose.

### test/test.ts
- `69-71` — R — "A FAILED read used to log the previous (usually zero) values…" — drop "used to"; state the invariant: `// A failed read is logged explicitly: silence would be indistinguishable from a real fix at the origin.`
- `229-239` — R — tourWorld taper comment — 10 lines of misdiagnosis history. Keep 3: *"200 mm/s (stakeholder); 60 cm/s was near the drivetrain ceiling. Accuracy-tuned shaping restored: the earlier 'taper too slow' reading was actually the yaw-taper double-count bug (see serviceMove) masking as a profile problem."*
- KEEP ×23: file header (tour map + button/RUN vocabulary), dot coordinates, measured lever arm block (42-49), tour docstrings (robot-relative rationale, straight-line WHEELS-ONLY discipline, tourWorld's deliberate non-worldReady() trap note, leverCal geometry), goto/face/seedxy handler comments (on-device closed-loop rationale — measured).

### test/testrig.ts — KEEP ×8 (the RUN:<n> vocabulary table, one-worker-fiber bus rule, lever-arm test-hook rationale; "This rig predates the named-verb dispatch" is a useful live note).

### tests/host/README.md
- "What's here" — R — stale/incomplete: lists only fake_ports.h / kernel_shim.cpp / test_kernel_harness.py. Either extend to the current inventory (add fake_pose_source.h, wire_mock_adapter.h, the three other shims, the eight other test files — one line each) or cut to "one shim + one test file per subsystem; see the file headers".
- "What this does NOT cover yet" — R — **STALE, the known one**: claims `wire_handler`/`wire_adapter`/`motion_engine` "none of which exist yet". They exist and are covered (test_wire_grammar/reliability/motion_verbs, test_motion_engine_*). Replace the section with what is genuinely uncovered: shims.cpp/protocol.cpp (CODAL-bound: tickDrive's settle loop, the watchdog, transports), and PXT/simulator behavior.
- Intro — R (light) — drop "This repo's first test suite" and the "later sprint 003 tickets" framing.
- KEEP: "Run it", "Build recipe".

### tests/host/fake_ports.h — KEEP ×10 (sampleTime-on-success and rebaseline-no-bus contracts, velocityValue's only-reader note — all earn their place).

### tests/host/fake_pose_source.h
- `1-11` — R (light) — drop "sprint 003 ticket 010's own AC"; keep the test-double contract.

### tests/host/wire_mock_adapter.h
- `1-18` — R — header — drop "(sprint 003 ticket 003, widened ticket 004)" and the "Ticket 004 widens this file…" paragraph; **stale**: "the production adapter, which gives WHEELS_V real effect and answers the other five kUnknown". 4 lines: recording double for Wire::Adapter; canned results are public fields; never linked into production; NOT diffDrive::WireAdapter.
- `46-51` — R — motion-verb canned-result comment — **stale** "the 'five verbs answer kUnknown' shape". 2 lines: one canned Result per verb; this mock drives no kernel — wire_motion_verb_shim.cpp's WaHandle does that.
- KEEP ×9: borrowed-pointer notes, per-verb last-args rationale (114-115), field-table/override comments.

### tests/host/kernel_shim.cpp — KEEP ×8.

### tests/host/motion_engine_shim.cpp
- `1-17` — R (light) — drop "sprint 003 tickets 006/007's own host tests"; keep the handle-shape + extend-don't-fork instruction.
- `35-38` — R (light) — drop "Sprint 003 ticket 010:"; keep pose-passed-per-call ordering note.
- `79-87`, `147-148`, `163` — R (light) — drop ticket tags in the three banners; keep the measured/velocity-vs-duty distinction (79-87's substance stays).
- KEEP ×9: incl. meMotorArmPosition's sample-time-must-advance contract (206-216).

### tests/host/wire_grammar_shim.cpp
- `1-13` — R (light) — drop "(ticket 002, widened by ticket 003)"; keep the one-shim-several-files pattern + RecordingSink/borrowed-pointer notes.
- KEEP ×10 (declaration-order-ordinal warnings are especially good).

### tests/host/wire_motion_verb_shim.cpp
- `1-65` — R — header — DELETE the "Sprint 003 ticket 012 extends the WaHandle surface three ways" changelog (8-27); keep: the two-handles/two-jobs table (29-42), the WaHandle-supplies-shims.cpp-definitions + single-process-wide-handle safety constraint (44-57), and the countsPerLength=1.0 convention (59-65). ~20 lines total.
- `8-27` — D — (the changelog, itemized above).
- `110-118`, `127-141`, `162-166`, `183-184`, `555-560`, `579-580` — R (light) — strip "sprint 003 ticket 011/012" tags; substance stays.
- KEEP ×12: RecordingSink duplication rationale, g_activeWaHandle contract, mirrors-production field-for-field notes, waCreate borrowed-pointer comment, waSetNowMs.

### Python test files (pattern items — substance is uniformly KEEP)
- test_kernel_harness.py `1-25` — R — module docstring: drop "This repo's first test suite" framing and **stale** "those land in later sprint 003 tickets" (they landed). Keep the pipeline description + session-scoped-compile rationale.
- test_motion_engine_primitives.py `1-43` — R — drop "sprint 003 ticket 006:" prefix; `233-239` — R (light) — drop "(Acceptance Criterion 1)".
- test_motion_engine_reductions.py `1-31` — R — drop ticket prefix/refs; `97-100` — R (light) — drop "Ticket 009:" tag.
- test_motion_engine_gotow.py `1-36` — R — drop ticket prefix and "Per the ticket:" (keep the nonzero-heading+position rationale); `387` — R (light) — drop "(ticket 007)".
- test_regression_post_move_neutral.py `83-84` — R — "See this ticket's own report for the recommendation to ticket 013." → delete sentence (the gap itself, lines 65-83, stays — it is the best "read before simplifying" warning in the repo). Commit anchor 3e919e5 stays: it names the regression under test.
- test_regression_yaw_taper_pure_turn.py `1-4` — R — drop "sprint 003 ticket 008:" prefix (bd9f005 anchor stays).
- test_wire_grammar.py `1-29` — R — drop ticket scoping ("ticket 002's own scope", "(sprint 003 ticket 003)"); `92-97` — R (light) — drop "widened (ticket 003) past ticket 002's original…"; `720-729`/`739-746`/`783-791`/`874-877` — R (light) — strip ticket tags from four banners/docstrings (behavioral content stays).
- test_wire_motion_verbs.py `1-43` — R — drop "sprint 003 tickets 004/011/012" and stale spec aside "(S5 … WHEELS_V real, five kUnknown)" describing the reference adapter where it reads as this project; banners at `183`, `412`, `579`, `636`, `746`, `901`, `1058`, `1091`, `1251`, `1357`, `1476` — R (one sweep) — strip "sprint 003 ticket NNN('s own)" tags; substance stays.
- test_wire_reliability.py `1-28` — R — drop "(sprint 003 ticket 003)"; keep the S8.9/2026-08-22 pointer (it dates the spec change, not the sprint).

### tools/
- otos_levercal.py `1-29` — R — docstring says "drives test.ts RUN:8" (and --verify → RUN:14) — **stale: test.ts has no numeric RUN vocabulary; the trigger is RUN:cal / RUN:cal:1** (and the code at 87 still sends RUN:8/RUN:14 → see handoff, fix tool + docstring together). Everything else in the file: KEEP (the linear-fit derivation and p0-exclusion measurement are keepers).
- rotation_check.py `1-21` — R — "firmware rotationScrub 1.040, from a pivot measured at 369.2 deg…" — **stale**: firmware now carries rotationalSlip 0.952 with the opposite sign of effect (motion_engine.h). Rewrite the "why it exists" paragraph to reference the resolved value or delete it; the tool's numeric RUN verbs are a handoff item.
- tour_square.py `1-15` — R — "The permanent fix caps that curvature (built, needs a flash)" — **stale**: main.ts goToWorld() has the curvature cap and 12-deg pivot-first in the current tree. `134-142` — R — self-contradictory block: first half advocates splitting long legs, second half reports splitting was tried and made it WORSE. Keep only the conclusion: `// Splitting long legs was tried and made things worse (SE 10.7 -> 24.0 cm); one hop per corner.`
- All other tools/ comments: KEEP — camlink's unit-traps block, robotlink's send-repeat measurement, make_deploy's two build traps, tour_run's camera-lag scoring note, tour_square's camera-respawn note, turn_sweep's sign-alternation note, truth_check's unwrap rationale are exactly the hard-won bench knowledge dimension 6 protects.

---

## 3. Handoff notes (stale comment ⇒ possible bug — one line each, not developed here)

1. **protocol.cpp:63** `kVersion = "1.0.0" // keep in sync with pxt.json` — pxt.json is at **1.0.10**: the sync the comment demands is already broken; ID/VER replies report the wrong version.
2. **tools speak a retired wire vocabulary**: otos_levercal (RUN:8/14), pivot_truth + rotation_check + truth_check (RUN:2/4/5/10, TLM:), turn_sweep (RUN:57xxx/58xxx, waits for TRN: which nothing emits), tour_capture/tour_watch/tour_run/practice_chart (TLM:/DIAG parsing) — current firmware emits no TLM/DIAG/TRN and test.ts answers only named RUN verbs, so these tools will run and silently record nothing (protocol.h:47-61 half-documents this for TLM only).
3. **main.ts:546** `maxNudges` is dead — declared for the pre-one-pass goToWorld, never read; delete variable + comment together.
4. **serial_transport.h:36-47** documents a `readLine()` that no longer exists (comment sits on `begin()`); confirm no external caller still expects a blocking read before deleting the paragraph.
5. **diffdrive.h** has four comments truncated mid-sentence (81, 84, 90, 125) — suggests a lossy vendoring step from upstream; diff the header against radio-robot-elite's copy before completing them, in case code was clipped too.
6. **shims.cpp:674-678** diagValue's "floats are scaled x100" is wrong for positions/velocities (raw counts) — check no DIAG/probe consumer divides by 100 where it shouldn't.
7. **shims.cpp:77-79** the orphaned "first one or two pivots over-rotate grossly (262/233 deg)" fragment cites clasi/issues — verify that defect is actually filed and still open before the sentence is deleted.
8. **wire_adapter.cpp:195-211** the DIAG-has-no-v6-equivalent narrowing is flagged only in a comment ("for whoever picks this up next") — convert to a CLASI issue so it survives the comment cleanup.
9. **otos_port.h:17-19** "lever-arm transform NOT ported (yet)" vs. implemented setOffset/sensorToCentre — stale, no bug found (test.ts applyArm() sets the arm), but confirm robot-integration docs don't repeat the claim.

---

## 4. Recurring anti-patterns (for future-agent coding guidelines)

1. **Sprint/ticket archaeology as file headers.** Headers narrate which ticket added what, in order ("Sprint 003 ticket 004… Ticket 011… Ticket 012 (this file, now)…"). wire_adapter.h spends 108 lines on it. Git history already stores this; the header should state the *current* contract only.
2. **Justification-to-reviewer essays around decisions.** Multi-paragraph "DECISION (this ticket's own acceptance criteria require one)…" blocks defending a choice against an imagined reviewer (wire_adapter.h lastDone(), shims.cpp:501-519 settle-loop essay). The keeper is the decision + one-line reason; the defense goes in the ticket/PR, not the source.
3. **Stale cross-layer claims after a refactor.** Comments assert what *another* file does and rot when it changes: "the other five answer kUnknown" (wire_handler.h, wire_adapter.cpp, wire_mock_adapter.h — all now false), "for the Protocol v5 wire link / COBS keyed on 0x0A" (serial/radio transports), "readLine()" references to a deleted method, README's "none of which exist yet". Rule: describe the contract at *this* seam; point elsewhere by name, never by restating its behavior.
4. **Diff restatement / caller-history comments.** "Fields formerly here moved to MotionEngine (ticket 006)", "now thin forwards into wheelsV() — the math is unchanged", "Second/Third/Fourth caller (ticket N)…" (shims.cpp). These describe the edit, not the code; the four-line function bodies below them already say everything.
5. **Orphaned/misplaced comments surviving code motion.** A comment stays behind (or lands on the wrong declaration) when its code moves: shims.cpp's dangling "Excludes the first one or two pivots…", probe()'s doc sitting 48 lines above probe() fused to setTaperWindows's, main.ts's `_startProtocol()` doc parked over the run-state variables, the "23/24" comment above `case 25`. Rule: a comment moves (or dies) with its code, and sits immediately above what it describes.

Counterexamples worth imitating (what KEEP looks like here): nezha_port.cpp's measured wedge/glitch armor comments, diffdrive.cpp's kMaxCycleGapUs block, wire_adapter.cpp's mradToRad, main.ts's no-initialiser trap, shims.cpp's vevov-wiring forensics and starvation-watchdog section, robotlink's send-repeat warning.
