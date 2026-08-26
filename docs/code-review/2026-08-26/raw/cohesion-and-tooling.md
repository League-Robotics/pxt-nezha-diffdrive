# Annex — Cohesion, duplication, hard-coded constants, tooling (2026-08-26)

Consolidated as **Q-01 … Q-09** in [`../review.md`](../review.md).

---

## Q-01 — One arc formula, four hand-written copies

Full treatment in [`correctness-geometry.md`](correctness-geometry.md). Recorded
here because it is simultaneously the review's top correctness finding *and* its
clearest duplication finding, and the two framings suggest different fixes.

| Site | Reached by | Status |
|---|---|---|
| `motion/motion_engine.cpp:186` `goToR` | wire `GO_TO_R`/`GO_TO_W` | correct (sprint 006) |
| `blocks/motion.ts:183` `startGoTo` | student blocks | **C-01** — 112.5 mm miss, measured |
| `test/test.ts:161` `legToward` | `RUN:tour:robot` | **C-02** — 0.53 × distance |
| `blocks/world.ts:224` `goToWorld` | `RUN:goto`, `RUN:tour:world` | **C-03** — 50° boundary collision |

The duplication framing is the more durable one: a fix landed on one of four
copies, and no mechanism existed to notice the other three. `goToR` is
host-portable, host-tested, already built, and already reachable from
`shims.cpp` — `engineGoToR()` exists for the wire and merely lacks a `//%`.
Three call sites could become one.

`motion_engine.h:70` even records the split as intentional — *"two paths sharing
one primitive, not one implementation"* — which was a defensible design call when
both paths were correct. It stopped being defensible when only one of them was
fixed.

---

## Q-02 — `shims.cpp`: seven subsystems, one header-less file

1173 lines, 485 of them code. `src/DESIGN.md` §9 enumerates its jobs, and the
list is the finding:

| Responsibility | Surface |
|---|---|
| Composition root | `Rig`, `ensure()`, the kernel `Config` bake, port wiring |
| Odometry | `odomUpdate()`, `x`/`y`/`heading`, `poseX/Y/Heading`, `resetPose`, `seedPose` |
| Move-engine forwarding | `startMove`, `updateMove`, `endMove`, `moving`, `progress` |
| Tick engine | `tickDrive()`, `stepBusy`, absolute-deadline pacing, `cycleStat` |
| Starvation watchdog | `watchdogEntry`, `commandLooksActive`, the only fiber this file starts |
| Config marshalling | `setKernelValue` / `getConfigValue` — 18 ordinals each |
| OTOS shim | `otosRef()`, `otosBegin/Read/Get/Zero/Calibrate/SetOffset` |
| Wire forwards | `engineWheelsX/MoveX/MoveV/GoToR/GoToW`, `engineDefaultCruiseMmS`, `engineMoveActive`, `setWheelsTimed`, `driveTwistTimed`, `diagValue` |
| Block surface | every `//%` function |

It is reached by `protocol.cpp` and `wire_adapter.cpp` through hand-maintained
same-package forward declarations, because it has **no header**. That convention
is deliberate and well-explained — including `protocol.h` would pull in
`radio_transport.h`, and PXT's per-file dependency scan would then demand a
`radio` package this project does not use. Fine.

The *breadth* is not defended anywhere, and it has a concrete cost: nothing in
this file is host-testable, because the whole translation unit includes `pxt.h`.
That is why `heading_wrap.h`, `encoder_glitch_armor.h` and
`encoder_pose_source.h` exist at all — each is a small piece carved out of a
`pxt.h`-bound file *specifically* to get it under test, and each carries a long
comment apologising for the carve. The pattern is sound; it just hasn't been
applied to the biggest candidate.

**The most separable piece is odometry.** `odomUpdate()` plus the three float
fields is pure differential dead-reckoning with a midpoint-heading integration —
no CODAL, no I2C, no PXT. It is also the thing `EncoderPoseSource` already wraps
by reference, and the thing every pose finding in two review cycles has touched.
Moved to `src/core/odometry.h` it would be host-testable in an afternoon, and
`Rig` would hold one member instead of five.

---

## Q-03 — π and the centidegree conversion, written out 13 times

`3.14159265f` appears 8 times in `shims.cpp` alone, plus `otos_port.h:107`,
`motion_engine.cpp:17` (`kPi`), `heading_wrap.h:52` (its own longer literal), and
`Math.PI` on the TS side.

The **cdeg → rad** conversion is written out verbatim five times in `shims.cpp`:

| Line | Function |
|---|---|
| 272 | `driveTwist()` |
| 300 | `driveTwistTimed()` |
| 385 | `startMove()` |
| 1155 | `otosSetOffset()` |
| 1166 | `seedPose()` |

```cpp
static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f
```

…and inverted twice more (`poseHeading()` at 840, `otosGet()`'s local
`kRadToCdeg` at 1093). `otosGet()` is the only site that names the conversion.

`shims.cpp`'s own header states the boundary convention — *"integers only. mm,
mm/s, centidegrees, centidegrees/s"* — which is exactly the right place for:

