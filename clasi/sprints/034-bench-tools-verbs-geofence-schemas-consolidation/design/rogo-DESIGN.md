# tools/rogo — `nc` for a robot over its WiFi TCP server

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-04 · **Status:**
stable (merged to master 2026-09-03 with the WiFi transport; this
document added at sprint 029's close, which found the subsystem
without one)

A single-file, standard-library-only CLI (`rogo.py`, packaged by
`pyproject.toml` so `pipx install` works from this checkout or straight
from git). It exists so a person at a terminal can talk to a robot on
the LAN with nothing installed but Python: find the robot, open its
TCP server, pipe lines.

## What it does

1. **Discovery.** Resolves `<name>.local` or listens for the firmware's
   own DNS-SD announcement (`<name> robot link` on `_robotlink._tcp`,
   re-announced every 60 s by `src/comms/wifi_link.*`). No zeroconf
   dependency: the mDNS query is hand-built, the same posture as the
   firmware's own announcer.
2. **Transport.** One TCP connection to port 7654 (the WiFi transport's
   TCP server; UDP on the same port is the other carrier and is
   `tools/wifilink.py`'s job, not rogo's).
3. **Pipe.** Interactive mode relays stdin lines to the robot and prints
   replies; argument mode (`rogo tovez PING STATUS`) sends the given
   lines, prints the replies, and exits. Lines go through verbatim: rogo
   does not add `#<id>` sequence numbers, so sequenced verbs (`GET`,
   `SET`, `TLM`, `MOVE_*`, ...) must be typed with their id, exactly as
   `docs/robot-connections.md` describes for any raw carrier.

## What it deliberately is not

- Not a link library. Scripts use `tools/robotlink.py` /
  `tools/wifilink.py` (sequence ids, HELLO resync, telemetry parsing);
  rogo is the human-shaped end of the same wire.
- Not a fleet tool. It knows one robot per invocation and keeps no
  registry; names come from the firmware's announcement, never from a
  config file (`identity-comes-from-hardware-not-config`).
- Not dependent on this repo at run time: `pipx install` copies only
  `rogo.py`, so it must never import from `tools/`.

## Versioning

`pyproject.toml`'s `version` follows the firmware's `0.YYYYMMDD.n`
scheme and is bumped by hand when `rogo.py` changes; `pipx reinstall
rogo` (or `pipx upgrade` for a git install) picks it up. There is no
release automation and no wheel on an index.

## Tests

None on the host: the module is stdlib networking against a live
firmware announcer. Its acceptance is `tools/wire_acceptance.py
--wifi-tcp <name>` (the carrier proof) and a manual `rogo <name> PING`.
A loopback test of the discovery parser would be the first thing to add
if `rogo.py` grows.
