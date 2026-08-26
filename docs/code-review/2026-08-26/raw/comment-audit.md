# Annex — Comment audit (2026-08-26)

Consolidated in [`../review.md`](../review.md) §"Comment hygiene". This annex
carries the measurements, the per-file table, the recurrence evidence, and a
work order.

**Scope**: all of `src/` (28 project-owned files plus the vendored kernel).
Counts are *non-blank* lines, classified by whether the line begins a comment or
sits inside a block comment.

---

## 1. The headline ratio

| Group | Code | Comment | Ratio |
|---|---:|---:|---:|
| `src/` project-owned (26 files) | 3687 | **4508** | **1.22** |
| `src/core/diffdrive.{h,cpp}` — vendored, human-written | 1103 | 53 | **0.05** |
| `tools/` — Python bench suite (23 files) | 3950 | 408 | **0.10** |

Three groups, one repository, the same readers, a factor of **twenty-four**
between them.

The comparison is the argument. The vendored kernel is the most subtle and
most dangerous code in the project — per-cycle PID with acceleration
feedforward, per-wheel accel/decel correction curves, slow adaptive bias,
twist-hold trim, lambda authority scaling, a speed floor, crawl-pulse
sub-breakaway dithering, two latch families, lease expiry, and lock-free
`Output` publication through an even/odd sequence counter — and it is
comprehensible at 0.05 comment lines per code line. Nothing in the wire layer or
the shim layer is harder than that.

---

## 2. Per-file, worst first

| File | Code | Comment | Ratio |
|---|---:|---:|---:|
| `comms/serial_transport.h` | 19 | 107 | **5.63** |
| `comms/radio_transport.h` | 39 | 197 | **5.05** |
| `motion/motion_engine.h` | 82 | 393 | **4.79** |
| `comms/wire_adapter.h` | 64 | 277 | **4.33** |
| `platform/encoder_pose_source.h` | 20 | 82 | **4.10** |
| `core/heading_wrap.h` | 11 | 44 | **4.00** |
| `core/encoder_glitch_armor.h` | 42 | 105 | 2.50 |
| `comms/protocol.h` | 66 | 151 | 2.29 |
| `comms/wire_handler.h` | 208 | 465 | 2.24 |
| `blocks/stop.ts` | 17 | 37 | 2.18 |
| `blocks/motion.ts` | 100 | 195 | 1.95 |
| `blocks/world.ts` | 77 | 143 | 1.86 |
| `blocks/pose.ts` | 14 | 21 | 1.50 |
| `comms/protocol.cpp` | 147 | 200 | 1.36 |
| `shims.cpp` | 485 | 599 | 1.24 |
| `blocks/run.ts` | 57 | 58 | 1.02 |
| `comms/wire_adapter.cpp` | 380 | 382 | 1.01 |
| `blocks/sim.ts` | 182 | 140 | 0.77 |
| `platform/otos_port.h` | 69 | 52 | 0.75 |
| `platform/nezha_port.h` | 74 | 55 | 0.74 |
| `comms/serial_transport.cpp` | 57 | 38 | 0.67 |
| `platform/nezha_port.cpp` | 198 | 118 | 0.60 |
| `motion/motion_engine.cpp` | 233 | 135 | 0.58 |
| `comms/wire_handler.cpp` | 756 | 427 | 0.56 |
| `comms/radio_transport.cpp` | 102 | 39 | 0.38 |
| `platform/otos_port.cpp` | 162 | 44 | 0.27 |
| `platform/platform_ports.h` | 26 | 4 | 0.15 |
| `core/diffdrive.h` *(vendored)* | 288 | 31 | 0.11 |
| `core/diffdrive.cpp` *(vendored)* | 815 | 22 | 0.03 |

The pattern is sharp and worth naming: **the `.cpp` files are broadly fine; the
`.h` files are where it lives.** Every file above 2.0 is a header except the two
smallest block modules. The six worst are all headers, and five of the six are
project-owned interfaces written or heavily edited during the sprint sequence.

