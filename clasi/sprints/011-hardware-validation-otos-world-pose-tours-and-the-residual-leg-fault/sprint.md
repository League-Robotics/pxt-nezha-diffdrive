---
id: '011'
title: 'Hardware validation: OTOS world-pose tours and the residual leg fault'
status: roadmap
branch: sprint/011-hardware-validation-otos-world-pose-tours-and-the-residual-leg-fault
use-cases: []
issues:
- otos-on-vevov-move-goto-world-pose-square-tours.md
- intermittent-cw-pivot-abort-wheel-reversal.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 011: Hardware validation: OTOS world-pose tours and the residual leg fault

> **Arc position.** This sprint sits downstream of three others, and unlike
> 006-009's mostly-thematic ordering (independent findings from the same
> code review, sequenced by triage priority rather than by dependency),
> this one has real, load-bearing dependencies:
>
> - **004 → 005, closed, in that order.** Sprint 004 makes radio a full v6
>   transport and gives v6 its `thdr`/`t` telemetry frame; sprint 005
>   retrofits the bench tools onto that frame. Until both land, the bench
>   tool family cannot read what this sprint needs: `tour_run.py` still
>   parses the retired v5 `TLM:` cleartext line (`tour_run.py:259`), and
>   `tour_capture.py` issues a numeric `RUN:<n>` verb (`tour_capture.py:42`)
>   that current firmware's `onRun()` dispatch never registers (its
>   handlers are all string names — see below). A capture run today would
>   silently produce nothing, or hit the wrong handler, before a single
>   OTOS number is ever measured.
> - **006, closed.** Sprint 006 fixes several motion-correctness defects
>   the 2026-08-23 code review found. This sprint's residual-leg-fault hunt
>   must run against hardware with those fixes already applied — otherwise
>   an "instrumented campaign" spends its budget re-discovering bugs 006
>   already put to bed instead of characterizing what survives them. The
>   Problem section below works out, finding by finding, which of 006's
>   fixes are even plausible causes of this particular fault.
>
> **Hardware dependency is total.** Every deliverable in this sprint is a
> measurement taken on vevov, on a mat, with the AprilCam running as ground
> truth. There is no code-review or host-test substitute for any of it —
> that is the point of the sprint.

## Goals

Theme: **measurement, not construction.** Almost everything the OTOS issue
asked to be *built* has already landed; what remains is proving it on real
hardware. The residual leg fault, symmetrically, cannot be fixed sight
unseen — it needs an instrumented hardware campaign before anyone can even
say confidently what's still wrong. Two goals:

1. Run the OTOS world-pose validation campaign the `otos-on-vevov-...`
   issue's own **Verification** section describes: score `goToWorld`
   tours against the encoder-only baseline, with the AprilCam as
   independent ground truth, and record the numbers the issue asks for.
2. Run an instrumented hunt for the residual distance-leg fault in
   `intermittent-cw-pivot-abort-wheel-reversal.md`, on post-006 hardware,
   following that issue's own "Next probes" list — and produce evidence
   (captured data, a narrowed signature) rather than promising a root
   cause, which a hunt sprint cannot honestly guarantee up front.

## Problem

Both issues predate sprints 003/004/006 and are partly stale. Read
file-by-file, most of the OTOS issue's *construction* is already done;
the residual-fault issue is an open hunt whose own probe list needs
checking against what 006 will already have fixed.

### OTOS world-pose: what's built, what remains

- **`otos_port.h`/`.cpp` — lever arm.** `setOffset()`, `setPose()`,
  `sensorToCentre()`, `centreToSensor()` are all fully implemented
  (`otos_port.cpp:139-192`) with the `offsetX_/offsetY_/offsetYaw_`
  members the issue asked for. The header comment at `otos_port.h:17-19`
  claiming this is "**NOT ported (yet)**" is **stale** — it predates the
  commit that shipped these functions and nobody updated the comment.
  That's a hygiene fix for sprint 009's comment-cleanup work order, not
  new work here.
- **`shims.cpp` — dual-pose seed.** `seedPose(int,int,int)`
  (`shims.cpp:1031`) already writes **both** pose sources — the encoder
  `Rig` x/y/heading and `OtosPort::setPose()` — exactly as the issue's
  "so their later divergence is the drift measurement" ask requires.
  Done.
- **Dual-pose TLM (`ox:oy:oh` columns) — genuinely not yet landed, but not
  this sprint's job.** Sprint 004 ticket 004 is building
  `WireAdapter::buildSnapshot()` with the POSE column set `seq now flags x
  y h ox oy oh vl vr i2cf` (ticket status: open, not yet closed as of this
  writing). This is the one real construction gap the OTOS issue asked
  for that hasn't shipped — it just belongs to 004, not 011. This sprint
  only needs it to have landed, which is exactly the hard dependency
  above.
