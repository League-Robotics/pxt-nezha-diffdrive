# Adversarial verification — correctness-wire.md findings

**Date:** 2026-08-23
**Verifier scope:** WIRE-01..WIRE-07 (all Major), plus spot-checks of two
Minors (WIRE-08, WIRE-09). Every verdict below was re-derived from source,
starting from the assumption the finding was wrong (hunting for missed
guards, callers that never pass the bad value, upstream clamps, contrary
tests, dead code). Severities checked against
`docs/code-review/guidelines.md` §Severity rubric.

| ID | Verdict | Justification (decisive evidence) |
|----|---------|-----------------------------------|
| WIRE-01 | **CONFIRMED** | `protocol.cpp:63` `kVersion = "1.0.0"` vs `pxt.json:3` `"1.0.10"`; the constant is the only source (`protocol.cpp:173` → `wire_handler.cpp:605,619`). No guard, no generator, no test pins it. Major stands. |
| WIRE-02 | **CONFIRMED** | `parseUint32` (`wire_handler.cpp:112-124`) admits 4294967295; no ceiling anywhere on X/GO_TO `timeout`; `wire_adapter.cpp:296` `now + timeout` wraps; `:419` signed check is ≥ 0 from the first poll for timeout > 2³¹ (re-derived: t = 2³¹ exactly gives INT32_MIN < 0, still live — the strict inequality in the finding is precisely right). `protocol.cpp:291` then never ticks; watchdog (`shims.cpp:624-637`) port-stops. Test-gap claim also verified: parametrize at `test_wire_motion_verbs.py:1490-1496` maxes at 5000 ms. |
| WIRE-03 | **CONFIRMED** (one wording caveat) | `setRxBufferSize(128)` (`serial_transport.cpp:24`) vs `kMaxLineBytes = 240` (`serial_transport.h:32`); during a live obligation the loop's only delay is `tickDrive()`, which sleeps to the kernel's 24 ms absolute deadline (`shims.cpp:526-542`) — drain cadence ~24 ms, and 24 ms × 11.52 B/ms ≈ 276 B > 128. Caveat: "guaranteed" is phase-dependent — what is guaranteed is loss for any >128-byte burst landing wholly inside one inter-drain gap; a drain landing mid-burst can save shorter lines. Failure scenario stands; Major stands. |
| WIRE-04 | **CONFIRMED** (serial half; radio half is planned work) | In-repo mechanism fully verified: `emitLine` is real TS-fiber traffic (`test/test.ts:53-156`, OCAL/TOUR results from RUN handlers), keepalives every 50 ms on the protocol fiber (`protocol.cpp:277-281`), both funnel into `SerialTransport::writeLine`'s two `send(..., SYNC_SLEEP)` calls with returns ignored (`serial_transport.cpp:28-35`). CODAL refuse-on-busy (`DEVICE_SERIAL_IN_USE`) is consistent with codal-core upstream but CODAL is not vendored — bench confirmation advisable; either refuse or interleave is a failure, as the finding says. **Dedup note the reviewer missed:** the radio-side remark duplicates open sprint 004 ticket 002 (`RadioTransport re-entrancy guard`) — cross-reference, don't re-report. But that ticket's own AC asserts "serial has no analogous second-caller hazard" (it only considered buffer corruption, not TX contention) — this finding directly rebuts that, so the serial half is *not* covered by planned work and matters at triage. |
| WIRE-05 | **CONFIRMED** (one precision fix) | Bare `200` at `protocol.cpp:92`; stale parity claim at `radio_transport.h:118-126` ("Sized the same as SerialTransport's bound" — that bound is 240 since ticket 005, `serial_transport.h:32`); silent clip + delimiter verified (`protocol.cpp:94`). Precision fix: the radio's own 200-clip (`radio_transport.cpp:134`) is currently *unreachable* — `emitLine` is `sendLine`'s only caller and pre-clips to 200, which fits `payloadBuf_[201]` exactly. The truncation that bites is emitLine's; the radio constant is drift, not a second live clip. Major stands on the silent-truncation scenario. |
| WIRE-06 | **CONFIRMED** | `out.otos = false;` unconditional (`wire_adapter.cpp:226`); `diagValue()`'s full ordinal table (`shims.cpp:679-715`, ordinals 0-25) has no OTOS-presence field to read; `engineGoToW` (`shims.cpp:889-895`) checks `otos.connected()` and drives — so the same session yields `status … otos=0` and a driving `GO_TO_W`. No other writer of the field exists. Major stands. |
| WIRE-07 | **CONFIRMED** (severity is judgment, rubric-consistent) | Inert overrides verified (`wire_adapter.h:318-321`), consumed fresh in every ack/nack (`wire_handler.cpp:476-489`) and keepalive (`:986-990`). Dedup checked: no `lastDone`/`DoneReason`/completion work anywhere in the sprint 004/005 plans (grepped both trees) — not planned work, so it stands as a finding. One softening fact: sprint 004's planned POSE frame includes `vl vr` (`sprint 004 sprint.md:103-104`), giving sprint-005 tooling a completion-inference channel at frame rate — but it flickers through zero exactly like STATUS `active`, so "no reliable completion *event*" holds. Major-as-landmine is defensible under "landmine likely to bite in normal development" (sprint 005 is the next sprint). |
| WIRE-08 | **CONFIRMED** (spot check) | `parseInt32` admits all of int32; `float(2147483647)` = 2147483648.0f (float spacing 128 at 2³¹, so wire values in [2147483584, 2147483647] all land there); `static_cast<int>` of it at `wire_adapter.cpp:257` is UB — saturates on Cortex-M VCVT, INT32_MIN via cvttss2si on the x86 host harness, which compiles the real `wire_adapter.cpp` (`tests/host/wire_motion_verb_shim.cpp`) — the host/hardware sign disagreement is real. `lround(value * 1000.0f)` (`:433-434`): `SET pid_kp 3000000` → 3e9 overflows 32-bit `long` on target (unspecified result). No clamp exists between grammar and adapter. Minor is right (inputs absurd-but-legal). |
| WIRE-09 | **CONFIRMED** (spot check, one scope correction) | `wire_handler.h:431` and `wire_handler.cpp:214` both spell `[18]`; deleting one initializer compiles, zero-fills the last entry (`name == nullptr`), and `strcmp(verb, e.name)` at `:427-432` is UB. Scope correction: not "every command" — a verb matching an entry *before* the hole breaks out early and is fine; what hard-faults is any **unrecognized-verb** line (which must nack instead) and **HELP** (`append(entry.name)` at `:657-660` walks all 18). The silent-on-removal / loud-on-addition asymmetry is exactly as stated. Minor is right — the trap needs a future edit mistake to arm. |

