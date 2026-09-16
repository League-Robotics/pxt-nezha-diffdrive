# calibrateL bench runs on vevov, 2026-09-15

Robot **vevov** (farm node zilch) on the main playfield, in front of the left arm of
the black cross, turned roughly 30-40 degrees off square to it. Firmware: this
repo at `radio-map-73` (== master 465ce00) plus the uncommitted `test/calibratel.ts`,
built locally with `bash scripts/build.sh --local --profile calibrate-l-bench`
against nezha-diffdrive **v1.20260914.1**, and flashed with
`mbdeploy deploy vevov --remote --hex built/binary.hex` at 15:42:29-15:43:54 PDT
(`Erased 246784 bytes (61 sectors), programmed 246784 bytes (61 pages)`, exit 0).

## What these logs are, and are not

- **Filtered, not raw.** Every run went through a small node script (leaguebot's
  `TcpLink` over zilch's `_mbserial` link, or `mbrelay connect` over torture). The
  scripts kept only lines matching `status|ack|nack|err|CALL:|DBG:|device|ERR` (the
  exact filter varies by run, noted below). The full byte stream was **not**
  saved. Lines below are copied verbatim from those scripts' output.
- `i2cf`/`cyc` deltas were computed by the script from two STATUS lines, before and
  after the command. Where only the delta was printed, the STATUS lines themselves
  were not kept.
- Times: `HH:MM:SS` stamps from the serial scripts are **UTC** (PDT + 7). Section
  headers from the radio runs are **PDT**.
- Camera: `aprilcam camera image arducam-ov9281-usb-camera`, main playfield, one
  frame per step. The files sit beside this log.
- Test verbs (all in `test/calibratel.ts`):
  - `sweep <cm>`: `whileDriving(sign*4 cm/s, 0)`, printing the bar on each change,
    stops at |x| >= cm or after 30 s.
  - `nudge <l> <r> <ticks>`: `resetPose(); setWheelSpeeds(l, r); <ticks> x driveTick()`
    (breaking early if it returns false); `stop(); pause(40)`; then prints pose x/heading.

## Run 1: forward sweep over radio (torture, relay guvov), 15:44:48 PDT

Command: `mbrelay connect vevov --send "RUN sweep 15 #1" --expect "CALL:sweep end" --timeout 30`

```
mbrelay: relay guvov tuned to vevov: channel 20 group 82
mbrelay: vevov answered PING
58371
ack 1 0 none
CALL:bar=...# x=5.6cm h=-1.05deg
CALL:bar=.### x=7.9cm h=-1.13deg
CALL:bar=###. x=9.8cm h=-0.94deg
CALL:bar=##.. x=10.9cm h=-1.05deg
CALL:bar=#... x=11.3cm h=-0.83deg
CALL:bar=.... x=12.9cm h=-0.87deg
CALL:sweep end
```

Bar is channel 0 (left) first; `#` = line. Radio drops lines, so the start line
and the `x=` of the end line are missing. Frames: `before.jpg` (before),
`after-fwd.jpg` (after; robot moved across the line).

## Run 2: reverse sweep over radio (relay getez), 15:44:55 PDT

Command: `mbrelay connect vevov --send "RUN sweep -15 #2" --expect "CALL:sweep end" --timeout 30`

```
mbrelay: relay getez tuned to vevov: channel 20 group 82
mbrelay: vevov answered PING
nack 1 0 none
HELLO
device NEZHA2 robot vevov 1198504156
HELLO
device NEZHA2 robot vevov 1198504156
HELLO
device NEZHA2 robot vevov 1198504156
mbrelay: never saw 'CALL:sweep end' within 30.0s
```

Nacked (the session had been reset, so it expected #1). Not a drive test.

## Run 3: reverse sweep over radio, id reset, 15:45:57 PDT

Command: `mbrelay connect vevov --send "RUN sweep -15 #1" --expect "CALL:sweep end" --timeout 30`

```
mbrelay: relay getez tuned to vevov: channel 20 group 82
mbrelay: vevov answered PING
ack 1 0 none
CALL:sweep -15cm start bar=....
mbrelay: never saw 'CALL:sweep end' within 30.0s
```

Frame `after-back.jpg`, taken right after: robot in the same place as `after-fwd.jpg`.

STATUS read three times over radio immediately afterwards:

```
status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
```

The same STATUS over the serial link (zilch, tcp 192.168.4.52:40881) right after:

```
device NEZHA2 robot vevov 1198504156
status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
```

## Run 4: idle STATUS x2 5 s apart, then a 1-tick nudge, serial

Filter: `status|ack|nack|err|CALL:|DBG:(drive|stall|i2c)|ERR`. Sequence:
STATUS, wait 5 s, STATUS, `RUN nudge 50 50 1`, wait 2.5 s, STATUS.

```
22:47:53 status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
22:47:59 status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1414 tlm=off next=1 done=0 reason=none
22:48:00 ack 1 0 none
22:48:01 CALL:nudged x=0cm heading=0deg
22:48:03 status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1415 tlm=off next=2 done=0 reason=none
```

Frame `after-nudge.jpg`.

## Run 5: reverse sweep over serial, 22:48:32 UTC

Sequence: STATUS, `RUN sweep -15`, wait for `CALL:sweep end` (up to 40 s), STATUS.

```
22:48:32 status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=1247 cyc=1415 tlm=off next=1 done=0 reason=none
22:48:33 ack 1 0 none
22:48:33 CALL:sweep -15cm start bar=....
22:49:03 CALL:sweep end x=0cm bar=....
22:49:04 status ready=1 active=0 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=2493 cyc=2666 tlm=off next=2 done=0 reason=none
```

The sweep ended on its 30 s time limit. Frame `after-back2.jpg`: robot unmoved.

## Run 6: 5-tick nudges, serial

Script printed per step: the `CALL:nudged` line, and the i2cf/cyc deltas from the
STATUS before and after (STATUS lines not kept).

```
start: i2cf=2493 cyc=2666
forward wheels  nudge 50 50 5: CALL:nudged x=0.1cm heading=-0.64deg | i2cf +1 over cyc +5
reverse wheels  nudge -50 -50 5: CALL:nudged x=0cm heading=0deg | i2cf +1 over cyc +5
spin CCW        nudge -50 50 5: CALL:nudged x=0cm heading=0.41deg | i2cf +1 over cyc +5
```

Frame `after-nudges.jpg`.

## Run 7: forward sweep 5 cm, then 40-tick wheel commands at +/-10, serial

Same format: the deltas, then the `CALL:|err|nack` lines seen during each step.

```
start: i2cf=2496 cyc=2681
forward sweep 5cm: i2cf +1 over cyc +60
    CALL:sweep 5cm start bar=....
    CALL:sweep end x=5.1cm bar=....
reverse -10/-10 x40: i2cf +3 over cyc +40
    CALL:nudged x=-7.2cm heading=2.71deg
forward 10/10 x40: i2cf +3 over cyc +16
```

The forward 10/10 step printed no `CALL:nudged` line within its 8 s wait. Frame
`after-tests.jpg`.

## Run 8: 40-tick wheel commands at +/-4, serial

The deltas also printed STATUS `active` and `reason` after each step. Lines seen
during each step (filter `CALL:|err|nack|DBG:`) are indented.

```
start: i2cf=2503 cyc=2821
reverse wheels -4/-4 x40: i2cf +36 over cyc +40 (active=1 reason=none)
    CALL:nudged x=0.3cm heading=0.6deg
forward wheels 4/4 x40: i2cf +2 over cyc +17 (active=1 reason=none)
```

The forward 4/4 step printed no `CALL:nudged` line within its 8 s wait.

## Run 9: STOP, then idle STATUS, serial

`STOP now` (sequenced), wait 1.2 s, STATUS:

```
ack 1 0 none
status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=2541 cyc=2901 tlm=off next=2 done=0 reason=none
```

Then STATUS twice, 3 s apart:

```
22:52:36 status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=2541 cyc=2901 tlm=off next=1 done=0 reason=none
22:52:39 status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 i2cf=2541 cyc=2901 tlm=off next=1 done=0 reason=none
```

Frame `now.jpg`: robot stopped on the line. Left there, as asked.

## Not recorded

- TLM FULL was never enabled, so no applied duty exists for any run.
- Diag 29 (emit drops), the lease-expiry and refusal diags were never read.
- No robot-console or other client was confirmed off vevov's radio. The three
  HELLOs in run 2 came from somewhere other than this session's scripts.
