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
- [ ] G1-G6 all pass, each cited with its capture artifact
      (`.claude/rules/measurement-citations.md`). NOT RUN 2026-09-04 --
      blocked behind the failed dance above; driving a robot that
      cannot reliably stop where commanded is unsafe.
- [ ] `stop_distance` and `omega_floor` measured, recorded in
      `firmware_bake.stop_distance_mm` and `MotionLimits::omegaFloor`'s
      default, and cited with their capture artifacts. NOT MEASURED
      2026-09-04 -- same blocker.
- [ ] `src/DESIGN.md` §3 updated (real file) with the measured
      constants' field-comment history. NOT DONE -- no measured
      constants exist yet to record.
- [ ] `docs/design/specification.md`'s constants table updated. NOT
      DONE -- same reason.
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
- [ ] Design §7's predicted "after" numbers (already confirmed on ideal
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
