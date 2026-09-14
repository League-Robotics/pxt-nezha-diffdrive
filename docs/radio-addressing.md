# Radio addressing: a board's name is its address

**This page is not the spec.** The normative definition is radio-robot-lib's
[`docs/design/radio-addressing.md`](https://github.com/League-Robotics/radio-robot-lib/blob/main/docs/design/radio-addressing.md)
(also the radio-robot-lib wiki page *Radio addressing*). If this page and that
spec disagree, the spec wins. `docs/radio-address-vectors.json` here is a
transcription of the spec's vectors, copied from microbit-radio-relay's
`server/tests/radio-address-vectors.json`.

The map changed on 2026-09-13. The old map (`channel = 25 + 2*(n % 25)`, group
`1 + n//25` skipping 10) is retired. It used only 25 channels, so robots shared
radio frequencies early (vevov and togov were both on 37).

## The map

A micro:bit's five-letter name is `NRF_FICR->DEVICEID[1]` modulo 3125, written in
base 5. Decode it back to `n`, first letter most significant:

```
consonants (letters 0, 2, 4)   z v g p t  = 0 1 2 3 4
vowels     (letters 1, 3)      u o i e a  = 0 1 2 3 4

channel = 11 + (n % 73)     # 11 .. 83
group   = 15 + (n % 241)    # 15 .. 255
```

Reverse (pair to name), used by diagnostics:
`n = (c-11) + 73 * ((((g-15) - (c-11) + 241) * 208) % 241)`. Reject the pair unless
`11 <= c <= 83`, `15 <= g <= 255` and `n < 3125`. Most pairs belong to no name.

## Where this repo implements it

| code | what it does |
|---|---|
| `tools/make_deploy.py` `derive_radio_from_name()` / `radio_address_to_name()` | the name-derived pair a build reports beside the config's pair; the config (`connection.radio_channel` / `radio_group` in radio-robot-lib) stays authoritative |
| `tools/robotlink.py` `radio_address()` | `tools/field_calibration.json`'s explicit pair for a robot when present, else the derivation |
| `tools/radio-address-dump` | the cross-repo conformance dump (`--list`, then `python [1|2]`) |

The robot firmware in this repo never derives its own address. A make_deploy
build bakes the config's pair into `kChannel` / `kGroup`; the calibration image
(nezha-robot-template) derives it at boot in `test/boot.ts` and calls
`diffDrive.setupRadio()`.

## Conformance

`tools/radio-address-dump python` must hash to the spec's **D2**
(`305d6ee08cfae978fe13e1179c6047a56e1b0b1abe23c2cb757f01461cf2d35f`), and the
three-column form to **D1** (`c22691f1c47bed3ac5317119487a30ea8fd0224d61c50bba551b1e624b548a84`).
`tests/tools/test_radio_address_dump.py` checks both, and microbit-radio-relay's
`just conformance` compares this repo with every other implementation.

## The fleet

| robot | n | new channel / group | old channel / group |
|---|---|---|---|
| gopiv | 1461 | 12 / 30 | 47 / 60 |
| tigez | | 52 / 179 | 55 / 114 |
| togov | 2681 | 64 / 45 | 37 / 109 |
| tovez | 2665 | 48 / 29 | 55 / 108 |
| vevav | 1046 | 35 / 97 | 67 / 43 |
| vevov | 1031 | 20 / 82 | 37 / 43 |
| zeguz | 425 | 71 / 199 | 25 / 19 |
| zetuv | 476 | 49 / 250 | 27 / 21 |

No two robots share a channel under the new map. The migration of the fleet is
tracked in microbit-radio-relay's `docs/plans/fleet-radio-address-migration.md`.
