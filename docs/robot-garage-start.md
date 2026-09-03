# Nezha DiffDrive robots (pxt-nezha-diffdrive)

Published to http://robot-garage.home/doku.php?id=nezha-diffdrive:start
by `tools/publish_wiki.py` -- **re-run `uv run python tools/publish_wiki.py --all`
after editing this file.**

The micro:bit + ELECFREAKS Nezha differential-drive robots (tovez,
gopiv, vevov, tigez, ...) run the `nezha-diffdrive` MakeCode extension:
a closed-loop wheel controller and the v6 ASCII wire protocol on USB,
WiFi and (optionally) radio.

- **Connecting to a robot** -- carriers, discovery, commands, gotchas:
  [connecting](http://robot-garage.home/doku.php?id=nezha-diffdrive:connecting)
- Source: the private `pxt-nezha-diffdrive` repo (`docs/` holds the
  design notes; `docs/knowledge/` the measured findings); the published
  extension is `League-Microbit/pxt-diff-drive` on GitHub.
- The farm the boards are flashed from: [mbdeploy](http://robot-garage.home/doku.php?id=mbdeploy),
  [nolanet](http://robot-garage.home/doku.php?id=nolanet).
- The radio relay pool, for boards that still use the v6 radio link:
  [micro:bit relay server](http://robot-garage.home/doku.php?id=microbit-relay:start).

Private facts that live only here: the mesh SSID the robots join is
"Busboom Mesh"; WiFi credentials are the gitignored
`config/wifi_secrets.json` in the repo checkout (copy it from another
checkout, never commit it).
