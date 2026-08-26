# Annex — Correctness: wire, shim, block and tooling detail (2026-08-26)

Consolidated as **C-05, C-10 … C-16** in [`../review.md`](../review.md), plus
the things this review checked and found **sound**, which are worth recording so
the next review does not re-derive them.

---

## What held up

Recorded because a review that only lists defects gives a false picture of the
codebase, and because several of these were 2026-08-23 findings that are now
genuinely closed.

| Area | Status |
|---|---|
| `wire_handler.cpp` field parsing | **Sound.** `parseIdDigits` pre-scans for digits before `strtoul` so `#+5`/`#-5`/`# 5` reject; `parseInt32`/`parseUint32`/`parseFloatField` demand whole-field consumption; `isWireSpace()` deliberately treats `\t\v\f\r` as ordinary field bytes so libc's leading-whitespace skip cannot smuggle a value through; exponent/hex/NaN/inf barred by character scan. |
| Line reassembly | **Sound.** `appendByte`/`onLineComplete` discard an overlong line **whole** rather than truncating to a parseable prefix, with `overflowing_` held to the next `\n`. The embedded-NUL edge (`"\0PING\n"` → 0 tokens → `tokens[0]` uninitialized) is explicitly guarded at `wire_handler.cpp:414` with a comment naming the exact divergence between the two scans. |
| Timeout hardening (R-06, R-18) | **Closed.** `clampMotionTimeout()` rejects `0` and clamps above 2³¹−1, once, at decode, for all six motion verbs. The 2³¹−1 choice is exactly the signed-difference half-range `hasLiveMotionObligation()` relies on. |
| `kVersion` drift (R-17) | **Closed.** `pxt.json` 1.0.10 == `protocol.cpp:42` `kVersion`, pinned by `test_wire_constants_drift.py::test_k_version_matches_pxt_json_version`. |
| Line-capacity drift (R-21) | **Closed.** All four 240-byte constants pinned equal by a drift test. |
| STATUS `otos` (R-22) | **Closed.** Reads `otosGet(7)` — the same boolean `engineGoToW()` gates on. `cyc=` added (sprint 010) so never-ticked and brick-unreachable are distinguishable. |
| Motion completion (R-23) | **Closed.** `lastDone`/`lastDoneReason` resolve for real, with a defensible priority order and careful before/after-dispatch ordering per verb kind. |
| `runArgCount()` null guard (R-15) | **Closed.** `run.ts:122` guards `runParts`. |
| `Protocol::runText()` bounds | **Sound.** Returns `""`, never `nullptr`, for an out-of-range slot — so `shims.cpp`'s unguarded `while (text[len] != '\0')` in `runCommandText()` cannot fault. |
| `OtosPort` mounting-rotation inverse | **Sound.** `read()` applies R(−offsetYaw); `setPose()` applies R(+offsetYaw). Re-derived from the matrices; they are exact inverses. |
| `EncoderGlitchArmor` rebaseline arithmetic | **Sound.** `encOffset_ = raw − int32(lastPosition_) * fwdSign_` then `pos = (raw − encOffset_) * fwdSign_` collapses to `lastPosition_` for `fwdSign_ ∈ {±1}` — continuity by construction, velocity reads ~0. |
| `tools/` consolidation (R-24, R-26) | **Closed.** One venv resolution (`camproc.resolve_venv()`), one `Cam` used by all seven tour tools, one `wrap()`, one `score_corners()`, one `path_deviation()` with the degenerate-segment guard. |
| Test suite | **597 passed.** Green throughout. |

---

## C-05 — MAJOR: the motion obligation is never cleared on completion

Writers of `motionObligationActive_`:

| Site | Sets |
|---|---|
| `wire_adapter.cpp:345` `onWheelsV` | true |
| `wire_adapter.cpp:376` `onWheelsX` | true |
| `wire_adapter.cpp:405` `onMoveX` | true |
| `wire_adapter.cpp:428` `onMoveV` | true |
| `wire_adapter.cpp:449` `onGoToR` | true |
| `wire_adapter.cpp:487` `onGoToW` | true |
| `wire_adapter.cpp:536` `onEstop` | **false** |
| `wire_adapter.cpp:568` `onStop` | **false** |

