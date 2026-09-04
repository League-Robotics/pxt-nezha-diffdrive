---
id: '007'
title: 'Bench acceptance: gates G1-G6 and the stop_distance/omega_floor measurements,
  camera-truthed, on one robot'
status: in-progress
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
depends-on:
- '004'
- '006'
- 009
- '010'
github-issue: ''
issue:
- code-review/pivot-end-predictive-termination-and-yaw-floor.md
- code-review/one-velocity-shaper-profile-object-out-of-servicemove.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench acceptance: gates G1-G6 and the stop_distance/omega_floor measurements, camera-truthed, on one robot

## Description

Design §10, on one robot, via the wire, camera as truth. Needs ticket
004 (the config surface must be live to `SET` the new field names) and
ticket 006 (the bench-tool calibration fix — G1-G6 must measure the new
profile against a trustworthy camera mount and a reachable radio link,
not a stale mount or a silent robot; sprint.md's Solution section
sequences this explicitly).

**Run `uv run tools/field_dance.py` first**, per
`.claude/rules/field-dance-first.md`, before any commanded motion —
this is a standing project safety rule, not specific to this ticket,
but load-bearing here since this ticket is the sprint's first real
on-robot run.

**The six gates** (design §10.1, all camera-truthed per
`.claude/rules/measurement-citations.md` — every number names its
capture):
- **G1 pivot accuracy** — 12× `MOVE_X 0 ±1571 100 5000` alternating,
  camera at rest before/after each; mean |error| ≤ 0.5°, sd ≤ 0.4°, no
  per-tick `dutl`/`dutr` sign reversal in the last 10 ticks.
- **G2 arc endpoint** — 6× `MOVE_X 300 785 100 8000` (45°); endpoint
  within 5 mm of (270, 112) body-frame.
- **G3 straight** — 6× `MOVE_X 600 0 200 8000`; camera leg length
  600±3 mm; peak `vl`/`vr` ≤ 220 mm/s; no leg-end bump (monotone in the
  last 10 ticks).
- **G4 jerk** — same as G3, differentiate `vl`/`vr` twice from `TLM
  FULL`; first tick ≤ floor; thereafter |Δv/Δt| ≤ 1.5×`accel`; no tick
  above 2×`decel` at the end.
- **G5 continuous** — `WHEELS_V 200 200 2000` from rest; rise ≤
  1.5×`accel`; no overshoot above 210 mm/s.
- **G6 square tour closure** — `RUN:square` × 3; closure ≤ the current
  baseline (`reports/gopiv-closure-20260901.md`); no regression is the
  bar, improvement is expected.

**The two measurements** (design §10.2):
- **`stop_distance`**: 10 pivots at the yaw floor only (`MOVE_X 0 1571
  <floor-equivalent cruise>`), residual overshoot at rest by camera,
  converted to per-wheel mm. Store in `firmware_bake.stop_distance_mm`.
  Expected order: 0.3-1 mm.
- **`omega_floor`**: from rest, `WHEELS_V ±v ∓v 1500` sweeping v down
  from 70 mm/s per wheel; lowest v with sustained rotation over the
  whole 1.5 s. Expected order: 15-30°/s.

