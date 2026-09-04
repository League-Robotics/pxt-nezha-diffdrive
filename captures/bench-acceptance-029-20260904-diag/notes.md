# Sprint 029 ticket 007 -- diagnostic session, 2026-09-04b (tovez)

**No commanded motion was sent this session. No new hardware
measurement exists in this directory.** This session was scoped as
diagnostic re-analysis of the 2026-09-04 evidence
(`captures/bench-acceptance-029-20260904/`) plus an attempted live
re-run of the procedure in this ticket's dispatch. The live re-run
could not start: both carriers this repo supports were unreachable
from this machine this session (see §1). Everything in §2-§5 below is
analysis of the EXISTING 2026-09-04 capture files and this repo's own
source, not a new measurement -- every number is cited to the file it
comes from, per `.claude/rules/measurement-citations.md`.

## 1. Environment blocker: no reachable carrier to tovez this session

Both carriers `.claude/rules/connecting-to-a-robot.md` documents for a
playfield robot were tried and both failed, with the exact commands and
output below.

**Radio relay (USB) -- no relay hardware present on this machine.**

```
$ /Users/eric/.local/bin/mbdeploy probe
ENUM  CONN  DEVICE NAME  COMMON NAME  ROLE          PORT   UID
1     no    gopiv        robot        NEZHA2               ...
2     no    tovez        robot        NEZHA2               ...
3     no    vevov        robot        NEZHA2               ...
4     no    zetuv        robot        NEZHA2               ...
5     no                                                    ...
6     no    tigez        robot        NEZHA2               ...
```

