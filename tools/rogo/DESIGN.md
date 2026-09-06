# tools/rogo — `nc` for a robot over its WiFi TCP server

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
stable. Re-checked against `tools/link.py`, which now owns the
sequenced-wire protocol for the rest of `tools/`: rogo still does not
use it and still must not — see "The duplication is deliberate" below,
the one section of this document a consolidation pass needs to read
before re-filing `rogo.py` as an accidental copy.

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

## The duplication is deliberate

`tools/link.py` (sprint 034 ticket 006) is the one owner of the
sequenced-wire protocol for everything else in `tools/` — `Sequencer`,
`LineBuffer`, `relay_setup_lines()`. **rogo does not use it and must
not.** Its socket reading and line splitting stay its own.

That is a decision, not an oversight (sprint 034 Design Rationale 3).
The alternatives were considered and rejected:

- *rogo imports `tools/link.py`* — breaks the whole premise outright.
  `pipx install tools/rogo` (or straight from git) copies `rogo.py` and
  nothing else; an import of a sibling directory that is not in the
  package makes the installed command fail on first run.
- *package `tools/link.py` so rogo can depend on it* — a published
  package to version, release and keep compatible, for one consumer,
  to save a few dozen lines.

So the copy stands, and this note stands with it: a future
consolidation pass that re-files rogo's line handling as an
unintentional duplicate should stop here. What keeps the two honest is
that rogo shares almost none of the surface — it deliberately does not
sequence at all (`rogo` sends lines verbatim; a sequenced verb must be
typed with its `#<id>`), so there is no id-allocation rule to drift.
`tests/tools/test_link.py::test_rogo_imports_nothing_from_tools` pins
the constraint from the other side.

## Versioning

`pyproject.toml`'s `version` follows the firmware's `0.YYYYMMDD.n`
scheme and is bumped by hand when `rogo.py` changes; `pipx reinstall
rogo` (or `pipx upgrade` for a git install) picks it up. There is no
release automation and no wheel on an index.

## Tests

`tests/tools/test_rogo.py` pins the parts that can be pinned without a
robot: the `dns-sd` parsers, against output captured verbatim on
2026-09-02 (macOS, tovez announcing from 192.168.1.213); the discovery
ORDER, with `_dns_sd`/`resolve_host` monkeypatched — including the
announced SRV port beating the 7654 default, which is the whole reason
discovery reads the port and not just the address; and the pipe itself
over a `socket.socketpair()`. No network, no subprocess.

What no host test can reach is the live announcer. That acceptance is
`tools/wire_acceptance.py --wifi-tcp <name>` (the carrier proof) plus a
manual `rogo <name> PING`.