`core/heading_wrap.h` is the clearest single specimen: **11 lines of code under
44 lines of comment**, for a six-line function. Thirty of those 44 lines explain
which sprint, ticket, issue file and code-review ID produced it, and why the
*other* half of the same fix could not be host-tested.

---

## 3. Sprint 009 ran, and the actively-edited files grew back

Comment-line counts immediately before sprint 009's dedicated cleanup
(`git show 84deed8^1:…`) against today:

| File | pre-009 | today | Δ |
|---|---:|---:|---:|
| `wire_adapter.h` | 440 | 277 | **−163** |
| `shims.cpp` | 706 | 599 | **−107** |
| `protocol.h` | 216 | 151 | −65 |
| `protocol.cpp` | 245 | 200 | −45 |
| `wire_adapter.cpp` | 423 | 382 | −41 |
| `serial_transport.h` | 133 | 107 | −26 |
| `wire_handler.h` | 471 | 465 | −6 |
| `motion_engine.cpp` | 135 | 135 | 0 |
| `motion_engine.h` | 374 | **393** | **+19** |
| `nezha_port.cpp` | 77 | **118** | **+41** |
| `wire_handler.cpp` | 378 | **427** | **+49** |
| `radio_transport.h` | 147 | **197** | **+50** |
| **total** | **3745** | **3451** | **−294 (−8%)** |

A whole sprint of dedicated cleanup — ten cleanup tickets, one per subsystem —
bought **8%**. And the four files sprints 010–013 actually touched are all
*above* their pre-cleanup counts: the cleanup was undone in exactly the places
where work continued.

`serial_transport.h` is the sharpest case: cleaned by sprint 009 ticket 005,
down from 7.00 to 5.63, and still 107 comment lines over 19 code lines.

**The conclusion is not "clean again."** Another cleanup sprint would buy another
8% and be re-consumed by sprints 014–017. The lever is at *write* time.

---

## 4. Volume, structurally

74 contiguous comment blocks of ≥14 lines, totalling **1938 lines** — 43% of all
project-owned comment volume sits in blocks long enough to be a document
section. The longest:

| Lines | Site | Opens with |
|---:|---|---|
| **119** | `motion/motion_engine.h:1` | file header |
| 77 | `comms/wire_handler.h:1` | file header |
| 70 | `platform/encoder_pose_source.h:1` | file header (63% of the whole file) |
| 41 | `platform/nezha_port.cpp:49` | `begin()`'s bus-hang guard — **keep** |
| 41 | `comms/wire_adapter.h:246` | "sprint 005 ticket 004: a REAL motion-completion signal (closes…" |
| 40 | `motion/motion_engine.h:420` | `travelCalib_` measurement — **keep** |
| 40 | `comms/wire_handler.h:361` | `feed()`'s contract |
| 40 | `comms/wire_adapter.h:1` | file header |
| 37 | `core/encoder_glitch_armor.h:1` | file header |
| 36 | `core/encoder_glitch_armor.h:62` | `kMaxDeltaCounts` derivation — **keep** |
| 36 | `comms/radio_transport.h:116` | truncation bound |
| 34 | `motion/motion_engine.h:307` | "---- settle-tick decision (sprint 008 ticket 004) ----" |
| 34 | `comms/wire_handler.cpp:213` | `formatConfigValue()`'s input bound |
| 33 | `shims.cpp:221` | "---- cross-fiber stop delivery (sprint 006 ticket 002) ----" |
| 30 | `motion/motion_engine.h:467` | `rotationalSlip_` derivation — **keep** |
| 30 | `comms/wire_handler.cpp:122` | "Sprint 008 (wire-timeout-hardening.md, R-06 + R-18, code review…" |
| 30 | `comms/serial_transport.h:25` | `kRingBytes` chronicle |

Four of these are exemplary and marked **keep** — see §7.

---

## 5. Archaeology markers

Comment lines containing `sprint N`, `ticket N`, `R-NN`, `KERN-NN`, `WIRE-NN`,
`BLK-NN`, `API-NN`, `MOD-NN`, `DES-NN`, `PY-NN`, or an `.md` filename:

