# Modularity & API Review — 2026-08-23 (raw annex)

Reviewer scope: guidelines dimensions **3** (modularity / information hiding)
and **4** (API quality vs. use cases), plus design-vs-implementation
assessment. Correctness bugs are handed off in one-liners at the end.
Every claim below was verified against the working tree at commit `46c40a8`
(reference searches shown or described per finding).

Prefixes: `MOD` = Part A (modularity), `API` = Part B (API vs. use cases),
`DES` = Part C (design assessment). Ordered most-severe-first.

---

## Major

### API-01 — The documented continuous-drive idiom `while (diffDrive.driveTick())` exits immediately; the robot is watchdog-stopped ~150 ms after a `setWheelSpeeds()`/`driveTwist()`

- **File(s):** `src/main.ts:91-99, 111-116, 129-141`; `src/shims.cpp:449-545`;
  `docs/design/specification.md` §4.2; `docs/design/usecases.md` UC-002 step 4.
- **Dimension:** 4 (API quality; also a correctness scenario — cross-noted in hand-offs).
- **Severity:** Major
- **Rationale:** `tickDrive()` returns `moveActive` — the move-*engine*'s
  post-`serviceMove()` state (`shims.cpp:470`, `return moveActive` at `:544`).
  `wheelsV()` **clears** the planner (`motion_engine.cpp:21`), so after
  `setWheelSpeeds()` there is never an active move and the first
  `driveTick()` returns `false`. The doc comments on `setWheelSpeeds`,
  `driveTwist`, and `driveTick` (`main.ts:91-99`), spec §4.2, and UC-002
  step 4 all prescribe exactly `while (diffDrive.driveTick())` as the way to
  keep continuous driving alive — a loop whose condition is false on its
  first evaluation. Scenario: student places `set wheel speeds 15 15`, adds
  the documented tick loop; the loop body never runs, no further steps occur,
  and the starvation watchdog port-stops the motors within ~100–150 ms
  (`shims.cpp:624-637`). The robot twitches and stops. The return contract is
  deliberate *for blocking moves* (`shims.cpp:444-447` — a move's final tick
  ends the `while`), but it is incompatible with the continuous-mode idiom
  the same API documents. Corroborating evidence that the real idiom is
  different: `test/testrig.ts:118-120` drives the drum with a **bare**
  `diffDrive.driveTick()` inside `basic.forever()`, never the documented
  `while` form; no in-tree program uses the documented idiom.
- **Remedy:** Either (a) return "anything is active" (move active **or**
  nonzero commanded/applied duty — `commandLooksActive()` at
  `shims.cpp:618-622` already computes this) so the documented idiom works,
  or (b) fix all four documentation sites to the `forever`/`while(true)`
  pattern and keep the return as a move-completion signal. Decide which side
  is wrong; today they contradict each other.
- **Confidence:** High (traced through both hardware shim and simulator body;
  the sim `_tickDrive` at `main.ts:849-868` has the identical contract).

### API-02 — The stall latch is a silent dead-end: no block, shim, or wire verb can clear it, and no student-facing surface can even see it

- **File(s):** `src/diffdrive.cpp:384-386, 455-458, 704-705`;
  `src/shims.cpp` (no bridge); `src/main.ts` (no block); `src/wire_adapter.cpp`
  (no verb/field); `docs/design/usecases.md` UC-002/UC-012.
- **Dimension:** 4 (missing operation + surprising silent failure).
- **Severity:** Major
- **Rationale:** Once `stallHalted_` sets (demanded duty + near-zero motion
  past `stallWindow`, default 500 ms), every subsequent step forces neutral
  (`diffdrive.cpp:483`) and the **only** reset path is
  `clearStallLatch()` → `clearStallReq_` (`diffdrive.cpp:455-458`).
  Reference search: `clearStallLatch` appears only in `diffdrive.h:201`,
  `diffdrive.cpp:384` — no shim, no `//%` binding, no block, no wire field or
  verb reaches it. `estopClear()` does **not** clear it (`diffdrive.cpp:374-376`);
  `resetAdaptiveState()` clears `stallLatched_` but not `stallHalted_`
  (`diffdrive.cpp:765`). Scenario: a student's robot pushes a wall for half
  a second → the program continues, every subsequent Drive/Move block is
  silently ineffective for the rest of the run, and nothing on any surface
  says why or offers recovery short of a power cycle. The wire host can *see*
  it (STATUS `flags` bit 2, `wire_adapter.cpp:121`) but also cannot clear it.
  UC-002's error flow and spec §4.8 already note the block gap; this review's
  assessment is that it is worse than a missing convenience: it is the only
  latched fault state with **no recovery operation anywhere in the system**.
- **Remedy:** (1) expose `clearStallLatch` as an advanced block and a SET-able
  wire action (or fold it into `clearEmergencyStop`, documented); (2) give
  students a readback — a `stalled?` reporter or a general
  `fault` reporter backed by `diagValue(2)`/`lastError()`.
- **Confidence:** High.

### API-03 — On the wire, "cruise/speed = 0 means the configured default" resolves to the drivetrain's full-duty ceiling (~87 cm/s), not a sane default

- **File(s):** `src/shims.cpp:340-346` (`engineDefaultCruiseMmS`),
  `src/wire_adapter.cpp:282-283, 307-308, 347-348, 364-365`;
  defaults `src/shims.cpp:168` (`fullDutyVelocity = 10795` counts/s),
  `src/motion_engine.h:328` (`travelCalib_ = 0.8102`).
