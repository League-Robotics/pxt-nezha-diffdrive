# Connecting to a robot

Published to http://robot-garage.home/doku.php?id=nezha-diffdrive:connecting
by `tools/publish_wiki.py` -- **re-run `uv run python tools/publish_wiki.py --all`
after editing this file.** This Markdown is the source of truth; the
wiki page is a rendering of it.

"Connect to tovez" means: reach the v6 wire on that board, send lines,
read lines. There are four carriers. The protocol is identical on all
of them; pick by where the board is and what you need.

| carrier | reaches | use when | tool |
|---|---|---|---|
| **WiFi, TCP** (Planet X Ai-WB2-12F, `:7654`) | any board with the module, joined to the mesh, from any host on the LAN | **the default** -- a plain line stream, no cable, no relay, real motion allowed | `nc <name>.local 7654`, `tools/wifilink.py --tcp` |
| **WiFi, UDP** (same module, `:7654`) | same | one datagram per line; a host that must not hold a socket open | `tools/wifilink.py` |
| **Farm USB** (mbdeploy serial daemon, TCP) | boards plugged into a nolanet node (magni, hodr, loki, meili) | lossless bench work on the stand, flashing, reading `DBG:` output | `mbdeploy connect --remote`, `wire_acceptance.py --tcp` |
| **Local USB** | a board plugged into this machine | same, on your desk | `tools/robotlink.py`, `mbdeploy connect` |
| **Radio** (relay pool) | a board whose deploy enabled the v6 radio link | legacy untethered runs; OFF by default since 2026-09-02 | `robotlink.py --radio` |

Which board you may use is assigned by the stakeholder for the session
at hand. Do not infer it from what is plugged in.

## WiFi -- the quickest path

The robot joins the mesh by itself at boot (credentials baked at deploy
time), then every 60 s announces `<name>.local` and the service
instance "`<name> robot link`" under both `_robotlink._tcp` and
`_robotlink._udp`. Its TXT record reads `name=<name> role=robot link=v6
port=7654`.

### TCP: a line stream, like USB

```bash
nc tovez.local 7654
```

You get the `device NEZHA2 robot tovez <serial>` banner immediately
(plus one `DBG:wifi ...` status line), then type wire lines and read
replies. With the tool:

```bash
uv run python tools/wifilink.py --tcp --robot tovez PING ID STATUS "STOP #1"
```

From Python:

```python
import sys; sys.path.insert(0, 'tools')
import wifilink
link = wifilink.TcpLink(wifilink.discover('tovez'))
link.read(1.0)                   # the connect-time banner
print(link.ask('PING'))          # ['pong 13513487']
link.close()
```

A standalone, stdlib-only equivalent, **`rogo`**, installs with pipx
and needs no checkout on the machine that runs it:

```bash
pipx install "git+https://github.com/League-Robotics/pxt-nezha-diffdrive.git#subdirectory=tools/rogo"
rogo tovez                      # interactive
rogo tovez PING STATUS          # one shot
rogo --browse                   # every robot announcing itself
rogo --discover tovez           # "<ip> <port>"
```

(From a checkout: `pipx install tools/rogo`, or `just rogo tovez`.) It
uses only mDNS -- `dns-sd -L` on `_robotlink._tcp`, then
`<name>.local:7654` -- never the broadcast `HELLO`, and it is a raw
pipe: the wire rules below apply as typed.

TCP facts:

- Up to three clients may be connected at once. **Replies go to
  whichever client sent the last line** ("newest client wins"); a
  second client connecting becomes the target until someone else
  speaks. One conversation at a time is the intended use.
- The robot greets each new connection with the banner. `nc` exits
  when its stdin closes, so pipe with a delay or use the tool.
- No keepalive is needed; the module is told never to time an idle
  client out (`AT+CIPSTO=0`); a 10-minute idle hold still answered
  (`tcp-idle-hold.log`).
- A line longer than 240 bytes is discarded whole.

### UDP: one datagram per line

```bash
uv run python tools/wifilink.py --robot tovez HELLO PING ID STATUS
```

- The host must bind local port **7655** (`wifilink` does): the robot
  learns its host from the first datagram and replies to that address.
- **The robot forgets a silent host after 60 s.** `WifiLink` sends a
  bare-newline keepalive every 15 s; a hand-rolled socket must too.
- First contact gets an extra banner (the new-host greeting).

### Discovery