| File | Lines |
|---|---:|
| `comms/wire_adapter.cpp` | 50 |
| `comms/wire_handler.h` | 47 |
| `shims.cpp` | 40 |
| `comms/wire_handler.cpp` | 40 |
| `motion/motion_engine.h` | 37 |
| `comms/wire_adapter.h` | 25 |
| `comms/radio_transport.h` | 20 |
| `motion/motion_engine.cpp` | 17 |
| `comms/serial_transport.h` | 16 |
| `comms/protocol.cpp` | 14 |
| `platform/nezha_port.cpp` | 9 |
| `core/encoder_glitch_armor.h` | 9 |
| `platform/encoder_pose_source.h` | 6 |
| `core/heading_wrap.h` | 5 |
| `comms/protocol.h` | 5 |
| `blocks/sim.ts` | 5 |
| *(9 more files, 1–4 each)* | 12 |
| **TOTAL** | **363** |

`core/diffdrive.{h,cpp}` — 1103 code lines — carry **2** between them.

This is the ratchet number. It is mechanically countable, it only ever goes up
under the current process, and every line of it is by definition information git
already holds.

---

## 6. The five anti-patterns, live

`guidelines.md` names these. All five are present in code written *after* the
guidelines were written.

### (1) Ticket archaeology as file header

`comms/serial_transport.h:25-55` — thirty lines introducing
`constexpr uint8_t kRingBytes{255};`:

> "RX/TX serial ring capacity used by begin() (sprint 004 ticket 006, code
> review R-19/WIRE-03; corrected by ticket 007 — remediating ticket 005's thrown
> exception). v5 sized these at a flat 128 B, tuned for a ~27-byte binary WHEELS
> frame… CONFIRMED (ticket 007; was UNVERIFIED under ticket 006)… Ticket 006's
> original `2 * kMaxLineBytes` (480) silently truncated to 224 on assignment…"

Everything a future reader needs, in three lines:

```cpp
// codal-core's setRxBufferSize()/setTxBufferSize() take uint8_t -- 255 is a
// hard ceiling, only ~15 bytes above one maximal 240-byte line, so two full
// lines in one drain window can still overflow. Brace-init so any future edit
// past 255 is a compile error (narrowing), not a silent truncation to 224.
constexpr uint8_t kRingBytes{255};
```

Same shape: `core/encoder_glitch_armor.h:1-37` (a header opening with
"**What this fixes.**" — a ticket write-up), `core/heading_wrap.h:1-21`,
`platform/encoder_pose_source.h:1-70`.

### (2) Justification-to-reviewer essays

`comms/wire_handler.cpp:122-149` spends 25 lines defending why
`kMaxMotionTimeoutMs` is a *sibling* of, and not a *reuse* of,
`kWireBoundaryCastCeiling` — including a paragraph on why including
`wire_adapter.h` here would invert the layering rule.

The load-bearing fact is one sentence: *2³¹−1 is exactly the signed-difference
half-range the `static_cast<int32_t>(now − deadline) < 0` idiom needs, so
`now + timeout` can never wrap past `now`.* The layering argument belongs in the
ticket.

### (3) Stale cross-layer claims

Five comment references to functions that do not exist anywhere in `src/` or
`test/`:

| Cited | From | Kind |
|---|---|---|
| `Protocol::formatDiag()` | `comms/radio_transport.h:196, 240`; `comms/wire_adapter.cpp:163` | **asserted as current — live defect** |
| `parseLine()` | `comms/protocol.cpp:130` | historical |
| `sendDebug()` | `comms/wire_handler.cpp:1138` | historical |
| `sendTelemetry()`, `sendDeviceBanner()` | `comms/protocol.h:57` | historical |

