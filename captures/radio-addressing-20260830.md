# Radio addressing: gopiv hardware verification (sprint 025 ticket 005)

**Target substituted from vevov/zavaz to gopiv/torture at dispatch time** —
vevov and zavaz were not connected/reachable this session; tovez was on
local USB but is explicitly out of scope (not the target). See the
ticket's own "Target substitution" section for the full mapping. gopiv is
a bench test rig (one motor, no wheels, never on the playfield), so this
is a link-level test only — no commanded motion anywhere in this capture.

gopiv derives **channel 47 / group 60** (n=1461). Its OLD (pre-migration)
address is **channel 5 / group 10**
(`radio-robot-lib/config/robots/gopiv.json` `connection.radio_channel=5`,
firmware group 10, the legacy hand-allocated convention).

Hard constraints observed throughout: `!CG <channel> <group>` only, never
`!N <name>` (microbit-radio-relay's `!N` implements an unrelated hash and
agrees with this scheme on 0/3125 names — ticket 005's "Hard Constraint"
section); never retune getez.

## 1. Pre-flash identity (from the chip — the only identity authority)

```
$ cd /Volumes/Proj/proj/RobotProjects/mbdeploy
$ uv run mbdeploy connect --remote gopiv HELLO
device NEZHA2 robot gopiv 2175407711
$ uv run mbdeploy connect --remote gopiv ID
id diffdrive gopiv 0.20260827.2 gopiv
```

