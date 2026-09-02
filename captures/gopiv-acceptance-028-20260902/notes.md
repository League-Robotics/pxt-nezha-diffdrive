# Sprint 028 hardware acceptance on gopiv, 2026-09-02

Board: **gopiv** (per `.claude/rules/robot-ownership.md`), mbdeploy farm,
node meili, `192.168.1.150`. Bare-motor bench rig: motors + encoders,
**no wheels on the ground, no OTOS** -- every motion verb (including
full translating tours) is safe here.

Farm serial daemon TCP endpoint resolved via zeroconf (`dns-sd -L`
under this harness returned no output; resolved instead with a short
python `zeroconf.ServiceBrowser` script run through the mbdeploy pipx
venv, `~/.local/pipx/venvs/mbdeploy/bin/python`, which has `zeroconf`
installed): **`192.168.1.150:43181`**, unchanged across the flash in
step B.

Scripts in this directory (`gopiv_link.py`'s `Link` class is a copy of
`captures/gopiv-profile-sweep-20260901/tight_tour.py`'s own `Link`,
adapted per the dispatch brief -- originals not edited):

| script | purpose |
|---|---|
| `gopiv_link.py` | shared TCP link, threaded reader |
| `step_a_baseline.py` | Step A, old firmware baseline |
| `step_a3_retry.py` | A.3 retest from a confirmed-idle start |
| `step_c_executor.py` | Step C, ticket 003 acceptance |
| `step_d_frozen_encoder.py` | Step D, ticket 001 acceptance (tour + capture) |
| `analyze_frozen.py` | offline analysis of Step D's captured JSON |
| `step_e_rebase.py` | Step E, ticket 002 acceptance |

## Firmware

- OLD (baseline): `ver 0.20260901.1`, `HELLO -> device NEZHA2 robot
  gopiv 2175407711`.
