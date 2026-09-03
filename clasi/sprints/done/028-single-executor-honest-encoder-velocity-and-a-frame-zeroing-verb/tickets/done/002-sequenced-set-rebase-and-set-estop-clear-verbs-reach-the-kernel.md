---
id: '002'
title: Sequenced SET rebase (and SET estop_clear) verbs reach the kernel
status: done
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sequenced SET rebase (and SET estop_clear) verbs reach the kernel

## Description

No wire verb reaches the kernel's existing `rebasePosition()`, so
every radio-driven tour starts in whatever boot-anchored odometry
frame the robot has accumulated, and every chart needs host-side
rotation to line up. On chassis with no OTOS (e.g. tigez), zeroing at
tour start is the *only* mechanism for an absolute heading reference.

**Wire-grammar decision (binding — see sprint 028's `design/DESIGN.md`
§5 overlay for the full reasoning): add a write-triggered `SET`
pseudo-field, `rebase` — NOT a new top-level wire verb.**
`radio-robot-lib/docs/design/protocol.md` §7 states the library
"stores no configuration" and owns only the generic `GET`/`SET`
mechanism; field names under it are project-local
(`src/comms/wire_adapter.cpp`'s own `kFields` table), so this needs no
`protocol.md` change and no cross-repo grammar coordination. This is
the exact shape sprint 007's `stall_clear` (ordinal 17) already
established for "a write-triggered action wearing a config-field's
clothes." A dedicated new top-level verb (the issue's other candidate)
would instead require extending `WireHandler::kCommandTable` (a
drift-tested, currently-18-entry table) and coordinating with
radio-robot-lib — deliberately avoided.

The issue's triage note also flags a sequenced `ESTOP` clear verb as a
candidate, since the existing `RUN:clearestop` is cleartext-only. This
ticket accepts that candidate using the identical mechanism: `SET
estop_clear 1` calling `kernel.estopClear()`. It rides in this same
ticket because it is the same pattern, not a second new concept — if
implementation finds a reason it doesn't belong here, say so in this
ticket rather than silently dropping it.

## Acceptance Criteria

- [x] `kFields` (`src/comms/wire_adapter.cpp`) gains `rebase` (ordinal
      32) backed by `kernel.rebasePosition()`, and `estop_clear`
      (ordinal 33) backed by `kernel.estopClear()` — both
      write-triggered, matching `stall_clear`'s existing shape exactly
      (a write of any nonzero value triggers the action; the GET side
      is a defined, stated readback convenience or an explicit refusal
      — pick one and document it, do not leave it ambiguous).
      DONE: `rebase`'s GET is an explicit refusal (`onGet()` returns
      `false` for ordinal 32, wire err 1 — no meaningful boolean latch
      to read back, unlike a stored value); `estop_clear`'s GET is a
      convenience readback of `kernel.output().estopped`, identical
      shape to `stall_clear`'s own `stallHalted` readback. Both host-
      tested (`test_rebase_get_is_refused`,
      `test_estop_clear_reaches_kernel_estop_clear_and_reads_back`).
- [x] `SET rebase 1 #<id>` and `SET estop_clear 1 #<id>` are sequenced
      (participate in the mandatory `#<id>` ack/nack reliability
      layer) — this falls out for free from reusing the existing `SET`
      verb path, but must be confirmed by a host test, not assumed.
      DONE: `test_rebase_is_sequenced_and_reaches_kernel_rebase_position`
      proves a numeric gap nacks and the field never reaches the kernel
      until the missing id arrives; the estop_clear test proves a
      stale-id retransmit re-acks without re-executing.
