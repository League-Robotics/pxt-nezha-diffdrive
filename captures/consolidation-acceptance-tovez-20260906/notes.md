## 2026-09-06 08:35:49

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: Pi serial daemon 192.168.4.52:41567
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tests/calibration/consolidation_acceptance.py tovez --serial 192.168.4.52:41567 --dot NW
- **date**: 2026-09-06
- **dot**: NW
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | PASS | output=true |
| robot answers PING | PASS | pong 777129 (attempt 1) |
| field centre (tag 1) | PASS | (+0.13, +0.02) cm, 0.13 cm from the origin |
| robot tag registered | PASS | tag 52 at (-40.94, +29.08) cm heading +173.0 deg |
| MOVE_X moves the robot | PASS | ack 1 4 stop for 'MOVE_X 100 0 0 8000 #1'; camera saw 9.32 cm against a commanded 10.0 cm, bearing +2.2 deg off the measured heading |
| pose vs ground truth | PASS | NW truth (-50.0, +30.0) vs camera (-50.28, +29.75) = 0.37 cm, heading +171.8 deg (registered, used unchanged) |
| geofence refuses/permits | PASS | refused (65.2, 0.0) with nothing sent, and permitted the in-bounds NW dot (-50.0, 30.0) (path-checked) |

### Measurements

```json
{
  "lights": {
    "output": true
  },
  "robot answers PING": {
    "pong": "pong 777129"
  },
  "field centre (tag 1)": {
    "x_cm": 0.130344993409714,
    "y_cm": 0.015660138786231837,
    "err_cm": 0.13128235697831767
  },
  "robot tag registered": {
    "fix": [
      -40.93951341846432,
      29.078285419173774,
      173.03006916853096
    ]
  },
  "MOVE_X moves the robot": {
    "wire": "MOVE_X 100 0 0 8000 #1",
    "id": 1,
    "reply": "ack 1 4 stop",
    "start": [
      -40.93951341846432,
      29.078285419173774,
      173.03006916853096
    ],
    "lines": [
      "ack 1 4 stop"
    ],
    "finish": [
      -50.22543675262219,
      29.853269999529847,
      170.29739852152966
    ],
    "travel_cm": 9.318206547809893,
    "commanded_cm": 10.0,
    "bearing_deg": 175.22926482662666,
    "bearing_err_deg": 2.1991956580957037
  },
  "pose vs ground truth": {
    "dot": "NW",
    "truth": [
      -50.0,
      30.0
    ],
    "pose": [
      -50.27657185326745,
      29.753225610251913,
      171.83435046646076
    ],
    "err_cm": 0.3706610169080794,
    "heading_deg": 171.83435046646076
  },
  "geofence refuses/permits": {
    "out_target": [
      65.15,
      0.0
    ],
    "in_dot": "NW",
    "in_target": [
      -50.0,
      30.0
    ],
    "refusal": "REFUSING drive to (65.2, 0.0): the projected path leaves the usable field (+/-55.15 x +/-32.65 cm -- LIMITS 67.15/44.65 less the 12 cm margin) at (59.4, 1.5), (65.2, 0.0). Planned path: (-50.2, 29.9) -> (65.2, 0.0). Nothing was sent; reposition the robot or re-plan -- the margin is not a knob."
  }
}
```

### Command lines sent

