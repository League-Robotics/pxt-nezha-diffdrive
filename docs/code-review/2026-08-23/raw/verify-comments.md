# Comment-audit spot-check — 2026-08-23

Adversarial verification of `raw/comment-audit.md` against the actual source and
the upstream repo. Sample: all 11 DELETE items + 16 REWRITE items chosen for
risk (diffdrive.*, nezha_port.*, and the largest compressions). Every verdict
below was checked against the code, not the audit's own quotations.

Verdict key: **AGREE** = the audit's verdict and replacement lose nothing
load-bearing. **CHALLENGE** = the replacement as specified destroys or
misstates load-bearing content; corrected text given in the notes.

## 1. DELETE items (11/11 sampled)

| # | Item | Verdict | Reason |
|---|------|---------|--------|
| D1 | otos_port.h 27-33 (PoseSource ticket note) | AGREE | `: public PoseSource` + the override docs at 61-66 say everything; layering fact restated in motion_engine.h (kept). |
| D2 | serial_transport.h 36-47 (begin()'s readLine paragraph) | AGREE | `readLine()` confirmed absent from the class and the whole tree (only stale comment refs at .h:58/60/67/77, .cpp:60); its truncation contract is restated in tryReadLine's kept doc; the real begin() doc (48-50) stays. |
| D3 | wire_adapter.cpp 313 (onMoveX ticket cross-ref) | AGREE | Pure "see identical comment above" + ticket tag; the referenced comment survives as R. |
| D4 | wire_adapter.cpp 331-332 (onMoveV ditto) | AGREE | The "duration IS the lease" half survives in kWheelsVDurationCeiling's kept doc and the header replacement's V-form/X-form split. |
| D5 | wire_adapter.cpp 351 (onGoToR ditto) | AGREE | Same as D3. |
| D6 | wire_adapter.cpp 377-378 (onGoToW ditto) | AGREE | Audit itself retains the one load-bearing clause ("only armed on the path that dispatched"); code structure (arming after the kUnimplemented early-return) also shows it. |
| D7 | main.ts 546 (`maxNudges` + comment) | AGREE | Declared, never read (grepped whole file); goToWorld is confirmed one-pass. See note N6 for an adjacent stale JSDoc the audit KEEP'd. |
| D8 | shims.cpp 77-85 (orphaned first-pivots fragment) | AGREE | Handoff-7 condition now VERIFIED: the 262/233-deg defect is filed, root-caused, and closed in `clasi/issues/done/first-move-after-idle-runs-at-full-duty.md` (names 262, 233, 277 explicitly); the kernel-level cure is the kept kMaxCycleGapUs block (diffdrive.cpp 424-440). Init-order invariant restated at 119-124 (kept). |
| D9 | shims.cpp 130-137 (moved-state diff narration) | AGREE | motion_engine.h's kept field comments carry every measurement; the thin forwards below are self-evident. |
| D10 | shims.cpp 237-244 (thin-forwards narration) | AGREE | The cdeg/s→rad→twist conversion is visible in the 4-line bodies; unit tags on the signatures are kept. |
| D11 | wire_motion_verb_shim.cpp 8-27 (ticket-012 changelog) | AGREE | Every fact in it (waNowMs/waSetNowMs, FakePoseSource + availability flag, engine* doubles) is restated at the definitions, which the audit keeps. |

## 2. REWRITE items (16 sampled)

| # | Item | Verdict | Reason |
|---|------|---------|--------|
| R1 | diffdrive.h 1-26 (header) | CHALLENGE | Replacement writes "Vendored from radio-robot-elite (src/firm/control)" — no `League-Robotics/radio-robot-elite` repo resolves on GitHub, and in the real upstream (`League-Robotics/radio-robot`) the kernel has MOVED to `src/firm/diffdrive/` (`src/firm/control/differential_drive.h` is now a thin forwarding-adapter header). Writing an unresolvable repo name and a stale path into the vendoring invariant misdirects the next vendorer. Content of the rewrite is otherwise fine. |
| R2 | diffdrive.h 81-82 (kRefusedNotBegun truncation) | AGREE | Upstream full text confirms the audit's completion is semantically faithful (see §3); code confirms it (checkCommandable gates on `begun_`, never `running_`). |
| R3 | diffdrive.h 84 (kCadencePreserved truncation) | AGREE | Upstream: "block applied, frozen cadence kept"; code confirms (setConfig applies the block, freezes cyclePeriod, returns kCadencePreserved). Audit's "cadence kept, rest applied" matches. |
| R4 | diffdrive.h 90-91 (maxDuty truncation) | CHALLENGE | Upstream continuation is "(lambda scales to **this**); **0 = ALL modes refused**". The audit's completion drops the 0-sentinel meaning — the declaration-site statement that an unset maxDuty refuses every command (code: checkCommandable's `maxDuty <= 0 → kRefusedUnconfigured`). Corrected: `// [%] authority rail (lambda scales to this); 0 = ALL modes refused`. |
| R5 | diffdrive.h 125 (cycleOverrunCount truncation) | AGREE | Upstream: "cycles that missed their absolute deadline — the observability half of lesson 17"; audit's completion keeps the fact, drops upstream-repo lore ("lesson 17") — correct call; also matches the private member's own kept comment (line 314). |
| R6 | diffdrive.cpp 1-6 (vendoring header) | CHALLENGE | Same naming problem as R1: replacement says "radio-robot-elite src/firm/control/…". Use the resolvable name and current path: `radio-robot src/firm/diffdrive/differential_drive.cpp`. The both-trees invariant itself is preserved correctly. |
| R7 | nezha_port.h 1-28 (header, light) | CHALLENGE | "Compress lines 3-7 to one provenance line" clips mid-sentence: the sentence "The write-shaping pipeline is NOT optional styling: each stage guards against a measured hardware failure" spans lines 7-8 and is the framing that protects the five stages from future "simplification". Corrected preamble: `// Ported from radio-robot nezha_motor.cpp + motor_armor.h's wedge detector. The write-shaping pipeline is not optional styling -- each stage guards a measured hardware failure:` (note: this file itself says "radio-robot", not "-elite"). Failure-mode list verbatim, as the audit says. |
| R8 | motion_engine.h 1-113 (113→20 header) | CHALLENGE | The exclusive keep-list omits two invariants that live ONLY here and that surviving method docs point at with "see header comment": (a) **odometry stays OUT of this class — callers must update it themselves around serviceMove()** (lines 89-92; an undocumented-calling-order contract; serviceMove's kept doc at 245-250 defers to the header for it), and (b) **goToR/goToW are single-shot reductions and `arrive` is accepted but unused** (lines 63-66; a silent-parameter-ignore; goToR's kept doc at 229 also defers to the header). Add both to the ~20 lines (or fold them into the method docs and fix the dangling "see header comment" pointers). Rest of the compression is sound. |
| R9 | motion_engine.h 335-346 (rotationalSlip_) | CHALLENGE | The replacement states "six 180-deg pivots turned 164-166 deg physical -> slip 0.952" — but 164-166/180 ≈ **0.915**, and the dropped middle of the comment is the only bridge from the measurement to the constant ("ratio 0.915. effectiveTrackWidth must therefore be 120.0 mm, so slip = 114.2/120.0 = 0.952"). As rewritten, a future re-measurer reproduces 0.915 from the same experiment and "fixes" the constant — precisely the failure this comment exists to prevent. Keep the full derivation chain: measured ratio 0.915 → effective track must be 120.0 mm → slip = 114.2/120.0 = 0.952, plus the sign-of-effect caution (that part of the replacement is fine). |
| R10 | wire_adapter.h 1-108 (108→12 header) | AGREE | All stated invariants preserved (signature-compat, no engine reference, host-portable, borrowed Identity, NowMsFn nullptr semantics, every-accepted-verb-arms-obligation with V-form/X-form deadline split). The dropped "unserviced move dies to the watchdog in ~100-150 ms" failure narrative survives verbatim in shims.cpp's kept "Move-completion stop delivery" comment. |
| R11 | wire_adapter.h 295-317 (lastDone essay, 23→3) | AGREE | Decision + reason (bridge functions void/availability-only; deliberately no MotionEngine reference) + revisit trigger all preserved; the defense-to-reviewer is exactly what dimension 6 deletes. |
| R12 | serial_transport.h 20-32 (kMaxLineBytes essay) | AGREE | The equality invariant (== WireHandler's 240) and the truncate-into-parseable-prefix hazard that motivates it are both preserved; ticket history correctly dropped. |
| R13 | radio_transport.h 106-115 (kGroup/kChannel) | AGREE | All fleet facts preserved (channel 4 = vevov's assignment, zavaz `!CG 4 10`, group 10, power 7); only the date/stakeholder attribution and Open-Question ref are dropped. |
| R14 | radio_transport.h 118-125 (kMaxPayloadBytes) | CHALLENGE | Replacement: "equals SerialTransport's only because both carry the same lines" — **it does not equal it**: kMaxPayloadBytes = 200, SerialTransport::kMaxLineBytes = 240 (raised 200→240 in ticket 005; radio's bound was never raised). Both the original comment and the audit's replacement restate a now-false equality. Corrected: `// [bytes] local truncation bound for sendLine(). NOTE: 200, tighter than SerialTransport's 240 -- a 201-240-byte emitted line is mirrored intact on serial but truncated on radio.` And file the discrepancy as an issue (see N5). |
| R15 | protocol.cpp 30-63 (identity constants) | CHALLENGE | The 5-line replacement covers name/serial/kVersion but drops kDrivetrain/kProfile — and `kProfile = "tovez"` is opaque without its one fact: "tovez" names the tuning bake the Rig defaults were measured from (not expressible by the constant). Add one line: `// kDrivetrain = kinematic type (package name); kProfile = the tuning bake the Rig defaults were measured from.` |
| R16 | shims.cpp 501-519 (settle-loop essay, 19→3) | AGREE | The 3-line KNOWN GAP preserves every load-bearing element: hardware-only, welded to Rig-local odomUpdate, extraction = real architectural change, the mirror-test's limits. |

Verified in passing (no loss found, all AGREE): wire_adapter.cpp 1-4 ("five
verbs answer kUnknown" confirmed stale — all six dispatch, onRun is the only
kUnknown), 195-211 (status narrowing → issue), 228-231 ("WHEELS_V-only"
confirmed stale), 74-82 kFields, the A-item at 422-436 (the ×1000/×0.001
fixed-point crossing is genuinely uncommented there and the proposed text is
correct); shims.cpp 264-279, 299-317, 674-678 (all three stale claims
confirmed: DIAG retired, `probe()` at shims.cpp:946 and wire_adapter.cpp both
call diagValue, only duty is ×100), 700-712 (the "23/24" comment does sit
above `case 25`), 788-809, 850-863, 875-888, 898-912 (fused triple comment
confirmed; probe() is 48 lines below its doc); serial_transport.h 1-12 and
serial_transport.cpp 18-23/59-61 (v5/COBS refs stale as claimed); main.ts
52-72 (jumbled triple confirmed: `_startProtocol()` is at line 86).

## 3. Truncation check — diffdrive.h

All four audited comments are **truly truncated mid-sentence**, not terse: each
ends dangling ("…start(): the", "…cyclePeriod:", "…(lambda scales to",
"…their absolute"). Pattern: the wrapped continuation lines of trailing
comments were dropped while the first physical line survived.

**Upstream found.** `https://github.com/League-Robotics/radio-robot` is
reachable; the kernel lives at `src/firm/diffdrive/differential_drive.h`
(the old `src/firm/control/differential_drive.h` is now a forwarding-adapter
header — the paths in this repo's vendoring comments are stale). Full upstream
sentences, verbatim:

| Line | Upstream complete comment |
|---|---|
| 81 | `// command before begin(). NOT before start(): the host harness commands and step()s WITHOUT ever launching the fiber, so readiness is begin()'s to grant, not start()'s` |
| 84 | `// post-begin setConfig with a differing cyclePeriod: block applied, frozen cadence kept` |
| 90 | `// [%] authority rail (lambda scales to this); 0 = ALL modes refused` |
| 125 | `// cycles that missed their absolute deadline — the observability half of lesson 17` |

The audit's proposed completions for 81, 84, and 125 are faithful to upstream
and to the local code. The completion for 90 loses the `0 = ALL modes refused`
sentinel (R4 above).

**Fifth truncation the audit missed** — diffdrive.h:91:
`fullDutyVelocity … // [counts/s] wheel rate at 100% duty;` ends at the
semicolon; upstream continues: `0 = uncalibrated → VELOCITY refused`
(matches code: checkCommandable refuses velocity mode when
`fullDutyVelocity <= 0`). Restore it with the other four.

No evidence of clipped **code** in the sections read (the clip pattern hits
only comment continuation lines), but handoff-5's recommendation stands: diff
the whole vendored pair against upstream `src/firm/diffdrive/` before editing.

## 4. Notes

- **N1 (counts):** 27 items sampled: 11 DELETE — all AGREE; 16 REWRITE — 8
  AGREE, 8 CHALLENGE. No DELETE destroys load-bearing content; the risk is
  concentrated in replacement texts that summarize measurements or name the
  upstream.
- **N2 (highest-stakes challenge):** R9 (rotationalSlip_). The rewrite's own
  numbers are internally inconsistent (164-166/180 ≠ 0.952); shipping it would
  set up the exact recalibration bug the original comment prevents.
- **N3 (repo naming):** "radio-robot-elite" appears in the audit's replacement
  texts (R1, R6) and already in otos_port.h; no such GitHub repo exists under
  League-Robotics — the public upstream is `radio-robot`, and nezha_port.h's
  own comment says "radio-robot". If "-elite" is a private/local checkout
  name, verify before baking it into vendoring comments; otherwise use
  `radio-robot (src/firm/diffdrive/)`.
- **N4 (handoff-7 resolved):** the orphaned 262/233-deg fragment's defect is
  filed and closed (`clasi/issues/done/first-move-after-idle-runs-at-full-duty.md`);
  D8 may proceed unconditionally.
- **N5 (new handoff — radio truncation gap):** kMaxPayloadBytes (200) vs
  serial/WireHandler line size (240): emitLine() mirrors to both transports,
  so a legal 201-240-byte v6 line is silently truncated on the radio path
  only. The ticket-005 raise that fixed serial never reached radio_transport.
  Convert to a CLASI issue alongside the audit's handoff items.
- **N6 (audit KEEP-list miss, adjacent to D7):** main.ts goToWorld's exported
  JSDoc (≈558-562) still says "Repeats until inside the arrival tolerance" —
  contradicted by the ONE-PASS block comment in its own body. The audit's
  "Public-API bar check … accurate and crisp" overlooked it; it should join
  the REWRITE list (same edit that deletes maxNudges).
- **N7 (method-doc pointers):** several motion_engine.h method docs defer with
  "see header comment"; after the R8 compression each such pointer must still
  resolve — the two contracts named in R8 are the ones that currently have no
  other home.
