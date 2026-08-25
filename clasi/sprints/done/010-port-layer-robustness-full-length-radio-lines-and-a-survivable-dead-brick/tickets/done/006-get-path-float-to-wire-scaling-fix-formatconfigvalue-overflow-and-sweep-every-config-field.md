---
id: '006'
title: 'GET-path float-to-wire scaling: fix formatConfigValue overflow and sweep every
  config field'
status: done
use-cases:
- SUC-003
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

- [x] `formatConfigValue()`'s intermediate scaling arithmetic no longer
      silently overflows for any field magnitude this project's config
      space plausibly holds (verified up to at least `fullDutyVelocity`'s
      real value, 10795.0, with headroom well beyond it).
- [x] The fix bounds the **input** value against a named, documented
      ceiling (not a post-scale clamp reachable by ordinary configured
      values) — mirroring `kWireBoundaryCastCeiling`'s doc-comment style
      so a future reader understands why the ceiling is where it is.
- [x] A new host test loops over all 18 `kFields` entries (not a single
      field), sets each to a representative value via the adapter's
      `onSet`/equivalent, and asserts the `GET` reply round-trips the
      real configured value.
- [x] A dedicated host test asserts `GET full_duty_velocity` on a kernel
      configured with 10795.0 replies `10795.000000`, not
      `4294.967040`.
- [x] Existing `formatConfigValue()` behavior for every already-correct
      field (`max_duty 100.000008`-style six-fixed-digit formatting) is
      unchanged — this is a targeted fix to the overflow path only, not
      a reformat.
- [x] `execSet()`'s own field validity is unaffected — this ticket
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

## Implementation Notes

**The scaling factor, confirmed by reading the code, not assumed:**
`kDivisor = 1,000,000u` (×10⁶) exactly as the issue's own root-cause
section already stated — `10795 × 1,000,000 = 10,795,000,000`, which
does exceed `uint32_t`'s ~4.29e9 range (unlike `10795 × 1000`, which
the ticket's own caution about not assuming ×10⁶ correctly rules out as
NOT the overflow's cause). The overflow line is real magnitude ≈ 4295
(`UINT32_MAX / 1,000,000`).

**The fix:** `formatConfigValue()` (`wire_handler.cpp`) now bounds the
INPUT magnitude against a new, internal, anonymous-namespace constant,
`kGetValueCeiling = 1,000,000.0f` (two orders of magnitude above
`fullDutyVelocity`'s own 10795.0), clamping only values that exceed it
— no real `kFields` value comes near this bound, so every field's real
GET reply is now the true value, never a clamp. The scaling
intermediate itself widened from `uint32_t` to `double` (then a
`uint64_t` for the exact integer split), which is what makes the
post-ceiling arithmetic safe rather than merely relocating the overflow.
`kGetValueCeiling` is declared in `wire_handler.cpp`'s own anonymous
namespace (mirroring `kMaxMotionTimeoutMs`'s placement immediately
above it), NOT `wire_handler.h` — it is purely an implementation detail
of one function, with no external caller needing it, so no header
change was needed. It is a deliberate SIBLING of
`kWireBoundaryCastCeiling` (`wire_adapter.h`), not a reuse: reusing that
symbol would require this host-portable, no-project-includes file to
include `wire_adapter.h`, inverting `src/DESIGN.md` §1's layering rule
(same reasoning `kMaxMotionTimeoutMs`'s own doc comment already gives
for a different ceiling pair).

**Sweep results:** all 18 `kFields` entries were exercised
(`tests/host/test_wire_motion_verbs.py`, field names discovered
dynamically from a bare `GET` dump, never hardcoded as "18"). Only
`full_duty_velocity` (10795.0) crosses the old ~4295 overflow line among
today's real seeded values — confirmed by direct measurement in this
sweep, not just by reading `shims.cpp`, since the sweep is now the
generic, repeatable proof.

**Test-discrimination proof:** the production fix was `git stash`ed and
all 5 new tests (4 in `test_wire_grammar.py`, 1 in
`test_wire_motion_verbs.py`) were confirmed to fail against the reverted
code — the `full_duty_velocity` sweep row failed with `4294.96704`, the
isolated tests failed with the literal `4294.967040` sentinel — then the
stash was restored and all tests confirmed green again.

**Deviation from the AC's literal wording, and why:** AC 4 asks for a
test through "a kernel configured with 10795.0" replying exactly
`10795.000000`. Direct `float32` computation
(`10795000.0f * 0.001f == 10795.0009765625f`) shows `wire_adapter.cpp`'s
own `onGet()` descale (`static_cast<float>(getConfigValue(...)) *
0.001f`, single precision, UNTOUCHED by this ticket — AC 6) makes an
EXACT `10795.000000` unreachable through the real kernel/adapter path
regardless of this fix; that pre-existing imprecision is a different,
out-of-scope function. The dedicated exact-match test instead exercises
`formatConfigValue()` directly, through `WireMockAdapter`'s
`onGet()` override (`test_wire_grammar.py`'s `wg` fixture,
`set_get_override()`), which is the correct isolation boundary for
proving the actual fixed function is now correct at exactly 10795.0.
The real `kFields`/kernel path is additionally covered by the AC 3
sweep (approx tolerance, matching this repo's own pre-existing
`test_get_set_field_name_table_round_trips` precedent), which confirms
`full_duty_velocity` round-trips close to 10795.0 through the real
adapter and never reproduces the old wraparound string. Flagging this
for team-lead/reviewer visibility rather than silently reinterpreting
the AC.

**`src/DESIGN.md`:** grepped for `formatConfigValue`/`kMaxScaled`/
scaling-related text — none found; §334's GET/SET paragraph documents
only the field-name-table mapping, not `formatConfigValue()`'s own
internals, so no existing doc-comment reference needed updating. No
edit made (per dispatch instruction not to touch design docs) — flagging
here in case team-lead judges an overlay note worthwhile anyway.

**Concurrency:** `wire_handler.cpp` and `wire_handler.h` were being
edited concurrently by ticket 003 (STATUS `cyc=`) during this ticket's
execution. `wire_handler.cpp`'s `cyc=` addition landed (and was
committed) before this ticket's own edit; `wire_handler.h` was not
touched by this ticket at all. `tests/host/test_wire_grammar.py` picked
up ticket 003's own STATUS/`cyc` test additions concurrently while this
ticket was working in the same file — staged and committed as two
separate hunks (this ticket's own insertion isolated via `git apply
--cached` against only its own hunk) so ticket 003's uncommitted work
was left untouched for that agent to commit itself.
