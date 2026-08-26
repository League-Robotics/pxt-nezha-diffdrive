---
status: done
sprint: '022'
tickets:
- 022-001
---

# The firmware hardcodes one radio channel, but the fleet is on several — tovez has been on the wrong one

Priority: **High** — it silently puts a robot on another robot's channel, which
makes a broadcast command ambiguous about which robot it reaches. That cost a
bench session on 2026-08-26.

## The defect

`src/comms/radio_transport.h` hardcodes:

```cpp
static constexpr uint8_t kGroup = 10;
static constexpr int kChannel = 4;
static constexpr int kTransmitPower = 7;
```

But the fleet is not on one channel. From `radio-robot-lib/config/robots/`:

| robot | `connection.radio_channel` | relay |
|---|---:|---|
| vevov | **4** | zavaz |
| tovez | **3** | getez |

Every robot flashed from this repo lands on **channel 4** regardless of its own
configuration. tovez has therefore been running on vevov's channel.

`tools/make_deploy.py`'s `--robot` argument selects only the **flash target**
(`flash(a.robot)`); it never reads robot configuration and never influences the
build. There is no per-robot build path at all.

## How it surfaced

2026-08-26: commands broadcast over the **zavaz** relay (channel 4) were
answered by **tovez**, which by its own config should not have been listening on
that channel. `ID` returned `id diffdrive tovez 1.0.10` over a relay that
`tools/robotlink.py`'s own docstring describes as *"vevov's relay (channel 4).
getez lives on channel 3 and belongs to another robot -- never retune it here."*

Because radio is a broadcast, a second powered robot on the same group and
channel would also receive every command and could also reply. During that
session a board named `vevov` was simultaneously present and had been
reprogrammed as a RADIOBRIDGE by someone else, so which robot was executing a
given `RUN:` verb could not be established from the link alone — only the
overhead camera could tell, and only for the one tag it was watching.

That ambiguity is the real hazard: **a motion command on a shared channel can
move a robot you are not looking at.**

## What to change

`make_deploy.py` must read the target robot's `radio_channel` from
`radio-robot-lib/config/robots/<robot>.json` and build a hex carrying that
channel.

Constraints worth stating up front:

- `make_deploy.py` already builds from a **scratch copy** (`sync()` into
  `.tmp/deploy-head`), so a build-time substitution into that copy is available
  without making the repo's own source per-robot.
- Any NEW file under `src/` must be added to `pxt.json`'s `files` array or it
  never reaches a build — `tests/host/test_pxt_manifest_completeness.py`
  enforces this in both directions.
- The repo's checked-in default must stay channel 4 so an un-parameterised build
  behaves exactly as today.
- `kGroup` (10) is shared fleet-wide and is not per-robot; do not make it one
  without evidence.

## Related

The fleet config also disagrees with itself in places worth a separate look —
`tovez.json` carries `trackwidth = 115` under a note specifying the
caliper-measured **128 mm**, and `rotational_slip = 1.0` under a note
documenting a measured revision to **0.9371**. Not this issue, but the same
config file.

`radio-group-setup-block.md` (sprint 021) proposes a student-facing block for
the radio group. That is a different concern — a runtime block for classroom
use, versus this build-time per-robot channel — but the two should agree on
where radio identity actually lives before both are built.
