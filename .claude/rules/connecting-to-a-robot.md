# Connecting to a robot

Full guide: `docs/robot-connections.md` (also published at
http://robot-garage.home/doku.php?id=nezha-diffdrive:connecting).
Read it before the first connection of a session. The short version:

- **WiFi TCP is the default carrier.** `rogo <name>` (pipx-installable
  from `tools/rogo`), `nc <name>.local 7654`, or
  `uv run python tools/wifilink.py --tcp --robot <name> PING STATUS`.
  The robot announces `<name>.local` and "`<name> robot link`" on
  `_robotlink._tcp`/`_udp` over mDNS every 60 s; `wifilink.discover()`
  falls back to a broadcast `HELLO`.
- **UDP** (`wifilink.py` without `--tcp`) needs a fixed host port 7655
  and a keepalive every 15 s; the robot forgets a host after 60 s.
- **Farm USB**: `mbdeploy list --remote`, then `mbdeploy connect
  --remote <instance> "STATUS"`. Use the node's mesh IP for the raw
  serial-daemon port; the service is exclusive and a flash kills it.
- **Radio** is OFF by default in the test program (2026-09-02):
  `make_deploy.py --radio-link` turns it on; otherwise the radio is left
  to MakeCode's own blocks.
- The board you may use is assigned by the stakeholder for this session.
- Sequenced verbs need `#<id>`; `HELLO` resets the sequence; `PING`
  is the liveness probe; `ESTOP` latches until reboot.
- Prove a carrier with `tools/wire_acceptance.py --wifi-tcp <name>`
  (`--only-all-verbs --no-estop` on a fresh boot).
