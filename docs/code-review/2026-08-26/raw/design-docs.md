# Annex — Phase 0: design documents against code (2026-08-26)

Consolidated as **D-01 … D-08** in [`../review.md`](../review.md). This annex
carries the evidence for each.

Doc set as reviewed: `docs/design/{design,overview,specification,usecases}.md`
plus per-root `DESIGN.md` for `src/`, `tools/`, `tests/`, `tests/host/`,
`tests/tools/`, `test/`.

---

## D-01 — `clasi design validate` fails (BLOCKER)

```json
{
  "ok": false,
  "messages": [
    "Missing design doc: subsystem directory .../src/blocks   has no DESIGN.md",
    "Missing design doc: subsystem directory .../src/comms    has no DESIGN.md",
    "Missing design doc: subsystem directory .../src/core     has no DESIGN.md",
    "Missing design doc: subsystem directory .../src/motion   has no DESIGN.md",
    "Missing design doc: subsystem directory .../src/platform has no DESIGN.md"
  ]
}
```

`.clasi/config.yaml` declares `sources: [src, tools, tests, test]`. Sprint 013
created five directories under `src/`; under the CLASI doc model each becomes a
subsystem needing a co-located `DESIGN.md`. None was written, and sprint 013's
final-sweep ticket (006) did not run the validator.

`guidelines.md` §"Phase 0 — Design documents first" states the requirement
directly: *"The doc set must pass `clasi design validate`."*

`src/DESIGN.md`'s own preamble names the tension and argues past it:

> "The directory split is coarse (five buckets for eleven layers), so it
> doesn't carry the fine-grained per-file behavioral and design detail below —
> this document still carries the logical subsystem breakdown as sections."

That is a reasonable position on *where the detail lives*. It is not a
resolution of the validator failure, and nothing in the repo records the
decision as a deliberate deviation.

**Two viable remedies, in order of preference:**

1. Five thin `src/<dir>/DESIGN.md` files — a paragraph of scope plus a pointer
   into the matching `src/DESIGN.md` section. This is exactly the pattern
   `tests/DESIGN.md` → `tests/host/DESIGN.md` already uses, and it makes the
   directory a reader can `ls` into self-describing.
2. Re-declare `sources:` as the five directories plus `src` itself, if the
   intent is that `src/` is one subsystem that merely happens to have folders.

---

## D-02 — `src/DESIGN.md` is 44% sprint-history appendix

Section sizes, measured:

| Section | Lines |
|---|---:|
| 1. Layer map and layering rules | 28 |
| 2. Kernel | 44 |
| 3. Motion engine | 100 |
| 4. Wire grammar | 103 |
| 5. Wire adapter | 112 |
| 6. Transports | 73 |
| 7. Hardware ports | 100 |
| 8. Protocol composition | 117 |
| 9. Shim + blocks | 276 |
| 10. Open questions / known limitations | 91 |
| 11. Host-vs-target language standard | 82 |
| **12. Sprint 006 — architecture diagram and change summary** | **103** |
| **13. Sprint 007 — architecture diagram and change summary** | **163** |
| **14. Sprint 008 — architecture diagram and change summary** | **241** |
| **15. Sprint 012 — architecture diagram and change summary** | **315** |
| **16. Sprint 013 — architecture diagram and change summary** | **80** |
| total | **2045** |

§12–§16 = **902 lines, 44%**.

This is the design-doc analogue of the ticket-archaeology comment anti-pattern
`guidelines.md` already bans in source (anti-pattern 1), and it fails the same
way. §15 is the clearest case: 315 lines describing sprint 012's split of
`main.ts` into six modules — whose product now lives in `src/blocks/`, a
directory §15 does not know exists, because §16 moved it one sprint later. A
reader has to hold §9, §15 and §16 simultaneously to work out what is true.

Each of these sections already exists, verbatim, in its own sprint's
`clasi/sprints/NNN-*/design/` overlay. Keeping §1–§11 and deleting §12–§16
loses nothing and halves the document.

**The recurrence guard matters more than the deletion**: something in the
sprint-close path appends one of these per sprint. Whatever that is should stop.

---

## D-03 — Status headers, stale by 2 to 10 sprints