2175407711 mod 3125 = 1461 = base5("gopiv") -> channel 47, group 60.
Firmware `0.20260827.2` is pre-sprint (fixed-channel firmware, predates
this sprint's self-addressing change).

MEASURED gopiv 2026-08-30, this capture file (section 1, commands above):
identity confirmed from silicon before touching anything.

## 2. Build (no `--flash`) — deploy-summary line and silicon-gate behaviour

Environment note: this worktree was missing `pxt_modules/` (gitignored
build output, not checked in) and needed `pxt install` once before any
build could run — unrelated to this ticket, just worktree bring-up.

```
$ cd <worktree>
$ uv run python tools/make_deploy.py --robot gopiv
make_deploy: cannot confirm --robot 'gopiv' against silicon -- --robot
'gopiv' does not resolve to a known board UID via mbdeploy's own registry
(/Volumes/Proj/proj/RobotProjects/radio-robot-elite/config/devices.json),
or the mbdeploy sibling checkout at /Volumes/Proj/proj/RobotProjects/mbdeploy
could not be imported -- continuing without the silicon gate (no --flash)
make_deploy: gopiv derives radio channel=47 group=60
...
hex: /Volumes/.../.claude/worktrees/blocks-local-codeserver-test-bf93c6/.tmp/deploy-head/built/binary.hex  (1506369 bytes)  [attempt 1]
```

Full log: `gopiv-build2.log` (scratchpad; key lines transcribed above and
below).

MEASURED gopiv 2026-08-30, this capture file (section 2): the
deploy-summary line reads exactly **`channel=47 group=60`** — matches the
derivation in section 1. Confirmed real compilation (not a stale-cache
no-op): the log contains `Building CXX object ... nezha-diffdrive/src/comms/radio_transport.cpp.obj` and 250+ other `Building CXX/ASM object`
lines, ending `Built target MICROBIT_hex` / `Built target MICROBIT_bin`,
hex present on disk at 1,506,369 bytes.

**Silicon gate on the no-flash / remote-board path — WARN, not
hard-fail, as designed for this ticket's substitution.** The gate
(`_verify_robot_silicon()`) cannot reach gopiv's silicon at all: it needs
local SWD/pyOCD, and gopiv is remote-only (`mbdeploy connect/deploy
--remote`). It prints the warning above and proceeds. This is the correct
behaviour for a no-`--flash` build with no board locally attached, but it
is a real gap for a *remote* board specifically: ticket 003's silicon
gate provides no identity protection for gopiv at any point in this
ticket. Identity for gopiv is instead established solely by `HELLO`/`ID`
over `mbdeploy connect --remote` (section 1 above and section 3 below) —
a live read of the board's own banner, so still the correct authority per
`.claude/rules/identity-comes-from-hardware-not-config.md`, just not
routed through the gate's own SWD path. Recorded as a follow-up-worthy
gap in the ticket, not fixed here (out of scope: verification only, no
src/tools changes).

## 3. Flash (remote) and post-flash identity

```
$ cd /Volumes/Proj/proj/RobotProjects/mbdeploy
$ uv run mbdeploy deploy --remote gopiv --hex <worktree>/.tmp/deploy-head/built/binary.hex
0003820 I Loading /tmp/mbdeploy-flash-697yx5pn.hex [load_cmd]
0006380 I Erasing... [loader]
0013464 C flash erase sector failure (address 0x00000000; result code 0x67) [__main__]
flash failed -- attempting CTRL-AP mass erase to recover a locked device, then retrying.
0003812 I Mass erasing device... [eraser]
0004021 I Mass erase complete [eraser]
0003819 I Loading /tmp/mbdeploy-flash-697yx5pn.hex [load_cmd]
0006349 I Erasing... [loader]
0017508 I Programming... [loader]
0034324 I Erased 398336 bytes (98 sectors), programmed 398336 bytes (98 pages), identical 0 bytes (0 pages) at 13.91 kB/s [loader]
rc=0
```

MEASURED gopiv 2026-08-30, this capture (section 3): the first erase
attempt failed (result code 0x67, locked-device signature); mbdeploy's
own recovery path (CTRL-AP mass erase, then retry) ran automatically and
the retry succeeded cleanly, exit code 0. Not treated as a defect --
this is documented, automatic recovery behaviour in the deploy tool
itself, not something this ticket's scope (verification only) touches.

```
$ uv run mbdeploy connect --remote gopiv HELLO
device NEZHA2 robot gopiv 2175407711
$ uv run mbdeploy connect --remote gopiv ID
id diffdrive gopiv 0.20260829.2 gopiv
```

MEASURED gopiv 2026-08-30, this capture (section 3): post-flash, the
board still answers as **gopiv** (device_id 2175407711 unchanged --
same silicon, confirming this is still gopiv and not a different board
answering), and `ID` now reports **`0.20260829.2`** (today's build,
package.json's version), up from the pre-flash `0.20260827.2` -- proof
the new self-addressing hex actually took, not a stale flash.

## 4. Radio positive control -- torture:8760 pool, `!CG 47 60`

Script: ad hoc `gopiv_radio_test.py` (scratchpad, not checked into the
repo -- this ticket is verification-only, no `src/`/`tools/` changes).
Never sends `!N`; refuses to tune a relay identified as getez (retries
the pool instead of stopping outright, since the ticket's "STOP if the
*only* relay obtainable is getez" implies trying past a single getez
hit first).

```
connect banner (untrusted): DEVICE:RADIOBRIDGE:relay:gozop:4267970133
relay board (via control-plane HELLO): gozop
sent '!CG 47 60' -> # channel: 47 group: 60 mode: RAW250 power: 7
sent '!GO'       -> # entering data plane
HELLO -> device NEZHA2 robot gopiv 2175407711
PING attempt 1/4 -> pong 51487
PING attempt 2/4 -> pong 52775
PING attempt 3/4 -> pong 54063
PING attempt 4/4 -> pong 55351
ID   -> id diffdrive gopiv 0.20260829.2 gopiv
```

MEASURED gopiv 2026-08-30, this capture (section 4): relay `gozop`
(not getez) tuned to `!CG 47 60`; gopiv answered `HELLO` (once, at
session start), 4/4 `PING`s with `pong <n>`, and `ID` naming gopiv on the
`0.20260829.2` firmware just flashed. **Positive control: PASS.**

## 5. Radio negative control (MANDATORY) -- torture:8760 pool, `!CG 5 10`

```
attempt 1: connect banner: DEVICE:RADIOBRIDGE:relay:getez:1784514240
  relay board (via control-plane HELLO): getez
  -> REFUSED to tune (getez is forbidden to retune); retried the pool.
attempt 2: connect banner: DEVICE:RADIOBRIDGE:relay:zetog:3446622357
  relay board (via control-plane HELLO): zetog
  sent '!CG 5 10' -> # channel: 5 group: 10 mode: RAW250 power: 7
  sent '!GO'      -> # entering data plane
  HELLO           -> (no reply)
  PING attempt 1/4 -> (no reply)
  PING attempt 2/4 -> (no reply)
  PING attempt 3/4 -> (no reply)
  PING attempt 4/4 -> (no reply)
  ID              -> (no reply)
```

MEASURED gopiv 2026-08-30, this capture (section 5): the pool's first
allocation was getez -- **not retuned**, per the hard constraint; the
script reconnected and got `zetog` instead. Tuned to gopiv's OLD address
(`!CG 5 10`); **zero replies** across `HELLO` (1x) + `PING` (4x) + `ID`
(1x) -- 6 attempts total, well past the "2-3 tries" floor the ticket
sets before concluding silence. **Negative control: PASS.** gopiv does
not answer on its old channel/group any more -- the migration to
channel 47 / group 60 is confirmed to have actually taken effect, not
merely to coexist with the old address.

## 6. Acceptance-criteria crosswalk

| criterion | result |
|---|---|
| Build prints derived pair (channel=47 group=60) | **PASS** -- section 2 |
| Silicon gate does not silently no-op | **PASS, with a documented gap** -- WARN-and-continue is correct for a *remote* board on the no-`--flash` path (section 2); the gate provides no protection for gopiv at any point in this ticket, since it is always remote here (recorded as a follow-up gap, not a defect to fix in this ticket) |
| Positive control: PING -> pong | **PASS** -- section 4, 4/4 |
| Positive control: ID names gopiv | **PASS** -- section 4 |
| Positive control: HELLO once, session start only | **PASS** -- section 4 |
| Identity read from HELLO/ID, never `mbdeploy probe`'s ROLE column | **PASS** -- `mbdeploy probe` never used for identity anywhere in this capture |
| Negative control: OLD pair silent, 2-3+ tries | **PASS** -- section 5, 6 attempts, zero replies |
| Never retune getez | **PASS** -- section 5, first getez allocation refused and the pool retried instead |
| Never send `!N` | **PASS** -- every tune in this capture is `!CG <channel> <group>` |
| Every MEASURED claim names its artifact | **PASS** -- this file, throughout |
| `src/`/`tools/` unmodified | **PASS** -- verification only; the ad hoc radio-test script lives in scratchpad, not the repo |

**Overall: full PASS.** Both controls ran, both matched expectation, and
the chain (firmware self-addressing -> `make_deploy`'s summary line ->
an explicitly `!CG`-tuned relay reaching real silicon) is proven
end-to-end on gopiv. The one open item is the silicon-gate coverage gap
for remote boards noted in sections 2 and 6 -- real, but out of this
ticket's scope (verification only).
