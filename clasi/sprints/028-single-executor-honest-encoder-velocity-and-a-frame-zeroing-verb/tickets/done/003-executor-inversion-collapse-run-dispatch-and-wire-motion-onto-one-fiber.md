---
id: '003'
title: 'Executor inversion: collapse RUN dispatch and wire motion onto one fiber'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: single-executor-for-command-dispatch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Executor inversion: collapse RUN dispatch and wire motion onto one fiber

## Description

Command dispatch still runs on three coexisting fiber models instead
of one deliberate one: wire motion ticks on the protocol fiber,
`RUN:` motion ticks on a MessageBus-forked fiber holding its own
`while (driveTick())` loop, and student blocks tick on the calling
fiber. Only the third is deliberate. The second is where the FPU
yield-hazard actually fires (two fibers doing float work concurrently
— the VFP guard, sprint 026 ticket 001, makes this SAFE, it does not
remove the second fiber), and it is also *why* `RUN:abort` currently
works at all ("by accident," per the issue: the second fiber runs
concurrently with whatever it's aborting).

**This ticket implements sprint 026's own already-specified design for
this exact item (that sprint's SUC-003), deferred there and not
re-derived here.** Read `clasi/sprints/done/026-fiber-safety-and-
command-dispatch/sprint.md`'s Architecture section (Design Rationale
subsections in particular) before starting — the "invert the pump, do
not make the executor drive the tour" decision, the `motionOwner_`
placement decision, and the `RUN:abort`/`RUN:clearestop`
bypass-the-queue decision are all already reasoned through there; this
ticket's job is to implement that design against the CURRENT tree
(sprint 026 tickets 001-002 and sprint 027's `EmitQueue` are merged;
verify `Protocol::run()`'s current shape against
`src/comms/protocol.cpp` before assuming the 026 sprint.md's code
excerpts are still byte-accurate — they described the PRE-implementation
state).

**Prerequisite — do not start this ticket until tickets 001 and 002 in
THIS sprint have merged.** Not a functional dependency (different
files), but this ticket is the highest-risk, hardware-only piece in the
sprint; landing the host-testable work first keeps a ticket-003
hardware failure unambiguous rather than confounded with an
unrelated regression from 001/002.

## Acceptance Criteria

- [x] Exactly one execution model remains for engine-facing motion:
      the protocol fiber. `Protocol` gains a `motionOwner_` field
      (`kNone`/`kWire`/`kJob`).
- [x] A queued RUN job is dequeued and dispatched via a new
      `dispatchJob()` that calls `runAction0()` directly on the
      protocol fiber (via a new `_registerRunDispatch(cb)` seam in
      `run.ts`/`shims.cpp`, replacing `control.onEvent(RUN_EVENT_SOURCE,
      ...)`) — not by raising a MessageBus event for a second fiber.
- [x] A running job's own tick loop (`while (driveTick())`, unchanged
      shape — do NOT turn the tour into a state machine the executor
      steps) advances one iteration per pass via a service hook that
      fires after `stepBusy = false` and before the pacing sleep, and
      NEVER fires inside `stepBusy` (the kernel's own encoder
      select-to-read settle window already yields twice inside
      `step()` — landing the hook there would break bus discipline).
- [x] `RUN:abort`/`RUN:clearestop` bypass the queue and take effect
      immediately regardless of `motionOwner_` — no queue delay.
      Hardware-timed: abort sent 0.3 s into a ~1.29 s pivot cuts it to
      0.34 s (`captures/tigez-executor-20260902/fixed-abort-timing-*.txt`).
- [x] A wire motion request (`MOVE_X`/`GO_TO_*`/etc.) arriving while
      `motionOwner_ == kJob` is refused with an error code, not
      silently overwriting the job's move.
- [x] `hasLiveMotionObligation()` stays wire-only — a RUN job gets no
      obligation tracking (it already has its own tick loop running on
      this fiber; extending obligation tracking to it would make a
      wire motion incorrectly report `kStop` where `kTimeout` is
      correct).