Natural completion is absent. `resolvePendingIfDue()` clears `pendingActive_`
and leaves the obligation armed:

```cpp
void WireAdapter::resolvePendingIfDue() const {
  if (!pendingActive_) return;
  const Wire::DoneReason reason = resolvePendingReason();
  if (reason == Wire::DoneReason::kNone) return;
  lastDoneId_ = pendingId_;
  lastDoneReason_ = reason;
  pendingActive_ = false;          // <-- obligation untouched
}
```

`protocol.cpp:355` reads the obligation as its tick gate:

```cpp
if (wireAdapter_.hasLiveMotionObligation()) {
  tickDrive();
} else {
  fiber_sleep(kPollIntervalMs);
}
```

So after **any** wire motion verb the protocol fiber ticks the kernel at 24 ms
for the whole declared `timeout`, regardless of when the move actually finished.
`timeout` is a mandatory backstop the API tells hosts to set generously; the only
ceiling is `kMaxMotionTimeoutMs` = 2³¹−1 ms = **24.8 days**.

Consequences, increasing in seriousness:

1. Continuous I2C traffic on a bus that looks idle. Candidate mechanism for
   `i2c-fault-count-climbs-on-idle-bus.md` — see
   [`correctness-stop-paths.md`](correctness-stop-paths.md) for the full
   fiber/bus argument.
2. Two fibers on the bus, one of them not covered by `stepBusy`.
3. A stale obligation surviving across unrelated later work in the same session.

An asymmetry worth noting alongside it: `onWheelsV`/`onMoveV` bound `duration`
at `kWheelsVDurationCeiling` (5000 ms — *"a dead host cannot mean a runaway"*),
but `onWheelsX`/`onMoveX`/`onGoToR`/`onGoToW` have **no** ceiling on `timeout`
beyond the shared 2³¹−1 decode clamp. That is defensible for the move itself
(a goal-directed move ends on arrival, not on the clock) — but the obligation
window inherits the same unbounded value, and that is what causes the tail.

**Remedy.** Clear `motionObligationActive_` in `resolvePendingIfDue()` and
`forceResolvePending()` — the two places that already know the motion is over.
The flag then means "a motion is outstanding", which is what `protocol.cpp`
reads it as.

---

## C-10 — MINOR: `execHelp()` silently truncates and can drop its own terminator

```cpp
// wire_handler.cpp:779
char buf[kMaxLineBytes];
size_t pos = 0;
auto append = [&](const char* text) {
  while (*text != '\0' && pos < sizeof(buf) - 1) buf[pos++] = *text++;
};
append("help");
for (const auto& entry : kCommandTable) { append(" "); append(entry.name); }
append("\n");
buf[pos] = '\0';
writeLine(buf);
```

Today's 18 verbs produce ~110 bytes against a 240-byte buffer, so it fits with
room. The landmine: `"\n"` is appended **last**, so the first thing lost to
truncation is the line terminator. A HELP reply without `\n` is a line the
host's reassembler never completes, and it glues the next reply onto it.

`execRun()`, twenty lines below, gets this exactly right — a `kMaxLineBytes + 1`
buffer with a comment explaining that `snprintf`'s NUL would otherwise eat the
`\n`. `execHelp` has neither the guard nor a test.

**Remedy.** Either a `static_assert` on the summed table width, or emit HELP as
multiple lines when it would overflow, or simply append `"\n"` into a reserved
final byte.

---

## C-11 — MINOR: the OTOS product id is re-typed across the shim boundary

```cpp
// platform/otos_port.h:102
static constexpr uint8_t kExpectedProductId = 0x5F;
// platform/otos_port.cpp:77
initialized_ = ok && (id == kExpectedProductId);
```

```ts
// blocks/world.ts:20
export function startWorldTracking(): boolean {
    return otosBegin() == 0x5F        // <-- independently re-typed
}
```

Plus a third statement of it in a `shims.cpp:1081` comment.

