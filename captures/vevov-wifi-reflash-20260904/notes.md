# vevov reflashed with the WiFi link, 2026-09-04 (farm node magni)

Same fix as tigez (`../tigez-wifi-reflash-20260904/notes.md`): the
2026-09-04 morning hex had WiFi disabled for want of
`config/wifi_secrets.json` in the main checkout.

Build `build.log`: `WiFi link ENABLED, ssid='Busboom Mesh'`, geometry bake
0.70066 / 128 / 0.987 / 2.2, radio link ON. Hex `vevov-wifi.hex` sha256
9dbaa5ad76d9d653485d27aa923693dba32a6bddf0992832d52caf6781c10bc0.
Flash `flash-1.log`: first try, 103 pages.

Measured over WiFi TCP, wheels up on the stand:
- `vevov robot link` on `_robotlink._tcp` and vevov.local:7654 reachable
  by the time the first probe ran (< 60 s after the flash);
  `id diffdrive vevov 1.20260904.3 vevov` (`wifi-first-contact.log`).
- `wire_acceptance.py --wifi-tcp vevov --only-all-verbs --no-estop`:
  40 passed, 0 failed, 0 blocked (`wifi-acceptance-full.log`).
- `wifi-soak-bench.log`: 20 alternating MOVE_X pivots in one TCP session,
  all acked and run to done, PING answered after each: 20/20, link held,
  46 s.