| Doc | Header claim | Reality |
|---|---|---|
| `docs/design/design.md` | *"Last reviewed: 2026-08-23 · Status: in-flux (as-built through sprint 008 … Sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)"* | 005–013 all closed and merged |
| `src/DESIGN.md` | *"as-built through sprint 008 … sprint 012 **executed and closing**"* | 012 and 013 both merged |
| `docs/design/overview.md` §Status | *"Code reflects work through sprint 003 (protocol v6, motion API, host test harness); sprints 004/005 (telemetry frames, radio command plane) are **planned, not built**."* | both shipped; ten sprints stale |

`overview.md` is the stakeholder-facing document and carries no
`Last reviewed:` header at all, so nothing signals its age. It currently tells a
reader the radio command plane does not exist.

`design.md`'s body is *partly* current — its subsystem map knows about sprint
013's directory grouping — which makes the stale header worse than a uniformly
old document: it invites trust.

---

## D-04 — `src/DESIGN.md` §10 states three limitations the code fixed

All three are present-tense assertions in the section a planner reads to decide
what still needs work.

### (a) The `tools/` telemetry retrofit

> "`tools/`'s bench scripts still parse the old cleartext `TLM:` prefix … the
> v6 `thdr`/`t` frames sprint 004 built are real but nothing in `tools/`
> consumes them yet — that retrofit is sprint 005 (roadmapped, not yet
> detail-planned)."

`tools/tlm.py` is a 430-line `thdr`/`t` decoder with header tracking, seq-gap
loss counting with 7-bit wraparound, arity rejection, orphan-frame accounting,
CSV writing with a meta sidecar, and two fail-loud guards. It has its own test
suite (`tests/tools/test_tlm.py`, 522 lines) against a shared golden fixture.
Sprint 005 is in `clasi/sprints/done/`.

### (b) The motion-completion channel

> "`WireAdapter::lastDone()`/`lastDoneReason()` permanently inert — hosts cannot
> observe motion completion via the reliability channel."

Sprint 005 ticket 004 built the whole resolution machine: `armPendingMotion()`,
`resolvePendingReason()` (with an explicit priority order — estop, stall, then
goal-directed vs lease-style), `resolvePendingIfDue()`, `forceResolvePending()`,
and the `engineMoveActive()` bridge in `shims.cpp`. §5 of this same document
describes it in detail. §10 was not updated.

### (c) The radio limits

> "radio's own TX cap (`kMaxPayloadBytes` = 200) is already provably exceedable
> by a legal, if pathological, telemetry frame (up to 239 bytes measured)" and
> "An inbound line longer than one fragment is **clamped to a parseable prefix**
> rather than reassembled or rejected, which can execute as a different,
> shorter, legal command, not merely drop one."

Both fixed in sprint 010:

- `radio_transport.h:152` — `static constexpr size_t kMaxPayloadBytes = 240;`
  (ticket 002), pinned by
  `test_wire_constants_drift.py::test_radio_max_payload_bytes_is_pinned_at_240`
  and by the four-way equality test.
- `radio_transport.cpp:63` (ticket 001) rejects over-length frames whole and
  counts them in `rxOversizeDropped_`, with a comment stating exactly why
  truncate-and-accept was the hazard.

**The single-fragment RX limit itself is still real** —
`if (!(flags & kFlagStart) || !(flags & kFlagEnd)) return;` still drops any
multi-fragment line — so the bullet's *headline* is correct and only its two
specifics are wrong. That is the dangerous shape: enough truth to be believed.

---

## D-05 — `travelCalib` changed in code; five places still publish 0.8102

`src/motion/motion_engine.h` (post-013, commit `fc84648`):

```cpp
float travelCalib_ = 0.7878f;  // [mm/deg] wheel travel per shaft degree
```

The field comment is exemplary — twelve `RUN:straight` legs at three distances
in both directions, camera-bracketed at rest, with the camera's own scale
verified against three fixed tag pairs (+0.13% / −0.09% / −0.11%), and a
scale-vs-offset fit proving this constant is the right knob rather than a
stopping-distance error. It even carries the knock-on warning for
`rotationalSlip_`.

Still publishing the superseded 0.8102:

| Site | Kind | Effect |
|---|---|---|
| `src/DESIGN.md:170` | doc | "Geometry defaults are the vevov bake: `travelCalib` 0.8102 mm/deg" |
| `docs/design/specification.md:694` | doc | the authoritative constants table |
| `docs/design/usecases.md:410` | doc | UC-013 calibration walkthrough |
| `tools/tour_watch.py:175` | **code** | `k = 0.8102/100` — DIAG counts/s → cm/s |
| `tools/tour_chart.py:61` | **code** | `--travel-calib` default |