- **`main.ts` — the functions.** `seedPose()`, `goToWorld()`, `worldX()` /
  `worldY()` / `worldHeading()`, `worldTrackingReady()` (the
  `otosConnected()`-shaped accessor), `setWorldSensorOffset()`,
  `startWorldTracking()`, `calibrateWorldSensor()`, `readWorld()` — all
  implemented. But `goToWorld`'s algorithm has **evolved past** the
  issue's own "Proposed fix": that section specified turn-first at 50°,
  one uncapped constant-curvature arc, and up to 6 arrival nudges
  (`maxNudges`). What shipped instead — informed by real vevov
  measurements recorded in its own comments (`main.ts:526-618`) — turns
  first at 12°, caps the arc at 25°, and runs strictly **one pass**, no
  nudging. `maxNudges` is still declared (`main.ts:546`) but referenced
  nowhere else — dead code from the abandoned nudge-loop design. The
  exported JSDoc directly above `goToWorld` still says "Repeats until
  inside the arrival tolerance," which is stale against the one-pass
  implementation. Both are comment/dead-code hygiene, not functional
  gaps — sprint 009's territory, not this sprint's.
- **`test/test.ts` — tours and calibration.** The issue's numeric
  `RUN:6`/`RUN:7`/`RUN:8` plan has been entirely superseded by a richer,
  already-working **named** command surface: `RUN:tour:world` (=
  issue's OTOS tour), `RUN:tour:robot` (an encoder+IMU contrast tour —
  see the nuance below), `RUN:tour:wheels` (open-loop contrast),
  `RUN:cal` / `RUN:cal:1` (lever-arm calibration = issue's `RUN:8`, plus
  its own verify pass), and `RUN:seed`, `RUN:seedxy`, `RUN:goto`,
  `RUN:face`, `RUN:fix`, `RUN:arm`, `RUN:probe`, `RUN:gap` for bench
  operation. **The lever-arm calibration has already been run and
  measured** on vevov (`test/test.ts:42-49`, dated 2026-08-20): arm
  −3.82 cm forward, −0.07 cm left, 0.89° yaw, fit residual **1.34 mm
  rms** — comfortably inside the issue's own verification bound (its
  reference failure case, uncorrected, was 42.7 mm). One nuance worth
  naming precisely rather than glossing over: the issue's `RUN:7` concept
  (host computes the arc, issues one raw `MOVE`, no nudges — "the
  contrast case for goTo") doesn't exist in that exact shape. What
  shipped instead, `RUN:tour:robot`, computes its arc **on the robot**
  from IMU heading and encoder position (no host computation, no OTOS
  reference) — a different but comparably-purposed contrast tour. A
  reasonable design substitution, not a gap.
- **`tools/` — forked into two generations.** `otos_levercal.py`,
  `tour_capture.py`, `tour_chart.py` exist as the issue asked, but
  `tour_run.py`, `tour_square.py`, and `tour_closedloop.py` (the latter
  two not mentioned in the issue at all — later additions) already speak
  the **current** named `RUN` vocabulary and already use `camlink.py` for
  AprilCam ground truth. `otos_levercal.py:87`, however, still issues
  `RUN:8` / `RUN:14` — numeric verbs `test/test.ts`'s current `onRun()`
  dispatch never registers (every handler name is a string) — so running
  it against current firmware is a silent no-op, the same class of defect
  the code review's R-16 found elsewhere, located here specifically.
  `tour_capture.py:42` has the same numeric-`RUN` habit and also still
  parses the retired v5 `TLM:t_ms:x:y:h` line (`tour_capture.py:68`), not
  the v6 frame 004/005 will produce. This is real, precisely-located
  remaining work — small, but a genuine blocker to using either tool in
  this sprint's campaign until retargeted.

### Residual leg fault: relationship to sprint 006's fixes

Per the issue's own 2026-08-20 rewrite: the dominant failure class was
root-caused and fixed (commit 3e919e5 — the missing final neutral step on
move completion, and the co-ticking protocol fiber that made it
intermittent). Its **RETIRED THEORIES** list is settled evidence, not a
checklist to redo: battery sag, tick-loop starvation, encoder 0x46 latch,
direction mirroring, track/scrub calibration are all closed with the
measurements that closed them. This sprint must not re-open any of them.

What remains: turn overshoot is gone (headings close within ~7°
consistently); tours complete ~70%, with occasional distance-leg errors —
a straight overrunning, or a tour truncating mid-leg (e.g. finals of
(-275,141) or (471,671,273°) in the 2026-08-20 warm campaign). The
signature differs from the fixed class: heading usually still closes.

The 2026-08-23 code review's motion-correctness cluster (which sprint 006
fixes) is a plausible source of some of this — but not all of it, and
tracing which finding actually touches the tour code matters more than
assuming "006 fixes motion, so it fixes this too":