If the expected id ever changes — a chip revision, a second supported sensor —
`otos_port.h` is updated, `initialized_` goes true, `connected()` goes true,
`worldTrackingReady()` returns true, `engineGoToW()` selects the OTOS — and
`startWorldTracking()` returns **false**. Every student program gated on it
refuses to run against a perfectly healthy sensor, and the block's own sibling
readback disagrees with it.

**Remedy.** `startWorldTracking()` should be:

```ts
export function startWorldTracking(): boolean {
    otosBegin()
    return worldTrackingReady()
}
```

The caller has no business knowing the product id; `otosBegin()`'s return value
is a diagnostic, not a contract.

---

## C-12 — MINOR: `RUN:` handlers mutate a global shaping profile and never restore it

| Handler | `setTaperWindows` | `setTaperFloors` | `setRampMs` | `setDefaultSpeed` | `setDefaultYawRate` |
|---|---|---|---|---|---|
| `openLoopProfile()` (tours, `straight`) | 400, 180 | 25, 12 | 400 | 20 | 90 |
| `RUN:goto` | 120, 80 | 45, 35 | 180 | **40** | 120 |
| `RUN:face` | — | — | — | — | 90 |
| `RUN:pivot` | 400, 180 | 25, 12 | 400 | — | `pivotYawRate` |

`RUN:face` sets only the yaw rate, so run after `RUN:goto` it closes its heading
loop under the **fast closed-loop** profile (taper 120/80, floors 45/35, ramp
180) instead of the accuracy profile. Same command, different physical
behavior, determined entirely by which command preceded it — and nothing in the
emitted transcript records which profile was in force.

`RUN:pivot` after `RUN:goto` inherits `defaultSpeed = 40` (harmless for a pure
pivot) but correctly re-sets everything that matters, which shows the intended
discipline; `RUN:face` is the one that does not follow it.

On a rig whose three open questions are all about a few degrees of rotation
error, a bench command whose shaping depends on history is a reproducibility
hole. **Remedy**: every handler calls one named profile function on entry —
`openLoopProfile()` or a new `closedLoopProfile()` — with no partial sets.

---

## C-13 — MINOR: `dutl`/`dutr` are percent × 100, and nothing says so

The chain:

| Layer | Value | Unit |
|---|---|---|
| `NezhaMotorPort::appliedDuty()` | `lastWrittenPct_ / 100.0f` | fraction, [−1, 1] — header says so |
| `diffdrive.cpp:795` | `left_.appliedDuty() * 100.0f` | **percent** — `diffdrive.h:136` says `[%]` |
| `shims.cpp:797` `diagValue(12)` | `out.appliedDutyLeft * 100.0f` | **percent × 100** |
| wire `dutl` column, `probe(12)` | as above | **10000 at 100% duty** |

Documentation of that last unit:

- `shims.cpp:766` — "positions/velocities raw counts", "duty x100"
- `blocks/sim.ts:289` — "12/13 applied duty x100"
- `tools/tlm.py:249-259` — the module that calls itself *"The only place any
  wire → engineering-unit scale factor is written"* — documents `x`, `y`, `ox`,
  `oy`, `h`, `oh`, `vl`, `vr` and **omits `dutl`/`dutr` entirely**.

Both source comments read naturally as "percent", which is wrong by 100×. The
one place that would settle it is silent. `tests/tools/test_tlm.py:346` carries
`'dutl': -1300` as fixture data — i.e. −13% duty — with no unit assertion.

**Remedy.** Add the two columns to `tlm.py`'s unit table with the derivation
(`fraction → ×100 in the kernel → ×100 again in diagValue`), and change the two
source comments to say "duty, percent ×100 (10000 == full duty)". Consider
whether the second ×100 earns its place at all — the wire is text, so integer
percent would lose nothing a bench operator needs.

---

## C-14 — MINOR: the simulator's turn rate is 4.3% off hardware's

```ts
// blocks/sim.ts:99
simYawRate = (right - left) / 115  // [rad/s]
```

Hardware: `setWheels()` → `MotionEngine::wheelsV()`, whose commanded body yaw
rate is `(right − left) / effectiveTrackWidth()`, and
`effectiveTrackWidth() = trackWidth / rotationalSlip = 114.2 / 0.952 =
**119.96 mm**`.

