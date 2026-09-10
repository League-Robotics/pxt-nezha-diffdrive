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

### Setting credentials from your own project (`setupWifi()`)

Everything above assumes the robot already knows which network to
join -- for the fleet, `tools/make_deploy.py::_inject_wifi_secrets()`
bakes `kWifiSsid`/`kWifiPassword` into a scratch copy of
`protocol.cpp` at deploy time, from a gitignored
`config/wifi_secrets.json`. That path is unchanged and is still what
every fleet build uses.

A student's own project never runs `make_deploy.py`, so the checked-in
constants stay empty -- an empty SSID is `WifiLink`'s own "disabled"
sentinel, and `enableWifiLink()` (see above) is a permanent no-op with
nothing baked. `diffDrive.setupWifi(ssid, password)` is the entry point
for that case: call it once, from `on start`, and it does both jobs
that `enableWifiLink()` and the bake otherwise split between them --
it stores the credentials AND brings the link up, in one call. There is
no separate `enableWifiLink()` step to remember.

```typescript
diffDrive.setupWifi("Busboom Mesh", "correct horse battery staple")
```

`setupWifi("")` -- an empty SSID -- disables the link explicitly, the
same zero-cost outcome as no WiFi module fitted at all. Useful for a
program that wants to be certain WiFi never comes up, distinct from
simply never calling `setupWifi()`.

`setupWifi()` is **not in the toolbox** -- it is `//% blockHidden=true`,
deliberately, the same as `enableWifiLink()` right above it. It is
reachable from TypeScript/JavaScript but you will not find it by
dragging blocks. That is on purpose: a visible, draggable block would
invite a beginner to drop a real passphrase straight into a shared,
tracked program -- exactly what the `secrets.ts` convention below
exists to prevent. WiFi credentials are for advanced students working
in VS Code, not a toolbox feature.

If a passphrase or SSID is too long (over 32 characters for the SSID,
63 for the password), `setupWifi()` clips it rather than overflowing --
and that clip is never silent. The next `DBG:wifi ...` line carries
`credsrc=` (0 = baked, 1 = set by `setupWifi()`, 2 = a credential
stored in flash via `WIFICRED SET`, walked on boot by
`WifiJoinSequencer` -- sprint 038 ticket 005) and `trunc=` (a bitmask: bit 0 SSID clipped, bit 1
password clipped -- `trunc=` only ever reflects the `setupWifi()` path,
not a flash-stored credential), so "joins nothing, no reason" is
diagnosable from the same status line you already read for everything
else WiFi. A call made after the link has already come up is also not
silent -- it changes nothing and prints `DBG:wifi late setupWifi()
ignored`.

`credsrc=2` beats `credsrc=1` beats `credsrc=0`: at boot, whenever the
flash-backed credential store holds any entry at all, `Protocol` hands
the join to `WifiJoinSequencer`, which walks its occupied slots in
order until one joins (advancing immediately on a definitive
wrong-password failure, retrying a few times on anything else before
moving on, then wrapping back to slot 0 and re-reading the store) --
preferred over both a `setupWifi()`-supplied credential and the
deploy-time bake. `WIFICRED SET`/`WIFICRED CLEAR` write flash
immediately; while the sequencer is walking a non-empty store, a write
is picked up on the walk's next pass back to slot 0, not only after a
reboot -- the `ack`/`err` reply to a `SET` still does not mean the
robot has joined on it yet, only that the write succeeded. An empty
store behaves exactly as before this feature existed (`credsrc=0` or
`1`, never `2`) -- see
`clasi/sprints/038-flash-backed-wifi-credential-store-with-join-failure-diagnostics/sprint.md`.

#### The `secrets.ts` convention

Keep credentials **in code, in a file that is not the tracked
program** -- the same shape `config/wifi_secrets.json` already has in
this repo, one level down, in the student's own project:

- `secrets.ts` -- **gitignored**, holds the real SSID and password,
  calls `diffDrive.setupWifi(...)` (or exports constants a tracked
  `boot.ts`/`on start` block calls it with).
- `secrets.example.ts` -- **tracked**, checked in beside it, same
  shape with placeholder values. Setup for a fresh clone is one step:
  copy `secrets.example.ts` to `secrets.ts` and fill in the real
  network name and password.

```typescript
// secrets.example.ts -- TRACKED. Copy to secrets.ts and fill in real
// values; secrets.ts itself is gitignored.
const WIFI_SSID = "YourNetworkName"
const WIFI_PASSWORD = "YourPassword"
```

```typescript
// boot.ts -- TRACKED, calls into the gitignored secrets.ts.
diffDrive.setupWifi(WIFI_SSID, WIFI_PASSWORD)
```