The two tools now convert wheel velocities with a constant the firmware no
longer uses: **2.8% error**, in the two tools used to *measure* accuracy, on a
rig with three open issues about accuracy. Test-comment references to 0.8102
also survive at `tests/host/test_wire_telemetry_projection.py:201` and
`tests/host/test_wire_motion_verbs.py:921` (comments only; no assertion depends
on the value).

**Remedy.** `tour_watch.py`'s conversion may simply be unnecessary now — the v6
`vl`/`vr` columns already carry mm/s (`wheelSpeed()`'s own unit,
`tlm.py`'s `wheels_mms()` documents the 1:1). Where a host genuinely needs the
constant, it should come off the wire, or be single-sourced with a drift test
the way `kVersion` already is.

---

## D-06 — `specification.md` §4.3 documents a behavior the code does not deliver

The spec faithfully transcribes `startGoTo`'s arc math:

> - turn angle `theta = 2 * atan2(y, x)` radians, signed
> - if `|y| < 0.01`: straight line, arc length `s = x`
> - else: signed radius `radius = (x² + y²) / (2y)`, arc length `s = radius * theta`
> - the resulting `(s, theta)` is handed to `startMove` as distance-and-yaw.

…and then describes the observable result as *"Drives a curved
(constant-curvature) path to a point in the robot's current coordinate frame,
then stops."*

That is true only while `|theta| < 50°`. Above it, `MotionEngine::moveX()`
splits, and the executed path is a pivot plus a straight leg of the arc's
*length* — see [`correctness-geometry.md`](correctness-geometry.md) for the
measured endpoints. The spec is the authoritative block-API reference; both the
spec and the code need to move.

§11's move-engine description is, by contrast, accurate — including its list of
`serviceMove()`'s end conditions, which correctly omits `estopped` and thereby
documents finding C-06 without noticing it.

---

## D-07 — Stale paths, after a sprint scoped to sweep them

Sprint 013 ticket 006: *"final sweep — DESIGN.md, doc/tool prose, repo-wide
stale-path verification."*

### `main.ts` — retired in sprint 012, still referenced 40 times

Live source (16):

| File:line | Text |
|---|---|
| `shims.cpp:143` | "match the block layer's own `defaultSpeed` (15 cm/s, main.ts)" |
| `shims.cpp:389` | "main.ts's block API still passes two INDEPENDENT rate ceilings" |
| `shims.cpp:742` | "reachable from a dedicated main.ts block" |
| `shims.cpp:745` | "backs the matching main.ts readback block" |
| `shims.cpp:1035` | "reported against main.ts(1,1), nowhere near the real cause" |
| `comms/protocol.h:100` | "main.ts's run dispatcher registers a TS handler" |
| `comms/protocol.h:234` | "Called from main.ts's …" |
| `comms/protocol.cpp:61` | "RUN_EVENT_SOURCE in main.ts" |
| `comms/protocol.cpp:63` | "this literal and main.ts's own …" |
| `comms/protocol.cpp:374` | "called once from a top-level statement in main.ts's `diffDrive` namespace" |
| `comms/wire_adapter.cpp:91` | "The `ConfigField` enum entries (main.ts)" |
| `comms/wire_adapter.cpp:96` | "the same order a human reading main.ts would expect" |
| `motion/motion_engine.h:13` | "main.ts's block API via shims.cpp's engine* forwards" |
| `motion/motion_engine.h:70` | "this project's own goToWorld() in main.ts" |
| `motion/motion_engine.cpp:229` | "matching this project's prior main.ts startGoTo()" |
| `blocks/sim.ts:162` | "no automated check reaches main.ts" |

Plus `tools/tour_square.py:5` and 23 occurrences in `src/DESIGN.md`.

`protocol.cpp:374` is the one most likely to cost someone time: it sends a
reader looking for the `startProtocol()` call site in a file that no longer
exists. It is in `src/blocks/motion.ts:66`.

### Pre-sprint-013 include paths in live headers (6)

| File:line | Says | Is |
|---|---|---|
| `motion/motion_engine.h:135` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `motion/motion_engine.h:148` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `platform/encoder_pose_source.h:10` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `comms/wire_handler.h:144` | `src/wire_adapter.cpp` | `src/comms/wire_adapter.cpp` |
| `comms/wire_handler.h:168` | `src/wire_adapter.cpp` | `src/comms/wire_adapter.cpp` |
| `comms/wire_handler.h:276` | `src/wire_adapter.h` | `src/comms/wire_adapter.h` |

Plus `tools/DESIGN.md:110` → `src/heading_wrap.h`.

### Comment references to functions that do not exist (5)

Found by scanning comment lines for `identifier()` tokens that appear nowhere in
non-comment source across `src/` and `test/`:

| Cited | From | Kind |
|---|---|---|
| `Protocol::formatDiag()` | `comms/radio_transport.h:196, 240`; `comms/wire_adapter.cpp:163` | asserted as current — **stale cross-layer claim** |
| `parseLine()` | `comms/protocol.cpp:130` ("the same tolerance the old parseLine() gave") | historical |
| `sendDebug()` | `comms/wire_handler.cpp:1138` ("the same '\n'/'\r'-stripping rule sendDebug()-style text would get") | historical |
| `sendTelemetry()` | `comms/protocol.h:57` | historical |
| `sendDeviceBanner()` | `comms/protocol.h:57` | historical |

The `formatDiag()` pair is the live defect: `wire_adapter.cpp:163` tells a
reader that *"shims.cpp's DIAG verb reads many more (protocol.cpp's
formatDiag())"* — a pointer into nothing. This is `guidelines.md`
anti-pattern 3, whose canonical example is a dangling `readLine()` reference.