`wire_adapter.cpp:163` tells a reader *"shims.cpp's DIAG verb reads many more
(protocol.cpp's `formatDiag()`)"* — a pointer into nothing. This is the exact
`readLine()` shape `guidelines.md` cites as canonical.

Plus the 16 `main.ts` references and 6 pre-sprint-013 include paths catalogued
in [`design-docs.md`](design-docs.md) D-07.

### (4) Diff restatement

- `shims.cpp:508-518` — *"this used to read `if (wasActive) odomUpdate(r);`,
  matching updateMove()'s own gate just below — so continuous-mode driving …
  never called this at all"* (11 lines).
- `motion/motion_engine.cpp:349` — *"extracted verbatim from shims.cpp::
  tickDrive()'s former inline loop … Behavior is identical to the loop it
  replaces, not merely similar: same bound, same threshold, same break
  condition, no new command ever issued."*
- `comms/wire_adapter.cpp:270` — *"`out.otos` used to hardcode false with a
  comment claiming no OTOS was wire-reachable — false even at the time it was
  written."*

Each describes the edit, not the code. The code below already says what it does.

### (5) Comments that outlived their code

Covered in D-07. The `main.ts` set is the bulk; `protocol.cpp:374`'s
*"called once from a top-level statement in main.ts's `diffDrive` namespace"* is
the one most likely to cost someone real time, because it sends a reader hunting
for a call site in a file that does not exist.

---

## 7. Two comments that are actively wrong

Not volume — correctness.

### `blocks/motion.ts:1-12` — the namespace docstring

This is the text that surfaces in the extension's own generated documentation
and the first thing a student reads.

> "The wheel servo runs in its own fiber on the micro:bit (the DiffDrive kernel,
> 24 ms cadence); every command below just talks to it. The hardware
> implementations live in the .cpp files; **the function bodies here are the
> browser-simulator fallbacks.**"

Both sentences false:

- The kernel's own fiber is **deliberately unwired** (`shims.cpp:190`,
  `// rig->kernel.start();` commented out). *"The robot only moves while
  something ticks"* is stated as a **system invariant** in
  `docs/design/design.md` §"Execution model". This paragraph teaches the exact
  mental model the tick model exists to replace.
- The simulator fallbacks moved to `blocks/sim.ts` in sprint 012. This file's
  bodies are the real block API.

### `blocks/motion.ts:200-206` — `isMoving()`

> "Is a move currently running? **Checks state only — it does not itself advance
> the move.**"

`isMoving()` → `_updateMove()` → `shims.cpp:441 updateMove()`, which calls
`engine.serviceMove()` — reissuing `kernel_.drive()`, potentially ending the
move, potentially firing `deliverStopNow()`. The 2026-08-23 verify pass found
this same claim false (BLK-12) and correctly cleared `moveProgress()`, whose
path *is* read-only. Unchanged since.

---

## 8. What "good" looks like — the keep list

The target is already in this tree. These earn every line and should not be
touched by any cleanup pass:

| Site | Why it earns its length |
|---|---|
| `motion/motion_engine.h:467-497` — `rotationalSlip_` | Names the exact wrong shortcut a future re-measurer would take (re-running the pivot experiment and stopping at the 0.915 ratio) and blocks it, showing the dropped middle step 109.8 → 120.0 that separates the two numbers. Unrecoverable from code. |
| `motion/motion_engine.h:420-459` — `travelCalib_` | Twelve camera-truthed legs, three distances, both directions, at rest; the camera's own scale verified against three fixed tag pairs; a scale-vs-offset fit proving this constant is the right knob rather than a stopping-distance error; and the knock-on warning for `rotationalSlip_`. |
| `platform/nezha_port.cpp:132-145` — reversal dwell | The measured (20, 50] ms window that latched 12/12 in the wedgelab campaign, and the bench signature the fix removes. |
| `platform/nezha_port.cpp:49-89` — `begin()` bus-hang guard | Names the resolved codal-nrf52 commit, the two upstream fixes it descends from, the ~11 s per-call bound, and — unusually and correctly — states plainly what is *not* confirmed and what trade-off was accepted. |
| `core/encoder_glitch_armor.h:62-97` — `kMaxDeltaCounts` | Derives 5000 from the kernel's own 24 ms cadence and the measured `fullDutyVelocity`, lands ~10× above worst-case plausible motion and ~10× below the smallest targeted discontinuity, and says explicitly it was not picked to make a bench run pass. |
| `comms/wire_adapter.cpp:39-67` — the three hazards | Numbered, each with real debugging history, each naming a silent catastrophic failure mode (odometry-mutating reads, the 0.1 mm vs centidegree split, the cache-vs-blocking-read distinction). |