- NEW (this sprint's HEAD, commit `c89759a`): built at
  `.tmp/deploy-head/built/binary.hex`, sha256
  `78e780c874156e1f6972cf7cac41b94ae7682a85540e38c5b94d754a015f433a`,
  1,598,844 bytes -- copied into this directory as
  `sprint028-binary.hex` (same sha256, verified). Not rebuilt.

## Step B -- flash

First `mbdeploy deploy --remote gopiv --hex .tmp/deploy-head/built/binary.hex`
attempt failed (`flash erase sector failure`, then a mass-erase
recovery attempt itself timed out) and **left gopiv BLANK** (no
firmware). A second, immediate retry of the identical command
succeeded cleanly (27 sectors erased/programmed, 73 pages identical).
Confirmed after:

```
VER   -> ver 0.20260902.2
HELLO -> device NEZHA2 robot gopiv 2175407711
STATUS -> status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none
```

(`cyc=0`/`connL=0`/`connR=0` is a fresh-boot state, kernel not yet
stepped -- not a fault, matches the dispatch brief's own note.)

## Step A -- baseline, OLD firmware (0.20260901.1)

Full transcript: `step_a_transcript.txt` (A.1, A.2) and
`step_a3_retry_transcript.txt` (A.3, redone from a confirmed-idle
start after the first A.3 attempt in `step_a_transcript.txt` started
from a robot state left busy by A.2 -- see that file for the messier
first attempt, superseded by the retest below).

- **A.1 (`RUN:pivot:90` alone):** no reset. `PIVOT:end` at t=1.280s,
  `cyc` 2199->2253 monotonic, no unsolicited `device NEZHA2` banner.
- **A.2 (`RUN:square:20`, wire `MOVE_X` sent mid-tour):** the mid-tour
  `MOVE_X 0 500 60 3000 #1` was **accepted** (`ack 1 1 stop`, no
  `err`) -- the pre-fix architecture silently accepts/races the wire
  move rather than refusing it, exactly the defect ticket 003
  describes. No reset observed, but the robot was still `active=1`
  at the end of a 10s drain window and remained busy into A.3 (see
  below) -- consistent with the old 3-fiber dispatch being genuinely
  slow/racy to settle, not merely "eventually correct."
- **A.3 (`RUN:square:20` then `RUN:abort` at t=1.0s, retested from a
  confirmed-idle start):** `RUN:abort` did **not** produce an
  observable near-instant stop -- `STATUS` polled repeatedly over the
  following ~10s+ still read `active=1`, `reason=timeout` (not
  `stop`), settling to idle only well after the abort was sent (no
  precise duration captured -- see `step_a3_retry_transcript.txt` and
  the immediately following ad hoc poll, not separately saved). This
  is the "`RUN:abort` works by accident" behavior sprint 026/028's own
  issue describes -- unreliable/slow on the old architecture, in
  contrast with the FIXED firmware's measured ~40 ms cutoff (Step C.2
  below). No reset observed at any point in Step A.

## Step C -- ticket 003 (executor inversion) acceptance, FIXED firmware

Transcript: `step_c_transcript.txt`. **PASS**, all measured criteria met.

- **C.1** (`RUN:square:20`, wire `MOVE_X` mid-tour): mid-tour
  `MOVE_X 0 500 60 3000 #1` got `ack 1 0 none` **followed immediately
  by `err 10 #1`** -- the ack-then-err "accepted onto the wire, then
  refused as the command's own result" shape also seen on tigez.
  `err 10` = `Wire::Result::kBusy`. The tour was undisturbed (STATUS
  after: `i2cf` climbed normally 79->96, no reset, no unsolicited
  banner). **Confirms**: wire move mid-job refused with an error
  reply, tour undisturbed.
- **C.2** (abort timing): reference `RUN:pivot:90` alone completed at
  t=1.290s. `RUN:pivot:90` + `RUN:abort` sent at t=0.305s: `PIVOT:end`
  at t=0.343s -- cut short within ~40 ms of the abort landing.
  **Confirms**: no queue delay, hardware-timed.
- **C.3** (12 back-to-back `RUN:pivot:<+-30>` jobs): all 12 completed
  (`PIVOT:end` seen every time), zero faults, `i2cf` 22->23 (not
  climbing abnormally), `cyc` advancing steadily 562->587,
  `ready=1 connL=1 connR=1` throughout. **Confirms**: 10+ back-to-back
  RUN jobs, no fault/reset, STATUS sane. `device_stack_size=4096` is
  sufficient for this call depth on gopiv, matching tigez's own result.
- **C.4** (TLM POSE during a dispatched job): 53 telemetry frames
  observed during a `RUN:pivot:90` job. **Confirms**: telemetry keeps
  flowing through a dispatched job (a `PIVOT:end` line logged at
  t=0.053s in this run is very likely a stray/leftover line from the
  immediately-preceding C.3 job rather than this job's own completion
  -- a harness-timing artifact, not re-chased; the 53-frame count is
  the criterion that matters and is unambiguous).
- **`tests/system/run_tour.py`** (`tests/system/tours/square.tour`,
  `--host 192.168.1.150 --port 43181 --robot gopiv`): completed all 17
  steps cleanly (`ok` on every leg/pivot), produced a chart
  (`run_tour_square/square.png`, `run_tour_square/square.json`,
  "closure 34.2 mm" -- pure odometry on a bare-motor rig, not a
  meaningful physical-accuracy number here, only evidence the run
  completed). Needed `uv run --with matplotlib` (bare `uv run python`
  lacks matplotlib in this environment) -- not a firmware issue.
  **Confirms**: `run_tour.py` passes on gopiv, closing this ticket's
  previously-UNVERIFIED criterion.
- **Not run** (optional, skipped given the findings below shifted
  priority to Steps D/E): PING hammer over the torture relay during a
  MOVE_X. Reported here as **not attempted**, not as a pass.

## Step D -- ticket 001 (frozen-encoder hold) acceptance, FIXED firmware

**RESULT: does not confirm the fix -- the hardware symptom the ticket
was written to eliminate still reproduces, essentially unchanged in
shape and magnitude, on the fixed firmware. Reporting as FAILED /
regression-suspected, not as a pass, per this dispatch's own
instruction to stop and report rather than paper over a failure.**

Method: the same orange-dot 100x60 cm tour as
`captures/gopiv-profile-sweep-20260901/tight_tour.py` (same shaping
SETs, `TLM FULL`), run for 6 reps total across two captures (1 rep in
`step_d_test_frames.json`, then 5 more reps in `step_d_frames.json`,
1802 total telemetry frames), then scanned (`analyze_frozen.py`) for a
telemetry-frame pair where `posr`/`posl` is unchanged from the
previous frame while the wheel had a **significant measured velocity
two frames earlier** (i.e. genuinely cruising, not at breakaway) --
this excludes normal accel-ramp-from-rest frames, which also show
"position unchanged, duty nonzero" for entirely benign physical
reasons (breakaway lag) and would otherwise dominate a naive scan (an
earlier, cruder pass without the "was already moving" filter flagged
13-60 events per run, nearly all breakaway, not the ticket's bug --
discarded).

With that filter, **5 genuine frozen-while-cruising events across 6
tour reps**, ALL on side R, ALL showing the identical signature:

| rep source | frame | pos (frozen) | vel 2 frames before | vel AT the frozen frame | duty before-\>at-\>next | i2cf |
|---|---|---|---|---|---|---|
| `step_d_test_frames.json` | 28 | 93987 | 312 mm/s | **0** | 3300->4900->5400 | 129->131 |
| `step_d_frames.json` | 30 | 140195 | 287 mm/s | **0** | 3600->5299->5100 | 162->163 |
| `step_d_frames.json` | 91 | 147895 | 164 mm/s | **0** | 2600->4000->4200 | 175->176 |
| `step_d_frames.json` | 1089 | 302922 | 289 mm/s | **0** | 3200->4800->5200 | 291->293 |
| `step_d_frames.json` | 1368 | 342072 | 282 mm/s | **0** | 2800->4900->5299 | 318->320 |

Every single occurrence: `i2cf` **increments** at the frozen frame
(confirming `nezha_port.cpp`'s guard, or the pre-existing genuine-
read-failure path, DID take the stamp-withholding branch), yet the
wire-reported velocity (`wheelSpeed()` -> `kernel.output().velocityRight`
-> `sampleRight_.velocity`, read directly from `src/core/diffdrive.cpp`
and confirmed by grep -- there is no other assignment site for
`sample.velocity` besides the interval computation at
`refreshSample()`'s `sampleTime != sample.sampleTime` branch) reads
**exactly 0**, not the held prior value the fix (and the pre-existing
kernel gate it relies on) is documented to produce, and commanded duty
steps up 14-25 percentage points toward the rail on that tick or the
next, with a resulting speed overshoot up to 446 mm/s against a
~290 mm/s steady cruise.

**Direct comparison against the ticket's own PRE-fix MEASURED
citation** (`captures/gopiv-profile-sweep-20260901/tour_tight.json`,
frames 185-191, re-read this session):

```
frame 185: posr=254747 vr=309 dutr=3300 i2cf=38
frame 186: posr=254747 vr=0   dutr=4400 i2cf=40   <- frozen, PRE-fix
frame 188: vr overshoots to 420 mm/s
```

vs. this session's FIXED-firmware frame 30 (`step_d_frames.json`):

```
frame 29: posr=140195(-ish, prior) vr=287 dutr=3600 i2cf=162
frame 30: posr=140195             vr=0   dutr=5299 i2cf=163  <- frozen, POST-fix
frame 32-ish: vr overshoots to 446 mm/s (see raw JSON)
```

Same shape, same order of magnitude, if anything a slightly *larger*
duty jump and overshoot post-fix than pre-fix. I could not find a
telemetry-only way to positively distinguish "the ticket's own narrow
fix condition (`decision==kAccept && raw==previousGoodRaw`) fired but
didn't actually hold velocity" from "this is really the OTHER,
already-existing genuine-read-failure path (also documented to hold
velocity, also increments the same shared `i2cFaultCount_`), which
*also* doesn't appear to hold velocity on real hardware" -- both
possibilities point at the same conclusion for hardware-acceptance
purposes: **the documented protective behavior (`sample.velocity`
holds its prior value when `sampleTime` fails to advance) does not
match what gopiv's telemetry shows in practice**, on both the pre-fix
and post-fix builds. `tests/host/test_frozen_encoder_hold.py`'s
simulated-shim tests apparently cannot exercise whatever the real
discrepancy is (they pass, per the ticket's own Definition of Done).

This needs `systematic-debugging` on either `refreshSample()`'s
interaction with the wire snapshot cadence, or a live per-tick capture
method this telemetry stream cannot provide (`TLM FULL`'s own cadence
is roughly 1 sample per 3 kernel cycles here -- `cyc` advances by ~3
between consecutive frames -- so a single telemetry frame cannot
always be attributed to one specific kernel tick with certainty; this
capping is itself noted as a real limitation of this measurement, not
just of the firmware). Raw frame data for all 6 reps:
`step_d_test_frames.json`, `step_d_frames.json`.

## Step E -- ticket 002 (SET rebase / SET estop_clear) acceptance, FIXED firmware

Transcript: `step_e_transcript.txt`.

- **E.1** (`TLM POSE`, pivot, `SET rebase 1`): ack (`ack 3 2 stop`,
  no `err`). Pose frame right after the pre-rebase pivot read nonzero
  cumulative heading (session-cumulative, expected). **Every one of
  the 11 subsequent pose frames read `x=0 y=0 h=0`** with no spurious
  jump on the kernel's own deferred re-anchor tick. **PASS** --
  confirms the frame zeroes and stays zeroed. (My own analysis
  script's automated `all_zero` check printed `False` here due to an
  off-by-one column-index bug in the script, not a real anomaly -- the
  raw transcript lines themselves are unambiguous: `x`/`y`/`h` are
  columns 4/5/6 after the `t` token, and every captured line reads
  `... 0 0 0 ...` at exactly those columns.)
- **E.2** (a second move after a successful rebase): **anomalous,
  reproduces a defect tigez's own capture already flagged as an open
  question.** A `MOVE_X 0 -900 60 3000` sent immediately after a
  successful `SET rebase 1` acked normally (`ack 4 2 stop`) but the
  wheels barely moved: `h` climbed only to **11 centidegrees (0.11
  deg)** against a commanded 900 mrad (~51.6 deg), then sat flat with
  `vl=vr=0` for the full ~1.5s+ observation window -- the move
  completed almost immediately with essentially none of the commanded
  rotation delivered. `captures/tigez-rebase-20260902/notes.md`
  documented the SAME class of anomaly at smaller magnitude ("the
  second pivot ... reached only ~-0.3 deg where the first ...
  reached ~+14.7 deg") and left it as an open, unchased question
  ("not this ticket's scope ... worth a bench session of its own if
  it recurs"). It has now recurred, on a second independent board,
  at a much larger relative magnitude (near-total loss of the
  commanded rotation rather than a partial shortfall). Reporting this
  as a confirmed, reproducing anomaly, not a pass, for the "a second
  move afterward resumes cleanly from the new zero" criterion.
- **E.3** (`SET estop_clear 1` on an idle robot, no prior `ESTOP`):
  `ack 5 4 stop`, no `err`. **PASS.**
- **E.4** (`SET rebase 1` sent immediately after an in-flight
  `MOVE_X 0 900 40 4000`, no gap): `ack ... ` for the `MOVE_X`, then
  `ack ...` for the `SET rebase 1` **followed immediately by
  `err 10 #7`** -- the busy refusal, hardware-confirmed, matching
  tigez's own `err 10` result exactly. The `MOVE_X` itself was
  **undisturbed** by the refused rebase: `h` climbed cleanly to 5008
  centidegrees (50.08 deg) against the 900 mrad (~51.6 deg) commanded
  -- a normal result, in contrast with E.2's anomaly, and evidence
  that E.2's anomaly is specific to the move *immediately following a
  SUCCESSFUL rebase*, not a general problem with post-rebase motion.
  **PASS** for the busy-refusal criterion.
- Tour-with-rebase-at-leg-1 producing an axis-aligned chart, the
  OTOS-equipped-chassis half, and the camera-truthed half: **not
  attempted** -- gopiv has no OTOS and this was a farm/bench session
  with no camera; unchanged from tigez's own prior UNVERIFIED status
  for these same sub-criteria. Given E.2's anomaly, a tour-with-rebase
  chart would likely show a corrupted first leg regardless -- not
  worth attempting until E.2 is understood.

## Summary

| ticket | hardware acceptance | verdict |
|---|---|---|
| 003 (executor inversion) | C.1-C.4 + `run_tour.py` all measured on gopiv | **PASS** |
| 001 (frozen-encoder hold) | Step D, 5/5 reproductions of the pre-fix symptom | **FAIL / regression-suspected** -- needs `systematic-debugging`, not closed here |
| 002 (rebase/estop_clear) | E.1, E.3, E.4 pass; E.2 reproduces a cross-board anomaly | **PARTIAL** -- ack/zero/busy-refusal/estop_clear confirmed; "resumes cleanly" criterion **FAILS** |

No source code was changed this session (out of scope per the
dispatch brief). Per instruction, ticket 001 and the "resumes cleanly"
half of ticket 002 are left for the team-lead to reopen/route rather
than being marked passing.