The comment says 115 is *"this simulator's fixed stand-in for the
caliper-measured `trackWidth_` (114.2 mm)"* — but hardware does not divide by
`trackWidth`, it divides by `trackWidth / rotationalSlip`. Sprint 007 fixed the
10× error here (R-12) and picked the wrong one of the two geometry numbers.

4.3% is small. The comment being wrong about *which quantity hardware uses* is
the part that will mislead the next reader, especially since
`docs/design/design.md`'s geometry doctrine turns on exactly that distinction.

`_driveTwist()`'s sim body is, by contrast, exactly right — `(yawRate/100) *
π/180` reproduces hardware's round trip through `effectiveTrackWidth()` and back
— so the two sim paths currently disagree with each other by 4.3% as well.

---

## C-16 — MINOR: `score_corners()` lets an early corner steal a late corner's sample

```python
# tools/field.py:72
used = 0
for tag in order:
    dx, dy = dots[tag]
    best, besti = None, used
    for i in range(used, len(rows)):        # <-- to the END of the run
        d = math.hypot(rows[i][1] - dx, rows[i][2] - dy)
        if best is None or d < best:
            best, besti = d, i
    ...
    used = besti
```

`used = besti` correctly stops a **later** corner from reclaiming an **earlier**
one's sample — which is what the docstring claims. Nothing stops the reverse:
the first corner's search covers the entire remaining run, so if the path passes
closer to that dot near the end (a closed lap does return near its start), `used`
jumps to the tail and every subsequent corner scores from a handful of final
samples.

The consequence is a silently plausible score, not an error — which is the same
failure shape the function's own docstring says it exists to prevent (*"a real
run once scored 'SW 31.3 cm' this way while the camera had been blind for 24 s
and the robot had already been and gone"*).

**Remedy.** Bound each corner's search to a window — the tour is a known
sequence of legs, so `rows` can be partitioned by arc length or by the `OCAL:`
corner fixes already in the capture — or at minimum stop each corner's scan at
the first local minimum after `used` rather than taking a global one.

---

## Smaller notes, recorded without a finding number

- **`progress()` reports 1000 when no move is active** (`motion_engine.cpp:381`,
  `shims.cpp:696`). Documented as *"matches `isMoving()? -> false` reading as
  'already there'"* — defensible, but it means `moveProgress()` reads 1.0 before
  any move has ever started, and drops to 0 mid-call when a pivot-then-straight
  move advances to its second phase.
- **`isMoving()`'s doc comment is still false.** `blocks/motion.ts:201` says
  *"Checks state only — it does not itself advance the move."* It calls
  `_updateMove()` → `shims.cpp:441 updateMove()`, which calls
  `engine.serviceMove()` — reissuing `kernel_.drive()`, potentially ending the
  move, potentially firing `deliverStopNow()`. The 2026-08-23 verify pass found
  this same comment false (BLK-12) and correctly cleared `moveProgress()`, whose
  path *is* read-only. Unchanged since.
- **`updateMove()` takes no `stepBusy` guard.** It does not call `step()`, so it
  cannot race the kernel's stepper directly — but it can fire `deliverStopNow()`
  (two I2C writes) from a different fiber while the stepper sits in its 4 ms
  encoder settle window. Deliberate per sprint 006 ticket 002's own reasoning;
  recorded because the tension with the bus-discipline invariant is not
  documented at either end.
- **Tautological range checks on a 32-bit target.** `parseIdDigits` and
  `parseUint32` both test `value > UINT32_MAX` on an `unsigned long`, which is
  32 bits on the real target — always false, and a plausible
  `-Wtautological-constant-compare` on some toolchains. Harmless; the `ERANGE`
  check beside it does the real work.
- **`wheelSpeed()` has no `//%`** and is reached only by
  `wire_adapter.cpp`'s forward declaration. Correct, and consistent with the
  file's convention — noted only because `src/DESIGN.md` §9 lists it among the
  block-facing surface.
- **`pxt.json`'s `microphone` dependency** remains unexplained. `src/DESIGN.md`
  §10 already flags it as genuinely unknown after two review passes; this pass
  also finds no reference in `src/` or `test/`. Leaving it documented-not-deleted
  is still the right call absent out-of-band knowledge.
