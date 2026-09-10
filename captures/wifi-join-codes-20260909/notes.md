# `+CWJAP:<code>` measured on the Ai-WB2-12F — gopiv, 2026-09-09

Hardware confirmation for sprint 038 ticket 001, run by the team-lead
on gopiv (on the playfield, reached over the Pi `null` serial daemon
with `mbdeploy deploy --remote` / a raw `_mbserial._tcp` tap). Build:
`tools/make_deploy.py --robot gopiv` at sprint-038 HEAD, so `credsrc=0`
throughout — the credentials are the baked `kWifiSsid`/`kWifiPassword`
constants, not `setupWifi()`.

**Every `cmd=AT+CWJAP=...` field in these logs is redacted here. It was
NOT redacted on the wire** — see
`clasi/issues/dbg-wifi-prints-the-passphrase-in-cleartext.md`, which
this session opened because of what these captures showed.

## The codes

| case | baked credentials | reply | `join=` |
|---|---|---|---|
| AP does not exist | ssid `NoSuchNetwork038` | `+CWJAP:3....ERROR..` | **3** |
| wrong password, real AP | real ssid, password's last character changed | `+CWJAP:2....ERROR` | **2** |

`bogusssid-tap.log` and `badpw2-tap.log`. This confirms two rows of the
vendor table (3 = cannot find target AP, 2 = wrong password) **on this
module**. Codes 1 (timeout) and 4 (connect fail) remain UNVERIFIED — no
case was contrived for them.

The retention behaviour ticket 001 specifies is visible in the same
logs: `join=` survives the `kJoin → kBackoff` transition (`state=6`
still reports the code) and the following restart (`state=1`, then
`state=2`), and resets to the `-` sentinel at the moment the next
`AT+CWJAP=` is sent, so a stale code is never attributed to a fresh
attempt.

## The finding that changes the design: the module rejoins on its own

`badpw-boot.log` — the SAME wrong-password build, flashed while the
module still had the real AP in its own non-volatile config:

```
DBG:wifi state=5 ip=192.168.1.218 ... cmd=AT+CIPSTO=0 reply=..OK.. credsrc=0 trunc=0 join=-
```

**It joined.** `state=5`, a real IP, `join=-` — no failure code, because
`AT+CWJAP=` was never sent. The Ai-WB2 persists the last AP it
associated with and auto-connects after the `AT+RST` in the configure
sequence, so `serviceJoin()` step 0's `AT+CWJAP?` poll matches and the
firmware jumps straight to `kAddress` with the baked credentials
untouched.

Consequences for sprint 038:

1. **A wrong baked password is invisible** on any module that has
   previously joined that AP. The two failure captures above were only
   obtainable by first flashing the bogus-SSID build, whose failed
   `AT+CWJAP=` displaced the module's stored config.
2. **`WifiJoinSequencer` (ticket 005) cannot assume its own list is
   what gets tried.** Walking entries in order is meaningless if the
   module silently reconnects to whatever it remembers. The sequencer
   needs to force the credential it intends to test — `AT+CWQAP` before
   the walk, `AT+CWAUTOCONN=0`, or an explicit `AT+CWJAP=` that does not
   short-circuit on the poll — and which of those is correct is now an
   architecture question with hardware evidence behind it.
3. Slot ordering is only observable once (2) is settled; any test of
   "entry 2 wins when entry 1 is wrong" written before then would be
   measuring the module's memory, not the sequencer.

## Artifacts

- `bogusssid-tap.log` — nonexistent SSID, `join=3`
- `badpw2-tap.log` — real SSID + wrong password, `join=2`
- `badpw-boot.log` — the auto-rejoin that masks a wrong password