```cpp
constexpr float kCdegToRad = 0.01f * 3.14159265f / 180.0f;
constexpr float kRadToCdeg = 1.0f / kCdegToRad;
```

Seven sites, one definition, and the boundary convention gets a name instead of
a paragraph.

---

## Q-04 — `kMaxLineBytes = 240`, declared four times

| Site | Name |
|---|---|
| `comms/serial_transport.h:23` | `diffDrive::kMaxLineBytes` |
| `comms/wire_handler.h:357` | `Wire::WireHandler::kMaxLineBytes` |
| `comms/radio_transport.h:234` | `RadioTransport::kMaxLineBytes` (private, RX) |
| `comms/radio_transport.h:152` | `RadioTransport::kMaxPayloadBytes` (public, TX) |

**Guarded**, and correctly so:
`test_wire_constants_drift.py::test_radio_serial_wire_capacity_constants_are_equal_at_240`
pins all four equal, with an error message that names the file each came from
and notes that this has already drifted twice.

Single-sourcing would invert the layering rule (`src/DESIGN.md` §1:
`wire_handler` may include no project headers at all), so a drift test is the
right mitigation rather than a compromise. Recorded as the *pattern* — a
mirrored constant held together by a test — not as a defect. It is the model the
other mirrored constants in this annex should follow.

---

## Q-05 — The default cruise speed is two constants in two units

```ts
// blocks/motion.ts:55
let defaultSpeed = 15      // [cm/s]
```

```cpp
// shims.cpp:143
float defaultCruiseMmS_ = 150.0f;  // [mm/s]
```

…with `shims.cpp`'s comment asserting the relationship:

> "Seeded to 150.0f to match the block layer's own `defaultSpeed` (15 cm/s,
> main.ts) — NOT derived from any kernel constant"

(and citing a file retired two sprints ago — see D-07).

Nothing enforces the match. `default_cruise` is settable over the wire
(`kFields` ordinal 15) and `defaultSpeed` from a block
(`setDefaultSpeed`, clamped to ≥1), so they diverge the moment either is used —
by design, arguably, since one is the wire's sentinel resolution and the other is
the block layer's move speed. But then the comment's claim that they *match* is
a snapshot, not a contract, and should say so.

`src/DESIGN.md` §10 already flags the 150 as *"a planning-time choice, not a
measured one"* — correct and worth keeping. The fix here is just to stop
asserting a coupling that is not maintained.

---

## Q-06 — Two classes named `Cam` in `tools/`

| Site | Role |
|---|---|
| `camlink.py:52` | runs **inside** the aprilcam venv as a subprocess; talks to the daemon |
| `camproc.py:72` | runs in the tool's own interpreter; **spawns** camlink and parses its stream |

Genuinely different contracts, and the consolidation from sprint 005 held —
all seven tour/ground-truth tools import `camproc.Cam`
(`pivot_truth`, `tour_run`, `tour_closedloop`, `tour_practice`, `turn_sweep`,
`tour_watch`, `tour_square`), which was the whole point of R-26.

The residual cost is only naming: a reader of `tour_run.py`'s `cam = Cam()` has
to check the import to know which contract they hold. `CamProc` / `CamClient`
would close it. Low priority.

---

## Q-07 — `tsconfig.json` cannot run; the block layer has no standalone check

`tsconfig.json` maintains a hand-edited `files` array — updated by sprint 012
(the `main.ts` split) and sprint 013 (the `blocks/` move), so it is *current*:

```json
"files": [ ..., "src/blocks/sim.ts", "src/blocks/run.ts", "src/blocks/pose.ts",
           "src/blocks/stop.ts", "src/blocks/world.ts", "src/blocks/motion.ts",
           "test/test.ts", "test/testrig.ts" ]
```

But `package.json` has one dependency (`pxt-microbit`) and no `typescript`;
`node_modules/typescript` does not exist. Nothing can execute this file.

So the **1149 lines of student-facing TypeScript** — the entire block API, the
simulator, the RUN dispatcher, `goToWorld` — are type-checked only by a full
`pxt build`, which the process runs once per sprint in the build-checkpoint
ticket. That is a real gate, not nothing. But:

- It runs once per sprint, not per change.
- It type-checks; it does not *execute*. C-01 is a live geometry defect in
  `startGoTo` that type-checks perfectly.
- `test_pxt_manifest_completeness.py` guards `pxt.json`'s file list; nothing
  guards `tsconfig.json`'s, so it can silently rot without anyone noticing —
  precisely because nothing reads it.

**Decide one way or the other.** Either add `typescript` as a dev dependency and
a pytest wrapper that shells `tsc --noEmit` (cheap, catches a real class), or
delete `tsconfig.json` so nobody maintains a file with no consumer.

The larger gap C-01 exposes — no TypeScript is *executed* by any test — is worth
a separate conversation. A minimal harness (node, a stub `diffDrive` namespace
capturing `startMove` calls) would have caught C-01, C-02 and C-03 in one
assertion each.

---

## Q-08 — No linter configured, so 6 real findings hide behind 205 false ones

`uvx ruff check tools tests` → **211 findings**, no configuration anywhere in
`pyproject.toml`.