## Longer notes

### WIRE-02 — extra derivation detail

The boundary: with deadline = now + t, the first-poll check computes
`(int32_t)(now − deadline) = (int32_t)(−t mod 2³²)`.

- t = 2³¹: −t mod 2³² = 2³¹ → INT32_MIN → **< 0 → still live** (works).
- t = 2³¹ + 1: → 2³¹ − 1 = INT32_MAX → **≥ 0 → dead on arrival**.
- t = 4294967295: → 1 → dead on arrival.

So the finding's "strictly greater than 2³¹" threshold is exact.
The V-forms genuinely cannot reach this (`kWheelsVDurationCeiling = 5000`
checked at `wire_adapter.cpp:253` and `:326`); the four X/GO_TO arming
sites (`:294-297`, `:314-317`, `:352-355`, `:379-382`) all take the raw
uint32. The proposed test additions (`window_ms = 2**31 + 1`, `2**32 − 1`
in the `:1490` parametrize) would fail today at the
`assert wa.has_live_motion_obligation()` immediately after `feed`.

### WIRE-04 — what is and isn't verifiable in-tree

Verified in this repo: two fibers reach `uBit.serial.send()` concurrently
(TS-fiber `emitLine`, protocol-fiber replies/keepalives); both `send()`
return values are discarded; `writeLine` is two sends, so even without a
drop, another fiber's line can be injected *between* content and
delimiter (SYNC_SLEEP releases the TX path between the two calls) —
merged lines need no CODAL-specific refusal behavior at all, only the
in-repo structure. The specific `DEVICE_SERIAL_IN_USE` refuse-on-busy
claim matches codal-core's `Serial::send` as published upstream, but
CODAL sources are not vendored here (build is cloud-side; searched the
repo and local caches — no `Serial.cpp`), so that half stays
bench-confirmable rather than tree-provable. Both behaviors are failures,
so the verdict does not hinge on which one this CODAL exhibits.

Triage pointer: sprint 004 ticket 002 fixes the *radio* scratch-buffer
re-entrancy and its AC explicitly walks past the serial path on the
grounds that serial has no member buffers. That reasoning addresses
corruption, not contention/drop — when this finding is converted to an
issue, it should be linked to that ticket so the serial guard decision is
made deliberately rather than by omission.

### WIRE-05 — reachability precision

Call-graph fact the finding overstates slightly: `RadioTransport::
sendLine` has exactly one caller (`Protocol::emitLine`, `protocol.cpp:95`
— v6 replies go only to `SerialSink`/serial), and `emitLine` clips to 200
first, so radio's own clip at `radio_transport.cpp:134` can never fire
today. The live defect is `emitLine`'s bare-200 clip on the serial path
(which could legally carry 240); the radio constant + stale parity
comment are the drift half. Remedy as proposed (one shared cap, loud
over-length handling) is unaffected.

### Severity spot-audit summary

All seven Major severities are rubric-consistent ("user-visible
misbehavior, a landmine likely to bite in normal development, or a
correctness bug with a demonstrated failure scenario"): WIRE-01/02/03/05
have demonstrated failure scenarios; WIRE-04's is demonstrated up to the
un-vendored CODAL detail; WIRE-06 is confidently-wrong wire data aimed at
the next sprint's tooling; WIRE-07 is a documented decision whose Major
rating is expressly a sprint-005 planning judgment — reasonable, not
inflated to Critical, and correctly not claiming a code defect. Neither
spot-checked Minor warrants an upgrade: WIRE-08 needs absurd (if legal)
inputs; WIRE-09 needs a future editing mistake to arm.