**Remedy with a guard.** A host test that greps `src/` and `docs/` for
`src/<file>` paths not present on disk would have caught every path finding
here, and would keep catching them. The pattern already exists —
`test_pxt_manifest_completeness.py` does exactly this for `pxt.json`'s file
list and would have failed loudly had sprint 013 mis-moved a file.

---

## D-08 — The geofence in the operating rules does not exist

`.claude/rules/playfield-testing.md`:

> Field is **134.3 x 89.3 cm**, AprilTag-1-centred, so limits are
> **±67.15 / ±44.65 cm**. Keep a **12 cm margin**.
>
> Before sending ANY commanded motion, compute the full projected path from a
> **measured** start pose … and confirm every waypoint clears the margin.
> **The geofence is what catches *unexpected* drift on top of that** — it is not
> the primary check.

Repo-wide search for `geofence`, `67.15`, `44.65`, `134.3`, `89.3` across
`*.py`, `*.ts`, `*.cpp`, `*.h`, `*.md` (excluding `node_modules`,
`pxt_modules`) returns hits **only in that rule file and its worktree copies**.

`tools/field.py` owns playfield geometry — `DOTS`, `ORDER`, `RECT`,
`score_corners()`, `path_deviation()`, `closure()` — and is imported by every
tour and ground-truth tool. It has no field boundary and no margin.

So the sentence describes a safety net that does not exist. Either:

- build it in `field.py` (`LIMITS = (67.15, 44.65)`, `MARGIN = 12.0`, plus a
  `clears_margin(rows)` the recorders call and a `check_path(waypoints)` the
  planners call), or
- correct the rule to state that the pre-flight path check is the *only* guard,
  so nobody plans a run believing a second one is watching.

---

## Doc-set summary

| Doc | Verdict |
|---|---|
| `docs/design/design.md` | body largely current; header stale (D-03) |
| `docs/design/overview.md` | **ten sprints stale** in §Status; no review header (D-03) |
| `docs/design/specification.md` | accurate except §4.3's goTo promise (D-06) and the constants table (D-05) |
| `docs/design/usecases.md` | accurate except the constants line (D-05) |
| `src/DESIGN.md` | §1–§9, §11 accurate and genuinely good; §10 wrong in three places (D-04); §12–§16 should not be here (D-02); 23 stale `main.ts` refs (D-07) |
| `tools/DESIGN.md` | accurate; one stale path (D-07) |
| `tests/DESIGN.md`, `tests/host/DESIGN.md`, `tests/tools/DESIGN.md` | accurate |
| `test/DESIGN.md` | accurate, deliberately thin |
| **validator** | **FAILS (D-01)** |
