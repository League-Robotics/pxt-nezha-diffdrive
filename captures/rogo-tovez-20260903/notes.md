# rogo against tovez over WiFi TCP, 2026-09-03

First live use of `tools/rogo.py` (branch claude/planetx-wifi-interface-5a5ebf,
d09d3bf) against tovez's Planet X WiFi TCP server. Read-only verbs only;
no motion was commanded. tovez firmware `0.20260902.3` (from `ID`), at
192.168.1.213, on farm node magni.

| check | result | artifact |
|---|---|---|
| `rogo --discover tovez` | `_robotlink._tcp` SRV -> `tovez.local.:7654` -> 192.168.1.213, TXT `name=tovez role=robot link=v6 port=7654` | `discover.log` |
| `rogo tovez HELLO PING STATUS ID VER --wait 2` | banner `device NEZHA2 robot tovez 2314287040` + `DBG:wifi state=5 ... tcp=1/1`, then device (HELLO), `pong`, `status ...`, `id diffdrive tovez 0.20260902.3 tovez`; `VER` answered nothing within 2 s | `args-mode.log` |
| `printf 'PING\nSTATUS\n' \| rogo tovez --wait 2` (stdin path) | `pong`, `status`, exit 0 | `stdin-mode.log` |
| `rogo 192.168.1.213 PING` (discovery skipped) | `pong` | `by-ip.log` |
| `just rogo tovez PING --wait 1 -q` | `pong`, no discovery notes | `just-rogo.log` |

Observations, not diagnosed here:

- The `DBG:wifi` status line's position varies: before the first reply
  on the first connection, after the replies on later ones. It is the
  robot's connect-time status line, not something rogo reorders.
- The robot's `drop=` counter went 0 -> 1 between the first and second
  connections. All five sent lines in those two sessions were answered
  (`VER` excepted, see above), so whatever was dropped was not one of
  rogo's lines with a visible reply.
- `VER` produced no reply over TCP within 2 s. UNVERIFIED whether it
  answers on USB on this build; `connecting-to-a-robot.md` lists it as
  an unsequenced verb.
