---
status: done
sprint: '001'
tickets:
- 001-001
- 001-002
- 001-003
- 001-004
- 001-005
---

# Implement simple protocol v5 (all commands, text pose-only TLM)

## Description

Implement a simplified variant of Protocol v5 in this extension, using
the wire specification at
`/Volumes/Proj/proj/RobotProjects/radio-robot-elite/docs/protocol-v5.md`
(the radio-robot-elite repo) as the reference.

Scope:

1. **Announcement line** — emit the boot/identity banner
   (`DEVICE:NEZHA2:robot:<name>:<serial>`), both at boot and as the
   reply to `HELLO`, per the spec's cleartext reply plane (§2.4).

2. **All commands** — implement the full v5 host→robot command verb
   set from the command registry (§2.4):
   - Cleartext, no data: `HELLO`, `PING` (reply `PONG:t=<ms>`), `ID`
     (reply `ID:<drivetrain>:<profile>:<version>`), `VER`
     (reply `VER:<version>`).
   - Binary command arms: `MOVE`, `CONFIG`, `STOP` (planned stop),
     `WHEELS`, `ESTOP` (halt-now), `GET_CONFIG`, `SET_FIELD`,
     `CALIBRATE`.
   All follow the v5 uniform line grammar
   `<COMMAND>[':' <data>]'\n'` (§2.1).

3. **Simplified TLM** — deviate from the spec here: instead of the
   binary `ReplyEnvelope{tlm: Telemetry}` frame (§8), produce a
   **simplified cleartext text record that returns only the pose**
   (x, y, heading). No other telemetry fields, no COBS+CRC framing on
   the TLM line.

The "simple" in simple protocol v5: the command surface and
announcement/reply plane match the spec, but the telemetry plane is
reduced to a text pose record.

Related: hardware testing per [[test-on-microbit-zetuv-via-mbdeploy]];
the square-drive test [[test-system-drive-square]] may serve as a
motion source while validating TLM pose output.
