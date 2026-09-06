# Session A -- tovez cold-boot baseline, 2026-09-04

Sprint 031 ticket 001. Board **tovez**, firmware **1.20260903.1**
(PRE-sprint-030 -- this is the "before" a fixed board can never produce
again). Carrier: zilch serial daemon (`zilch.local:35851`); zilch is a
Pi Zero mounted ON the robot, so no cable drag.

Identity from the chip, not the registry:
`HELLO` -> `device NEZHA2 robot tovez 2314287040`.

Pre-flight: room lights `output: true`; camera
`arducam-ov9782-usb-camera` calibrated, `calibration_stale: false`,
flat-field present; **AprilTag 1 (fixed field centre) reads
(-0.009, -0.040) cm**, as it must. Tag 52 explicitly re-registered
(`camlink.py --register tovez`) so `yaw_rad` IS the robot heading --
read via `field.pose_from_registered_samples()`, never through
`robot_heading_from_tag_yaw()`.

Harness path-checks every segment with `field.check_path()` from a
measured camera pose before commanding it.

## Boot 1

Confirmed genuinely cold: pre-move
`status ready=0 active=0 connL=0 connR=0 otos=1 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none`
(`cyc=0`, kernel had never ticked).

Ten `MOVE_X 40 0 100 4000` segments (4 cm each), camera fix between
each, STATUS polled at 8 Hz throughout.

Artifacts: `boot1/segments.json`, `boot1/status-8hz.log` (257 samples).

| seg | commanded [cm] | camera travel [cm] | heading after [deg] |
|---|---|---|---|
| start | -- | -- | -4.26 |
| 1 | 4.0 | 3.31 | +0.13 |
| 2 | 4.0 | 2.86 | +3.38 |
| 3 | 4.0 | 3.23 | +2.29 |
| 4 | 4.0 | 3.17 | +6.12 |
| 5 | 4.0 | 2.85 | +8.82 |
| 6 | 4.0 | 3.23 | +8.92 |
| 7 | 4.0 | 3.16 | +8.49 |
| 8 | 4.0 | 3.20 | +12.72 |
| 9 | 4.0 | 2.97 | +12.60 |
| 10 | 4.0 | 2.88 | +16.19 |

### Finding 1 -- travel runs ~78 % of commanded, consistently

30.86 cm of camera-measured travel for 40.0 cm commanded (77.2 %). Every
individual segment lands between 2.85 and 3.31 cm for a 4.0 cm command;
no segment is close to nominal. This matches the same day's 2 cm probe
(1.53 cm measured / 2.0 cm commanded = 76.5 %,
`captures/tovez-preflight-20260904/notes.md`).

At 4 cm a segment is short enough that breakaway/stiction and the taper
floor dominate, so this is NOT yet evidence of a travel-calibration
error at cruise -- a longer leg is needed to separate the two. Recorded
as an observation, not a calibration constant.

### Finding 2 -- a consistent LEFT yaw drift on nominally straight legs

Heading went -4.26 deg -> +16.19 deg across 30.9 cm of straight-line
driving: **+20.5 deg total, ~+2 deg per 3 cm segment**, monotonic apart
from sampling noise. The robot is not driving straight; it curves left.

This is the leg yaw asymmetry
`tovez-drivetrain-tuning-and-restated-acceptance-bars.md` describes, and
it is consistent with the project's standing finding that rotation error
is injected by the LEGS, not the pivots
(`.claude/rules/playfield-testing.md`).

Note the first move after idle is known to yaw hard (cold breakaway on
one wheel), but this drift does not decay across ten segments -- it
persists at roughly constant rate, so it is not only a cold-start
artifact.

### Finding 3 -- NO raw-zero teleport observed on this boot

Position progresses smoothly across all ten segments; no jump,
no teleport-and-return. Per the ticket's own acceptance criterion,
**absence of the defect on a given boot is data, not a reason to stop
early** -- recorded as such. Two further cold boots are required before
anything can be said about the raw-zero fix's baseline.

### Finding 4 -- `reason=` is poll-timing dependent, live

Across 257 samples: 229 `reason=stop`, 12 `reason=none`, and **zero
`reason=timeout`**. Yet the same firmware, hours earlier, answered
`done=1 reason=timeout` to a single `STATUS` issued after a 2 cm move
that arrived early (`captures/tovez-preflight-20260904/notes.md`).