Every one states **a measured hardware fact a reader cannot recover from the
code**. That is the whole test, and this repo already knows how to pass it.

---

## 9. Proposed standard

Add to `guidelines.md` as a **write-time** rule, not a cleanup-time one:

> A comment must state something a competent reader cannot recover from the code
> in front of them: a unit, a sign convention, an invariant, a measured hardware
> fact, a wire layout, or a hazard.
>
> **Sprint numbers, ticket numbers, issue filenames, code-review IDs, and "this
> used to be X" belong in the commit message.** Git already stores them, and a
> reader who wants them can `git log -L`.
>
> If the comment is longer than the code it describes, it is a design-doc
> section wearing a comment's clothes. Move it, or cut it to the fact.

### Mechanical enforcement, available today

A host test in the existing style — `test_pxt_manifest_completeness.py` is the
model: no compiler, reads source as text, cheap:

```python
_MARKERS = re.compile(
    r"\bsprint \d|\bticket \d|\bR-\d\d|KERN-\d\d|WIRE-\d\d|BLK-\d\d|API-\d\d",
    re.I)
_BUDGET = 363          # measured 2026-08-26; ratchet DOWN, never up

def test_archaeology_marker_budget():
    ...
    assert total <= _BUDGET
```

Vendored `core/diffdrive.{h,cpp}` excluded (upstream owns them; they carry 2).

The value is not the number — it is that every future sprint that adds a ticket
reference has to either cut one elsewhere or consciously raise the budget in a
diff someone reviews.

---

## 10. Work order

Ordered by ratio × reader impact. **Apply by content match, not by the line
numbers above** — `guidelines.md`'s own §"Applying a comment audit safely" is
right that these rot, and sprints 012 and 013 moved every file in this list.

| # | Target | Action | Est. lines removed |
|---:|---|---|---:|
| 1 | `blocks/motion.ts` namespace docstring | **Rewrite — correctness, not volume.** State the tick model. | +0 |
| 2 | `blocks/motion.ts` `isMoving()` doc | **Rewrite — correctness.** It *does* advance the move. | +0 |
| 3 | `comms/serial_transport.h` | Collapse the `kRingBytes` and `writeLine()` chronicles to their contracts | ~70 |
| 4 | `comms/radio_transport.h` | Same; also fix the two `formatDiag()` references | ~110 |
| 5 | `motion/motion_engine.h` header (119 lines) | Cut to the two-primitive contract + the sign convention; the reductions are already documented at each method | ~70 |
| 6 | `platform/encoder_pose_source.h` header (70 lines) | Keep the LIFETIME and HEADING WRAP paragraphs — both load-bearing. Cut the ticket/issue framing and the host-testability narration | ~40 |
| 7 | `core/heading_wrap.h` | Keep the ±π boundary-case paragraph. Cut the sprint/ticket framing and the "why this can be host-tested and the wiring can't" narration | ~28 |
| 8 | `comms/wire_adapter.h` | Collapse the `sprint 005 ticket 004` block (41 lines) to the `lastDone` contract | ~30 |
| 9 | `comms/wire_handler.cpp:122` | Cut the sibling-vs-reuse essay to the wraparound sentence | ~22 |
| 10 | `shims.cpp` §cross-fiber stop, §tick engine, §watchdog | Keep the mechanism, cut the ticket narration and the diff restatement at `:508` | ~50 |
| 11 | `core/encoder_glitch_armor.h` header | Keep `kMaxDeltaCounts` entirely. Cut the "What this fixes" ticket write-up | ~30 |
| 12 | Repo-wide | Delete the 5 dangling function references and the 16 `main.ts` references | ~21 |

Rough total: **~470 lines**, ~10% of project-owned comment volume, concentrated
in the six worst headers and touching no `.cpp` logic except `shims.cpp`'s
section banners.

**Sequence matters**: items 1 and 2 are correctness fixes on the
student-facing surface and should not wait for a volume pass. Item 12 is
mechanical. Items 3–11 want the recurrence guard (§9) landed first, or sprints
014+ will refill them the way 010–013 refilled sprint 009's work.