- [x] `RUN_EVENT_SOURCE = 0x2001` and the MessageBus event path it
      named are deleted from both `protocol.cpp` and `run.ts`.
      `test_wire_constants_drift.py`'s pin on that literal is deleted
      with the code it pinned, not left vacuously passing.
- [x] `test_run_abort_source_pin.py` is rewritten: the pin moves from
      "an abort handler exists" to "abort bypasses the queue."
- [x] `tests/system/run_tour.py` (the host-driven `.tour` suite) passes
      unchanged. **MEASURED gopiv 2026-09-02**, bare-motor bench rig
      (wheels off the ground, so a full translating tour is safe there
      — see `.claude/rules/robot-ownership.md`):
      `uv run --with matplotlib python tests/system/run_tour.py
      tests/system/tours/square.tour --host 192.168.1.150 --port 43181
      --robot gopiv` completed all 17 steps cleanly and produced a
      chart (`captures/gopiv-acceptance-028-20260902/run_tour_square/
      square.png`, `.../square.json`). Supersedes the tigez in-place-
      pivot substitution below, which stays in the record as
      corroborating (not superseding) evidence for the other Hardware
      acceptance items.
- [x] `device_stack_size` — currently 4096 per sprint 026's own open
      question about whether this is enough headroom for the
      executor's new call depth (service hook + `runAction0` + a
      student's own RUN handler) — is confirmed sufficient by hardware
      testing below, or revised with a MEASURED citation if not.
      **Correction to this criterion's own premise**: `device_stack_size`
      was NOT actually 4096 in `pxt.json` before this ticket (sprint 026
      planned the bump but it was never landed — verified via `git log
      -p -- pxt.json`, no prior commit ever added it). This ticket adds
      it (`pxt.json`'s `yotta.config.device.stack_size`) and confirms
      4096 is sufficient: 12 back-to-back RUN pivot jobs with no fault,
      each exercising `dispatchJob() -> runAction0() -> test.ts's onRun
      handler -> tickToCompletion() -> driveTick() -> tickDrive() -> the
      service hook -> serviceOnce()`
      (`captures/tigez-executor-20260902/fixed-executor-inversion-*.txt`,
      Step D).
- [x] Hardware acceptance (no host-test substitute exists for this
      ticket — `protocol.cpp`/`shims.cpp` include `pxt.h`):
  - [x] Baseline (current/pre-ticket firmware): **MEASURED gopiv
        2026-09-02**, old firmware `ver 0.20260901.1`, full
        `RUN:square:20` tours (gopiv's bare-motor bench rig makes a
        real translating tour safe, unlike tigez's bench-tethered
        session — no substitution needed here). No reset observed
        across A.1/A.2/A.3. A wire `MOVE_X` sent mid-tour acked with
        no `err` (`ack 1 1 stop`), consistent with the pre-fix
        architecture accepting/racing it rather than refusing it — the
        same qualitative result tigez's own baseline found. `RUN:abort`
        sent mid-tour did NOT produce a near-instant stop: `STATUS`
        stayed `active=1`/`reason=timeout` for several seconds past the
        abort before eventually settling — additional, gopiv-specific
        evidence that "abort works by accident" on the old architecture
        (unreliable/slow, not just eventually-correct).
        `captures/gopiv-acceptance-028-20260902/step_a_transcript.txt`,
        `.../step_a3_retry_transcript.txt`. tigez's own baseline
        (`captures/tigez-executor-20260902/baseline-pre-inversion-
        final-*.txt`) stays in the record as corroborating evidence.
  - [x] Fixed firmware: **MEASURED gopiv 2026-09-02**, `ver
        0.20260902.2`, full `RUN:square:20` tours (not substituted with
        pivots — see above): a wire `MOVE_X` sent mid-tour is
        observably refused (`ack 1 0 none` immediately followed by
        `err 10 #1`), tour undisturbed; `RUN:abort` sent 0.305s into a
        `RUN:pivot:90` cuts `PIVOT:end` from a 1.290s reference down to
        0.343s (~40 ms after the abort landed) — matching tigez's own
        0.3s->0.343s measurement almost exactly; 12 back-to-back
        `RUN:pivot` jobs ran with zero faults, `i2cf`/`cyc` sane,
        `ready=1 connL=1 connR=1` throughout; `TLM POSE` kept flowing
        (53 frames) through a dispatched `RUN:pivot:90` job.
        `captures/gopiv-acceptance-028-20260902/step_c_transcript.txt`.
        tigez's own fixed-firmware pivot battery
        (`captures/tigez-executor-20260902/fixed-executor-inversion-*.txt`,
        `fixed-abort-timing-*.txt`, `fixed-tlm-during-job-*.txt`) stays
        in the record as corroborating evidence.
  - [ ] Whether the radio-traffic wedge and tigez wedge issues (see
        sprint 026's Open Question 1 — largely resolved by sprint 027,
        confirm still true here) hold clean under this restructuring
        too. **Still UNVERIFIED over radio specifically** — this gopiv
        session also tested the farm's TCP serial daemon transport
        only (lossless, wired), not the zavaz/torture radio relay; the
        optional PING-hammer-during-MOVE_X check was not attempted this
        session (time). `EmitQueue` serializes both transports
        identically so there is no new radio-specific code path in
        this ticket's diff, but a literal radio-traffic-during-motion
        retest was not run on either board.
  - [x] A disassembly census (per sprint 026 ticket 001's own
        precedent) is NOT required again here — that was ticket 001's
        acceptance criterion for the VFP guard itself, not this
        ticket's.

## Implementation Plan

**Approach.** Implement sprint 026's own Architecture section verbatim
in shape (re-read it first — do not re-derive). Key structural pieces,
per that record: `Protocol` gains `motionOwner_`; `Protocol::run()`'s
loop gains `dispatchJob()` (dequeue + `runAction0()` call) after
`drainEmitQueue()` and before the wire/radio poll (confirm exact
placement against the CURRENT loop body — it now includes 027's
`drainEmitQueue()` call, which sprint 026's own sprint.md predates); a
service hook on `tickDrive()`/`Rig` (kept out of `shims.cpp`'s own
surface per sprint 026's Design Rationale, so no new CODAL surface
leaks there) lets a running job's tick loop advance on this fiber.

**Files to modify** (per sprint 026's own Architecture Overview,
re-verify each against current source before assuming no drift):
`src/comms/protocol.{h,cpp}`, `src/blocks/run.ts`, `src/shims.cpp`
(new `_registerRunDispatch` seam), possibly `src/platform/
platform_ports.h`/`Rig` (the service hook's exact home — sprint 026's
Design Rationale says "kept out of shims.cpp deliberately," confirm
where it actually lands).

**Testing plan.** No host-test substitute exists for the core
restructuring (both `protocol.cpp` and the TS dispatch path require
CODAL/`pxt.h` or PXT runtime). `test_wire_constants_drift.py` and
`test_run_abort_source_pin.py` are host-testable and must be
updated/rewritten as part of this ticket regardless. Hardware
acceptance per the Acceptance Criteria above and sprint.md's own
Success Criteria — budget 2-3 bench sessions per the issue's own
estimate; use a reliably-reachable board (sprint 026 ended with
magni's USB port dropping repeatedly — avoid that host if still
unreliable).

**Documentation updates.** The sprint's `design/DESIGN.md` overlay
already documents the target shape (§8's "Sprint 028: one execution
model, not three" and its component diagram); update it in place only
if implementation reveals a real deviation from the planned design
(e.g., the service hook's actual home differs from what planning
assumed) — do not silently implement something different from what
the overlay says without updating the overlay to match.
