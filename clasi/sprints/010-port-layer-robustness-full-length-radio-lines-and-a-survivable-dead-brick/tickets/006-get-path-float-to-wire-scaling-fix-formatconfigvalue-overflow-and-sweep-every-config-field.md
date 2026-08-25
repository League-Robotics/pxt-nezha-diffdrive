---
id: '006'
title: 'GET-path float-to-wire scaling: fix formatConfigValue overflow and sweep every
  config field'
status: open
use-cases: ['SUC-003']
depends-on: []
github-issue: ''
issue: get-full-duty-velocity-returns-garbage.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# GET-path float-to-wire scaling: fix formatConfigValue overflow and sweep every config field

## Description

`GET full_duty_velocity` returns `4294.967040` on a robot whose kernel
correctly holds `10795.0f` — confirmed as a real reporting defect, not a
readiness artifact (`get-full-duty-velocity-returns-garbage.md`'s own
"RESOLVED AMBIGUITY" section: the value is byte-identical before and
after the kernel becomes ready, and `ready=1` itself proves the internal
value is correct, since `out_.ready` requires
`active_.fullDutyVelocity > 0.0f`).

**Root cause, found by reading the code (not assumed):**
`WireHandler::formatConfigValue()` (`src/wire_handler.cpp:231-245`) is
the single function both GET code paths call
(`execGet()`, lines 762 and 775). It computes:

```cpp
constexpr uint32_t kDivisor = 1000000u;  // 10^6
...
float scaled = magnitude * static_cast<float>(kDivisor) + 0.5f;
if (scaled > kMaxScaled) scaled = kMaxScaled;  // kMaxScaled = 4294967040.0f
const uint32_t scaledInt = static_cast<uint32_t>(scaled);
```

For `fullDutyVelocity` = 10795.0: `scaled` = 10,795,000,000.5, which
exceeds `kMaxScaled` (≈4.29e9, the largest value representable as
`uint32_t`), so it clamps to exactly `kMaxScaled`. Dividing that clamped
value by `1,000,000` for the whole/fractional split produces
`4294.967040` — **exactly** the observed output, and exactly the same
output for *any* field whose real magnitude reaches roughly 4295,
regardless of the field's actual value. This is **not**
`fullDutyVelocity`-specific: reading every seeded `Config` value in
`shims.cpp::ensure()` (max_duty 100, ki 6.0, iMax 765.6, pidMax 1276.0,
vMin 255.2, posErrMax 127.6, biasMax 303.7, stallSpeed 191.4, stallDemand
510.4, stallWindow 500.0, twistHoldGain 2.0) confirms `fullDutyVelocity`
(10795.0) is simply the only one of today's 18 fields whose real value
crosses that line — the defect is generic to the function, latent for
any future field or SET value that does the same.

**Why raising the clamp does not fix this**: `uint32_t` cannot represent
`real_value × 1,000,000` for any real value much past ~4295, no matter
where the clamp threshold is set inside `uint32_t`'s range — the type
itself is the ceiling, not the clamp's chosen value. The fix must widen
the intermediate arithmetic, not relocate the clamp.

**The fix**, mirroring WIRE-08's inbound `kWireBoundaryCastCeiling`
pattern (sprint 007 ticket 007, `wire_adapter.h:182`) applied here to
the outbound mirror the issue itself identifies: compute the scaled
value in a wide-enough intermediate (`double` is sufficient — float's
own precision, not the intermediate integer width, is the real accuracy
ceiling, and IEEE `double` holds `magnitude × 1e6` exactly for every
value this project's config fields plausibly reach), and bound the
**input** magnitude against an honest, named ceiling before scaling,
refusing (or logging/flagging, per implementation-time review of what a
GET reply can honestly do — GET never produces an `err`, per
`execGet()`'s own comment, so an out-of-ceiling value should format to
an explicit sentinel or the true magnitude via a fallback representation
rather than the same wrong-looking clamp) rather than silently
substituting an unrelated fixed number.

## Acceptance Criteria

- [ ] `formatConfigValue()`'s intermediate scaling arithmetic no longer
      silently overflows for any field magnitude this project's config
      space plausibly holds (verified up to at least `fullDutyVelocity`'s
      real value, 10795.0, with headroom well beyond it).
- [ ] The fix bounds the **input** value against a named, documented
      ceiling (not a post-scale clamp reachable by ordinary configured
      values) — mirroring `kWireBoundaryCastCeiling`'s doc-comment style
      so a future reader understands why the ceiling is where it is.
- [ ] A new host test loops over all 18 `kFields` entries (not a single
      field), sets each to a representative value via the adapter's
      `onSet`/equivalent, and asserts the `GET` reply round-trips the
      real configured value.
- [ ] A dedicated host test asserts `GET full_duty_velocity` on a kernel
      configured with 10795.0 replies `10795.000000`, not
      `4294.967040`.
- [ ] Existing `formatConfigValue()` behavior for every already-correct
      field (`max_duty 100.000008`-style six-fixed-digit formatting) is
      unchanged — this is a targeted fix to the overflow path only, not
      a reformat.
- [ ] `execSet()`'s own field validity is unaffected — this ticket
      touches only the GET-reply formatting function; inbound `SET`
      parsing (`parseFloatField()`) is untouched, confirmed by reading
      it, per sprint.md's Architecture (WIRE-08's inbound fix already
      covers that direction).

## Implementation Plan

**Approach.** A self-contained fix inside one pure function in
`wire_handler.cpp`. No new module, no cross-module dependency change.

**Files to modify:**
- `src/wire_handler.cpp` — `formatConfigValue()`'s intermediate
  arithmetic and input-bounding logic.
- `src/wire_handler.h` — if a new named ceiling constant is introduced
  (mirroring `kWireBoundaryCastCeiling`'s placement pattern, adapted for
  this file's own host-portable, no-project-includes convention per
  `src/DESIGN.md` §4).

**C++11 gate coverage — IN gate.** `wire_handler.cpp` is one of the four
files the `-std=c++11 -fsyntax-only` syntax gate already covers
(`src/DESIGN.md` §11). A `double` intermediate and a named `constexpr`
ceiling are unremarkable C++11; confirm the gate passes as part of this
ticket's test run.

**Testing plan.**
- New: the 18-field sweep test (loop, not one-field patch, per the
  issue's own "Suggested check when fixing").
- New: the specific `fullDutyVelocity`-at-10795.0 regression test.
- Existing: run `tests/host`'s existing GET/SET-formatting tests
  (`test_wire_handler_get_set*.py` or equivalent) to confirm the
  already-correct fields' six-fixed-digit formatting is unchanged.

**Documentation updates.** `src/DESIGN.md` §4's `formatConfigValue()`
doc-comment reference (if one exists) or §5's GET/SET paragraph gains a
note on the widened arithmetic — landed via this sprint's design
overlay.