```
PING
MOVE_X 100 0 0 8000 #1
STATUS
STATUS
STATUS
STATUS
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).

## Session addendum (team-lead, 2026-09-06 ~08:00 PDT)

**Board**: tovez, firmware `1.20260905.1` (`ver`/`id` over zilch's serial
daemon `192.168.4.52:41567`, port re-resolved via `_mbserial._tcp`).
Camera `arducam-ov9782-usb-camera`, tag 52 registered from
`tools/field_calibration.json` (`mount_yaw_rad -1.5708`, the fleet
convention; the daemon's registry held it across its restart).

**Staging.** The acceptance's check (b) runs AFTER the 10 cm probe, so
the robot was staged 10 cm east of the NW dot facing west with v6
`MOVE_X` legs, each camera-fixed and path-checked (scratch script,
lines: `MOVE_X 0 -323`, `MOVE_X 0 -110`, `MOVE_X 709 0`, `MOVE_X 0 320`;
final pose (-40.9, 29.1) 173.0 deg). The consolidated
`reposition.Repositioner` (cleartext `RUN:goto`) was tried first from
(25.5, 6.3) and produced ZERO motion in three attempts while the board
kept answering -- see the brick note below; not re-tried after the
brick came on, so whether `RUN:goto` works on this build with a
powered brick is UNVERIFIED here.

**Nezha brick was OFF at first.** Signature, MEASURED tovez 2026-09-06:
`STATUS ... ready=0 ... cyc=0` on a fresh boot; `MOVE_X 0 -323 0 8000 #1`
-> `ack 1 0 none`, camera turned +0.1 deg (commanded -18.5); the next
`MOVE_X ... #2` got no reply and PING/STATUS timed out for the next
several minutes (the CODAL I2C `waitForStop()` spin,
`.claude/rules/playfield-testing.md`). NEW: the board was NOT dead --
when the stakeholder switched the brick on, the blocked transaction
completed and the board came back by itself with
`status ready=1 active=0 connL=0 connR=0 ... i2cf=2 cyc=2 next=3 done=2
reason=stop`, i.e. it executed both queued ids. No reset, no reflash.
The wedge is a wait on the brick, not a crash.

**wire_acceptance.py** `--tcp 192.168.4.52:41567 --no-motion --no-estop`
(no motion: the robot was parked on the NW dot facing the wall; no
ESTOP section: it latches until reboot): **61 passed, 2 failed, 0
blocked**. The two failures are the sprint-033 wire checks --
`GET rebase -> ack AND err 12` answered `err 1` (unknown name), and the
reserved ceiling id `#4294967295` answered `nack 1 1 stop` instead of
`nack + err 3` -- both EXPECTED on firmware 1.20260905.1, which predates
sprint 033 (closed 2026-09-06, hex at
`captures/sprint-033-build-checkpoint-20260906/`). Not a tool defect;
the tool should ideally BLOCK those two on a pre-033 `ver`. All 18 verbs
and the cleartext `RUN:` carve-out passed. The all-verbs section's
`ESTOP during a gap` case left the robot latched: final
`status ready=1 ... flags=33 i2cf=36 cyc=243 next=38 done=33 reason=estop`
-- tovez needs a reboot before it can be driven again. Camera pose after
the run (-50.24, +29.84) yaw 170.9 deg: unchanged from the acceptance's
end pose, so the all-verbs motion verbs (each followed by STOP) did not
move it.

**Test hygiene defect found**: `tests/calibration/test_consolidation_acceptance.py`
wrote eight BLOCKED sections into THIS real capture file when the host
suite ran at 04:32-04:33 (default capture dir, real Shelly read). They
were stripped from this file; the test must use a tmp capture dir
(issue filed).
## 2026-09-06 10:47:49

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/bin/pytest tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
## 2026-09-06 10:49:25

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/bin/pytest tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
## 2026-09-06 11:06:48

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/lib/python3.13/site-packages/pytest/__main__.py tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
## 2026-09-06 11:10:24

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/lib/python3.13/site-packages/pytest/__main__.py tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
## 2026-09-06 12:29:31

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/lib/python3.13/site-packages/pytest/__main__.py tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
## 2026-09-06 12:45:46

- **board**: tovez
- **camera**: arducam-ov9782-usb-camera, tag 52
- **carrier**: WiFi TCP tovez:7654 (the default carrier)
- **command**: /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/.venv/lib/python3.13/site-packages/pytest/__main__.py tests/ -q
- **date**: 2026-09-06
- **dot**: NE
- **program**: tests/calibration/consolidation_acceptance.py

### Results

| check | status | detail |
| --- | --- | --- |
| lights | BLOCKED | output=false -- THE FIELD IS DARK. A dark field looks exactly like a broken camera or a lost robot. Turn them on: curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true" |
| MOVE_X moves the robot | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| pose vs ground truth | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |
| geofence refuses/permits | BLOCKED | not run: pre-flight 'lights' did not pass. Nothing is commanded from an unconfirmed bench. |

### Measurements

```json
{
  "lights": {
    "output": false
  },
  "MOVE_X moves the robot": {},
  "pose vs ground truth": {},
  "geofence refuses/permits": {}
}
```

### Command lines sent

```
(nothing was sent)
```

> captures/ is GITIGNORED. Commit this artifact with `git add -f <path>` or the MEASURED citation that names it points at nothing (.claude/rules/measurement-citations.md).