| Rule | Count | Real? |
|---|---:|---|
| `F811` redefined-while-unused | 91 | **No** — pytest fixture shadowing; ruff does not model fixtures |
| `I001` unsorted imports | 39 | Style; the `sys.path.insert` prelude in every tool makes this awkward by construction |
| `EXE001` shebang not executable | 17 | Style |
| `RUF100` unused noqa | 12 | Housekeeping |
| `RUF059` unused unpacked variable | 11 | Mostly intentional |
| `PLW1510` subprocess without check | 8 | Mostly intentional |
| `RUF007` zip instead of pairwise | 8 | Style |
| **`F401` unused import** | **4** | **Yes** |
| `B904` raise-without-from | 2 | **Yes** |
| `B023` loop-variable closure | 2 | No — thread joined within the iteration |
| `B008` call in default argument | 1 | **Yes**, though deliberate |
| *(others)* | 6 | Mixed |

The genuinely actionable set:

| Site | Finding |
|---|---|
| `tests/host/test_wire_motion_completion.py:38` | `pytest` imported unused |
| `tests/tools/test_camproc.py:24, 28` | `os`, `pytest` imported unused |
| `tools/otos_bench.py:22` | `argparse` imported unused |
| `tools/tour_watch.py:150`, `tools/truth_check.py:144` | `raise SystemExit(str(e))` inside `except` — loses the `DeadTelemetryError` chain, which is the one exception the fail-loud guard exists to raise |
| `tools/truth_check.py:165` | `def sampler(prev=math.degrees(c0))` — the mutable-default trick to seed a closure local; correct but obscure |

Six things worth doing, invisible behind 205 that are not. **Remedy**: a
`[tool.ruff.lint]` block selecting `F, E9, B`, with `F811` ignored under
`tests/` (or `flake8-pytest-style` enabled so fixtures are understood). Then
`ruff check` becomes a gate that means something and can join the suite.

### C++ side

`tests/host/test_kernel_harness.py` compiles with `-Wall -Wextra` and tolerates a
wall of `-Wdeprecated-volatile` from the vendored kernel's `++cfgSeq_` (one per
config setter, ~16 of them, at C++20). Upstream owns that code and it is
byte-stable by design, so the right move is a targeted
`-Wno-deprecated-volatile` on `diffdrive.cpp`'s compilation with a one-line
comment, not a change to the file — leaving the warning stream meaningful for
everything else.

---

## Q-09 — One hard-coded absolute path to one person's machine

```python
# tools/camproc.py:58
_DEFAULT_VENV = '/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'
```

Overridable via `APRILTAGS_VENV`, and single-sourced through `resolve_venv()` —
a genuine improvement on the five independent copies the 2026-08-23 review found
(R-24), and correctly documented at both `camproc.py:15` and `camlink.py:4`.

Residual: every camera tool fails on any other machine until that env var is
set, and the failure surfaces as *"camera down"* rather than *"wrong
interpreter"*. A `shutil.which('aprilcam')` probe, or an explicit
`FileNotFoundError` naming the env var when the path does not exist, would turn
a confusing failure into an actionable one — which matters because
`.claude/rules/playfield-testing.md`'s standing advice is that a dark field
"looks exactly like a broken camera", and a missing interpreter should not add a
third indistinguishable cause.

---

## Structural observations, not findings

**The mirrored-constant pattern is now split cleanly in two.** The ones with
drift tests (`kVersion`, the four 240s, `RUN_EVENT_SOURCE`, the `kDiag*`
ordinals) have held across five sprints without drifting. The ones without
(`travelCalib` in three docs and two tools, `0x5F` across the shim boundary,
`defaultSpeed`/`defaultCruiseMmS_`, the sim's 115 vs hardware's 119.96) have
*all* drifted or are structurally able to. That is a clean natural experiment,
and it says the remedy is not "single-source everything" — it is "every mirrored
constant gets a drift test, or gets merged."

**The carve-out-to-test pattern works and should be used more.**
`heading_wrap.h`, `encoder_glitch_armor.h`, `encoder_pose_source.h` and
`MotionEngine::settleToRest()` are each a small pure decision lifted out of a
`pxt.h`-bound file specifically to get it under test. All four are good code and
all four are tested. The apologetic 40–70-line headers each carries are the
tax (see [`comment-audit.md`](comment-audit.md)) — but the *pattern* is the
right one, and `odomUpdate()` is the obvious next candidate.

**Silent-refusal-as-policy has now compounded to six states.** The 2026-08-23
review counted five ways the robot can be "off" that a caller distinguishes only
by reading separate readbacks (e-stop, stall latch, watchdog soft stop, lease
expiry, cruise sentinel). This review adds a sixth: a `drive()` refusal that
`MotionEngine` discards (C-07). `src/DESIGN.md` §10 records sprint 007's
decision to defer the unified "why won't it move" surface, and the reasoning
(the watchdog's soft stop is deliberately non-latching while the others latch)
is sound. Worth noting only that the count is going up, and that
`lastError()` — already latched, already reachable at DIAG ordinal 20 — is
closer to the answer than the deferral note suggests.