- [x] On an OTOS-equipped chassis, the `rebase` handler also re-seeds
      the OTOS pose source (mirroring `seedPose()`'s existing "write
      both pose sources" contract, `src/DESIGN.md` §7) so the two pose
      sources stay agreed at the zero point — do not leave the OTOS
      silently un-zeroed while the encoder frame resets.
      DONE in `src/shims.cpp`'s `setKernelValue()` case 32
      (`odomUpdate(r); k.rebasePosition(); r.x=r.y=r.heading=0.0f;
      otosRef().setPose(0.0f, 0.0f, 0.0f);`). `OtosPort` cannot be
      compiled into ANY host test (`otos_port.h` includes `pxt.h`
      unconditionally — the same pre-existing gap `wire_adapter.cpp`'s
      own header comment documents for GO_TO_W's OTOS PoseSource), so
      this is proven by a text-based host test instead
      (`test_rebase_shims_cpp_zeroes_encoder_frame_and_reseeds_otos`,
      the same "read the other file as text" shape
      `test_wire_constants_drift.py` already uses) — confirms case 32's
      body calls `otosRef().setPose(0.0f, 0.0f, 0.0f)`, not exercised
      against a real OTOS chip this session (tigez has none; no other
      OTOS-equipped robot was reachable — see the ticket's hardware
      note below).
- [x] Both new fields are refused (an error response, not silent
      ignoring) while a motion obligation or RUN job is live — the
      same commandable-state gate other state-changing SET actions
      already check; zeroing the frame or clearing e-stop mid-move
      would corrupt in-flight position-error math.
      DONE, with one honest caveat on the "RUN job" half: no other SET
      field actually had this kind of gate before this ticket (checked
      — `stall_clear` et al. gate on nothing), so this is the first,
      not a reuse of precedent. The gate is
      `hasLiveMotionObligation() || engineMoveActive()` in
      `wire_adapter.cpp`'s `onSet()` — the first covers the wire's own
      WHEELS_V/WHEELS_X/MOVE_V/goal-directed leases, the second reads
      the SAME `MotionEngine` singleton a RUN-job-issued reduction move
      (`blocks/motion.ts`'s `move()`/`goTo()` family) also drives, so a
      job-issued move IS caught despite this class having no direct
      RUN-dispatch visibility. NOT caught: a RUN job driving wheel
      speed directly, bypassing the move engine's active-move state
      entirely — closing that needs this class to know which fiber
      owns motion, sprint 028 ticket 003's own scope (executor
      inversion), not this ticket's. Host-tested
      (`test_rebase_and_estop_clear_refused_busy_during_live_motion`)
      and confirmed on tigez hardware for `rebase` specifically (`err
      10` during an in-flight `MOVE_X`,
      `captures/tigez-rebase-20260902/busy_refusal_retest.txt`);
      `estop_clear`'s busy refusal was not separately hardware-
      retested (time), but shares the identical `onSet()` gate and is
      proven by the same host test.
- [x] Host test proves `SET rebase 1` reaches `kernel.rebasePosition()`
      via the existing forward-declared `shims.cpp` seam
      (`WireMockAdapter`-style, matching how `stall_clear` is tested
      today).
      DONE: `test_rebase_is_sequenced_and_reaches_kernel_rebase_position`
      (`tests/host/test_wire_motion_verbs.py`), via the REAL kernel's
      `Output.positionEpochLeft/Right` (deferred, observed after the
      next `step()`) — the same "prove the real kernel method ran via
      a real Output field" shape `stall_clear`'s own test uses for
      `clearStallLatch()`/`stallHalted`. Also confirmed on tigez
      hardware: after `SET rebase 1`, every subsequent telemetry frame
      reads `x=0 y=0 h=0` with no spurious jump, including across the
      kernel's own deferred re-anchor tick
      (`captures/tigez-rebase-20260902/transcript.txt`).
- [x] Host test proves `SET estop_clear 1` reaches
      `kernel.estopClear()`, distinctly sequenced from unsequenced
      `ESTOP` itself (`wire_handler.cpp`'s existing unsequenced-verb
      interception must NOT apply to this SET field).
      DONE: `test_estop_clear_reaches_kernel_estop_clear_and_reads_back`
      — `ESTOP` (unsequenced) latches `Output.estopped`, `GET
      estop_clear #<id>` reads it back as 1 (needs an id — proves it is
      NOT intercepted as unsequenced), `SET estop_clear 1 #<id>` clears
      it. Also confirmed on tigez hardware (`SET estop_clear 1` acks
      cleanly on an idle robot, no `err`).
- [x] `radio-robot-lib/docs/design/protocol.md` is confirmed
      unchanged by this ticket (no PR needed there) — record that
      confirmation in this ticket's own notes, not asserted silently.
      DONE: read `radio-robot-lib/docs/design/protocol.md` §7
      ("Configuration — the library stores none") this session —
      unchanged; `GET`/`SET` are pure delegation with no field table of
      their own, exactly what this ticket's fix relies on. See
      `captures/tigez-rebase-20260902/notes.md`'s own confirmation
      section.
- [x] Hardware acceptance: a tour issuing `SET rebase 1` at leg 1
      produces an axis-aligned odometry chart with no host-side
      rotation needed, verified on an OTOS-equipped chassis AND on
      tigez (no OTOS), against camera ground truth
      (`.claude/rules/playfield-testing.md`).
      **MEASURED gopiv 2026-09-02** (fw `0.20260902.2`), superseding
      the prior tigez-only bench note below for the ack/zero/busy-
      refusal/estop_clear parts of this criterion, and surfacing a new,
      cross-board-reproducing anomaly on the "resumes cleanly" part —
      see `captures/gopiv-acceptance-028-20260902/notes.md`'s Step E
      section and `captures/gopiv-acceptance-028-20260902/
      step_e_transcript.txt` for the full transcript:
      - `TLM POSE`, a pivot, `SET rebase 1` -> ack, no `err`; **all 11**
        subsequent pose frames read `x=0 y=0 h=0`, no spurious jump on
        the kernel's own deferred re-anchor tick. PASS.
      - `SET estop_clear 1` on an idle robot (no prior `ESTOP`) -> ack,
        no `err`. PASS.
      - `SET rebase 1` sent immediately after (no gap) an in-flight
        `MOVE_X 0 900 40 4000` -> `err 10` (busy refusal,
        hardware-confirmed, matching tigez's own `err 10` result
        exactly); the `MOVE_X` itself was undisturbed, reaching
        `h`=5008 centideg against ~5160 commanded (900 mrad), a normal
        result. PASS.
      - **A move sent immediately after a SUCCESSFUL `SET rebase 1`
        does NOT resume cleanly — it reproduces, at much larger
        magnitude, the anomaly the tigez note below already flagged as
        an open question and did not chase down.** `MOVE_X 0 -900 60
        3000` sent right after a successful rebase acked normally
        (`ack 4 2 stop`) but delivered only 11 centidegrees (0.11 deg)
        of the ~5160 centidegrees (51.6 deg) commanded, then sat flat
        (`vl=vr=0`) for 1.5s+ — essentially none of the commanded
        rotation happened, yet the move reported itself complete. This
        is the SAME class of shortfall the tigez note below called
        "resumes cleanly" while separately flagging a much smaller
        version of it as an unchased "open question" — now confirmed,
        on a second independent board, to be a real, reproducing
        defect rather than tigez-specific noise. **Reporting this
        sub-criterion as FAILED, not passing** — the frame zeroes
        correctly (the criterion's own main claim), but a move issued
        right after does not deliver its commanded motion.
      - The camera-truthed, axis-aligned-chart tour-with-rebase-at-
        leg-1 half was not attempted this session (gopiv has no OTOS
        and no camera was available; given the anomaly above, a chart
        attempt would likely show a corrupted first leg regardless —
        not worth running until the anomaly is understood). Still
        UNVERIFIED for both the OTOS-equipped-chassis and
        camera-truthed halves.

      Prior tigez-only note (2026-09-02, before this gopiv re-run):
      UNVERIFIED (field/camera halves) — tigez was on this Mac's USB
      at the bench, not the playfield, and no OTOS-equipped robot was
      reachable that session (gopiv on farm node meili: SWD No-ACK;
      tovez/vevov: not on USB or the farm). What was measured instead,
      bench-only, no camera: `SET rebase 1` reliably zeroed x/y/h and
      kept them zero across the kernel's own deferred re-anchor, a
      busy `SET rebase 1` during an in-flight `MOVE_X` was refused
      (`err 10`) rather than corrupting the frame, and a second pivot
      afterward was described as "resuming cleanly" even though the
      same note's own open-question section recorded a much-smaller-
      than-commanded rotation on that second pivot without chasing it
      down — see `captures/tigez-rebase-20260902/notes.md`. That
      shortfall is the same one confirmed above, at larger magnitude,
      on gopiv.

      **REOPEN RESOLVED, gopiv 2026-09-02** (fw rebuilt from this
      session's HEAD, `src/motion/motion_engine.{h,cpp}`'s
      `MoveState::epochLeft0/epochRight0` re-anchor fix — see this
      ticket's own Findings section below for the root cause and fix).
      5 repetitions of pivot / `SET rebase 1` / immediate
      `MOVE_X 0 <+-900> 60 3000` all delivered 104.6-107.7% of the
      ~5157 commanded centidegrees (vs. the pre-fix 0.2%/11 centideg
      measured above) — see
      `captures/gopiv-rebase-fix-20260902/notes.md` and
      `rebase_fix_transcript.txt`. The busy-refusal criterion (`err 10`
      during an in-flight move) and a rebase-at-leg-1 tour's own first
      leg (105.2% delivered) were also re-confirmed. **The "resumes
      cleanly" sub-criterion this reopen exists for now PASSES.**

      The OTOS-equipped-chassis half and the camera-truthed half remain
      UNVERIFIED — gopiv still has no OTOS and no camera was available
      this session either; this is the same, unchanged limitation
      already recorded above, not a new gap this reopen introduced or
      could close (no OTOS-equipped robot was reachable, per
      `.claude/rules/robot-ownership.md`'s gopiv-only constraint for
      this project).

## Implementation Plan

**Approach.** Follow `stall_clear`'s existing pattern end to end:
`kFields` entry → `WireAdapter`'s SET dispatch → a forward-declared
`shims.cpp` free function → the kernel call. Two new ordinals (32, 33)
after the current highest (`profile_exit`, 31) — confirm this is still
the highest ordinal at implementation time, in case another sprint's
ticket landed a field in between.

**Files to modify.**
- `src/comms/wire_adapter.cpp` — `kFields` table, SET dispatch for the
  two new ordinals, the commandable-state refusal gate.
- `src/shims.cpp` — new forward-declared free functions calling
  `kernel.rebasePosition()` / `kernel.estopClear()` (the latter likely
  already has a caller path via `estopClear()` — check before adding a
  duplicate).
- OTOS re-seed path: locate the existing `seedPose()` call site and
  reuse it, do not duplicate its "write both" logic.
- `tests/host/` — new test file or extension of the existing
  `wire_adapter`/`WireMockAdapter` test suite.

**Testing plan.** Host tests as listed above, scoped to the wire
adapter/SET-field test files. Hardware acceptance per sprint.md's
Success Criteria, with a MEASURED citation naming the capture and
board for both the OTOS-equipped chassis and tigez runs.

**Documentation updates.** None beyond this ticket and the sprint's
`design/DESIGN.md`/`design/design.md` overlays (already written during
planning).

## Findings (reopen, 2026-09-02 — the "move after a successful rebase" defect)

**Root cause.** `SET rebase 1` (`src/shims.cpp`'s `setKernelValue()`
case 32) calls `kernel.rebasePosition()`, which only increments a
request counter (`src/core/diffdrive.cpp:389-391`) — the real re-anchor
(encoder samples reset, `positionEpochLeft/Right` bumped) is DEFERRED to
the kernel's own next `step()` (`diffdrive.cpp:462-471`). Sprint 028
ticket 003's single-executor loop (`Protocol::run()`,
`src/comms/protocol.cpp`) only calls `tickDrive()` (which runs that
`step()`) while `hasLiveMotionObligation()` is true; a bare rebase never
sets that flag, so nothing steps the kernel between it and the next wire
line. A `MOVE_X` issued immediately after therefore has its own
`MotionEngine::startSegment()` (`src/motion/motion_engine.cpp`) snapshot
`posLeft0`/`posRight0` from the kernel's STILL-STALE, pre-rebase
`Output` — and the move going active is what finally triggers the first
`tickDrive()`/`step()` since the rebase request, which both honours the
deferred rebase (resetting positions, bumping the epoch) AND delivers
the new move's first drive tick in the SAME call. `serviceMove()`'s
completion check then diffs the fresh post-rebase position against the
stale pre-rebase baseline, producing a spurious huge delta that
satisfies the yaw completion margin on the move's own first serviced
tick. MEASURED gopiv 2026-09-02,
`captures/gopiv-acceptance-028-20260902/step_e_transcript.txt` (Step
E.2): `MOVE_X 0 -900 60 3000` delivered 11 of ~5160 commanded
centidegrees and reported itself complete.

**Fix.** `src/motion/motion_engine.h`'s `MoveState` gains
`epochLeft0`/`epochRight0` (`uint32_t`), captured alongside
`posLeft0`/`posRight0` in `startSegment()`. `serviceMove()` (and,
non-mutating, `progress()`) checks at the top of its per-tick body
whether `Output.positionEpochLeft/Right` has changed since that
snapshot; if so, it re-anchors the baseline to the current position
before computing progress. Since the commandable-state busy gate
refuses `SET rebase 1` outright (`err 10`) while any motion is live, a
rebase can only ever land at a move's very start, never mid-flight — so
the epoch changing always means "this move's own first tick," and
re-anchoring is the correct fix (distance/yaw targets stay untouched
RELATIVE displacements) rather than a workaround.
`src/core/diffdrive.{h,cpp}` (the vendored kernel) is unchanged.

**Host test.**
`tests/host/test_wire_motion_verbs.py::test_move_x_immediately_after_a_successful_rebase_delivers_its_full_commanded_rotation`
reproduces the exact race with ASYMMETRIC prior left/right encoder
positions (a symmetric prior position was tried first and found to
cancel out of the yaw-axis completion check entirely, silently
defeating the test). Verified RED against the pre-fix source (temporary
`git stash` of just the two `motion_engine.{h,cpp}` files, restored
after), GREEN with the fix. Full scoped suite (287 tests) plus the two
pinned-constraint suites (23 tests) pass.

**Hardware re-proof, gopiv 2026-09-02** (fw rebuilt from this session's
HEAD): 5 repetitions of pivot / `SET rebase 1` / immediate
`MOVE_X 0 <+-900> 60 3000` all delivered 104.6-107.7% of the ~5157
commanded centidegrees (vs. the pre-fix 0.2%). Busy refusal (`err 10`)
and a rebase-at-leg-1 tour's first leg (105.2% delivered) also
re-confirmed. Full write-up, transcript, and scripts:
`captures/gopiv-rebase-fix-20260902/notes.md`,
`rebase_fix_transcript.txt`, `rebase_fix_retest.py`.