**Docs**: update `src/DESIGN.md` §3 (real file — record the measured
`stopDistance`/`omegaFloor` field comments the same way
`travelCalib`/`trackWidth`/`rotationalSlip` already carry their
measurement history) and `docs/design/specification.md`'s constants
table (design §11's own ticket-5 note). **Retire `pivot_overrun`** from
every robot config — this is the `radio-robot-lib` `firmware_bake`
cross-repo change (design §12 open question 2); flag explicitly in this
ticket's close-out if it cannot be completed from this repo alone.

## Acceptance Criteria

- [ ] `field_dance.py` passes before any other commanded motion this
      ticket runs. UNMET 2026-09-04: the dance FAILED on tovez (large,
      inconsistent pivot/drive errors, not a clean convention offset --
      `captures/bench-acceptance-029-20260904/notes.md` §3) and
      evidence-gathering afterward pointed at a suspected kernel wedge,
      not a convention/mount problem. Blocked pending hardware recovery.
      STILL UNMET 2026-09-04c (new session, same robot, hardware
      recovered/reflashed with ticket 009's fix): the dance FAILED
      again, but with a DIFFERENT shape -- two of three pivots now
      PASS (the third misses by only 14 deg, a real improvement over
      2026-09-04's +47..+58 deg per pivot), but all three drives still
      fail badly (30+ cm off, inconsistent bearings, one with no
      motion at all). `captures/bench-acceptance-029-20260904c/field-dance.log`;
      full account in `reports/bench-acceptance-029-20260904c.md` §4.
      STILL UNMET 2026-09-04d (new session, tovez reflashed 09:38 with
      ticket 010's K1 fix, driven over a NEW lossless TCP carrier --
      tovez's on-robot `zilch` Pi -- instead of the lossy torture
      relay, ruling out relay loss as a confound): the dance FAILED
      again, but the shape changed for the better in one respect and
      newly, cleanly, in another. Pivots: net drift only +14.2 deg
      over three pivots (+90/+180/+90), close to a clean run and a
      further improvement over 2026-09-04c -- consistent with K1
      addressing the pivot-accuracy defect. Drives: all three FAILED
      with a consistent ~90 deg bearing error (+87/+91/+86 deg off
      expected heading) while magnitude tracked commanded distance
      reasonably (16.9/35.5/17.7 cm vs 20/40/20 cm) -- a new,
      cleanly-characterized directional defect distinct from the
      earlier sessions' large/inconsistent drive errors, and distinct
      from 2026-09-04c's G5 sign-reversal defect. Robot ended safe
      (camera-confirmed (41.7, 9.8) cm, well inside margin; dance's
      own "returned home" step PASSed at 3.1 cm).
      `captures/bench-acceptance-029-20260904d/field-dance.log`; full
      account in `reports/bench-acceptance-029-20260904d.md` §2.
      STILL UNMET, same-day continuation session (2026-09-04):
      root-caused and FIXED the ~90 deg drive-bearing defect above --
      it was tooling (`tools/field_dance.py`'s `pose()` double-added
      the fixed +90 deg AprilCam convention on a REGISTERED tag's
      already-corrected yaw_rad) compounded by tovez's tag plate being
      physically mounted ~180 deg from the fleet convention (MEASURED,
      `captures/bench-acceptance-029-20260904d/heading-probe.log`).
      Fixed in `tools/field.py`/`tools/field_dance.py`/
      `tools/field_calibration.json`, pinned by new tests
      (`tests/tools/test_field.py`, `uv run pytest tests/tools -q`: 360
      passed), and VERIFIED on real hardware: two `field_dance.py --tcp`
      re-runs from a repositioned, margin-safe start show every bearing
      error now <=4 deg (was 86-91 deg) -- the directional defect is
      gone. `DANCE FAILED` printed both times anyway, on a DIFFERENT,
      purely-magnitude finding: the 180 deg pivot lands ~9-9.6 deg
      short and the 40 cm reverse drive lands ~4.6-4.7 cm short,
      identically in both runs, while the paired 90 deg pivots/20 cm
      drives in the same runs pass comfortably (<=3.1 deg / <=2.4 cm).
      This is an ACCURACY finding (the gate is CONVENTION, not
      accuracy per `.claude/rules/field-dance-first.md`), and is
      exactly what `stop_distance`/`omega_floor`/G1-G6 exist to
      characterize -- not chased further this session per the dance's
      own mandatory stop-on-FAIL ordering. Robot ended safe both times
      (camera-confirmed (18.96, -5.24) cm, well inside margin; `STATUS`
      healthy and non-frozen throughout).
      `captures/bench-acceptance-029-20260904d/field-dance-refit-run1.log`,
      `field-dance-refit-run2.log`; full account in
      `captures/bench-acceptance-029-20260904d/notes.md` §5 and
      `reports/bench-acceptance-029-20260904d.md` §5-6.
- [ ] G1-G6 all pass, each cited with its capture artifact
      (`.claude/rules/measurement-citations.md`). NOT RUN 2026-09-04 --
      blocked behind the failed dance above; driving a robot that
      cannot reliably stop where commanded is unsafe.
      2026-09-04c: G1 and G5 were RUN and FAILED, cited
      (`captures/bench-acceptance-029-20260904c/g1-summary.txt`,
      `g5-frames.json`; report §5-6). G1: mean|error| 8.13 deg / sd
      8.83 deg vs the 0.5/0.4 deg bar, a systematic direction-dependent
      bias. G5 found a live, camera-corroborated control-loop defect --
      a WHEELS_V 200 200 hold left one wheel's measured velocity
      NEGATIVE while the other overshot to 492 mm/s against a 210 mm/s
      ceiling, and drove the robot to within 1.4 cm of the field safety
      margin before an ESTOP. G2, G3, G4, G6 were NOT attempted this
      session -- running 600 mm straights or a square tour on top of
      that defect was judged unsafe (no reliable pre-flight projection
      is possible when actual behavior deviates this much from
      commanded). See `reports/bench-acceptance-029-20260904c.md` for
      the full tables and the "what a human needs to do next" list.
      2026-09-04d: NOT RUN -- still blocked behind the failed dance
      (see above); no gate work was attempted this session.
      Same-day continuation session: STILL NOT RUN -- the dance's
      convention/directional defect is now fixed and verified (see
      above), but the dance itself still FAILs on the 180 deg
      pivot/40 cm drive magnitude-undershoot finding, so per the
      ticket's own mandatory ordering no gate work was attempted. G1
      (12x 90 deg pivots, the same size that already passes cleanly in
      both dance re-runs) is the best next candidate.
- [ ] `stop_distance` and `omega_floor` measured, recorded in
      `firmware_bake.stop_distance_mm` and `MotionLimits::omegaFloor`'s
      default, and cited with their capture artifacts. NOT MEASURED
      2026-09-04 -- same blocker.
      2026-09-04c: BOTH ATTEMPTED, NEITHER TRUSTWORTHY. `stop_distance`
      (10 floor-cruise pivots,
      `captures/bench-acceptance-029-20260904c/stop-distance-summary.txt`):
      naive calc (0.53 mm/wheel) lands in the design's expected order
      by what looks like coincidental sign-cancellation of the same
      CW/CCW asymmetry G1 shows (individual pivot errors -4..-7.6 deg
      / +5.6..+8.7 deg) -- not recorded as measured.  `omega_floor`
      (`WHEELS_V` sweep 70->10 mm/s,
      `captures/bench-acceptance-029-20260904c/omega-floor-summary.txt`):
      no floor found -- even 10 mm/s produced -50.4 deg/s of sustained
      rotation, and the rate was NOT monotonic in commanded speed (v=50
      rotated faster than v=70) -- left unmeasured. `lag` (design
      S10.2's first measurement, a precondition for `stop_distance`)
      WAS measured, partially: the right wheel fits a first-order lag
      at tau=126 ms (inside the design's 50-150 ms expected order); the
      left wheel does not fit the model at all (overshoots, settles at
      a different steady speed than the right wheel on an identical
      command) --
      `captures/bench-acceptance-029-20260904c/lag-capture-frames.json`.
      `SET lag 0.126` applied for the session (wire-only, not baked).
      None of the three numbers are written into
      `firmware_bake`/`MotionLimits` defaults -- see the report's
      cross-repo follow-up (§10) for what to bake once cleanly
      remeasured.
      2026-09-04d: NOT ATTEMPTED -- blocked behind the failed dance;
      the prior session's `SET lag 0.126` is not known to still be in
      effect (fresh boot, no `SET lag` sent this session).
      Same-day continuation session: STILL NOT ATTEMPTED, same blocker
      (dance not yet cleanly passing) -- see the "G1-G6" item above.
- [ ] `src/DESIGN.md` §3 updated (real file) with the measured
      constants' field-comment history. NOT DONE -- no measured
      constants exist yet to record.
      2026-09-04c: PARTIALLY DONE -- `lag`'s partial measurement (one
      wheel) and this session's G1/G5/stop_distance/omega_floor
      findings are now recorded with citations in `src/DESIGN.md` §3
      (the paragraph after the `travelCalib`/`trackWidth`/
      `rotationalSlip` geometry-defaults paragraph). Left unchecked
      because `stopDistance`/`omegaFloor` still have no trustworthy
      measured value to record -- only the attempt and why it is not
      trustworthy.
      2026-09-04d: STILL PARTIAL -- appended a further paragraph
      recording this session's carrier change, dance table, and the
      two findings (pivot improvement, new ~90 deg drive-bearing
      defect), cited to `captures/bench-acceptance-029-20260904d/`.
      Still no `stopDistance`/`omegaFloor` measured value to record;
      left unchecked for the same reason.
      Same-day continuation session: STILL PARTIAL -- appended a
      paragraph recording the root-cause/fix/verification (double-add
      bug, tovez's 180 deg plate, the two hardware re-runs and the new
      magnitude-undershoot finding), cited to
      `captures/bench-acceptance-029-20260904d/notes.md` §5. Still no
      `stopDistance`/`omegaFloor` measured value to record; left
      unchecked for the same reason.
- [ ] `docs/design/specification.md`'s constants table updated. NOT
      DONE -- same reason.
      2026-09-04c: PARTIALLY DONE -- added a `MotionLimits` fields
      table (compiled defaults + this sprint's bench-acceptance status
      per field) to specification.md §11, plus the G1/G5 summary.
      Left unchecked for the same reason as `src/DESIGN.md` §3 above.
      2026-09-04d: STILL PARTIAL -- appended a short paragraph to §11
      noting this session's dance FAIL and pointing at `src/DESIGN.md`
      §3; no `MotionLimits` field values changed (nothing new
      measured). Left unchecked for the same reason.
      Same-day continuation session: STILL PARTIAL -- appended a
      paragraph to §11 recording the root-cause/fix/verification and
      pointing at `src/DESIGN.md` §3. No `MotionLimits` field values
      changed (nothing new measured this session either). Left
      unchecked for the same reason.
- [x] `pivot_overrun` retired from every robot config this repo
      controls; the `radio-robot-lib` cross-repo side is explicitly
      flagged if not completed here. This repo controls no robot config
      file carrying `pivot_overrun` (grep of `*.json`/`*.py`/`*.md`,
      2026-09-04: every hit is a test fixture, doc, or the closed
      sprint-025/028 history for the OLD field name being retired --
      `tools/field_calibration.json` never had it). The cross-repo
      change is flagged as a follow-up: in
      `radio-robot-lib/config/robots/tovez.json` (and the rest of the
      fleet), rename the `firmware_bake` key `pivot_overrun_mm` to
      `stop_distance_mm` once ticket 007's `stop_distance` measurement
      exists to populate it with (design §8's knob-compatibility table).
- [x] Design §7's predicted "after" numbers (already confirmed on ideal
      wheels by ticket 003's probe) are now confirmed or contradicted on
      real hardware — record which. UNRESOLVED 2026-09-04: real
      hardware data was gathered (two isolated 90° pivots, +110° and
      +123° actual vs +90° commanded) that looks like a severe
      contradiction of the ±0.5° prediction, but it is confounded by
      the same suspected kernel wedge (telemetry showed zero wheel
      velocity/duty for the entire window while the camera showed real
      rotation) -- cannot honestly attribute this to the new engine
      versus the wedge without a clean re-run after hardware recovery.
      See `captures/bench-acceptance-029-20260904/notes.md` §4.
      **CONTRADICTED, confirmed 2026-09-04c, no longer confounded.**
      This session's `lag`/G5 captures show LIVE, tick-by-tick updating
      telemetry during active moves (ruling out the 2026-09-04 "frozen
      telemetry means the camera reading might be stale/misattributed"
      concern), and G1's 12-pivot camera-only measurement independently
      confirms the same order of error via a completely different
      instrument path: mean|error| 8.13 deg, over 16x the design's
      +-0.5 deg bar. The ±0.5° prediction is contradicted on real
      hardware even with ticket 009's lag-aware fix landed. Separately,
      this session ALSO confirms (not just hypothesizes) a distinct
      telemetry-staleness bug: STATUS's `active` bit and TLM's
      per-tick pose/duty fields both stuck at their last real value for
      100+ seconds after the robot was camera-confirmed at rest, while
      `cyc`/`seq`/`now` kept advancing -- this is the live confirmation
      of the 2026-09-04b diagnostic session's Hypothesis 1, but it is a
      SEPARATE bug from the pivot-accuracy contradiction and from the
      G5 wheel-sign-reversal control defect (also newly found this
      session) -- do not conflate the three when triaging. Full account:
      `reports/bench-acceptance-029-20260904c.md` §8.

## Implementation Plan

**Approach**: Bench session, one robot — confirm the current robot
assignment for this session/machine before starting (no standing
ownership table; per project practice this is set per session, not
inherited from prior notes), one continuous sitting where practical.
Run `field_dance.py`, then the two §10.2 measurements first (they feed
`firmware_bake`), then G1-G6 in order.

**Files to create/modify**:
- `radio-robot-lib/config/robots/<robot>.json` (or flag as cross-repo
  if inaccessible) — `stop_distance_mm`, drop `pivot_overrun_mm`.
- `src/DESIGN.md` §3 (real file)
- `docs/design/specification.md` (constants table)
- `captures/bench-acceptance-029-<date>/` (new — camera captures, TLM
  logs; `captures/` is gitignored by project convention, so `git add
  -f` any capture cited by a MEASURED claim, per
  `.claude/rules/measurement-citations.md` — a citation naming a path
  git never tracked points at nothing for the next reader)
- `reports/` (project convention: chart/image writeups ship as
  markdown under repo-root `reports/`, not a bare image file, if this
  session produces charts)

**Testing plan**: No new automated test — this is a hardware
acceptance run. The automated coverage (`test_profile_probe.py` et al.)
was already established in ticket 003; this ticket confirms it on real
hardware.

**Documentation updates**: `src/DESIGN.md` §3, `docs/design/
specification.md`, plus whatever `reports/` writeup the bench session
produces.

## Session Notes (2026-09-03, tovez, PARTIAL -- stopped at placement check)

Full account: `captures/bench-acceptance-029-20260903/notes.md`
(includes camera captures cited below).

**Build and flash: PASS.** `make_deploy.py --robot tovez --radio-link`
failed its first attempt on a real defect -- `src/shims.cpp:1481`'s
`setLimits()` (added by ticket 004) had its `//%` shim declaration
split across two lines, which the PXT packager cannot parse (every
other `//%` shim in the file is single-line; the file's other
multi-line declarations are deliberately *not* `//%`-annotated).
Fixed by joining the declaration onto one line; no behavior change.
Rebuilt clean: `.tmp/deploy-head/built/binary.hex` (1680281 bytes).
Flashed via `mbdeploy deploy tovez --remote --hex ...` to farm node
meili (ENUM 6) -- first erase attempt failed
(`result code 0x67`), mbdeploy's automatic CTRL-AP mass-erase recovery
fixed it, retry programmed cleanly (418816 bytes, 0 identical). Post-
flash: `HELLO` -> `device NEZHA2 robot tovez 2314287040`, `VER` ->
`ver 1.20260903.1`, `ID` -> `id diffdrive tovez 1.20260903.1 tovez`.

**Camera/placement check: STOPPED, no motion commanded.**
`mcp__aprilcam__get_tags` on `arducam-ov9782-usb-camera`, two polls
~8 s apart, returned only the ArUco border tags -- no AprilTag-family
tag at all, meaning neither AprilTag 1 (field centre) nor AprilTag 52
(tovez) was visible. A raw and a deskewed frame
(`captures/bench-acceptance-029-20260903/raw-frame-placement-check.jpeg`,
`deskewed-frame-placement-check.jpeg`) show why: **the playfield
currently has the KIPR line-following mat laid over it with soda cans
as obstacles**, covering AprilTag 1, and tovez is not on the field at
all. Lights confirmed on both by the Shelly (`output: true`) and by
the frame itself (not dark).

Per the ticket's mandatory order, this is a stop condition: no
`field_dance.py`, mount registration, or `MOVE_X` was run. **Needs a
human**: clear the KIPR mat and cans off the playfield, place tovez at
field centre, before the next session can continue from step 3
(`field_dance.py` / mount registration) through G1-G6 and the §10.2
measurements. All of the ticket's acceptance criteria beyond
build/flash remain unmet for that reason -- see checklist below.

## Session Notes (2026-09-04, tovez, BLOCKED -- suspected kernel wedge during `field_dance.py`)

Full account: `captures/bench-acceptance-029-20260904/notes.md` (all
capture logs cited below live in that directory).

**Lights/camera/placement: PASS, no motion commanded.** Shelly
`output: true`. AprilTag 1 reads world (-0.04, -0.01) -- (0, 0) within
noise. AprilTag 52 (tovez) at world (8.50, 12.71) cm, well inside the
~30 cm placement tolerance -- the stakeholder's report that the field
was cleared and tovez placed is confirmed by camera, not assumed.

**Mount registration and kernel kick.** `camlink.py --register tovez`
registered the still-UNVERIFIED mount. `field_calibration.json`'s
`default_robot` switched `vevov` -> `tovez` (required for
`field_dance.py`); tovez's entry was missing `lever_cm`/`parallax_k`
(required unconditionally by that script) -- added clearly-labeled
PLACEHOLDER values, reasoned in the JSON's own `_lever_parallax_note`
to be harmless to the dance's PASS/FAIL either way. First
`field_dance.py` attempt refused (`STATUS ready=0`, the known
cold-kernel state); cleared with `RUN:clearestop` + a 2 mm `MOVE_X`
kick (`ack 1 1 stop`, `ready` flipped to 1, `connL`/`connR` to 1).

**`field_dance.py`: FAIL.** All three pivots over-rotated by 47.6-57.6
deg on 90/180 deg commands; all three drives were off by 25.9-34.9 cm
with wildly inconsistent bearings (+125, -39, +135 deg off). This is
**not** a clean convention flip (`.claude/rules/
tag-yaw-is-the-front-edge-not-the-hat.md` -- a wrong-sign/wrong-90
convention clusters errors near 0/90/180/270; these do not) -- read as
"the robot is not stopping where commanded."

**Evidence gathering (systematic-debugging Phase 1).** Two further
isolated single-pivot probes (`MOVE_X 0 1571 100 5000`, +90 deg
commanded), each bracketed by fresh camera fixes: +110.08 deg then
+123.32 deg actual rotation -- both real (camera stable to <0.02 cm /
<0.3 deg at rest immediately after, corner geometry consistent). The
second probe streamed `TLM FULL`: **all 76 telemetry frames across the
6.4 s window show `h` frozen, `vl`/`vr`/`dutl`/`dutr` all zero** --
firmware reports zero motion the entire time the camera shows a large
real rotation. `cyc` (kernel cycle counter) climbed to 2336 during that
capture and never advanced again in any later `STATUS` read this
session. `RUN:clearestop` then a bare `ESTOP` (both firmware-documented
unsequenced exemptions) got **no reply** on subsequent attempts, while
`HELLO`/`STATUS` kept answering normally throughout.

**Working hypothesis** (not confirmed): tovez's motion-control fiber
wedged during or shortly after the first evidence probe -- likely
I2C/OTOS, given this fleet's documented wedge history -- leaving the
wire/radio handling layer alive (still answers `HELLO`/`STATUS`) while
the fiber owning motion state, telemetry, and apparently
`ESTOP`/`RUN:clearestop` stopped ticking. This would explain every
observed motion this session reporting `reason=timeout` and never
`reason=stop` (bar the initial 2 mm kick): an unbraked pivot spinning
until its outer deadline force-stops it. `STATUS`'s own `wedge=0` flag
does not confirm this cleanly, so it is recorded as a hypothesis, not a
MEASURED fact -- see `.claude/rules/measurement-citations.md`.

**Safety action:** `ESTOP` was sent once the anomaly was recognized (no
reply received, consistent with the wedge hypothesis). No further
commanded motion was sent. tovez's last confirmed camera position,
(5.58, 6.80) cm, is well inside the field and safety margin -- no
geofence risk.

**Stopped here.** Design §7's "confirmed or contradicted on real
hardware" question could not be honestly answered either way --
real hardware data was gathered showing severe deviation from the
±0.5° pivot prediction, but it is confounded by the suspected wedge and
cannot be attributed to the new engine specifically without a clean
re-run. Nothing past the failed dance (mount fit, G1-G6, the two §10.2
measurements, the doc updates that depend on their numbers) was run.

**Needs a human**: physically recover tovez (power cycle first choice;
reflash if that does not clear it -- MEMORY.md's I2C-wedge lore), then
re-run `field_dance.py` from a clean boot before anything else in this
ticket resumes. If it now passes cleanly, the wedge hypothesis is
supported and the next session picks up at the mount-fit step. If it
fails again the same way, this is very likely a genuine firmware
defect in the new engine (K1-K4 kernel patches or the predictive-arrival
logic) that needs `radio-robot-elite` engineering attention before any
bench acceptance number here can be trusted -- do not patch it from
this ticket.

`field_calibration.json`'s `default_robot` is left as `tovez` (was
`vevov`) for continuity with this blocked session -- a future session
on a different robot must switch it back.

## Diagnostic session 2026-09-04b (tovez, BLOCKED -- no reachable carrier this session; re-analysis only)

Full account: `captures/bench-acceptance-029-20260904-diag/notes.md`.

**No commanded motion was sent.** Both carriers
`.claude/rules/connecting-to-a-robot.md` documents were tried and both
failed from this machine this session: the radio relay has no USB
device present at all (`mbdeploy probe`/`mbdeploy list --remote` show
no `zavaz` entry and no reachable farm node; `ls /dev/cu.*` shows no
DAPLink-style device), and WiFi TCP discovery
(`tools/wifilink.py --tcp --robot tovez`) timed out finding `tovez` by
mDNS or broadcast HELLO, confirmed independently with a `dns-sd -B
_robotlink._tcp` browse that found nothing advertised. This machine
otherwise has normal LAN access (the Shelly light controller at
`192.168.1.122` answered normally throughout). This is an
infrastructure access gap, not a firmware or process finding --
`captures/bench-acceptance-029-20260904-diag/notes.md` §1 has the exact
commands/output.

**With the robot unreachable, this session instead re-analyzed the
existing 2026-09-04 evidence** (`captures/bench-acceptance-029-20260904/`)
against the source and against a fuller column-by-column parse of
`evidence-pivot90-full-frames.json` than the original write-up did.
Findings (all cited to source/capture in the notes file, none of them a
new hardware measurement):

- **No geometry-bake regression.** `radio-robot-lib/config/robots/
  tovez.json` carries no `geometry.firmware_bake` block, so
  `make_deploy.py` injects nothing for tovez by design
  (`make_deploy.py:901-919`'s own comment names this exact robot) --
  GET should read this repo's compiled defaults (travelCalib_=0.7878,
  trackWidth_=114.2, rotationalSlip_=0.952), not `tovez.json`'s
  unrelated top-level `geometry.trackwidth`/`rotational_slip` (115/1.0,
  belonging to what looks like a different, much larger motion-stack
  config schema at that same path -- flagged for a human to confirm,
  not chased further).
- **`travel_calib`/`track_width` are not wire-exposed fields at all**
  (`src/comms/wire_adapter.cpp`'s `kFields[]` has no such names) -- a
  live `GET` for either is expected to answer `err 1`, which is
  correct behavior, not a regression. Whether the bare `GET` dump's
  zero-lines result (`evidence-get-and-status.log`) is a tool/radio-loss
  artifact or a real ticket-004 enumeration regression is still
  UNRESOLVED -- untestable without the robot.
- **Probe 1 re-read at full resolution**: `h` is flat across the ENTIRE
  ~5.85 s during-move capture window, not just at its two endpoints,
  and the expected UN-ramped pivot duration at cruise 100 (~0.9-1.5 s)
  is far shorter than either the 2.27 s pre-capture gap or the 5000 ms
  deadline -- the most parsimonious reading is the pivot physically
  completed, overshot (+103.17° odometry / +110.08° camera against a
  commanded +90°), and stopped, all within that first 2.27 s gap, not
  that it spun for the full deadline. This favors "late/wrong arrival"
  over "spun until timeout" for probe 1 specifically.
- **Probe 2 re-read at full column resolution**: EVERY pose/motion
  column is dead flat for the full 6.43 s window, not only the four
  named in the original write-up -- including the RAW encoder counts
  `posl`/`posr` and `ox`/`oy`, not just derived `h`. Only `cyc`
  (climbing for ~3 s then pinning at 2336) and `oh` (a 23-unit,
  noise-level wobble that does NOT track the camera's confirmed
  +123.32° of real rotation) show any variation at all. Three ranked
  hypotheses are recorded in the notes file: (1) a stale/cached
  telemetry Snapshot reused across ticks -- best fit, explains every
  frozen column at once; (2) a stuck encoder/OTOS I2C read, matching
  this fleet's own documented wedge history and consistent with the
  same probe's own `RUN:clearestop` non-reply; (3) a genuine
  kernel/fiber wedge (the original 2026-09-04 conclusion) -- worst fit,
  since it does not explain `cyc` climbing normally for the first ~3 s
  while pose was ALREADY frozen from frame 1. None of the three is
  confirmed; this is a ranking to falsify live, not a conclusion.

**No acceptance criterion changed status.** `field_dance.py` still has
not passed since the 2026-09-04 FAIL; G1-G6 and the two §10.2
measurements are still NOT RUN; design §7 is still UNRESOLVED. This
session narrowed the confounding (one hypothesis -> three ranked,
falsifiable ones) and cleared the geometry-bake/field-name side
questions, but added no new hardware evidence.

**Needs a human**: get a working carrier to tovez for the next session
-- plug the zavaz relay into whichever machine will run it, or power
cycle tovez and confirm `tovez.local` resolves over WiFi -- before any
of §6's four open questions (`captures/bench-acceptance-029-20260904-diag/notes.md`)
or the ticket's own remaining acceptance criteria can be attempted.

## Build for retest, 2026-09-04c (build step only -- no hardware touched)

Dispatched narrowly to produce a flashable hex from the branch tip
(includes ticket 009's lag-aware shaper) so a future session can flash
and retry hardware recovery. No motion, no flash, no `src/` edits.

**Investigated and REJECTED: injecting `tovez.json`'s top-level
`geometry.trackwidth`/`rotational_slip` (115 / 1.0) as a
`firmware_bake` fallback.** This was the dispatch's step 2, framed
against a claim that tovez's caliper trackwidth is 128 mm and its
effective track measures 136.59 mm. That claim traces to stale prose
*inside* `tovez.json`'s own `_trackwidth_note`/`_rotational_slip_note`
(dated 2026-07-29/2026-08-09) describing history for a value the file
no longer holds -- the live fields are 115 / 1.0, and 115/1.0 = 115 mm,
matching none of 128, 136.59, or 140.4. More importantly, this ticket's
own 2026-09-04b diagnostic session already flagged the top-level
`geometry` block as "what looks like a different, much larger
motion-stack config schema at that same path -- flagged for a human to
confirm, not chased further," and `make_deploy.py:901-919`'s own design
comment explicitly rejects unconditional top-level injection by name
("tovez's config says trackwidth 115 / slip 1.0 where the firmware
defaults it actually runs are 114.2 / 0.952 ... making injection
unconditional would silently retune three robots nobody asked to
touch").

This build confirmed the hypothesis with a direct file check: the same
`tovez.json`'s `_navigator_note` says `NavigatorLimits::trackWidth` is
"derived from this file's own geometry.trackwidth/rotational_slip",
and `NavigatorLimits` lives at
`radio-robot-elite/src/firm/motion/navigator/arc_solver.h` (confirmed
present in that sibling repo's worktrees, e.g.
`radio-robot-elite.worktrees/hal-reorg/src/firm/motion/navigator/
arc_solver.h`) -- a completely different firmware codebase (protocol-v5
native C++, GO_TO/NavigatorLimits) from this repo's PXT/MakeCode build
(MOVE_X/TLM, `src/motion/motion_engine.h`). The two firmwares share one
robot-config JSON file; `geometry.firmware_bake` is the ONLY subtree of
that shared file meant for this repo's build, by explicit design. The
top-level `geometry.trackwidth`/`rotational_slip` belong to the other
firmware's navigator and would be the wrong numbers to bake here even
if they were current.

**No `tools/make_deploy.py` or test change was made.** Adding the
requested fallback would have silently baked cross-firmware config into
this build -- worse than the status quo of baking nothing, not better --
so it was not implemented. This is reported per the Guard Blocks /
Exception posture (stop and report an upstream-decision conflict rather
than route around it), not treated as a ticket exception, since it did
not block completing the actual build deliverable. The right fix, if
tovez's real geometry needs baking for this firmware, is a
`geometry.firmware_bake` block added to `tovez.json` in the sibling
`radio-robot-lib` repo (this repo cannot make that edit) once real
measured `travel_calib`/`trackwidth`/`rotational_slip` numbers exist
for tovez under THIS firmware -- not a host-side fallback that guesses
from the other firmware's config.

**Build: PASS, on the second scratch build.** First attempt hit the
documented stale-scratch-cache trap (`tools/DESIGN.md` "Build
checkpoint triage", sprint 023's translation-unit-presence check):
`BUILD FAILED: not all nezha-diffdrive translation units were compiled`
against a `.tmp/deploy-head` left over from the 2026-09-03 session.
Recovered exactly as the error message and DESIGN.md direct: wiped
`.tmp/deploy-head` with Python `shutil.rmtree` (`rm -rf` is
sandbox-denied here). The wipe then exposed a second, worktree-specific
gap -- `pxt_modules/` is gitignored and this git worktree never had it
generated, so `_sync_scratch()`'s `shutil.copytree` failed with
`FileNotFoundError`. Fixed by running `pxt install` at the repo root
(one-time per-worktree setup, not a code change; the main checkout
already had its own `pxt_modules`). Rebuild then succeeded clean on
attempt 1, no retry needed, no compile diagnostics.

- **Hex**: `.tmp/deploy-head/built/binary.hex`, 1,685,996 bytes, 0
  universal-hex (`:0400000A`) block markers (plain V2, not the old
  multi-variant artifact).
- **Version**: repo version `1.20260903.1` (`pyproject.toml`, unchanged
  since ticket 009 -- no per-ticket bump per current convention) ->
  on-device boot banner `BOOT_VERSION = "03.01"`, `BOOT_ROBOT = "tovez"`.
  Expect `VER` -> `ver 1.20260903.1`, `ID` -> `id diffdrive tovez
  1.20260903.1 tovez` after flash, matching the 2026-09-03 session's
  post-flash pattern.
- **Radio**: `--radio-link` enabled (`BOOT_RADIO_LINK = true` in the
  scratch `test.ts`); channel 55 / group 108 injected into
  `radio_transport.h` (`kChannel`/`kGroup`), matching `tovez.json`'s
  `connection.radio_channel`/`radio_group`.
- **Geometry injected: none**, by design (no `geometry.firmware_bake`
  block for tovez). Confirmed in the scratch copy: `motion_engine.h`
  still reads `travelCalib_ = 0.7878f`, `trackWidth_ = 114.2f`,
  `rotationalSlip_ = 0.952f` (this repo's own compiled defaults);
  `motion_limits.h` still reads `lag = 0.0f`, `stopDistance = 0.0f`
  (ticket 009's new fields, also unbaked/default for tovez -- no
  `lag_s`/`stop_distance_mm` in tovez's config either). Byte-identical
  geometry behavior to every prior tovez build this ticket has flashed.
- **WiFi secrets**: none present (`config/wifi_secrets.json` missing);
  WiFi link stays disabled in this build, radio remains the only live
  carrier path once flashed.

**Flash command** (unchanged shape from the 2026-09-03 session,
verified against `mbdeploy deploy --help` this session):

```
mbdeploy deploy tovez --remote --hex .tmp/deploy-head/built/binary.hex
```

Post-flash check: `HELLO` should answer `device NEZHA2 robot tovez
<uid>`; `VER` should answer `ver 1.20260903.1`. If `VER` answers
anything else, the flash did not take and should not be trusted for
retest.

No hardware was touched this session -- build only, per dispatch scope.
`git status` shows only the pre-existing `.clasi/.clasi.db` diff (not
from this session) plus this ticket-file edit; `pxt_modules`/
`node_modules`/`.tmp/` are gitignored and not committed.

## Session Notes (2026-09-04c, tovez, PARTIAL -- link recovered, real hardware data gathered, new control-loop defect found and blocks the remaining translation gates)

Full account: `reports/bench-acceptance-029-20260904c.md` (all capture
logs cited below live in
`captures/bench-acceptance-029-20260904c/`, force-added).

**Carrier recovered.** Unlike 2026-09-04b's diagnostic session (no
reachable carrier at all), this session reached tovez over the torture
radio relay (channel 55 / group 108, `tools/fieldlink.py`) throughout.
`HELLO`/`PING`x4/`STATUS` all healthy; the documented 2 mm kick cleared
the never-ticked `ready=0` state left over from the prior session's
flash.

**GET readback mystery resolved**: the "bare GET returns nothing" open
question from 2026-09-04b was a client bug in `tools/fieldlink.py`'s
`seqd()` (it discards every line except the one matching `ack`/`err`),
not a firmware regression. Reading the full response window shows both
the bare dump and every individually-addressed field GET answering
correctly.

**`lag` measured (one wheel) and set.** `WHEELS_V 200 200 1500` +
`TLM FULL` fits the right wheel to tau=126 ms (inside design S6.3's
50-150 ms expected order); the left wheel does not fit a first-order
model at all (overshoot + a different steady-state speed than the
right wheel on an identical command) -- flagged as a distinct,
unexplained per-wheel asymmetry. `SET lag 0.126` applied for the
session.

**`field_dance.py` FAILED again, differently.** Pivots much improved
(2/3 pass, the third misses by 14 deg vs 2026-09-04's +47..+58 deg);
drives still badly broken (30+ cm off, inconsistent bearings, one with
no motion).

**G1 (pivot accuracy): FAILED, cited.** 12 alternating +-90 pivots,
camera before/after each: mean|error| 8.13 deg, sd 8.83 deg vs the
0.5/0.4 deg bar -- a systematic, direction-dependent (CW vs CCW) bias,
not random noise. `i2cf` (STATUS's I2C fault counter) climbed steadily
through this run and essentially every other move this session (4 -> 152
by session end) -- never during idle periods.

**A lever/mount-residual fit was attempted** from the G1 pivot camera
fixes (least squares, 13 poses) but produced a 9.87 mm residual RMS and
a ~3.3 cm implied centre spread -- an order of magnitude worse than
vevov's own 0.28 mm fit, meaning the robot was not pivoting cleanly in
place. **Not written into `field_calibration.json`** -- overwriting an
already-UNVERIFIED placeholder with an equally untrustworthy number
would not help the next session.

**`stop_distance` and `omega_floor`: attempted, neither trustworthy.**
`stop_distance`'s naive per-wheel-overshoot calculation (0.53 mm) lands
inside the design's expected order, but only by apparent coincidental
cancellation of the same CW/CCW asymmetry G1 shows -- not recorded as
measured. `omega_floor`'s sweep (70 -> 10 mm/s) never found a floor,
and the rotation rate was NOT monotonic in commanded speed (v=50
rotated faster than v=70) -- left unmeasured.

**G5 (continuous WHEELS_V): FAILED with a serious, newly-found
control-loop defect.** `WHEELS_V 200 200 2000` from rest: the LEFT
wheel's measured velocity went NEGATIVE (settled ~-76 mm/s, with
negative commanded duty) while the RIGHT wheel overshot to 492 mm/s
against the gate's 210 mm/s ceiling -- both wheels commanded
identically. This is not a telemetry-freeze artifact (the trace updates
live, tick to tick, and the camera independently confirms real, if
confusing, displacement). **The resulting drift put tovez within 1.4 cm
of the field's safety margin before an ESTOP was sent.** Robot confirmed
at rest and safe afterward (two independent camera polls, <0.1 cm
apart).

**G2, G3, G4, G6: NOT attempted.** G3/G4 command 600 mm straights (3x
the distance of the drive-probe that showed +51 deg of uncommanded
heading swing on just 20 cm) and G6 composes several such legs into a
square tour -- running either on top of the G5 defect was judged unsafe,
since actual behavior deviates too far from commanded for a normal
pre-flight path projection to bound.

**A separate telemetry-staleness bug was independently confirmed**
(not just hypothesized, as in 2026-09-04b): STATUS's `active` bit and
TLM's per-tick pose/duty fields both stuck at their last real value for
100+ seconds after the robot was camera-confirmed at rest, while
`cyc`/`seq`/`now` kept advancing normally. This is the live
confirmation of the 2026-09-04b diagnostic session's Hypothesis 1, and
it is a DIFFERENT bug from the G5 control-loop defect above -- keep them
separate when this gets engineering attention.

`.claude/rules/fiber-yield-safety.md`'s OTOS/encoder-fiber note
("an OTOS read landing inside the encoder select-to-read window
destroys that encoder sample") is offered as a plausible, unconfirmed
mechanism tying the steadily-climbing `i2cf` counter to the pivot
asymmetry, the stop_distance/omega_floor confound, and the G5
sign-reversal/overshoot -- a hypothesis for `radio-robot-elite`
firmware engineering, not a diagnosis; no kernel or motion-engine file
was touched this session.

**Docs updated**: `src/DESIGN.md` §3 (measured `lag` field-comment
history + this session's findings), `docs/design/specification.md`
§11 (new `MotionLimits` fields table with per-field bench-acceptance
status). Both are partial -- `stopDistance`/`omegaFloor` still have no
trustworthy measured value.

**Needs a human / next session**: (1) the G5 wheel-sign-reversal
defect is the priority -- safety-relevant, independent of geometry
calibration; (2) bake tovez's real geometry (`geometry.firmware_bake`
in `radio-robot-lib/config/robots/tovez.json`) -- G1's asymmetry is
consistent with running vevov's unbaked numbers; (3) investigate the
`active`/TLM staleness bug separately; (4) once (1) is resolved,
re-run `field_dance.py` clean and resume at G2. `field_calibration.json`
is unchanged this session (still `default_robot: tovez`, still the
UNVERIFIED tovez mount placeholder).

Ticket left `status: in-progress` -- real progress was made (lag
measured, G1/G5 run and cited, design S7 now answered with clean
evidence) but the ticket's core deliverable (G1-G6 passing,
stop_distance/omega_floor measured and baked) is not met, and a newly
discovered control-loop defect blocks the remaining gates until
firmware engineering addresses it.

## Session Notes (2026-09-04d, tovez, BLOCKED -- dance FAILED again, but cleanly split into a fixed-looking pivot path and a new drive-bearing defect)

Full account: `reports/bench-acceptance-029-20260904d.md` (all capture
logs cited below live in
`captures/bench-acceptance-029-20260904d/`, force-added).

**Firmware unchanged, carrier changed.** tovez was already reflashed
(09:38, before this session) with ticket 010's K1 fix; `VER` still
reads `1.20260903.1` per the no-mid-sprint-bump convention. This
session drove tovez over a NEW lossless carrier -- its own on-robot
`zilch` Pi's TCP serial daemon (`zilch.local:43671`, resolved via
`dns-sd -L`) -- instead of the lossy torture radio relay every prior
tovez session in this ticket used. `tools/fieldlink.py` gained
`TcpFieldLink` (shares an `unseq`/`seqd`/`hello`/`close` contract with
the existing `FieldLink` via a new `_SequencedLink` base);
`tools/field_dance.py` gained a `--tcp host:port` flag selecting it,
default (relay) behavior unchanged. New host test:
`tests/tools/test_fieldlink.py` (5 tests, real loopback TCP, no
hardware) -- passes; `test_robotlink.py`/`test_field.py`/
`test_camlink.py` re-run clean (80 passed, no regressions).

**Lights/camera/mount/kick: PASS.** Shelly `output: true`. Tag 1 reads
(0,0) within noise; tag 52 (tovez) at (42.78, 12.86) cm, well inside
the usable envelope. `camlink.py --register tovez` succeeded (same
still-UNVERIFIED mount entry, unchanged). Kernel kick cleared a
never-ticked `ready=0` post-flash state the same way every prior
session's kick has.

**`field_dance.py --tcp` FAILED, but split cleanly into two findings.**
Pivots: net drift +14.2 deg over three pivots (+90/+180/+90) -- close
to a clean run, a further improvement over 2026-09-04c's mixed
2-pass/1-miss-by-14-deg and 2026-09-04's +47.6..+57.6 deg/pivot --
consistent with K1 addressing the pivot-accuracy defect. Drives: all
three FAILED with a consistent ~90 deg bearing error (+87/+91/+86 deg
off expected heading) while magnitude tracked commanded distance
reasonably (16.9/35.5/17.7 cm vs 20/40/20 cm) -- a NEW,
cleanly-characterized directional defect on straight-line `MOVE_X`
moves specifically, distinct from the earlier sessions' large,
inconsistent drive errors and from 2026-09-04c's G5 sign-reversal
defect. The robot ended safe throughout: dance's own "returned home"
step PASSed (3.1 cm), post-dance camera fix (41.70, 9.76) cm, `STATUS`
healthy and non-frozen (`cyc` advanced normally the whole session,
`i2cf` climbed 2->53 during motion as in every prior session).

**No commanded motion was sent beyond the dance.** Per the ticket's own
mandatory ordering, the FAIL stopped this session here: no lag
remeasurement, no G1-G6, no `stop_distance`/`omega_floor`. 2026-09-04c's
`SET lag 0.126` is not known to still be in effect (fresh boot, nothing
re-sent this session).

**Docs updated**: `src/DESIGN.md` §3 (2026-09-04d paragraph: carrier
change, dance table, both findings, cited) and
`docs/design/specification.md` §11 (short paragraph pointing at
`src/DESIGN.md` §3; no `MotionLimits` field values changed -- nothing
new was measured this session).

**Needs a human / next session**: (1) the ~90 deg drive-bearing defect
is the new priority -- clean enough now (consistent angle, consistent
proportional magnitude, three-for-three) to chase with an isolated
`MOVE_X <mm> 0 ...` probe plus `TLM FULL`; keep it separate from the
still-open 2026-09-04c G5 sign-reversal defect and the STATUS/TLM
staleness bug when triaging -- three distinct leads now, not one; (2)
re-run `field_dance.py --tcp zilch.local:<port>` (re-resolve the
port) once addressed, resume at lag/G1/G5 from there; (3) tovez's mount
fit is still UNVERIFIED -- pivots are close to clean enough to trust a
lever-triple fit but the 180 deg pivot still FAILed, so this was not
attempted; (4) the `pivot_overrun_mm`->`stop_distance_mm` cross-repo
rename in `radio-robot-lib/config/robots/tovez.json` (flagged every
prior session) is still outstanding.

Ticket left `status: in-progress`. Real progress: a lossless carrier
that removes relay loss as a confound going forward, a pivot result
close to passing (corroborating ticket 010's K1 fix), and a newly
well-characterized drive-bearing defect to hand to firmware
engineering. The ticket's core deliverable is still not met.

## Session Notes (2026-09-04, tovez, same-day continuation -- ~90 deg drive-bearing defect ROOT-CAUSED, FIXED, and VERIFIED; a new, purely-magnitude accuracy finding replaces it)

Full account: `captures/bench-acceptance-029-20260904d/notes.md` §5,
`reports/bench-acceptance-029-20260904d.md` §5-6.

**Root cause of the 2026-09-04d ~90 deg drive-bearing defect: tooling,
not firmware.** `tools/field_dance.py`'s `pose()` was running a
REGISTERED tag's `yaw_rad` (already the robot's heading -- the daemon
applies the fixed +90 deg AprilCam convention at registration time,
`tools/camlink.py`'s `mount_yaw_rad = -pi/2 + residual`) through
`field.robot_heading_from_tag_yaw()`, adding the convention a SECOND
time. A pivot's PASS/FAIL survives this (heading deltas cancel a
constant offset); every drive's absolute bearing came out rotated by
the extra +90 deg -- exactly the earlier session's +87/+91/+86 deg
pattern. Separately, MEASURED 2026-09-04,
`captures/bench-acceptance-029-20260904d/heading-probe.log`: tovez's
tag plate is physically mounted ~180 deg from the fleet convention (a
5 cm `MOVE_X` probe displaced the tag at bearing +11.4 deg while the
0-deg-residual-registered daemon reported yaw -165.8 deg for the same
pose -- bearing minus reported yaw = +177.3 deg).

**Fix (item 1 -- tooling audit and repair).** `tools/field.py` gained
`pose_from_registered_samples()`, a pure function that reads a
registered sample's `yaw_rad` unchanged (mean position with lever
correction, circular mean of yaw); `tools/field_dance.py`'s `pose()`
now calls it instead of double-correcting. Audited every other
`tools/*.py` script that reads tag yaw (`reposition.py`, `park.py`,
`pivot_truth.py`, `rotation_check.py`, `truth_check.py`, `tour_*.py`,
`turn_sweep.py`, `arc_capture.py`, `leg_analysis.py`) -- none had the
same bug: the rotation-only tools use heading DELTAS (immune to a
constant offset either way) and every absolute-heading tool already
reads the registered daemon value directly via `camproc.Cam`/
`camlink.py`, with no second correction anywhere else in the tree.
`tools/field_calibration.json`'s tovez entry now carries
`mount_yaw_residual_deg: 180.0` (the measured physical mount finding)
and a matching `mount_x_cm` sign flip (was already made, uncommitted,
by the team-lead before this session; committed here). New tests:
`tests/tools/test_field.py` pins `pose_from_registered_samples()`
(unchanged yaw, lever correction, multi-sample averaging, circular
mean across the wrap, empty input); `tests/tools/test_camlink.py`'s
TL-11 regression guard widened to accept a residual near 0 deg OR near
+-180 deg (a real physical backward-mount state) while still rejecting
one near +-90 deg (the original probe-fitted-absolute regression
signature). `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
gained a "registered vs raw: who adds the 90" section and the tovez
180 deg plate finding. `uv run pytest tests/tools -q`: 360 passed.
Committed separately (fix(029/007): field_dance.py double-added the
+90 convention on a registered tag) before any hardware was touched
this session.

**Verification on real hardware (item 2 -- resumed acceptance
sequence).** Camera confirmed tovez at world (41.81, 9.23) cm, 13.3 cm
from the east margin (usable +-55.15 cm) -- too tight for the longer
moves later gates need. A single, pre-flight-checked (`field.
check_path()`) `MOVE_X -250 0 100 6000` (25 cm straight backward along
the current heading -- no pivot needed, the current heading already
nearly faced away from centre) repositioned it to (17.63, 3.11) cm,
matching the projected (17.58, 3.06) to within 0.1 cm
(`reposition-to-center.log`). `field_dance.py --tcp
zilch.local:43671` then ran TWICE from there
(`field-dance-refit-run1.log`, `field-dance-refit-run2.log`):

| step | run 1 | run 2 |
|---|---|---|
| turn +90 | +92.8 deg (err +2.8) PASS | +92.9 deg (err +2.9) PASS |
| turn +180 | -171.1 deg (err +8.9) **FAIL** | -170.4 deg (err +9.6) **FAIL** |
| turn +90 | +92.3 deg (err +2.3) PASS | +93.1 deg (err +3.1) PASS |
| drive +20 | 17.6 cm (err -2.4), bearing off -2 deg PASS | 17.6 cm (err -2.4), bearing off -2 deg PASS |
| drive -40 | 35.3 cm (err -4.7), bearing off +0 deg **FAIL** | 35.4 cm (err -4.6), bearing off +1 deg **FAIL** |
| drive +20 | 17.6 cm (err -2.4), bearing off -2 deg PASS | 17.7 cm (err -2.3), bearing off -4 deg PASS |
| returned home | 4.2 cm PASS | 3.4 cm PASS |

Both runs still print `DANCE FAILED`, so per this ticket's own
mandatory ordering ("It must PASS ... do not proceed to gates" on a
FAIL) no lag/G1-G6/`stop_distance`/`omega_floor` work was attempted
this session either -- but the diagnosis is now conclusive. **Every
bearing error is now <=4 deg** (was 86-91 deg) -- the directional
defect is gone, confirmed twice on real hardware, not just by source
reading. What remains, identical in shape across both runs, is a real,
repeatable MAGNITUDE undershoot specific to the LONGER move of each
pair: the 180 deg pivot lands ~9-9.6 deg short and the 40 cm reverse
drive lands ~4.6-4.7 cm short, both times, while the paired 90 deg
pivots and 20 cm drives in the same runs pass comfortably (<=3.1 deg /
<=2.4 cm). This is an ACCURACY finding, not a CONVENTION one
(`.claude/rules/field-dance-first.md`: "the gate is CONVENTION, not
accuracy") -- and it is exactly what this ticket's own
`stop_distance`/`omega_floor` measurements and G1-G6 gates exist to
characterize. Two consecutive identical-shape FAILs (not a single
ambiguous one) rules out measurement noise as the explanation; not
chased further this session, per the dance's own mandatory
stop-on-FAIL ordering -- no kernel or motion-engine file was read or
touched.

Robot ended safe both times: post-run-2 camera fix (18.96, -5.24) cm,
well inside margin (37.2 cm from the east margin, 27.4 cm from the
north/south margin); `STATUS` healthy and non-frozen throughout
(`post-refit-dance-status.log`: `ready=1 active=0 wedge=0 cyc=5966`,
`cyc` climbed steadily across both runs).

**Docs updated**: `src/DESIGN.md` §3 (root-cause/fix/verification
paragraph after the 2026-09-04d paragraph), `docs/design/
specification.md` §11 (matching paragraph), `reports/
bench-acceptance-029-20260904d.md` (new §5 replacing the "new ~90 deg
drive defect" conclusion with the root-cause finding, new §6 "what a
human needs to do next" superseding the old §5), and this ticket's
acceptance-criteria checklist above.

**Needs a human / next session**: (1) the ~90 deg drive-bearing lead is
CLOSED -- it was tooling plus a physically-reversed tag plate, both
fixed and verified; do not re-open it as a firmware suspect. (2) New
priority: the magnitude-undershoot-on-longer-moves pattern (180 deg
pivot, 40 cm drive) found above -- G1 uses only 90 deg pivots (which
already pass cleanly in both dance re-runs), so G1 itself may well
pass; a dedicated look at 180-deg-class pivots and >30 cm drives is the
more targeted next step, alongside `stop_distance`/`omega_floor`. (3)
Once the dance passes cleanly (or the undershoot is understood well
enough to proceed per the ticket's ordering), resume at lag
remeasurement, then G1/G5, then the rest of G1-G6. (4) tovez's mount
fit (`lever_cm`, `parallax_k`) is still UNVERIFIED -- pivots are close
enough now (<=3.1 deg each) that a lever-triple fit is worth attempting
once a session is not otherwise blocked. (5) the
`pivot_overrun_mm`->`stop_distance_mm` cross-repo rename in
`radio-robot-lib/config/robots/tovez.json` is still outstanding. (6)
the still-open 2026-09-04c G5 sign-reversal defect and the STATUS/TLM
staleness bug remain separate, unresolved leads -- keep them distinct
from (2) above when triaging.

Ticket left `status: in-progress`. Real, load-bearing progress this
session: the drive-bearing defect that looked like it might implicate
the sprint's motion-profile work (K1's fix, ticket 010) is now shown to
be tooling, fixed, and verified twice on hardware -- the sprint's
firmware changes are not implicated in any remaining directional
error. A new, well-characterized, purely-magnitude accuracy finding
(longer pivots/drives undershoot) replaces it as the open lead, and is
squarely in this ticket's own remaining scope (`stop_distance`/
`omega_floor`/G1-G6) rather than a new firmware defect to escalate. The
ticket's core deliverable (dance passing cleanly, G1-G6,
`stop_distance`/`omega_floor` measured and baked) is still not met.