- **R-08 (cross-fiber stop lands in the settle window ~⅓ of the time,
  wheels hold last duty until the ~100-150 ms watchdog) is the strongest
  plausible cause on record for "a straight overrunning."** The symptom
  matches almost exactly. This sprint's campaign is the first real chance
  to see whether that failure mode is actually gone post-fix.
- **R-07 (brick-reset teleport) is a plausible-but-unconfirmed
  contributor to "a tour truncating mid-leg."** Sprint 006 runs the
  decisive bench experiment (power-cycle mid-drive, watch DIAG 10/11 +
  pose) and records confirmed-or-ruled-out directly in
  `brick-reset-odometry-teleport.md`. Whatever that experiment finds,
  this sprint inherits it as settled rather than re-litigating it.
- **R-02/R-03/R-04 (the `goTo`/`GO_TO_R` pivot-split miss, long-way arcs,
  and dead arrival tolerance) do NOT plausibly touch this fault.** Those
  live in the `goTo(x,y)`/`startGoTo()` → `moveX()`/`GO_TO_R`
  theta-encoding path (`main.ts:258-292`, `shims.cpp:411`). The tour code
  never calls it: `goToWorld` and `tourRobot`'s `legToward()` each compute
  their own bearing/arc math directly against the plain
  `move()`/`startMove()` distance-and-yaw primitive, sidestepping
  `moveX`/`GO_TO_R` entirely. Fixing that geometry in sprint 006 will not
  change a single tour result.
- **R-09 (continuous-mode odometry chord error) doesn't apply either** —
  the tours run exclusively in discrete move mode
  (`tickedMove`/`tickedMove` → `startMove()` + `while (driveTick())`),
  never in continuous velocity/twist mode.
- **R-05 (OTOS seed heading clamp) is unlikely related** — the fault's
  own signature says heading usually still closes, and every seed this
  project uses (0°/90°/180°) is nowhere near the ±180° wrap boundary that
  defect concerns.
- **The issue's own second next-probe — the `moveDeadline` duration math
  for legs that truncate (`motion_engine.cpp`'s `move_.deadline`,
  `motion_engine.h:281-311`) — is covered by none of the code review's
  findings and is not part of sprint 006's fix list.** It remains
  squarely this sprint's own thing to check. Sprint 006 buys a clean
  baseline; it does not buy an answer here.
- **First-move-after-boot special-casing** (the issue's third
  next-probe) has no code evidence either way found during this
  planning pass — it stays an open item for the campaign itself to
  chase, not something ruled in or out yet.

