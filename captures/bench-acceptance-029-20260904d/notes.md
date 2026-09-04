# Bench acceptance 029/007 — session 2026-09-04d (tovez)

Continuation of the 2026-09-04c session, after ticket 010 landed K1's
fix (twist-hold reference now integrates the floored *commanded* twist,
not the trimmed targets) and tovez was reflashed with that build at
09:38 (`.tmp/deploy-head/built/binary.hex`, 1,688,876 bytes; `VER`
still `1.20260903.1` per the sprint's no-mid-sprint-bump convention).

Firmware **unchanged this session** — no flash was done here, only the
09:38 reflash the dispatch prompt reported as already done. This
session's own changes are host-tooling only: a new TCP carrier for
`tools/fieldlink.py`/`field_dance.py`, plus the captures/docs below.

## 0. Carrier

Prior tovez sessions in this ticket drove over the lossy torture radio
relay (`tools/fieldlink.FieldLink`, 66-83% per-line loss measured).
This session used tovez's own on-robot Pi Zero (`zilch`), a lossless
TCP pipe to the board's USB serial via the mbdeploy serial daemon.

Port resolution (dynamic — resolve fresh each session):

```
$ dns-sd -L tovez _mbserial._tcp local.
tovez._mbserial._tcp.local. can be reached at zilch.local.:43671
```

Confirmed 09:50:42, also cross-checked with `mbdeploy list --remote`
(ENUM 2, `tovez ... zilch`).

Raw connect + PING sanity check (`link-probe.log`): connects clean,
`PING` -> `pong 757919`.

`tools/fieldlink.py` gained `TcpFieldLink` (direct `host:port` TCP,
no `!CG`/`!GO` relay tuning) alongside the existing `FieldLink`
(torture relay), both sharing one `_SequencedLink` base
(`unseq`/`seqd`/`hello`/`close`) so `field_dance.py --tcp host:port`
picks the carrier without any other code caring which one it is on.
Host tests: `tests/tools/test_fieldlink.py` (5 tests, real loopback TCP
server, no hardware) — all pass.

## 1. Pre-flight: lights, camera, mount registration, kernel kick

- Shelly `192.168.1.122` `Switch.GetStatus id=0` -> `output: true`
  (09:50, `link-probe.log` predates this by seconds; lights confirmed
  separately, not logged to a file — trivial one-line curl, result
  quoted here).
- Camera (`arducam-ov9782-usb-camera`, `mcp__aprilcam__get_tags`):
  tag 52 (tovez) at world (42.78, 12.86) cm, yaw 3.168 rad; tag 1
  (field centre) at (-0.05, -0.09) cm — (0,0) within noise. Robot well
  inside the usable envelope (|x|<=55, |y|<=32.6).
- `uv run python tools/camlink.py --register tovez` ->
  `camlink-register.log`: registered from `field_calibration.json`'s
  still-UNVERIFIED tovez mount entry (`lever_cm=[0,0]` placeholder,
  `parallax_k` borrowed from vevov) — unchanged this session, not
  re-fit (a lever-triple fit needs pivots clean enough to trust, which
  this session's dance did not establish).
- Kernel kick (`kick.log`): fresh TCP connect, `HELLO` ->
  `device NEZHA2 robot tovez 2314287040`; `STATUS` pre-kick:
  `ready=0 ... cyc=0` (never-ticked, expected after a flash);
  `RUN:clearestop` -> `ESTOP:cleared`; `MOVE_X 2 0 100 3000` (2 mm
  kick) -> `ack 1 0 none`; `STATUS` post-kick:
  `ready=1 active=0 connL=1 connR=1 ... i2cf=2 cyc=126 ... reason=timeout`.
  `i2cf` was already nonzero (2) after just the kick — flagged, not
  chased (matches 2026-09-04c's observation that `i2cf` climbs during
  motion and holds flat at idle).

## 2. `field_dance.py --tcp zilch.local:43671`

Full transcript: `field-dance.log`. Summary table:

| step | expected | measured | err | result |
|---|---|---|---|---|
| turn +90 | +90.0 | +91.5 | +1.5 | PASS |
| turn +180 | +180.0 | -170.4 | +9.6 | **FAIL** |
| turn +90 | +90.0 | +90.0 | -0.0 | PASS |
| drive +20 cm | 20.0 | 16.9 | -3.1 | **FAIL** (bearing off +87°) |
| drive -40 cm | 40.0 | -35.5 | -75.5 | **FAIL** (bearing off +91°) |
| drive +20 cm | 20.0 | 17.7 | -2.3 | **FAIL** (bearing off +86°) |
| returned home | 0.0 | 3.1 | +3.1 | PASS |

Net heading drift over the three pivots: +14.2° (+4.7°/pivot).

**Verdict: FAILED.** Per this ticket's mandatory ordering, no further
commanded motion was sent this session — no lag measurement, no G1/G5,
no stop_distance/omega_floor, no G2-G4/G6. Post-dance camera fix
confirms the robot ended safe: tag 52 at (41.70, 9.76) cm, well inside
the field margin; `STATUS` (`post-dance-status.log`) reads
`ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=53
cyc=2103 tlm=off next=1 done=10 reason=timeout` — healthy, not frozen
(`cyc` had advanced normally the whole session; no repeat of the
2026-09-04c telemetry-staleness bug in this simple check, though this
was not a targeted re-test of that bug and should not be read as
"fixed").

**Reading the result.** Two genuinely different things happened this
session compared to 2026-09-04c:

1. **Pivots improved sharply.** +14.2° net drift over three pivots
   (a +90/+180/+90 sequence) is close to what a clean run looks like
   (`.claude/rules/field-dance-first.md`'s own vevov reference: net
   drift within a few degrees) and is a large improvement over both
   2026-09-04's +47.6..+57.6°/pivot and 2026-09-04c's mixed
   2-pass/1-miss-by-14°. Consistent with K1's fix addressing (at least
   part of) the pivot-accuracy defect, though a single dance run is not
   the 12-pivot G1 gate and this is not a substitute for running it.
2. **Drives show a new, cleanly-characterized defect.** All three
   drives failed with consistent ~90° bearing error (+87°, +91°, +86°)
   — the actual direction of travel was roughly perpendicular to where
   the camera-tracked heading said "forward" (or "backward") should be
   — while the MAGNITUDE of each drive tracked the commanded distance
   reasonably well (16.9/35.5/17.7 cm vs 20/40/20 cm commanded, not the
   wildly-inconsistent-and-oversized errors 2026-09-04/2026-09-04c's
   drives showed). This looks like a real, repeatable directional
   defect specific to straight-line `MOVE_X` moves, not measurement
   noise or a wedge/frozen-telemetry artifact (the dance still returned
   home safely, and `i2cf`/`STATUS` behaved normally throughout).

Neither is confirmed against firmware source this session — no kernel
or motion-engine file was read or touched. This is a bench-observation
finding for the next session (or `radio-robot-elite` engineering) to
chase, not a diagnosis.

## 3. Not attempted this session

Lag re-measurement, G1-G6, `stop_distance`, `omega_floor`: all blocked
by the failed dance, per the ticket's own mandatory ordering ("stop
driving, capture, and report — do not proceed to gates" on a dance
FAIL). `SET lag 0.126` from 2026-09-04c is NOT known to still be in
effect — this is a fresh boot (flashed at 09:38) and no `SET lag` was
sent this session; the compiled default (`lag=0.0`) applies unless a
future session re-sends it.

## 4. Needs a human / next session

1. **The ~90° drive-bearing defect is the new priority** — it is
   cleanly characterized (consistent angle, consistent
   proportional-to-commanded magnitude, three-for-three) and safety
   permitting should be relatively easy to reproduce with a single
   isolated `MOVE_X <mm> 0 ...` probe plus `TLM FULL`, looking at
   whether the internal heading-hold reference or the drive/turn axis
   selection is doing something 90°-rotated. This is a good candidate
   for `radio-robot-elite` firmware engineering, same as the G5 defect
   was.
2. Re-run `field_dance.py --tcp zilch.local:<port>` (port is dynamic,
   re-resolve) once that is addressed; resume at lag/G1/G5 from there.
3. tovez's mount (`field_calibration.json`) is still UNVERIFIED
   (`lever_cm=[0,0]` placeholder) — a real lever-triple fit needs
   pivots clean enough to trust, which this session's pivots (mean
   +14.2°/3, individual up to +9.6° on the 180) are close to but the
   180-pivot's FAIL means not yet there. Consider fitting once the
   drive defect is resolved and a cleaner pivot run is available.
4. `default_robot` in `field_calibration.json` left as `tovez` for
   session continuity, matching every prior session in this ticket.