Every entry reads `CONN=no` -- this is the cached registry
(`.claude/rules/playfield-testing.md`: "`mbdeploy probe`'s ROLE column
is a cached registry, not a live read"), not a live USB scan result,
and it does not even carry a `zavaz` row. `ls /dev/cu.*` on this Mac
shows no DAPLink-style `/dev/cu.usbmodem*` device at all -- only
Bluetooth, a debug console, a `wlan-debug` pseudo-device, and one
`wchusbserial212240` (a CH340-class adapter, not a micro:bit; not
attempted, since `open_link(radio=True)` resolves the relay port itself
via `probe_port('zavaz')`, which found nothing). `mbdeploy list
--remote` (the farm-node path) returned an empty table -- no farm node
is reachable this session either. `robotlink.open_link(radio=True,
robot='tovez')` therefore fails at its own port-not-found check before
ever reaching the robot:

```
zavaz relay not found by `mbdeploy probe` -- is it plugged in? (never
hard-code a port; it moves on replug. last known: /dev/cu.usbmodem2121302)
```

**WiFi TCP -- tovez not discoverable on this network.**

```
$ uv run python tools/wifilink.py --tcp --robot tovez PING STATUS
wifilink: tovez not found by mDNS (tovez.local) or by broadcast HELLO
on :7654 within 8s -- is the module joined? (watch the robot's USB for
`DBG:wifi state=5`)
```

A direct `dns-sd -B _robotlink._tcp local.` browse (6 s window) found
no advertised service at all. This machine IS on the playfield's LAN
segment -- `curl` to the Shelly light controller at `192.168.1.122`
succeeds (`output: true`, confirmed before and unaffected by any of
this) and `ifconfig` shows `en0`/`en1` on `192.168.1.0/21` -- so this is
not a general network-access problem; tovez's WiFi radio specifically
did not answer, consistent with it not being joined to a network this
session (matching the wedge/reset history from the prior 2026-09-04
session, where the last confirmed state left the robot idle after a
suspected anomaly and no explicit re-join was performed since).

**Conclusion: this ticket's on-hardware procedure (steps 1-6 of the
dispatch) could not be run this session.** This is an infrastructure
access gap (no physical relay, no WiFi join), not a firmware or process
finding, and per `.claude/rules/mcp-required.md`/the programmer agent's
Guard-Blocks discipline the right move is to stop and report rather
than fabricate or approximate a result. **A human needs to either plug
the zavaz relay into whichever machine runs the next session, or get
tovez re-joined to WiFi (power cycle is the usual fix per prior
sessions' notes) and confirm `tovez.local` resolves,** before this
ticket's live procedure can run again.

## 2. Re-analysis of the 2026-09-04 evidence: the geometry-bake check
   (dispatch step 1's first half) -- answerable from source, no
   hardware needed

The dispatch asked to compare `travel_calib`/`track_width`/
`rotational_slip` GET values against what `make_deploy.py --robot
tovez` should have baked. Read directly (no robot needed):

- `radio-robot-lib/config/robots/tovez.json`'s `geometry` object has NO
  `firmware_bake` key at all (`geometry.firmware_bake` is absent;
  confirmed with `json.load(...).get('geometry',
  {}).get('firmware_bake')` -> `None`).
- `tools/make_deploy.py:1001-1022` (`_read_robot_firmware_bake`)
  returns `{}` for a config with no `firmware_bake` block -- this is
  explicitly NOT an error (`make_deploy.py:1005-1008`: "a MISSING
  config file is not fatal: geometry baking is opt-in and most robots
  do not use it").
- `make_deploy.py:1041-1042` (`_inject_geometry`): `if not bake: return
  []` -- nothing gets substituted into the deploy-scratch copies of
  `motion_engine.h`/`motion_limits.h` for tovez.
- So GET should report this repo's own compiled-in defaults, not
  anything from `tovez.json`'s top-level `geometry.trackwidth: 115` /
  `geometry.rotational_slip: 1.0` (those ARE present in the file, but
  they are read by a DIFFERENT, unrelated project's config schema --
  see the caveat below -- and are not consulted by this repo's bake
  path at all without an explicit `firmware_bake` block).
- The compiled defaults, read directly from
  `src/motion/motion_engine.h`: `travelCalib_ = 0.7878f` (line 519),
  `trackWidth_ = 114.2f` (line 524), `rotationalSlip_ = 0.952f` (line
  556); `src/motion/motion_limits.h`: `stopDistance = 0.0f` (line 61,
  correctly zero -- this ticket's own §10.2 measurement is what is
  meant to populate it, and it has not run yet).

**Reading: no bake regression.** `make_deploy.py`'s own header comment
(lines 901-919) explains this exact case by name: "tovez's config says
trackwidth 115 / slip 1.0 where the firmware defaults it actually runs
are 114.2 / 0.952 ... injection ONLY when the robot's config carries an
explicit `geometry.firmware_bake` object." A live GET this session
would be expected to read back 0.7878 / 114.2 / 0.952 (travel_calib /
track_width / rotational_slip) if the firmware build matches this
repo's current source -- **and confirming that IS still a live-hardware
task**, since a GET could just as easily reveal a stale flash. This
paragraph only clears the "was the bake injection itself broken by
ticket 004" question, which does not need the robot.

**Caveat worth flagging, not chased further:** `radio-robot-lib/config/
robots/tovez.json` on this machine is NOT the small, this-repo-shaped
config the ticket's own dispatch prose implies (`firmware_bake.
stop_distance_mm`, etc., per S4.7/S8's own naming). It is a much larger
`schema_version: 2` document (PID gains, `planner_shaper` S-curve
fields, `wheel_control`, sprint numbers in the 100s-130s) that reads
like a different, considerably more built-out motion stack than this
repo's own `src/motion/*`. `_read_robot_firmware_bake()` handles this
gracefully (no `firmware_bake` key -> `{}` -> no injection, exactly as
designed), so it does not block anything here, but it is worth a human
confirming this is genuinely the config `make_deploy.py --robot tovez`
is meant to be reading, and not evidence of two different `tovez.json`
files under this same path across different checkouts of
`radio-robot-lib`.

## 3. Re-analysis of the 2026-09-04 evidence: GET field names
   (dispatch step 1's second half)

The dispatch's own field-name list includes `travel_calib` and
`track_width`. **Neither is a wire-exposed field.** Read directly from
`src/comms/wire_adapter.cpp`'s `kFields[]` table (lines 125-259): the
declared names are `max_duty, full_duty_velocity, pid_kp, pid_ki,
pid_i_max, accel_kaff, pid_max, twist_hold_gain, v_floor, pos_err_max,
stall_speed, stall_demand, stall_window, lambda_enabled, crawl_pulse,
default_cruise, rotational_slip, stall_clear, stop_distance, accel,
decel, v_max, jerk, omega_max, rebase, estop_clear, omega_floor,
arrive_dist, arrive_yaw` -- no `travel_calib`, no `track_width` (`grep
-n '"travel_calib"\|"track_width"' src/comms/wire_adapter.cpp` ->
no hits). This matches the S4.7 design intent noted right on
`trackWidth_`'s own declaration comment: those two fields "stay in
motion_engine.h," internal to `MotionEngine`, with no wire accessor. So
a live `GET travel_calib #n`/`GET track_width #n` would be EXPECTED to
answer `err 1` (`ERR_UNKNOWN`, `wire_handler.cpp:1145-1148`) on
correctly-behaving current firmware -- that is not evidence of a
regression, and the dispatch's own field list should drop these two
names for any future run (or re-read them as "expected to fail" rather
than as part of the pass/fail set).

The remaining question -- **whether the bare `GET #n` dump
(`evidence-get-and-status.log`: ack received, zero `get` lines) is a
tool/radio-loss artifact or a real regression in ticket 004's
`fieldCount()`/`fieldName()` enumeration, and whether individual named
`GET <name> #n` calls work where the bare dump did not** -- is
UNRESOLVED. It needs the live retest this session could not run (§1).
One relevant fact from the existing capture, though: the ack for that
bare GET (`evidence-get-and-status.log`: `ack 1 2 timeout`) shows
`done=2` -- i.e. by the time this GET ran, id 2 (the `MOVE_X` from
Probe 1, `evidence-pivot90-01.log`) WAS recorded as the last-completed
sequenced command, not stuck pending forever. That is independent
evidence the move in Probe 1 did reach some form of completion
(see §4) rather than hanging indefinitely, even though the GET dump
itself came back empty.

## 4. Re-analysis of the 2026-09-04 evidence: Probe 1
   (`evidence-pivot90-01.log`, `TLM POSE`, `MOVE_X 0 1571 100 5000`)

Exact numbers from the log, not re-derived: pre-move `TLM POSE` frames
(3 lines) all read `h=64152` at `now=682157/682213/682381`. The `MOVE_X`
ack line follows immediately (`ack 2 10 timeout` -- `done=10` here is
STALE, left over from the prior `field_dance.py` run's own last
completed id, matching the "lazy completion channel" reading: the ack
for a command answers with whatever `done`/`reason` the link already
had cached, not necessarily this command's own outcome). The first
captured `t` line during the move is `t 82 684653 ... h=74469`; the
last is `t 47 690501 ... h=74469` -- IDENTICAL to the first.

- **Gap before the first during-move frame:** `684653 - 682381 =
  2272 ms` (~2.3 s) with no `t` lines at all -- matches the dispatch's
  own framing exactly.
- **Odometry heading delta:** `74469 - 64152 = 10317` centidegrees =
  **+103.17 deg** on a commanded +90 deg (per MEMORY.md's "TLM units:
  ... h cumulative centideg").
- **Camera delta (independent instrument):** BEFORE
  `yaw_rad=2.6273 (150.53 deg)`, AFTER `yaw_rad=4.5485 (260.61 deg)` --
  **+110.08 deg** raw.
- **`h` is flat across the ENTIRE ~5.85 s during-move capture window**
  (`now` 684653 to 690501), not just at the two endpoints quoted in the
  original write-up.

**Reading:** a nominal 90 deg pivot at cruise 100 mm/s, using this
repo's own compiled defaults (`trackWidth_=114.2`,
`rotationalSlip_=0.952` -> effective track ~119.96 mm), has an expected
UN-ramped duration around 0.9 s (`omega = 2*100/119.96 = 1.667 rad/s`,
`1.571 rad / 1.667 rad/s = 0.94 s`); with accel/decel ramps, plausibly
1-1.5 s total -- far shorter than either the 2.27 s pre-capture gap or
the 5000 ms deadline. Since `h` is IDENTICAL at the very first captured
frame and stays identical through the last (2.27 s to 8.1 s after the
command), the simplest reading consistent with all of: (a) the short
expected move duration, (b) the flat `h` for the whole visible window,
and (c) `done` having advanced to id 2 by the next GET check (§3), is
that **the pivot physically ran to completion, overshot, and stopped,
all within that first 2.27 s gap** -- not that it spun continuously for
five seconds until a hard deadline. `reason=timeout` on every ack this
session (never `reason=stop`) is then better read as the "lazy,
resolved-on-the-next-line" quirk the dispatch describes, not literal
evidence the move ran its full clock.

This does NOT resolve the ~7 deg gap between the odometry overshoot
(+103.17 deg) and the camera overshoot (+110.08 deg) -- both instruments
agree there was a LARGE real overshoot (13-20 deg past commanded 90),
they just disagree on the exact size by an amount roughly consistent
with ordinary wheel scrub/slip (`rotationalSlip_=0.952` already prices
in ~4.8% typical scrub) but not conclusively so. Distinguishing "target
computed wrong" from "arrival detected late" needs per-tick telemetry
DURING the active pivot, which this capture does not have (the 2.27 s
gap is exactly the window where that distinction would show up) -- a
live re-run with a shorter TLM-start-to-MOVE_X gap, or telemetry that
free-runs even while a wire move's fiber is active, would settle it.

## 5. Re-analysis of the 2026-09-04 evidence: Probe 2
   (`evidence-pivot90-full-telemetry.log` /
   `evidence-pivot90-full-frames.json`, `TLM FULL`, same command)

The original write-up characterized this capture as "`h` frozen,
`vl`/`vr`/`dutl`/`dutr` all zero, `cyc` climbs then freezes." Re-parsing
`evidence-pivot90-full-frames.json` programmatically (all 76 frames,
all 19 telemetry columns) sharpens that considerably:

```
column   distinct values   range
seq      76                0..126 (wraps -- expected, seq is mod-cycled)
now      76                899029..905457  (6428 ms span)
flags    1                 31 (constant)
x        1                 -46 (constant)
y        1                 -23 (constant)
h        1                 85807 (constant)
ox       1                 352 (constant)
oy       2                 -10..-9 (noise-level)
oh       24                -11961..-11938  (23-unit range)
vl       1                 0
vr       1                 0
i2cf     1                 29 (constant -- no fault-count increments
                            during this window)
cyc      32                2210..2336  (climbs for ~35 frames, then
                            pins at 2336 for the remaining ~40)
posl     1                 -13038 (constant -- RAW encoder count,
                            not just the derived heading)
posr     1                 9766 (constant, same)
dutl     1                 0
dutr     1                 0
lexc     1                 0
wrng     1                 0
cycovr   1                 0
```

**Every pose/motion field is dead flat for the full 6.43 s window --
not only `h`, but the RAW encoder counts (`posl`/`posr`), the
OTOS-derived x/y (`ox`/`oy`, apart from 1 count of noise on `oy`), and
duty/velocity.** The one column that is not flat, `oh` (OTOS heading),
only ranges over 23 units across the whole window -- if that is the
same centidegree-ish scale as `h`, 23 units is ~0.2 deg, i.e. sensor
noise, not a signal tracking the camera's independently-confirmed
+123.32 deg of real rotation. So `oh`'s small wobble does not rescue
the "OTOS was still live and tracking" reading either -- it looks like
noise on top of an equally stale base, not a moving signal.

`cyc` is the ONLY column that visibly advances, and only for
roughly the first half of the window (`899029` to `~902053`, about
3.0 s), before it too pins at 2336 for the remaining ~3.4 s -- matching
the original write-up's observation that `cyc=2336` never advanced
again in any later `STATUS` this session.

**Reading, three candidate explanations, in order of how well they fit
this fuller column picture:**

1. **A stuck/stale telemetry SNAPSHOT, not a stuck kernel.** If
   `emitTelemetry()`'s underlying `Snapshot` were captured once
   (plausibly at TLM-start or MOVE-start) and reused for every emitted
   `t` line rather than freshly sampled per tick, EVERY field this
   capture shows frozen (`h`, `x`, `y`, `ox`, `oy`, `posl`, `posr`,
   `vl`, `vr`, `dutl`, `dutr`) is explained at once, while `seq`/`now`
   (which are presumably stamped fresh per emission, not part of the
   cached Snapshot) still advance normally -- which is exactly what is
   observed. This is the most specific, most falsifiable hypothesis of
   the three: a live re-run need only confirm whether individual `t`
   lines during an active MOVE_X ever show ANY pose field changing
   before the move's own completion, independent of whether `cyc` is
   moving.
2. **A stuck encoder/OTOS READ path (I2C wedge), matching this fleet's
   own documented history** (MEMORY.md "I2C wedge is stale state, not
   firmware"; "RUN:probe bricks the board"). This would explain
   `posl`/`posr`/`h` specifically (all downstream of the same encoder
   read), and is consistent with `RUN:clearestop` getting no reply in
   this SAME probe's own log (`evidence-pivot90-full-telemetry.log`:
   `clearestop: None`, sent before the move even started) -- if
   whatever this wedges also gates the cleartext-verb fiber, that
   would explain both symptoms with one cause. It does NOT cleanly
   explain why `oh`'s noise-only wobble also fails to track the real
   rotation, unless OTOS's own read is wedged too (plausible if it
   shares an I2C bus/read cadence with the encoders, but not confirmed
   here).
3. **A genuine kernel/fiber wedge** (the original 2026-09-04
   conclusion). This fits the `cyc` freeze at 2336 (a true kernel
   stall) but does not explain why `cyc` visibly climbed normally for
   the FIRST ~3 s of this SAME capture while every pose field was
   ALREADY frozen from frame 1 -- if the kernel were wedged the whole
   time, `cyc` should never have climbed at all during this window; if
   it wedged only partway through (at cyc=2336), that does not explain
   why pose was frozen for the ~3 s BEFORE that point too, while `cyc`
   was still advancing.

None of these three is confirmed from the existing captures alone --
they are ranked by fit, not proven. Hypothesis 1 (stale snapshot) best
explains the FULL breadth of frozen columns without requiring a second,
unrelated coincidence (`cyc` climbing then stopping) to also line up;
hypothesis 2 (I2C wedge) is the closest fit to this fleet's own
documented failure mode and to the same probe's own `RUN:clearestop`
non-reply; hypothesis 3 (kernel wedge, the original reading) is the
worst fit to the `cyc`-still-climbing-while-pose-is-frozen detail once
it is examined at full column resolution. **This ranking is itself
something a live re-run should treat as a hypothesis to falsify, not a
conclusion to build on.**

## 6. What a live session still needs to answer

Every item below needs the robot reachable (§1) -- none of it can be
settled by re-reading these captures further:

1. **Does a fresh GET (bare dump AND every individual named field)
   work at all right now**, and do `travel_calib`/`track_width`/
   `rotational_slip` read back this repo's compiled defaults (0.7878 /
   114.2 / 0.952) -- confirming the flash matches current source rather
   than a stale build?
2. **Does telemetry show ANY field changing DURING an active MOVE_X**,
   sampled with TLM already running and with as little dead time as
   possible between `TLM FULL` and `MOVE_X` (probe 1's own 2.27 s gap
   is the thing to eliminate) -- this alone discriminates hypothesis 1
   (stale snapshot: nothing changes until the move's true end, then a
   single jump) from a working engine (pose visibly ramps every tick).
3. **Does `RUN:clearestop`/`ESTOP` get a reply on a robot that has NOT
   yet run any `MOVE_X` this session** -- if the no-reply symptom is
   present even before any pivot is sent, that rules out "the pivot
   itself wedges something" and points somewhere in session/connect
   state instead.
4. **Does the SAME +90 deg pivot, re-run cleanly after a power cycle,
   still overshoot by double digits** -- this is still the single
   highest-value confirmation, unchanged from the original 2026-09-04
   write-up's own "needs a human" list, and nothing in this session's
   re-analysis weakens that recommendation.

None of the ticket's acceptance criteria changed status this session:
`field_dance.py` still has not passed since the 2026-09-04 FAIL, G1-G6
and the two §10.2 measurements are still NOT RUN, and the design §7
question is still UNRESOLVED for the same reason the 2026-09-04 session
left it -- this session narrowed WHY it is confounded (three
ranked hypotheses instead of one) but did not add new hardware
evidence.