The difference is purely *when* the host asked: an 8 Hz poll resolves
the pending reason while the deadline is still live and latches `stop`;
a single late poll resolves it after the deadline and reads `timeout`.
That is a direct live confirmation of
`wire-done-reason-is-resolved-lazily.md`, and of why sprint 031 ticket
003 moved the latch to the engine's own end tick rather than leaving it
to whenever a caller happens to poll.

### Finding 5 -- `i2cf` climbs during a run

`i2cf` 0 -> 6 across ten segments (`flags` 0 -> 31). Small, but it is not
zero and it grows. Worth watching against the post-sprint-030 build,
whose bus-ownership guard is meant to stop exactly this class of
collision.

## Boot 2

Confirmed cold (`cyc=0 next=1`). The harness **repositioned itself** --
it scored every 5 deg heading for straight-line room inside the safe
box, picked 200 deg (90 cm of room vs the 40 cm needed), pivoted there
with `MOVE_X 0 <mrad>` under camera closed loop, then ran the same ten
4 cm segments. The pre-pivot is recorded in `boot2/segments.json` as a
pre-step, since boot 1 had none.

Note the serial daemon's port is **dynamic** -- 35851 on boot 1, 44525
on boot 2. It must be re-resolved from `_mbserial._tcp` after every
power cycle, never cached.

Artifacts: `boot2/segments.json`, `boot2/status-8hz.log` (248 samples).

| seg | commanded [cm] | camera travel [cm] | heading after [deg] |
|---|---|---|---|
| after pre-pivot | -- | -- | -157.96 |
| 1 | 4.0 | 2.98 | -158.63 |
| 2 | 4.0 | 3.17 | -158.10 |
| 3 | 4.0 | 3.03 | -153.11 |
| 4 | 4.0 | 2.75 | -151.23 |
| 5 | 4.0 | 3.12 | -148.93 |
| 6 | 4.0 | 3.12 | -146.68 |
| 7 | 4.0 | 2.41 | -144.13 |
| 8 | 4.0 | 3.07 | -143.03 |
| 9 | 4.0 | 3.14 | -142.66 |
| 10 | 4.0 | 3.07 | -140.73 |

### Both boots agree -- the two headline numbers reproduce

| | travel vs commanded | yaw drift | per cm |
|---|---|---|---|
| boot 1 | 30.86 / 40.0 = **77.1 %** | +20.02 deg | **+0.649 deg/cm** |
| boot 2 | 29.86 / 40.0 = **74.6 %** | +17.23 deg | **+0.577 deg/cm** |

Two independent cold boots, different start poses, opposite compass
directions (boot 1 drove east, boot 2 drove ~south-west), and the
shortfall and the LEFT curve both reproduce within a few percent. The
drift is in the same rotational sense (counter-clockwise / left) in both
runs, so it is a property of the drivetrain, not of the heading it
happens to be pointing.

### Boot 2 -- `otos=0` for the entire run

All 231 samples read `otos=0`; boot 1 read `otos=1` throughout. The OTOS
did not initialise on this power-up. `connL=1 connR=1` the whole run, so
the wheel encoders were fine and the travel/yaw numbers above stand --
the OTOS is not in that measurement path.

Recorded as its own observation: an OTOS that comes up on one power
cycle and not the next is a real intermittency, and it is exactly the
kind of thing this baseline exists to catch. UNVERIFIED whether it
correlates with anything else; boot 3 is the next data point.

### Boot 2 -- again no raw-zero teleport, and again no `reason=timeout`

Position progresses smoothly; no jump. All 231 samples `reason=stop`,
zero `timeout`, consistent with boot 1 and with the poll-timing
explanation in Finding 4 above. `i2cf` 1 -> 8 across the run (boot 1:
0 -> 6), so the slow climb reproduces too.

## Boot 3

Confirmed cold (`cyc=0 next=1`), `otos=0` again. Self-repositioned:
picked heading 205 deg (76 cm of room), pivoted, ran the same ten 4 cm
segments. Daemon port was 33941 this boot (35851 / 44525 / 33941 across
the three -- dynamic every time).

Artifacts: `boot3/segments.json`, `boot3/status-8hz.log` (242 samples).

### THE FINDING -- two segments ended early, and both reported a NORMAL end

