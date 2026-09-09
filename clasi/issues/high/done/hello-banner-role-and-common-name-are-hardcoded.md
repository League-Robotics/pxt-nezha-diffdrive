---
status: done
sprint: '037'
tickets:
- 037-001
- 037-003
- 037-004
- 037-006
- 037-007
---

# HELLO banner `role` and `common_name` are hardcoded literals — make them settable

Priority: **High** — same class as `kprofile-needs-a-runtime-setter.md`
and sprint 036's `setupWifi()`, and these two should be planned
together: it is one pattern applied three times.

Stakeholder direction 2026-09-07, citing radio-robot-lib's wiki
`protocol#24-the-hello-banner-is-not-this-grammar-2026-08-27`:
"make sure that we can programmatically set the role and common_name in
the HELLO line."

## Current state: no, we cannot

`WireHandler::sendBanner()` (`src/comms/wire_handler.cpp:1431-1438`):

```cpp
char buf[96];
snprintf(buf, sizeof(buf), "device NEZHA2 robot %s %s\n", identity.name,
              identity.serial);
```

`NEZHA2` (role) and `robot` (common_name) are **string literals inside
the format string**. They are not in `Wire::Identity`, not baked by
`make_deploy.py`, and not settable at runtime. Only fields 4 and 5
(`device_name`, `serial`) are variable, and both come from silicon.

## The spec

`microbit-radio-relay/docs/announce.md` (the authority; the wiki section
points at it) defines five fields:

```
DEVICE:<role>:<common_name>:<device_name>:<serial>
```

| # | field | meaning |
|---|---|---|
| 1 | sentinel | literal prefix |
| 2 | `role` | device class / firmware family — `RADIOBRIDGE`, `RADIORELAY`, and ours `NEZHA2` |
| 3 | `common_name` | generic role name within the class — `relay`, ours `robot` |
| 4 | `device_name` | `microbit_friendly_name()` |
| 5 | `serial` | `microbit_serial_number()` |

Note the field naming is counter-intuitive and easy to get backwards:
**`role` is `NEZHA2`** (the firmware family), **`common_name` is
`robot`** (the generic name within it). Not the other way round.

## Design — third instance of an established pattern

Follow sprint 036's `setupWifi()` (`protocol.cpp:229`) and the design in
`kprofile-needs-a-runtime-setter.md`; reviewers should treat divergence
from those as needing a reason.

1. Add `role` and `commonName` to `Wire::Identity`
   (`wire_handler.h:96-102`), defaulted so existing behaviour is
   byte-identical.
2. Add `kRole = "NEZHA2"` / `kCommonName = "robot"` constants beside
   `kProfile`/`kVersion` in `protocol.cpp`'s identity block.
3. Point `identity.role` / `identity.commonName` at **Protocol-owned
   buffers seeded from those constants**, not at the literals. As with
   `setProfile()`, `WireAdapter::identity()` hands out borrowed
   `const char*` that `sendBanner()`'s `snprintf` dereferences at emit
   time — so a runtime setter is picked up by the next banner with no
   second `setIdentity()` and no ordering trap.
4. `Protocol::setDeviceRole(const char* role, const char* commonName)`,
   plus the TS/shim surface, following `setupWifi()`'s arity and
   toolbox-visibility shape (sprint 036 ticket 004 pinned those; the
   same traps apply).
5. `sendBanner()` takes both from `identity`, never from a literal.

## Two constraints that are NOT optional

**Whitespace must be rejected or stripped.** `announce.md` says "no
internal whitespace", and for our space-separated emission that is not a
style rule — a space inside `role` or `common_name` shifts every
downstream field position. radio-robot-lib's codec parses the banner
positionally (`tests/host/robot_v6/test_codec.py:122-124` asserts
`fields == ("NEZHA2", "robot", "testbot", "SN001")`), so one space turns
a 4-field reply into 5 and breaks every consumer. Validate at the
setter; do not trust student input.

**The 96-byte banner buffer has no cap on these fields.** Safe today
only because they are compile-time literals. A runtime setter must clip
into fixed buffers, same as `wifiSsid_[33]` — see the identical hazard
noted for `profile` in `wire_handler.cpp:815-826`.

## Related finding — WITHDRAWN 2026-09-08, there is no disagreement

> **This section was wrong and is retained only so the correction is
> findable.** It claimed the space-delimited banner diverged from
> `announce.md` and needed a cross-repo decision. It does not.
>
> The robot's space dialect and the relay's colon dialect are both
> correct. The robot's is space-delimited because v6 dropped `:` as a
> field separator when it retired v5 (dfca4f8, 2026-08-23) — the
> announcement line went with it, deliberately.
>
> `mbdeploy`'s `probe_type` (`devices.py:150-196`) accepts **both**
> dialects and has since 2026-08-27, returning the identical five-field
> dict either way. And `announce.md`'s only regex is
> `DEVICE:(RADIOBRIDGE|RADIORELAY):relay:...` — hardcoded to relays, so
> it never matched a robot in any dialect; it is the relay's spec, not a
> robot spec.
>
> Nothing is broken, nothing needs to converge, and the robot banner
> must NOT be "fixed" to colons. See `radio-robot-lib`
> `docs/design/protocol.md` §2.4 (corrected) and that repo's withdrawn
> issue `hello-banner-emit-the-specified-colon-announcement-format.md`.

### The original (incorrect) text follows

Reported here because it was found while answering the above; it is NOT
part of this issue's fix and must not be changed without a cross-repo
decision.

`announce.md` specifies an uppercase `DEVICE` sentinel, **colon**
separators and `\r\n`. The wiki's §2.4 explicitly says the HELLO banner
"carries colons because it belongs to a separately specified protocol".

This firmware emits a lowercase `device` sentinel, **space** separators
and `\n`:

```
device NEZHA2 robot vevov 1198504156
```

The relay's own banner does follow the spec
(`DEVICE:RADIOBRIDGE:relay:getez:1779042496`), so the two device classes
are on different grammars today.

The space form is not an accident and is not cheap to change — it is
pinned by tests in BOTH repos:

- this repo: `tests/host/test_wire_grammar.py:457,470,544,587,631`,
  `tests/tools/test_rogo.py`, `test_robotlink.py`, `test_fieldlink.py`,
  `tests/host/test_wifi_link.py:413`
- radio-robot-lib: `tests/host/robot_v6/test_codec.py`,
  `test_sim_e2e.py`, `test_transport.py`, `tests/host/rogo/`,
  `tests/protocol/test_protocol_harness.py`, `test_protocol_adversarial.py`,
  plus `tools/sim/`

Changing the robot banner to colons is a breaking protocol change across
two repos and every host tool. Whether the spec or the implementation is
wrong is a **stakeholder decision**, not something to infer. Raise it
before anyone "fixes" either side.

## Verification

Host tests mirroring sprint 036 tickets 003/004: default banner
byte-identical to today's (this is the important one — it is what proves
the refactor to owned buffers changed nothing), setter precedence,
whitespace rejection, truncation, and a set-after-first-banner call
(which should SUCCEED, unlike WiFi). On-hardware confirmation is a
`HELLO` before and after a `setDeviceRole()` call — UNVERIFIED until run.