- **Dimension:** 4 (wire API as its own use case — wrong-thing-easy).
- **Severity:** Major
- **Rationale:** All four X/GO_TO verbs substitute
  `engineDefaultCruiseMmS()` for a 0 cruise/speed. That function returns
  `fullDutyVelocity / countsPerMm` = 10795 / (10/0.8102) ≈ **875 mm/s** — by
  definition the speed at 100% duty. So the *documented default sentinel*
  (`MOVE_X 500 0 0 5000` — "use the configured default") commands a
  flat-out lunge. The project's own bench history says exactly this speed
  regime "was near the drivetrain ceiling and produced unusable runs"
  (`test/test.ts:229-230`); the block layer's own default is 15 cm/s
  (`main.ts:49`). A bench host reaching for the convenient sentinel gets the
  most violent possible move — the easy thing is the wrong thing. (Whether
  the external motion-api.md mandates *this* interpretation of "configured
  default" could not be checked here — that spec lives in radio-robot-lib —
  but nothing on this robot configures a cruise default *other than* the
  full-duty ceiling, and no wire field exists to set one.)
- **Remedy:** Introduce a real configured default cruise (a `default_cruise`
  GET/SET field, seeded ~150 mm/s, mirroring the block layer's
  `defaultSpeed`), and have `engineDefaultCruiseMmS()` return it; keep
  full-duty velocity as the *ceiling*, not the *default*.
- **Confidence:** High on behavior; Medium on spec-conformance judgment.

### API-04 — STATUS hard-codes `otos=0`, lying about the one hardware fact a wire host needs before GO_TO_W

- **File(s):** `src/wire_adapter.cpp:222-226`; `src/wire_handler.cpp:623-640`;
  contrast `src/shims.cpp:889-896` (`engineGoToW` checks `otos.connected()`).
- **Dimension:** 4 (silent misinformation on the wire) + 3 (a needed bridge
  function is missing while the state is reachable one file away).