| seg | camera travel [cm] |
|---|---|
| 1 | **0.93** |
| 2 | 3.19 |
| 3 | 2.97 |
| 4 | 3.11 |
| 5 | 3.31 |
| 6 | 3.19 |
| 7 | **1.84** |
| 8 | 3.31 |
| 9 | 3.09 |
| 10 | 3.05 |

Every other segment across all three boots landed between 2.41 and
3.31 cm for a 4.0 cm command. Segments 1 and 7 here are far outside
that band.

**Both reported `reason=stop`.** Across all 242 samples there is not a
single `timeout`, `aborted`, or any other reason -- the firmware
believes both short segments completed normally. That is exactly the
failure the issue describes: an early-ending segment that is
indistinguishable, from the wire, from a good one. A bench tool that
trusted `reason=` would score these as passes.

Cycle counts do NOT collapse on the short segments -- `cyc` advances
19 cycles across segment 1 and 17 across segment 7, against 20-25 for
the healthy ones. So the kernel kept ticking; the wheels simply did not
deliver the distance. This is not a stalled control loop.

Segment 1 is the first move after the pre-pivot, so cold breakaway is
the obvious candidate there. Segment 7 has no such excuse -- it sits in
the middle of a warm run between two healthy segments. **Two different
causes may be at work, and this capture does not separate them.**
Diagnosis belongs to ticket 005 (host test with a lagged, skewed wheel
model); this ticket's job was to catch it with `reason=` recorded live,
which it did.

### Three-boot summary

| boot | travel vs commanded | yaw drift | per cm | otos | short segs |
|---|---|---|---|---|---|
| 1 | 30.86 / 40 = 77.1 % | +20.02 deg | +0.649 deg/cm | 1 | none |
| 2 | 29.86 / 40 = 74.6 % | +17.23 deg | +0.577 deg/cm | 0 | none |
| 3 | 28.01 / 40 = 70.0 % | +26.22 deg | +0.936 deg/cm | 0 | 2 |

Boot 3's higher per-cm drift is at least partly an artifact of dividing
a similar absolute drift by a shorter travel -- the two short segments
cost ~4 cm of denominator. Absolute drift (+17 to +26 deg over ~30 cm)
is the more comparable figure.

## OTOS init -- `otos=1` on boot 1, `otos=0` on boots 2 and 3

Source reading (NOT a hardware measurement):
`OtosPort::begin()` (`src/platform/otos_port.cpp:74-80`) sets
`initialized_ = ok && (id == kExpectedProductId)` with
`kExpectedProductId = 0x5F`, and `connected()` returns
`initialized_ && connected_`. `otosBegin()` is called **exactly once per
boot**, from `test/test.ts:819` on the main fiber. Nothing retries it
automatically -- the only other call sites are the `RUN:probe` handler
(`test.ts:647`) and the `calibrate world sensor` block
(`src/blocks/world.ts:22`), both operator-triggered.

**So a single failed probe at boot latches `otos=0` for the entire
session.** That is a genuine firmware weakness independent of whatever
made the probe fail here.

Why it failed is NOT yet established. The firmware emits
`OTOS:boot:id=<id>:connected=<n>` at every boot (`test.ts:820`), which
distinguishes the cases (id 0 = nothing answered; id != 0x5F = wrong
device; id == 0x5F with connected=0 = init-logic fault). That banner
has not been captured yet -- a listener is holding a socket open to
catch it on the next power cycle
(`otos-boot-banner-watch.log`). UNVERIFIED until then.

Circumstantial, not conclusive: boot 1 (`otos=1`) followed a long
power-off during charging; boots 2 and 3 (`otos=0`) followed quick
cycles. Consistent with the chip needing longer to be ready than the
one-shot boot probe allows, but the banner is what would settle it.

Incidental from the listener: `BG:wifi state=0 ip=- peer=-:0 tcp=0/0`
-- the WiFi stack is not up on this firmware, which is why
`tovez.local` never resolved all session.


## SUPERSEDED -- see the correction at the end of this file.

## (superseded) the OTOS is not answering on the I2C bus. Not firmware.

MEASURED tovez 2026-09-04, `captures/session-a-20260904/otos-boot-banner-watch.log`
line 189, firmware 1.20260903.1:

```
RX OTOS:boot:id=0:connected=0
```

`OtosPort::begin()` sets `lastProbeId_ = id` straight from
`readReg8(kRegProductId, &id)`, and `id` is initialised to 0. `readReg8`
returns false on an I2C NAK without writing `val`. So **id=0 means the
chip did not answer its product-ID read** -- it is not a wrong device
(that would report a non-zero id != 0x5F) and not an init-logic fault
(that would report id=0x5F with connected=0).