This sprint therefore runs after 006 specifically so the campaign measures
a robot with R-08 (and, contingent on 006's bench result, R-07) already
fixed — separating "was this the settle-window stop race" from "is there
something else" cleanly, instead of re-discovering symptoms 006 already
resolved.

## Solution

1. **Fix the two stale bench tools first** — small, contained, not new
   construction: retarget `otos_levercal.py` from `RUN:8`/`RUN:14` onto
   `RUN:cal`/`RUN:cal:1`, and retarget `tour_capture.py` off the numeric
   `RUN:<n>` verb and the v5 `TLM:` line onto `tools/tlm.py` (sprint 005's
   shared parser) and the current named `RUN` vocabulary. Neither tool is
   usable for this campaign until this lands.
2. **OTOS validation campaign.** Run `RUN:tour:world` (`goToWorld`,
   OTOS-guided) and `RUN:tour:robot` (encoder+IMU baseline) repeatedly on
   vevov, on the mat, with the AprilCam running throughout as an
   independent ground-truth check — **diagnostics only, never steering a
   move in flight**, per the issue's own stakeholder doctrine and this
   project's standing camera-is-diagnostics-not-control rule. Capture
   dual-pose telemetry (once 004/005 land) to chart OTOS-vs-encoder
   divergence per corner, and compare against `RUN:straight`'s
   already-recorded encoder-only baseline (9-54 mm closure, 1-7° residual
   heading at 60 cm sides) as the improvement reference. Re-confirm the
   lever-arm calibration still holds on the current build rather than
   re-deriving it from scratch (it is already measured at 1.34 mm rms).
3. **Residual-fault campaign.** Run enough `RUN:tour:world` /
   `RUN:tour:robot` repetitions on post-006 hardware to get a real failure
   rate, not a single pass/fail. Log per-leg **believed-vs-target** data
   at every move end (what did the move think it hit, versus the OTOS and
   AprilCam ground truth) — the issue's own first next-probe. Specifically
   watch whether R-08's fix eliminated "straight overrunning," and
   separately investigate the `moveDeadline` duration math and
   first-move-after-boot behavior, since nothing else in the pipeline
   touches either.
4. **Do not re-test any RETIRED THEORY.** Treat that list as closed
   evidence; if a symptom looks like it might be one of them again, that
   itself is a finding worth recording, not a reason to re-run the
   original experiment.
5. Record every result back into both issue files. If the residual fault
   is resolved, close it there. If not, file a sharpened successor issue
   that states plainly what this campaign additionally ruled out and what
   it narrowed the remaining suspects to.

## Success Criteria

A hunt sprint cannot honestly promise a root cause, so success is defined
as **instrumented and characterized**, not "found":

- A recorded, charted set of OTOS-tour runs (`RUN:tour:world`) against the
  encoder-only baseline (`RUN:tour:robot`/`RUN:straight`), with per-corner
  OTOS and encoder closure both logged and compared against the issue's
  own verification bar and the 9-54 mm/1-7° baseline.
- The lever-arm calibration re-confirmed as still holding on the current
  build (not re-derived from nothing).
- Per-leg believed-vs-target data captured across a real campaign (not
  one run) on post-006 hardware; the residual failure signature — rate,
  which legs, straight-overrun vs. mid-leg-truncation split — is written
  down with numbers, whether or not a cause is found.
- The deliverable is **either** a fix (if the campaign lands on one)
  **or** a filed, sharpened successor issue naming what this campaign
  additionally retired and what it narrowed the remaining suspects to —
  an open-ended "find the bug" outcome is not acceptable on its own.
- `otos_levercal.py` and `tour_capture.py` are retargeted onto the current
  `RUN` vocabulary and v6 telemetry, and are actually used successfully in
  the campaign.
- No RETIRED THEORY is re-opened; no new motion feature ships; no wire
  protocol work is done here.

## Scope

### In Scope

- Running the OTOS validation campaign and the residual-fault campaign on
  vevov, on the mat, with the AprilCam as ground truth.
- Per-leg believed-vs-target logging and analysis for the residual fault.
- Investigating the `moveDeadline` duration math and first-move-after-boot
  behavior — the two next-probes nothing else in the pipeline covers.
- Retargeting `otos_levercal.py` and `tour_capture.py` onto the current
  named `RUN` vocabulary and (once available) the v6 telemetry frame —
  small, contained tooling fixes needed to run the campaign at all.
- Recording campaign results back into both issue files; filing a
  sharpened successor issue if the residual fault is not resolved.

### Out of Scope

- Any new motion feature or navigation behavior beyond what already ships.
- The full wire protocol work the OTOS issue itself already deferred
  (GET/SET, TLM subscription grammar, SEED/CAL verbs, the case flip) —
  a separate follow-up package, unrelated to sprint 004's radio-transport
  scope.
- Re-litigating any RETIRED THEORY (battery sag, tick starvation, encoder
  latch, direction mirroring, track/scrub calibration).
- Any change to `radio-robot-lib`.
- The comment/dead-code hygiene items surfaced above (the stale
  `otos_port.h` "NOT ported" comment, the stale `goToWorld` JSDoc, the
  dead `maxNudges`) — these belong to sprint 009's comment-cleanup work
  order, not here.
- Starting this sprint's detail planning before sprints 004, 005, and 006
  have all closed (see the Arc position note above).

## Test Strategy

Hardware-only — there is no host-test or code-review substitute for any
of this sprint's deliverables. Methodology:

- Repeated `RUN:tour:world` and `RUN:tour:robot` runs on vevov, on the
  mat, across enough repetitions to produce a real rate, not a single
  pass/fail.
- The AprilCam running throughout as independent ground truth — read for
  scoring only, per doctrine never in the control loop for a move in
  flight.
- Per-leg logging via the existing on-robot instrumentation (`OCAL:`
  fixes, `GAP`/`wpk`/`DIAG` traces) plus, once 004/005 land, the dual-pose
  `thdr`/`t` telemetry frame charted through `tour_chart.py`.
- Explicit before/after framing against the pre-006 baseline already on
  record (9-54 mm/1-7° encoder-only; ~70% completion with occasional
  distance-leg errors), so the campaign can say whether the post-006
  numbers actually moved.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.