- **Severity:** Major
- **Rationale:** `WireAdapter::status()` sets `out.otos = false`
  unconditionally, with a comment claiming "No OTOS in this project's
  wire-reachable surface yet". That claim is false one verb over: GO_TO_W's
  entire accept/refuse decision *is* the OTOS's connected state
  (`engineGoToW()` → `otos.connected()`), reached through the same
  forward-declaration seam `status()` already uses for `diagValue()`. Today a
  host on a robot with a live, seeded OTOS reads `status ... otos=0` and has
  no way to learn GO_TO_W is available except by sending one and parsing the
  `err 6` refusal. There is also no GET field and no diag ordinal for OTOS
  presence — STATUS's boolean is the designed slot for it, and it is wired
  to a constant. (Distinct from the filed `status-lost-diag-numeric-surface`
  issue, which is about DIAG's *numeric* fields.)
- **Remedy:** Add a `bool otosConnected()` bridge in `shims.cpp` (one line:
  `otosRef().connected()`), forward-declare it in `wire_adapter.cpp`, and
  wire `out.otos` to it.
- **Confidence:** High.

### API-05 — UC-007's main flow (startMove + poll `moving?`) runs the robot for zero distance: polling half-advances the move engine while the kernel never steps

- **File(s):** `src/main.ts:267-320` (`startMove`/`isMoving`);
  `src/shims.cpp:415-425` (`updateMove` — `serviceMove()` but **no**
  `kernel.step()`); `docs/design/usecases.md` UC-007;
  `docs/design/specification.md` §4.4.
- **Dimension:** 4 (awkward required sequence; trap block).
- **Severity:** Major
- **Rationale:** The advanced blocks `start move`/`start go to` + `moving?`
  are a shipped, palette-visible pattern whose obvious composition cannot
  work: `isMoving()` → `updateMove()` calls `engine.serviceMove()` (reissuing
  kernel leases, running the deadline clock) but never `kernel.step()`, so no
  duty ever reaches the motors; the watchdog port-stops within ~150 ms; the
  student's `while (diffDrive.isMoving()) {...}` then spins for the move's
  full `duration + 1500 ms` deadline against a motionless robot before
  `expired` ends it (`motion_engine.cpp:274, 290`). The obligation to run a
  *concurrent* `driveTick()` loop is documented only in `startMove`'s doc
  comment — discoverable in JS view, invisible in block view. This is a
  known, honestly-documented tick-model gap (main.ts:269-276, spec §4.4,
  UC-007 step 3), but no filed issue covers it, and "documented trap" is
  still a trap for the audience this palette serves. Note also the shape
  smell: `moving?` is a *reporter* that advances a state machine
  (`_updateMove()` side effects, spec §4.4).
- **Remedy:** Make `startMove`/`startGoTo` spawn the tick source themselves
  (`control.inBackground` loop that runs while the move is active — the
  simulator body effectively already self-advances via `simIntegrate()`), or
  pull the two blocks from the palette until they are safe; make `moving?`
  read-only (`_progress()`-style) once a real tick source exists.
- **Confidence:** High.

### API-06 — UC-013 cannot actually calibrate a non-reference chassis: `rotationalSlip` has no setter on any surface, so the only reachable knob is the one the doctrine forbids

- **File(s):** `src/motion_engine.h:172-178, 346`; `src/shims.cpp:753-758`
  (`setGeometry` — trackWidth/travelCalib only); `src/wire_adapter.cpp:88-104`
  (no geometry fields at all); `docs/design/design.md` "Geometry doctrine";
  UC-013.
- **Dimension:** 4 (missing operation; wrong-thing-easy) — with a design-vs-
  implementation edge: the doctrine and the API contradict each other.
- **Severity:** Major
- **Rationale:** The geometry doctrine is explicit: never adjust `trackWidth`
  to make a turn land; all rotational scrub correction lives in
  `rotationalSlip`, measured per chassis against camera truth. But
  `rotationalSlip_` is a hard-coded vevov measurement (0.952,
  `motion_engine.h:346`) with **no setter anywhere** — not in C++
  (`motion_engine.h:178`: "Read-only for now"), not in `setGeometry`, not in
  the block API, not in the wire `kFields` table. Scenario (UC-013's actor):
  a teacher builds a different kit, measures turns landing ~5% off, and finds
  exactly one turn-affecting knob in the palette — `set track width` — whose
  use for this purpose the design forbids and which silently skews odometry
  and twist conversion when so abused. The API's shape actively funnels users
  into the documented anti-pattern.
- **Remedy:** Add `setRotationalSlip()` + a third `setGeometry` path (or a
  dedicated advanced block "set turn slip"), and a `rotational_slip` wire
  field; document the measurement procedure next to it.
- **Confidence:** High.

### MOD-01 — The wire's reported version has already drifted: ID/VER answer `1.0.0` while the extension is `1.0.10`

- **File(s):** `src/protocol.cpp:63` (`kVersion = "1.0.0"  // keep in sync
  with pxt.json`); `pxt.json:3` (`"version": "1.0.10"`).
- **Dimension:** 3 (duplicated constant across artifacts) — the exact
  landmine `src/DESIGN.md` §10 predicted ("can drift"); it has fired.
- **Severity:** Major
- **Rationale:** The manual-mirror convention has already failed by ten patch
  releases: every `id`/`ver` reply, and the fleet tooling keying off them,
  reports a version that predates the entire v6 sprint. Any bench debugging
  session that trusts VER to identify the flashed build will be misled —
  precisely the class of "instrument lies" failure this project keeps paying
  for. Verified: no build step rewrites `kVersion` (no generator input
  anywhere in-tree references it).
- **Remedy:** Generate it: `make_deploy.py` already rewrites a scratch
  `pxt.json` — have it (or a tiny pre-build step) emit a `version_mirror.h`;
  at minimum, add a host test that greps both files and fails on mismatch
  (the host harness already compiles `protocol.cpp`-adjacent files; a pure
  Python file-compare test is enough).
- **Confidence:** High.

### MOD-02 — The tour/bench scripts are built by copying whole scaffolds: 7 copies of the camera thread, 7 of `wrap()`, 6 of the playfield constants, 2 divergent Python-interpreter paths, and 2 repositioning implementations

- **File(s):** `Cam` class: `tools/tour_run.py:46`, `tour_practice.py:50`,
  `tour_watch.py`, `tour_square.py`, `turn_sweep.py`, `tour_closedloop.py`,
  `pivot_truth.py` (7 sites; diffed — run-vs-watch differ in 45 lines,
  run-vs-practice in 60, i.e. drifted copies, not clones of a shared
  module). `wrap()`: `pivot_truth.py`, `reposition.py`, `practice_chart.py`,
  `truth_check.py`, `tour_run.py`, `tour_closedloop.py`, `turn_sweep.py`.
  `DOTS`/`ORDER`: `tour_run.py:33`, `tour_square.py:22`,
  `tour_practice.py:35`, `tour_closedloop.py:33`, `tour_watch.py:36`,
  `practice_chart.py:15`. Interpreter path: `tour_run.py:31` uses the pipx
  aprilcam venv; `tour_square.py:20`, `tour_practice.py:32`,
  `turn_sweep.py:31`, `tour_closedloop.py:29`, `tour_watch.py:31` use
  `/Volumes/Proj/.../AprilTags/.venv/bin/python3` — two different
  environments running the same `camlink.py`. Repositioning:
  `tour_run.py:160` `place()` reimplements `reposition.py:27`'s
  `Repositioner.go()` (same seedxy/goto/face protocol, separately evolved).
- **Dimension:** 3 (duplication).
- **Severity:** Major
- **Rationale:** This is the copy-scaffold pattern the charter names, and the
  drift it warns about is already observable: the Cam copies have diverged
  (different read loops, different fix medians), and the interpreter constant
  has forked into two venvs — a future aprilcam upgrade will silently split
  the fleet of tools into working and broken halves. Sprint 005 consolidates
  **only** the TLM parsing slice (`tools/tlm.py`); nothing planned touches
  the camera scaffold, `wrap`, the playfield constants, or repositioning.
- **Remedy:** A `tools/bench.py` (or extending `camlink.py`/`robotlink.py`):
  `Cam` thread, `wrap()`, `DOTS`/`ORDER`/`START`, the interpreter path
  resolved once, and `Repositioner` as the single placement implementation;
  fold into sprint 005's scope while those files are already open.
- **Confidence:** High.

### DES-01 — The radio RX path is structurally undersized for sprint 004's "radio speaks full v6": 64-byte buffers, single-slot drop-on-busy, single-fragment-only, against a 240-byte grammar

- **File(s):** `src/radio_transport.h:139` (`rxLine_[64]`),
  `src/radio_transport.cpp:60-61` (truncate to 64; drop if unconsumed),
  `src/protocol.h:224` (`rxLineBuf_[64]`); `src/radio_transport.h:126` /
  `src/radio_transport.cpp:134` (TX cap 200); `src/wire_handler.h:275`
  (grammar max 240); `clasi/sprints/004-.../sprint.md` Phase A.
- **Dimension:** Part C (structural risk to planned work), rooted in
  dimension-3 constant fragmentation (see MOD-04).
- **Severity:** Major (as a risk to sprint 004; no defect today — today's RX
  is RUN-only and `kRunTextBytes` is 48, so 64 suffices).
- **Rationale:** Sprint 004 Phase A routes radio RX into a second
  `WireHandler`. The plan covers the TX re-entrancy hazard but not RX
  capacity: a legal v6 command line is up to 240 bytes
  (`WireHandler::kMaxLineBytes`), while the radio RX path truncates at 64
  bytes twice (`rxLine_`, `rxLineBuf_`) and `onDatagram()` silently clamps
  (`len > sizeof(rxLine_)` → truncate) — a truncated line handed to `feed()`
  is exactly the "still-parseable prefix the host never sent" case the
  serial path was deliberately widened to 240 to avoid
  (`serial_transport.h:21-31`). The single-slot `rxReady_` drop and
  MORE-fragment drop also mean a v6 host bursting `SET`+`MOVE_X` loses
  commands invisibly — tolerable for idempotent `RUN:`, hostile to a strict
  `#id` sequence (every drop stalls the stream into nack-retransmit).
- **Remedy:** As part of 004 Phase A: size radio RX line buffers off
  `Wire::WireHandler::kMaxLineBytes` (the yotta config already raises the
  packet size to 250, `pxt.json`), and either accept multi-fragment RX or
  document/enforce single-packet command lines; make truncation drop-whole,
  never clamp.
- **Confidence:** High on the facts; Medium on how much of this 004's
  ticketing would have caught anyway.

---

## Minor

### MOD-03 — Dead-code cluster: v5 and superseded-sprint remnants still compiled into every student build

- **File(s)/evidence** (each verified by repo-wide reference search across
  `src/ test/ tests/ tools/`, `.ts/.cpp/.h/.py`):
  - `driveTwistTimed()` — `src/shims.cpp:289-297`. Only caller was the
    deleted v5 binary MOVE handler; `protocol.cpp` now forward-declares only
    `tickDrive` (`protocol.cpp:26`); `wire_adapter.cpp`'s declaration block
    (`:22-70`) does not include it. Referenced only in comments.
  - `wheelSpeed()` — `src/shims.cpp:938-943`. No callers anywhere (its
    consumer was the retired v5 TLM formatter).
  - `cycleStat()` — `src/shims.cpp:558-568` + its TS side `_cycleStat`
    (`src/main.ts:876-884`): `_cycleStat` is a non-exported function nothing
    calls, so the C++ is unreachable from TS and has no C++ caller. The
    comment's own justification is speculative ("future wire-protocol
    reporting").
  - `moving()` — `src/shims.cpp:640`. No `//% shim=diffDrive::moving`
    binding exists (`isMoving()` uses `updateMove`), no C++ caller.
  - `rxFrames_`/`rxAccepted_` — `src/radio_transport.h:141-147`: public
    fields never incremented **and** never read; the comment says they are
    "Read by Protocol::formatDiag()", which was deleted in sprint 003.
  - `maxNudges` — `src/main.ts:546`: "bounded arrival retries" for a
    goToWorld that is deliberately one-pass; never referenced.
  - `MoveState::cmdScale` — `src/motion_engine.h:296`: write-only
    (`motion_engine.cpp:107, 269`); nothing reads it.
  - `OtosPort::present()` — `src/otos_port.h:52`: no callers.
  - `probe()` TS export — `src/main.ts:962-963`: its doc comment says test
    programs sample it per tick; no in-tree `.ts`/`.py` calls it (the
    `RUN:probe` handler in `test.ts:333` is the OTOS probe, unrelated).
- **Dimension:** 3 (required-code / vestigial paths).
- **Severity:** Minor (individually); the cluster is the residue of the v5
  retirement and the tick-model cutover and should go as one ticketed sweep.
- **Remedy:** Delete `driveTwistTimed`, `wheelSpeed`, `moving`,
  `rxFrames_`/`rxAccepted_`, `maxNudges`, `cmdScale`, `present()`; decide
  `cycleStat`'s fate (delete, or actually wire it to sprint 004's FULL
  telemetry columns which cover the same fields — in which case delete the
  TS side); keep `probe()` only if a test program is actually going to use
  it, and fix its comment either way.
- **Confidence:** High.

### MOD-04 — Wire-line capacity is five independently-owned constants (240 / 240 / 200 / 200 / 64) whose "kept equal" claims have already gone stale

- **File(s):** `src/wire_handler.h:275` (240); `src/serial_transport.h:32`
  (240, comment: kept equal to WireHandler's); `src/protocol.cpp:92`
  (`emitLine` truncates at literal `200`; `src/DESIGN.md` §8 admits it
  "predates the 240 raise"); `src/radio_transport.h:126` (`kMaxPayloadBytes
  = 200`, comment claims "Sized the same as SerialTransport's bound" —
  no longer true); `src/radio_transport.h:139` / `src/protocol.h:224` (64).
- **Dimension:** 3 (duplication) / 2-adjacent (constants drift landmine).
- **Severity:** Minor today (every current line fits); becomes load-bearing
  in sprint 004 (see DES-01; the sprint plan itself leans on the 200-byte
  radio cap as a formatting constraint).
- **Remedy:** One source of truth — `Wire::WireHandler::kMaxLineBytes` is
  the protocol's own number; derive the transport and emitLine caps from it
  (a plain `constants` header with no CODAL dependency keeps the layering).
  Where a smaller cap is genuinely intended (radio payload), write the
  derivation and delete the stale "same as" comments.
- **Confidence:** High.

### MOD-05 — Cross-layer protocol constants duplicated with nothing but "must match" comments: the RUN event source (TS vs C++) and the diag ordinal table (C++ ×2 + TS comment)

- **File(s):** `src/main.ts:154` (`RUN_EVENT_SOURCE = 0x2001`) vs
  `src/protocol.cpp:85` (`kRunEventSource = 0x2001`); diag ordinals:
  `src/shims.cpp:679-714` (authoritative switch) vs
  `src/wire_adapter.cpp:132-141` (`kDiag*` re-declarations) vs
  `src/main.ts:957-961` (`probe()`'s index list in prose). Also the switch
  itself has drifted internally: `case 25` is spliced between the comment
  "23/24: rejected implausible encoder reads" and cases 23/24
  (`shims.cpp:709-712`).
- **Dimension:** 3 (duplication).
- **Severity:** Minor
- **Rationale:** PXT gives no way to share a constant between TS and C++,
  but nothing even *pins* these — a re-order of the `diagValue` switch
  breaks `WireAdapter::status()` silently (booleans read from wrong
  ordinals), and an event-source change breaks RUN dispatch with no
  diagnostic. The host harness already compiles `wire_adapter.cpp` against
  a test-double `diagValue` — a pinning test asserting the ordinal meanings
  is cheap.
- **Remedy:** Name the diag ordinals once in a small header
  (`diag_fields.h`, enum) used by `shims.cpp` and `wire_adapter.cpp`; add a
  host test pinning the STATUS-relevant ordinals; leave 0x2001 duplicated
  but pinned by a grep-style test alongside MOD-01's version check.
- **Confidence:** High.

### MOD-06 — The goTo arc reduction exists in three hand-written copies (TS blocks, C++ engine, test program), and the block path bypasses the engine's own implementation

- **File(s):** `src/main.ts:292-307` (`startGoTo`: `theta = 2*atan2`,
  `R = (x²+y²)/(2y)`, `s = R·theta`); `src/motion_engine.cpp:150-172`
  (`goToR`: identical formula, its comment even says "matching this
  project's prior main.ts startGoTo()"); `test/test.ts:127-133`
  (`legToward`: the same radius/theta math a third time);
  `src/main.ts:622-633` (goToWorld's chord variant of the same geometry).
- **Dimension:** 3 (duplication).
- **Severity:** Minor
- **Rationale:** `goToWorld` being a deliberately separate heuristic is
  documented and accepted (`src/DESIGN.md` §9). But `startGoTo` is not the
  heuristic — it is the *plain* reduction, the exact algorithm
  `MotionEngine::goToR()` owns, re-derived in TS because the block path
  routes `startGoTo → startMove → engineMoveX` instead of `engineGoToR`.
  Three hand-maintained copies of sign-sensitive geometry is how this
  project's shipped-four-times cable-order class of bug travels. (The
  straight-line epsilons happen to agree today: 0.01 cm ≡ 0.1 mm.)
- **Remedy:** When the dual-rate question (MOD-07) is settled, route the
  block goTo through `engineGoToR`; give `test.ts`'s `legToward` a shared
  helper or fold it onto `goToWorld`'s planner.
- **Confidence:** High on the duplication; Medium on remedy priority.

### MOD-07 — `startMove()` reverse-engineers MotionEngine's internal reduction to synthesize a `cruise`, duplicating the wheels-x math outside the engine

- **File(s):** `src/shims.cpp:351-412` (computes `distTargetCounts`,
  `yawTargetCounts`, `left/right = dist ∓ yaw`, dominant, cruise — the same
  reduction `motion_engine.cpp:74-100` performs again immediately after).
- **Dimension:** 3 (duplication / information leak: the shim depends on the
  engine's internal normalization to reproduce legacy dual-rate behavior).
- **Severity:** Minor (well-commented, algebraically verified in comments)
- **Rationale:** The block API's two independent ceilings (speed, yawRate)
  are real requirements, but the reconciliation lives on the wrong side of
  the boundary: `shims.cpp` must know that `moveX` commands
  `distTarget/dominant × cruise` for its algebra to hold — an invariant of
  `motion_engine.cpp` that nothing pins. A change to the engine's
  normalization silently changes block-move speeds.
- **Remedy:** Give MotionEngine a `moveXDualRate(distance, rotation, speed,
  yawRate, timeout)` that owns the derivation next to the math it depends
  on; the shim becomes a unit-converting forward like every other bridge.
- **Confidence:** High.

### MOD-08 — Public mutable diagnostics fields punch information-hiding holes in the ports

- **File(s):** `src/nezha_port.h:102-107` — a `public:` island mid-private
  section exposing `maxDrivenStreak_`/`glitchCount_` as writable fields
  (read by `shims.cpp:707, 711-712`); `src/radio_transport.h:141-147` —
  same pattern (`rxFrames_`/`rxAccepted_`, now dead per MOD-03).
- **Dimension:** 3 (public surface wider than needed).
- **Severity:** Minor
- **Rationale:** Trailing-underscore names announce "private" while the
  access specifier says otherwise; any caller can zero a wedge-evidence
  counter. The kernel's own `Output` snapshot shows the right pattern for
  diagnostics readout.
- **Remedy:** `uint32_t maxDrivenStreak() const` accessors; delete the
  radio pair outright (MOD-03).
- **Confidence:** High.

### MOD-09 — Stale-architecture comments (and one public-facing description) still describe the deleted v5 stack and the pre-tick-model fiber

- **File(s)/claims, each contradicting the current design docs:**
  - `pxt.json:4` — extension description shown in MakeCode: "The wheel
    controller runs in its own fiber." False since sprint 002 (tick model,
    `design.md` Execution model). Public-facing.
  - `src/main.ts:8-9` — same claim in the file header.
  - `src/serial_transport.h:2` ("Protocol v5 wire link"), `:8-12`
    (COBS/binary-verb rationale), `:36-50` (a full doc block for the deleted
    `readLine()` sitting above `begin()`); `serial_transport.cpp:18-19,
    60` ("binary v5 frame", "mirrors readLine()").
  - `src/radio_transport.h:54-57` says "channel 0" while `kChannel = 4`
    (`:115`) — internally contradictory; `:124` "(TLM/DEVICE)" and `:144`
    "Protocol::formatDiag()" reference deleted machinery.
  - `src/wire_adapter.cpp:1-4` — "why five motion verbs answer kUnknown":
    all six have real effect (the header it defers to says so).
  - `src/otos_port.h:17-19` — "NOT ported (yet): sensorToCentre/
    centreToSensor" while the same file declares both (`:121-126`) and
    `setOffset()` applies them.
  - `src/shims.cpp:675-677` — "protocol.cpp is the only caller" of
    `diagValue()` (WireAdapter::status() and `probe()` also call it);
    `shims.cpp:77-79` — orphaned sentence fragment atop `Rig` ("Excludes
    the first one or two pivots…" with no referent).
- **Dimension:** design-vs-implementation (each is a false architecture
  claim; the code side is right, the text side wrong). The fuller
  delete/rewrite list belongs to the comment-hygiene reviewer — these are
  flagged here because each misstates structure, not style.
- **Severity:** Minor (pxt.json's description is the one with user reach —
  fix that first).
- **Remedy:** One sweep ticket; new pxt.json description text.
- **Confidence:** High.

### API-07 — A wire host cannot observe motion completion; the only signal is the velocity-derived `active` bit in STATUS

- **File(s):** `src/wire_adapter.h:295-321` (`lastDone()`/`lastDoneReason()`
  permanently 0/none — documented decision); `src/wire_adapter.cpp:229-234`
  (`active` ≈ nonzero measured velocity).
- **Dimension:** 4 (wire use-case walk: "are replies observable?" — acks
  yes, completion no).
- **Severity:** Minor (deliberate, documented in `src/DESIGN.md` §10 and the
  header; not re-litigated here — recorded because the wire walk this review
  was asked to do hits it immediately: a host sequencing MOVE_X → MOVE_X has
  to poll STATUS and infer completion from velocity, which the settle/taper
  phase makes ambiguous). The bench tools' reliance on `RUN:` + `emitLine`
  result lines instead of the motion verbs is partly this gap's shadow.
- **Remedy:** When revisited (the header already marks it a candidate):
  thread `DoneReason` through one bridge function; sprint 004's telemetry
  `flags`/`seq` columns may serve as the poor-man's completion channel in
  the interim — worth stating in that sprint's docs if so.
- **Confidence:** High.

### API-08 — The wire GET/SET namespace has no geometry fields: a bench host can calibrate nothing it can persist

- **File(s):** `src/wire_adapter.cpp:88-104` (`kFields` — 15 kernel-config
  names, no `track_width`/`travel_calib`/`rotational_slip`).
- **Dimension:** 4 (missing operation, host use case).
- **Severity:** Minor
- **Rationale:** The calibration tools (`otos_levercal.py`,
  `reposition.py`, `truth_check.py`) exist to *measure* geometry, yet the
  wire can neither read back nor set any geometry value — calibration
  results can only be applied by editing source (`motion_engine.h`
  defaults) or via blocks (two of the three values; see API-06 for the
  third). GET's read-back purpose ("a config read-back can never report a
  derived number", `design.md`) argues for exposing `track_width`,
  `travel_calib`, `rotational_slip`, and read-only `effective_track_width`.
- **Remedy:** Extend `kFields` with the geometry ordinals (new
  `setKernelValue`/`getConfigValue` cases routing to the engine setters).
- **Confidence:** High.

### API-09 — Palette organization and unit conventions: wire-trigger and tick blocks live in "Move"; Setup mixes cm with mm/deg; two indexed escape hatches are the de-facto diagnostics API

- **File(s):** `src/main.ts:137-138` (`driveTick` → group "Move" though its
  contract pairs with the Drive group); `:186-209` (`onRun`/`onRunCommand` —
  wire triggers — also group "Move"); `:710` (`set wheel calibration
  %calib mm/deg` amid an otherwise all-cm student surface — spec §4.1
  declares cm/deg as *the* student units); `otosGet(what)`/`probe(what)`
  magic indices as the only diagnostics readback (`main.ts:985-991,
  957-963`).
- **Dimension:** 4 (consistency/discoverability).
- **Severity:** Minor
- **Rationale:** A student browsing "Move" finds two blocks (`on run …`)
  that only fire when a bench host sends wire commands, and does not find
  `drive tick` where the Drive blocks that need it live. mm/deg is the
  natural unit for wheel calibration, but it is the lone non-cm student
  input and the block caption is the only warning.
- **Remedy:** A "Remote"/"Advanced" group for the RUN blocks; move
  `driveTick` to Drive (or show it in both); keep mm/deg but say so in the
  block's tooltip prominently; leave `otosGet`/`probe` unexported-to-palette
  as they are (correct) but consider named wrappers if student programs
  start needing them.
- **Confidence:** High on facts; Medium on the grouping call (taste-adjacent,
  kept Minor).

### DES-02 — The authoritative block reference and use-case set lag the shipped palette: the World group, `driveTick`, and the RUN blocks have no §4 entries and no use cases

- **File(s):** `docs/design/specification.md` §4 preamble (self-declares the
  gap); `docs/design/usecases.md` (UC-001..016 — none covers
  startWorldTracking/seedPose/readWorld/worldX/Y/Heading/goToWorld/
  setArrivalTolerance/calibrateWorldSensor/setWorldSensorOffset, `driveTick`,
  or `onRun`/`onRunCommand`); shipped blocks: `src/main.ts:434-634, 129-209`.
- **Dimension:** design-vs-implementation — the document side is wrong
  (behind), per the charter's "every divergence names which side."
- **Severity:** Minor (honestly self-flagged in §4; but the charter's Phase 0
  makes closing it this review round's work, and Part B above had to walk
  the World group against *no* use case — UC coverage for goToWorld's
  one-pass semantics would have caught API-01's documentation cousin
  earlier).
- **Remedy:** Spec §4 tables for World/tick/RUN groups; UC-017..UC-019
  (drive to a world point; seed from external fix; bench-trigger a named
  test) — the sprint-004 SUC set overlaps but is wire-facing, not
  block-facing.
- **Confidence:** High.

### DES-03 — Sprint 004's two-handlers-one-adapter plan meets adapter state that is implicitly single-session: the TLM subscription is global

- **File(s):** `src/wire_adapter.h:334` (`mode_` — one per adapter);
  `clasi/sprints/004-.../sprint.md` Phase A/B (`telemetryEnabled()`
  projected off the shared adapter's `mode_`).
- **Dimension:** Part C (structural risk to planned work).
- **Severity:** Minor
- **Rationale:** The plan is right that per-handler `expectedNext_` isolates
  sequence state, but `TLM` lands on the shared adapter: a serial host
  sending `TLM OFF` silences the radio host's stream and vice versa; the
  boot-default `kOff` + "the radio host subscribes itself" flow works only
  until a second host attaches. Same class of question for
  `motionObligation` (shared — probably correct: the robot ticks for
  whichever host commanded motion) and `setIdentity` (fine). Worth one
  explicit decision line in 004's tickets: is TLM mode per-transport or
  robot-global?
- **Remedy:** Decide and document; if per-transport, `mode_` moves to the
  handler or to a per-sink wrapper.
- **Confidence:** Medium (the plan may already intend robot-global).

### DES-04 — The shims.cpp forward-declaration seam is scaling past its safety margin: 15+ conventions-only signatures across four files, and return-type drift is invisible to the linker

- **File(s):** `src/wire_adapter.cpp:22-70` (12 declarations),
  `src/protocol.cpp:26` (+1), `src/shims.cpp:996, 1009` (2 in the reverse
  direction), `tests/host/wire_motion_verb_shim.cpp:182ff` (the whole set
  mirrored again as test doubles); sprint 004 adds `buildSnapshot()`s
  sources through the same seam.
- **Dimension:** 3 (hidden coupling by convention) / Part C.
- **Severity:** Minor
- **Rationale:** The seam itself is good design (it is what makes
  `wire_adapter.cpp` host-testable), and parameter-type drift *is* caught by
  C++ name mangling at link time. But return types are not mangled for
  ordinary functions: changing `int wheelSpeed(int)` to `float` in one file
  links cleanly and reads garbage — a real, silent class of drift across
  four files that must stay synchronized by hand, growing every sprint.
- **Remedy:** One declarations-only header (`shims_api.h`: pure prototypes,
  `<cstdint>` only, no pxt.h) included by `shims.cpp`, both consumers, and
  the test shim. Decoupling is preserved (it is declarations, not a Rig
  reference); the compiler now enforces the "must stay
  signature-compatible" comments.
- **Confidence:** High.

### DES-05 — Subsystem responsibilities: seven of eight pass the single-sentence test; `shims.cpp` is the C++ twin of the filed main.ts monolith, and the odometry seam under it keeps accumulating consumers

- **File(s):** `src/shims.cpp` (composition root + odometry + tick engine +
  settle loop + watchdog + OTOS surface + three families of wire bridges —
  §9 of `src/DESIGN.md` needs five bullets to describe one file);
  cross-refs: `clasi/issues/break-up-main-ts-into-modules.md` (TS side),
  `clasi/issues/settle-tick-loop-is-not-host-testable.md` (the odometry
  seam's existing cost).
- **Dimension:** Part C.
- **Severity:** Minor (structural observation feeding existing issues, not a
  new defect).
- **Rationale/assessment:** Kernel, motion engine, wire grammar, wire
  adapter, transports, protocol composition, and the host harness each state
  their responsibility in one sentence and honor it — the sprint-003
  extraction genuinely worked, and the include graph matches the layer table
  exactly (verified; see "Not findings"). The two grab-bags are the two
  shim files. Input to the main.ts issue (invited by the dedup note): the
  issue's proposed split is right; add that **the simulator (`sim.ts`) and
  the RUN dispatcher are the two pieces with zero coupling to the rest** and
  can move first with no behavioral risk, whereas config/motion/pose share
  the `defaultSpeed`/`defaultYawRate` state and should move together. On the
  C++ side, the highest-leverage cut is the one `src/DESIGN.md` §9 already
  gestures at: move odometry (and with it the settle loop) into
  MotionEngine *before* sprint 004 bakes in three more odometry consumers
  via `buildSnapshot()` — afterwards the same extraction costs three more
  call-site migrations and re-tests a telemetry surface.
- **Remedy:** Sequence the odometry extraction ahead of (or inside) sprint
  004; treat watchdog+tick engine+Rig as a `rig.cpp` unit leaving `shims.cpp`
  as pure `//%` bindings when it is next opened.
- **Confidence:** Medium (sequencing judgment).

---

## Suggestion

### MOD-10 — `PoseSource` lives in `motion_engine.h`, so the hardware port layer includes the whole MotionEngine (and transitively the kernel) to implement a three-method interface

- **File(s):** `src/motion_engine.h:133-140`; `src/otos_port.h:38`.
- **Dimension:** 3 (layering nuance — within the letter of the DESIGN table,
  since PoseSource is "a port interface it implements", but the include
  drags the full engine declaration into a leaf that needs none of it).
- **Severity:** Suggestion
- **Remedy:** `pose_source.h` (12 lines, `<cstdint>`-free), included by both.
- **Confidence:** High.

---

## Correctness suspicions handed to other reviewers (one line each)

- `src/main.ts:233` — `runArgCount()` reads `runParts.length` with no
  `!runParts` guard (its siblings have one): crashes if called outside a RUN
  handler before any RUN arrived.
- `src/shims.cpp:678` vs `:696-697` — `diagValue` doc says "floats are
  scaled ×100" but cases 14/15 return raw counts/s; any consumer honoring
  the comment mis-scales velocities.
- `src/main.ts:786-787` — `simIntegrate` deducts the **full** step's
  `|dMm|`/`|dRad|` from the move remainders while crediting only the
  frac-clipped pose; remainder bookkeeping and pose can disagree on the
  terminal step.
- `src/protocol.cpp:92` — `emitLine` silently truncates at 200 bytes; no
  caller can detect it (feeds sprint 004's frame-width constraint).
- API-01 above doubles as a correctness scenario (UC-002's documented main
  flow does not drive the robot) — flagged here so the correctness reviewer
  owns the verdict on which side (code vs. doc) to fix.

## Not findings — checked and cleared

- **Layering:** the full include graph of `src/` was enumerated and matches
  `src/DESIGN.md` §1's table exactly — kernel is libc-only; motion engine
  sees only the kernel; wire grammar has no project includes; wire adapter
  sees only the grammar; transports/ports keep `pxt.h` out of their
  headers; no upward reference from any lower layer. No violations in
  either direction (MOD-10 is a nuance, not a breach).
- **tests/host:** no copied scaffolds — every suite imports
  `compile_shared_lib` from `test_kernel_harness.py` or reuses fixtures via
  import; the test-double math mirror in `wire_motion_verb_shim.cpp` is a
  documented, deliberately-pinned seam.
- **Kernel surface** (`start()`/`run()`, `rebasePosition()`): unused here
  but vendored byte-stable — correctly kept (only `clearStallLatch`'s
  *unreachability from any surface* is a finding, API-02).
- **`tour_square.py` / `tour_closedloop.py`:** kept-for-reference status is
  documented in `tools/DESIGN.md`; not dead code.
- **Six tools parsing the retired `TLM:` line:** covered by sprint 005's
  `tools/tlm.py` plan — cross-referenced, not re-reported (per dedup list).
- **`TLM` verb acking modes that emit nothing yet:** sprint 004 planned
  work, not a finding.
- **`emitTelemetry()` being keepalive-only, GO_TO_W refusing without an
  OTOS, the settle loop's host-testability, main.ts's monolithism, testrig
  type-checking, the unpowered-brick boot wedge:** all filed issues or
  planned sprints — cross-referenced where adjacent (API-04, DES-05), not
  re-reported.
- **Wire reliability design** (strict ids, decode-failure-is-a-NAK, no
  duplicate-id code, HELLO resync): coherent and well-tested; the
  cruise-sentinel *mechanism* (<0 refuse / 0 substitute / unconfigured
  refuse) is also sound — only the substituted value is contested (API-03).
- **RadioTransport member scratch buffers, RUN dedupe ring, NUL
  characterization:** deliberate, measured, documented.
- **`microphone` dependency in `pxt.json`:** assumed deliberate (micro:bit
  V2 gating alongside `disablesVariants: ["mbdal"]`); listed in spec §2.
  No rationale is recorded anywhere — worth one sentence in the spec, not a
  finding.
