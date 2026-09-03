# Connecting to a robot

"Connect to tovez" means: reach the v6 wire on that board, send lines,
read lines. There are four carriers. Pick by where the board is and what
you need; the protocol is identical on all of them.

| carrier | reaches | use when | tool |
|---|---|---|---|
| **WiFi** (Planet X Ai-WB2-12F, UDP :7654) | any board with the module, joined to the mesh, from any host on the LAN | the default for a board that has it -- no cable, no relay, real motion allowed | `tools/wifilink.py`, `wire_acceptance.py --wifi` |
| **Farm USB** (mbdeploy serial daemon, TCP) | boards plugged into a nolanet node (magni, hodr, loki, meili) | lossless bench work on the stand, flashing, reading `DBG:` output | `mbdeploy connect --remote`, `wire_acceptance.py --tcp` |
| **Local USB** | a board plugged into this Mac | same, on your desk | `tools/robotlink.py`, `mbdeploy connect` |
| **Radio** (relay pool) | any board, on the playfield | untethered runs when the board has no WiFi | `robotlink.py --radio`, `wire_acceptance.py --radio` |

Which board you may use is assigned by the stakeholder for this session
(see the `robot-assignment-is-per-session` memory). Do not infer it from
what is plugged in.

## WiFi -- the quickest path

The robot joins the mesh by itself at boot (credentials baked at deploy
time) and announces `<name>.local` plus "`<name> robot link`" on
`_robotlink._udp` every 60 s. So:

```bash
uv run python tools/wifilink.py --robot tovez HELLO PING ID STATUS
```

That resolves `tovez.local` by mDNS (falls back to a broadcast `HELLO`
on :7654), sends each line, prints each reply. `--host 192.168.1.213`
skips discovery; `--discover` only prints the address; `--browse` lists
every robot announcing itself. From Python:

```python
import sys; sys.path.insert(0, 'tools')
import wifilink
link = wifilink.WifiLink(wifilink.discover('tovez'))
print(link.ask('PING'))          # ['pong 13513487']
print(link.ask('STATUS'))
link.close()
```

Facts that matter on this carrier (MEASURED tovez 2026-09-02,
`captures/tovez-wifi-20260902/`):

- **One datagram is one line.** The host must bind local port **7655**
  (`wifilink` does) -- the robot learns its host from the first datagram
  and replies to that address. An ephemeral port would be forgotten on
  the next run.
- **The robot forgets a silent host after 60 s.** `WifiLink` sends a
  bare-newline keepalive every 15 s; a hand-rolled socket must too, or
  after a minute of only listening the replies stop.
- **First contact gets an extra banner**: the robot greets a new host
  with the `device ...` line, so the first `HELLO` shows it twice.
- Round trip is ~40 ms (median, 0/50 lost), ~53 ms with telemetry
  streaming; telemetry runs at ~18 Hz. USB is 5 ms. Do not use WiFi
  timing as a proxy for wire-level cadence measurements.
- Nothing authenticates the port. Anyone on the LAN can drive the robot.
- If discovery fails: the join takes 6-170 s from a cold module. Watch
  the board's USB for `DBG:wifi state=5 ip=...` (state 5 = ready; the
  line repeats every 10 s while not ready and once per state change), or
  check `dns-sd -B _robotlink._udp`.

## Farm USB

```bash
mbdeploy list --remote                          # which node has the board
mbdeploy connect --remote <instance> "STATUS"   # one line, exit 1 on silence
```

The instance name is the board's five-letter name when the daemon could
read it over SWD, else `mb-<last 8 of uid>` (tovez on magni is
`mb-6e052820`). For a scripted session the daemon's serial port is a raw
TCP byte pipe: `ssh eric@<node> sudo ss -tlnp | grep python3` lists
two ports per board; `INFO\n` answers `OK {...}` on the flash port and
nothing on the serial port. `wire_acceptance.py --tcp <ip>:<port>`
uses it. Use the node's mesh address (magni = 192.168.1.147);
`magni.local` resolves to an unreachable 10.x address.

The serial service is **exclusive**: a second client gets `ERR busy`,
and a flash kills whoever is connected. Opening it does NOT reset the
board (the daemon holds DTR low); a local macOS serial open does.

## Local USB and radio

`tools/robotlink.py` (`open_link(port)` / `open_link(radio=True)`) is
the existing object every tour tool uses; `playfield-testing.md` has the
relay channels and the `!N`/`!CG` tuning hazard.

## The wire, on any carrier -- what trips people first

- Sequenced verbs need a trailing `#<id>` counting from 1
  (`STOP #1`, `TLM POSE #2`). Without it the line is silently dropped.
  `HELLO PING ESTOP HELP ID VER STATUS` take no id.
- `HELLO` is a session RESET (`expectedNext_ = 1`), not a liveness
  probe. Use `PING`; use `STATUS` to see where the sequence stands.
- Track your counter from the robot's `ack <n>`/`nack <n>`, never by
  blind increment -- `nack n` means "send me n".
- `ESTOP` latches; only a reboot (a reflash, on the farm) clears it.
- Each carrier has its own sequence counter on the robot, so a WiFi
  session and a USB session do not disturb each other.

To check a carrier against the whole verb table:
`uv run python tools/wire_acceptance.py --wifi tovez` (or `--tcp`,
`--usb`, `--radio`); `--only-all-verbs --no-estop` on a fresh boot is
the gentlest full pass.