`wifilink.discover('tovez')` resolves `tovez.local` through mDNS, then
falls back to a broadcast `HELLO` on `:7654`; `--discover` prints the
address, `--browse` lists every robot announcing itself. By hand:
`dns-sd -B _robotlink._tcp`, `dns-sd -G v4 tovez.local`.

If nothing answers: a cold module takes 6-170 s to join. The board's
USB prints `DBG:wifi state=<n> ip=... tcp=<mask>/<server> ...` on every
state change and every 10 s until ready; state 5 is ready. After a
reflash the module keeps its association, so the link is usually back
within seconds.

### Measured (tovez, 2026-09-02, `captures/tovez-wifi-20260902/`)

| what | result |
|---|---|
| every v6 verb over UDP, fresh boot | 39/40 pass, wheels turning on all six motion verbs (`all-verbs-wifi-run2.log`) |
| every v6 verb over TCP, fresh boot | 39/40, identical (`all-verbs-wifi-tcp-run3.log`) |
| same section over farm USB, same boot | 40/41, identical outcomes (`all-verbs-usb-run2.log`) |
| PING round trip, idle | 50/50 answered, median 40 ms, p90 60 ms |
| PING round trip with telemetry streaming | 30/30, median 53 ms |
| telemetry over WiFi | 17.9 Hz (the firmware's 50 ms floor holds) |

On the final build (merged with sprint 028): every-verb 40/40 over
TCP and 40/40 over UDP on a fresh boot; 12 motion+STOP cycles with
telemetry streaming acked in a median 72 ms (TCP) / 79 ms (UDP), none
late; a 10-minute idle TCP hold still answered. Known wrinkle: two TCP
runs that followed an earlier session on the same boot saw acks 1-3 s
late (unresolved; see the knowledge doc). Prefer UDP for long or
telemetry-heavy sessions until that is understood. A USB round trip is
5 ms; do not use WiFi timing for wire-cadence measurements.

Nothing authenticates the port: anyone on the LAN can drive the robot.

## Farm USB

```bash
mbdeploy list --remote                          # which node has the board
mbdeploy connect --remote <instance> "STATUS"   # one line; exit 1 on silence
```

The instance name is the board's five-letter name when the daemon could
read it over SWD, else `mb-<last 8 of uid>` (tovez on magni is
`mb-6e052820`). For a scripted session the daemon's serial port is a raw
TCP byte pipe: on the node, `sudo ss -tlnp | grep python3` lists two
ports per board; `INFO\n` answers `OK {...}` on the flash port and
nothing on the serial port. `wire_acceptance.py --tcp <ip>:<port>` uses
it. Use the node's mesh address (magni = 192.168.1.147); `magni.local`
resolves to an unreachable 10.x address.

The serial service is exclusive: a second client gets `ERR busy`, and a
flash kills whoever is connected. Opening it does not reset the board
(the daemon holds DTR low); a local macOS serial open does.

## Local USB and radio

`tools/robotlink.py` (`open_link(port)`, `open_link(radio=True)`) is the
object every tour tool uses. The v6 radio link is **off by default**
in the test program: `tools/make_deploy.py --radio-link` (or
`connection.v6_radio_link: true` in the robot's radio-robot-lib config)
turns it on for a build. While it is off the radio is untouched, so
MakeCode's own `radio` blocks (a student's joystick, 32-byte packets)
work in the same program. `playfield-testing.md` in the repo's rules has
the relay channels.

## The wire, on any carrier -- what trips people first

- Sequenced verbs need a trailing `#<id>` counting from 1
  (`STOP #1`, `TLM POSE #2`). Without it the line is silently dropped.
  `HELLO PING ESTOP HELP ID VER STATUS` take no id.
- `HELLO` is a session reset (`expectedNext_ = 1`), not a liveness
  probe. Use `PING`; use `STATUS` to see where the sequence stands.
- Track your counter from the robot's `ack <n>` / `nack <n>`, never by
  blind increment: `nack n` means "send me n".
- `ESTOP` latches; only a reboot (a reflash, on the farm) clears it.
- Each carrier has its own sequence counter on the robot, so a WiFi
  session and a USB session do not disturb each other. TCP and UDP
  clients on WiFi share one counter; start a new client with `HELLO`.

To check a carrier against the whole verb table:
`uv run python tools/wire_acceptance.py --wifi-tcp tovez` (or `--wifi`,
`--tcp`, `--usb`, `--radio`); `--only-all-verbs --no-estop` on a fresh
boot is the gentlest full pass.