### The retry test rules out "just needs more time"

`RUN:probe` re-runs `otosBegin()` on demand. Run well after boot
(2026-09-04, same session, board answering `pong 217661` normally
before and after):

- the host timed out waiting for a reply (`no response within 2s`);
- `PING` afterwards answered normally, so the board did NOT wedge;
- `STATUS` afterwards still read `otos=0`, `i2cf=0`, `cyc=0`.

So a retry does not recover it, and the OTOS read blocks the wire for
seconds while it fails. **The sensor is silent, not slow.**

### But it worked on boot 1, so the chip is not simply dead

Boot 1 read `otos=1` for its whole run; boots 2, 3 and 4 read `otos=0`.
Same firmware, same board, same session. An intermittent that answers on
one power-up and not the next points at a **physical fault -- a marginal
I2C connection or power to the OTOS -- not a dead chip and not the
firmware.**

### Two real firmware weaknesses this exposed (secondary, not the cause)

1. **One-shot init, no retry.** `otosBegin()` is called exactly once
   (`test/test.ts:819`); a single failed probe latches `otos=0` for the
   whole session. Nothing automatic retries. (Source reading.)
2. **An OTOS read blocks the wire for seconds when the chip is silent.**
   `RUN:probe` stalled the host past its 2 s timeout. RUN handlers run on
   the protocol fiber, so a silent sensor makes the whole command channel
   unresponsive -- the exact failure class sprint 032 ticket 002 is
   scoped to fix, now observed on hardware rather than argued from
   source.

Neither weakness caused `otos=0`. Both make it worse than it needs to
be. The firmware's own banner reported the fault accurately and
immediately -- it did its job.

### What this does NOT invalidate

The travel and yaw-drift numbers from all three boots stand: `connL=1
connR=1` throughout every run, and the OTOS is not in the wheel-odometry
or camera measurement path. Boot 1 (otos=1) and boots 2-3 (otos=0) agree
on both headline figures, which is itself evidence the OTOS state does
not affect them.


## CORRECTION (v1, itself corrected below) -- the sensor was always fine

The section above concluded an "intermittent physical fault -- a
marginal I2C connection or power feed." **That conclusion was wrong.**

MEASURED tovez 2026-09-04, same session, after the stakeholder powered
the Nezha brick on:

```
RUN:probe  ->  OPROBE:95:1        # 95 == 0x5F == kExpectedProductId
STATUS     ->  ... otos=1 ...
```

The OTOS answered immediately and correctly. No reseat, no rewiring.

What was actually true the whole time:

- the brick was off, so the OTOS had no power and NAKed its product-ID
  read -- hence `OTOS:boot:id=0:connected=0`;
- `otosBegin()` runs exactly once at boot, so powering the brick on
  afterwards could not fix it -- `STATUS` still read `otos=0` with
  `cyc=0` until a forced `RUN:probe` retry;
- boot 1 read `otos=1` because the brick happened to be on then.

Every observation was consistent with "unpowered" from the start.
`.claude/rules/playfield-testing.md` has a section titled "**The robot
is OFF -- check this first**" precisely for this, and the more exotic
"marginal connection" reading went beyond what the evidence required.

The genuine defect that remains is the one-shot init, filed as
`clasi/issues/tovez-otos-silent-on-i2c-intermittently.md`.


## CORRECTION v2 -- it was the OTOS's own supply, NOT the Nezha brick

The correction above says "the brick was off." That is also wrong, and
the distinction is not pedantic.

**The Nezha brick was powered during all three Session A boots.** The
proof is in this file: the robot drove 28-31 cm under command on every
boot, camera-measured, and `connL=1 connR=1` once the kernel ticked.
Motors do not turn and encoders do not answer on an unpowered brick.

What was off was power or an enable feeding the **OTOS alone**. Which
device that was is NOT established -- the stakeholder switched something
on and the sensor answered. Naming it would be a guess. That is
precisely why the symptom looked so confusing: the drivetrain behaved perfectly
while the world sensor stayed dark, which reads as a sensor fault rather
than a power-sequencing one.

So the corrected chain is:

1. the OTOS's supply was off at micro:bit boot -> its product-ID read
   NAKed -> `OTOS:boot:id=0:connected=0`;