**The trap:** PXT compiles a *fixed* file set, read from the project's
own `pxt.json` `files` array -- it does not discover files by scanning
the directory. `secrets.ts` has to be listed there for the build to
include it, but the moment it is listed *and* gitignored, anyone who
clones the project without first creating `secrets.ts` has a build
that fails outright, not a build that silently skips WiFi. List
`secrets.example.ts` in `files` too (or leave it untracked-but-present
via `.gitignore`) so the copy step above is the only thing a fresh
clone needs.

This convention is a **VS Code checkout** property only. The MakeCode
web editor has no git and no filesystem of its own to `.gitignore` --
a `secrets.ts` file there buys separation from the rest of the tracked
program (so it is not accidentally read top-to-bottom with everything
else) but not actual secrecy: anyone who opens or shares that web
project sees it. Real secrecy needs the VS Code + git checkout, where
`secrets.ts` genuinely never leaves the machine it was created on.

### Provisioning credentials from a host tool (`WIFICRED`)

Sprint 038's flash-backed credential store adds a wire verb so a bench
tool can hand a board a whole list of networks -- up to 8 slots -- with
no rebuild and no secret ever baked into a hex. Grammar, MEASURED
gopiv 2026-09-09/10,
`captures/wifi-credential-store-20260909/notes.md`:

```
HELLO
WIFICRED SET <slot> <ssid> <password> #<id>    -> ack <id> ...
WIFICRED #<id>                                 -> wificred <slot> <ssid> <haspw>
WIFICRED CLEAR <slot> #<id>                    -> ack <id> ...
```

- **Every form is sequenced**, including the bare enumeration -- a
  `WIFICRED` sent with no `#<id>` parses as `#0` and is silently
  dropped, enumerating nothing.
- **`<password>` is mandatory on `SET`.** `WIFICRED SET 1 SecondNet #3`
  (no password field) returned `err 2`.
- Slots are `0`..`7`. `haspw` is `0`/`1`. **The passphrase is never
  readable back** on any path, under any input -- the enumeration
  reports only whether a slot has one.

**A flash MASS-ERASES the whole chip, so credentials do not survive
`mbdeploy deploy`.** MEASURED gopiv 2026-09-09/10, same capture: a
store written before `mbdeploy deploy --remote gopiv` enumerated empty
afterward -- the programmed range never reaches the store's flash
page, this is pyOCD's mass-erase, not an overwrite. **Provision AFTER
flashing, never before.**

`DBG:wifi`'s full field list (`src/comms/protocol.cpp`'s
`emitWifiDebug()`): `state= ip= peer= tcp= to= restarts= sent= rx=
drop= mdns= cmd= reply= credsrc= trunc= join= ssid= haspw=`. Two of
those are new alongside `credsrc=`/`trunc=` above:

- **`ssid=`/`haspw=`** -- the SSID currently active/attempted at
  whichever source `credsrc=` names, and whether it has a password.
  Never the password. `ssid=- haspw=0` (never a bare empty field) when
  nothing is configured at the active source yet.
- **`join=`** -- the WiFi module's own `+CWJAP:<code>` from the most
  recent join attempt, or `-` when no code was captured (a plain
  timeout). This is the raw vendor number, deliberately unmapped in
  firmware (Ai-WB2/ESP-AT documentation says `2` = wrong password,
  `3` = AP not found, `4` = connect failed, `1` = timeout, but those
  meanings are read from vendor docs, not confirmed on this hardware --
  treat the number as a diagnostic hint, not a certainty).

**Two failure shapes that look alike on a status line but are not.** A
module that is absent or unpowered answers `DBG:wifi` with nothing at
all -- no line, not even `reply=` empty. A module that is present but
failing to join answers `reply=..OK..` and loops, `restarts=` climbing
every cycle:

```
DBG:wifi state=2 ... restarts=2783 ... cmd=AT+CIPDINFO=1 reply=..OK.. credsrc=1 trunc=0
```

`state=2` is `kJoin`. Seeing `reply=` populated at all means the
module is alive and answering AT commands -- the hardware is fine; the
credentials or the AP are what to check next (`join=`, above, or `ssid=`
against what you meant to provision).

#### `tools/provision_wifi.py`

`tools/robotlink.py` grows three helpers matching this verb's shape
(`wificred_set()`, `wificred_clear()`, `wificred_list()` -- the last
parses the bare enumeration into
`[{'slot': int, 'ssid': str, 'has_password': bool}, ...]`, never a
password), and `tools/provision_wifi.py` is a small script built on
them for a whole bench session -- one board, one or more slots, no
hand-typed wire lines:

```bash
# one slot, password from an env var (never on the command line or in
# shell history)
WIFI_PW=hunter2example uv run python tools/provision_wifi.py \
    --usb /dev/cu.usbmodem2121302 --slot 0 --ssid MyNetwork \
    --password-env WIFI_PW

# a board's whole list, one session, from a local (gitignored) manifest
uv run python tools/provision_wifi.py --wifi gopiv \
    --manifest ~/.secrets/gopiv-wifi.json

# read back what is stored -- ssid + whether a password is set, never
# the password
uv run python tools/provision_wifi.py --wifi gopiv --list
```

