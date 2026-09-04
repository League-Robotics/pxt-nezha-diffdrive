# tigez reflashed with the WiFi link, 2026-09-04 (farm node meili)

Why: yesterday's fleet hex was built from the main checkout, which had no
`config/wifi_secrets.json` (it lived only in the wifi-transport worktree),
so make_deploy left the WiFi link DISABLED (`../fleet-flash-20260904/notes.md`).

Build: `uv run python tools/make_deploy.py --robot tigez --radio-link` after
copying the secrets in (`build.log`: `WiFi link ENABLED, ssid='Busboom Mesh'`,
geometry bake 0.78623 / 114.4 / 0.9617 / 5.5, radio link ON). Hex
`tigez-wifi.hex`, sha256
0f44a9e7941659ba5b338a08cf03728d3a0e65821e146723c9e9944b17aab436, version
1.20260904.2.

Flash: `mbdeploy deploy --remote tigez --hex ...` -- attempt 1 timed out
reading the probe after the mass erase and left the board BLANK
(`flash-1.log`, same failure as 2026-09-04 morning); attempt 2 succeeded
(`flash-2.log`, 46 pages programmed).

## Measured over the WiFi TCP link (wheels up on the farm stand)

- Within ~40 s of the flash tigez announced `tigez robot link` on
  `_robotlink._tcp` and `tigez.local` resolved to 192.168.1.217; a raw
  TCP connect to :7654 got the `device NEZHA2 robot tigez 3527777815`
  banner.
- `wifilink.py --tcp --robot tigez PING STATUS ID` -> `pong`, status,
  `id diffdrive tigez 1.20260904.2 tigez` (`wifi-acceptance.log`).
- `wire_acceptance.py --wifi-tcp tigez --only-all-verbs --no-estop`:
  **40 PASS / 0 FAIL** (`wifi-acceptance-full.log`), every verb incl.
  WHEELS_X / MOVE_X / MOVE_V / GO_TO_R / GO_TO_W turning the wheels.
- Soak (`wifi-soak-bench.log`): 20 alternating `MOVE_X 0 +-1571` pivots
  over one TCP session, each acked, each run to `done`, PING answered
  after every one -- 20/20 alive in 46 s, link never dropped. This is
  the unloaded stand; gopiv's WiFi died on the FIELD under motor load,
  which this does not reproduce. Next: the same soak on the playfield.