2. `otosBegin()` is one-shot, so `otos=0` latched for the session;
3. powering the sensor on later changed nothing until a forced
   `RUN:probe` retry, which then returned `OPROBE:95:1`;
4. boot 1 read `otos=1` because the sensor happened to be powered then.

Every travel and yaw number in this file stands unchanged -- they came
from wheel encoders and the overhead camera, neither of which involves
the OTOS.

## Session B, step 1 -- post-fix run on the ticket-008 build

Flashed tovez with ticket 008's consolidated build (sprint 030 + this
sprint's 003/005 fixes). Flash needed a CTRL-AP mass erase to recover a
locked device first, then programmed 418816 bytes cleanly.

Flash confirmed by identity, not assumption:
`HELLO` -> `device NEZHA2 robot tovez 2314287040`;
`ID` -> `id diffdrive tovez 1.20260904.5 tovez` (was `1.20260903.1`).

`otos=1` at boot this time and for all 178 samples -- the world sensor
was powered before the micro:bit booted, unlike Session A's boots 2-3.

Same harness, same ten 4 cm segments, `boot4-postfix/`.

### Four-run comparison

| run | firmware | travel | % cmd | yaw | deg/cm | short segs | otos |
|---|---|---|---|---|---|---|---|
| 1 | pre-fix | 30.86 | 77.1 | +20.02 | +0.649 | -- | 1 |
| 2 | pre-fix | 29.86 | 74.6 | +17.23 | +0.577 | -- | 0 |
| 3 | pre-fix | 28.01 | 70.0 | +25.75 | +0.919 | 1, 7 | 0 |
| 4 | **post-fix** | 31.36 | **78.4** | +36.33 | **+1.158** | -- | 1 |

### Good: no early-ending segments

All ten segments landed between 2.76 and 3.37 cm. Boot 3's two short
segments (0.93, 1.84 cm) did not recur. **This is one run and boots 1
and 2 were also clean, so it is NOT evidence the ticket-005 fix works** --
the defect is intermittent and a single clean run cannot distinguish a
fix from a quiet day. Ticket 010's three cold boots are the actual test.

### CONCERN 1 -- yaw drift roughly DOUBLED

+1.158 deg/cm, against +0.577 to +0.919 on the pre-fix builds. Highest
of the four runs, about twice boot 2.

### CONCERN 2 -- `i2cf` climbed far more, not less

Item 1's acceptance criterion is that `i2cf` must not climb across a
mid-drive OTOS scenario. It climbed **0 -> 35** across the pre-pivot plus
ten segments (22 of that during the pre-pivot alone, then 22 -> 35 over
the segments).

The only like-for-like comparison is boot 1, the other run with
`otos=1`: **0 -> 6** over ten segments on the PRE-fix build. Boots 2 and 3
had `otos=0`, i.e. no OTOS bus traffic at all, so their low counts are
meaningless here.

So with the OTOS actually active, the post-sprint-030 build -- the one
whose entire purpose is a bus-ownership guard preventing exactly this
class of collision -- shows **more** I2C faults than the build without
it. **Item 1 FAILS as its criterion is written.**

### Why I stopped rather than continuing to tuning

Tickets 011/012 tune kernel gains and per-wheel asymmetry against
measured behaviour. Tuning on a build showing doubled yaw drift and a 5x
`i2cf` increase would produce constants fitted to a possibly-faulty
build, which would then be baked as defaults in ticket 015. Those
numbers would have to be thrown away.

### What is NOT yet established -- do not read these as proven

Confounds not controlled for, any of which could explain part or all of
both concerns:

- **Battery state.** The robot has run many cycles this session and was
  last recharged hours ago. Battery drain is documented in this project
  as degrading rotation before translation -- which is the exact shape
  of concern 1.
- **`otos=1` vs `otos=0`.** Runs 2 and 3 did no OTOS I2C whatsoever. The
  post-fix run did. Some `i2cf` increase versus those two is expected
  and means nothing; the boot-1 comparison is the one that matters.
- **Different start poses and headings** on every run.
- **One run.** No repeat.

The honest statement is that two metrics moved the wrong way on a single
post-fix run with uncontrolled confounds. That is a reason to
investigate before tuning, NOT a demonstration that sprint 030 regressed
the bus. UNVERIFIED either way until repeated on a charged battery with
`otos=1` on both builds.