`--usb`/`--radio`/`--wifi` select the carrier exactly as they do for
`tools/wire_acceptance.py`, above. The password is read from
`--password-env`, `--password-file`, or (neither given) a
non-echoing interactive prompt -- there is no plain `--password` flag,
because a command-line argument is visible in `ps` and shell history.
Nothing this script reads, writes, or prints ever contains a
passphrase; see its own module docstring for the manifest file's
shape (never commit that file). `rogo` (a raw pipe where the caller
types the sequence ids by hand) can also drive `WIFICRED` directly for
a one-off check, the same as any other verb -- there is no dedicated
`rogo` helper for it, by design (the ticket that added this tooling
scoped a polished provisioning UI as explicitly out of scope).

## Device identity -- what `HELLO` and `ID` announce

`HELLO` is how every carrier's discovery finds a robot, so what it
announces is an interface, not a cosmetic string.

```
device NEZHA2 robot gopiv 2175407711
       ^role  ^common_name
             ^^^^^^^^^^^^^ settable from your program
                   ^device_name ^serial -- from silicon, never settable
```

Five fields: a sentinel, then `role` (the device class / firmware
family), `common_name` (the generic name within that class),
`device_name` (`microbit_friendly_name()`), and `serial`
(`microbit_serial_number()`). The naming is counter-intuitive and easy
to get backwards: **`role` is `NEZHA2`**, **`common_name` is `robot`**.
Not the other way round.

`ID`'s middle field is a sixth identity value, `profile` -- which
robot's config this image is running:

```
id diffdrive gopiv 1.20260908.1 gopiv
             ^profile
```

### Setting identity from your own project (`setDeviceRole()`, `setProfile()`)

`role`, `common_name` and `profile` used to be compile-time constants:
`role`/`common_name` were string literals inside the banner's format
string, and `profile` came from `kProfile`, which
`tools/make_deploy.py::_inject_profile()` bakes into a scratch copy at
deploy time. A student's own project never runs `make_deploy.py`, so
`profile` stayed `unbaked` no matter how much configuration the program
loaded at runtime, and `role`/`common_name` could not be changed at all.

Both are now runtime-settable:

```typescript
diffDrive.setDeviceRole("NEZHA2", "robot")   // role, common_name
diffDrive.setProfile("gopiv")                // ID's profile field
```

Call them wherever you like -- unlike `setupWifi()`, **a late call
works**. There is no late-call guard, because nothing borrows into these
buffers the way `WifiLink::Config` borrows into the credential ones. The
next `HELLO` or `ID` picks up whatever the current value is, so calling
a setter after the first banner has already gone out is legitimate and
takes effect immediately. A call made as the very first statement of
`on start` also works -- the buffers are seeded from the baked defaults
in `Protocol`'s constructor, before any fiber starts, so an early call
cannot be overwritten by the seed.

Both are **not in the toolbox** (`//% blockHidden=true`), the same as
`setupWifi()` and `enableWifiLink()`. Reachable from
TypeScript/JavaScript, not by dragging blocks.

**Whitespace is stripped, not rejected.** The banner is space-delimited
and parsed *positionally*, so a space inside `role` or `common_name`
would shift every field after it and turn a 5-field line into a 6-field
one -- breaking every consumer. Rather than fail the call, the setters
remove all whitespace and accept the result:

```typescript
diffDrive.setDeviceRole("my robot", "the bot")   // stores myrobot / thebot
```

Over-length values are clipped rather than overflowing the banner
buffer, and the clip is not silent: the `DBG:role` and `DBG:profile`
lines carry `trunc=` (for `DBG:role`, a bitmask -- bit 0 role, bit 1
common_name). `DBG:profile` also carries `src=` (baked vs runtime), so
"which robot's config does this image think it is running" is
answerable from the same line.

Calling neither setter leaves the announced identity byte-identical to
what the firmware has always emitted.

MEASURED gopiv 2026-09-08,
`captures/identity-setters-gopiv-20260908/`: baseline byte-identical;
role/common_name/profile all settable at runtime; `"my robot"` stored as
`myrobot`; over-length values clipped with `trunc` reported and the
banner still a well-formed 5-field line; a setter called as the first
statement of `on start` already reflected in the very first banner.

> **Know before you change these.** `role` and `common_name` are what
> cross-repo discovery keys on -- `microbit-radio-relay`'s
> `probe_type`, and `radio-robot-lib`'s positional banner codec, both
> expect `NEZHA2`/`robot` for a robot. Setting them to something else
> makes the robot announce itself as a device class those tools do not
> know. That is the point of the interface (a differently-classed
> device can now say so), but it is not a cosmetic rename.

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
