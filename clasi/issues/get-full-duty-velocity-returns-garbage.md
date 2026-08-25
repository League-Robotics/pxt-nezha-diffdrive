---
status: pending
sprint: '010'
---

# `GET full_duty_velocity` returns 4294.967040 where the firmware sets 10795.0

Priority: **High** — found on hardware (tovez, 2026-08-24), reproducible, and
safety-relevant. Not a code-review finding; observed during the post-sprint-008
bench session.

## The observation

`src/shims.cpp`'s `ensure()` sets the kernel config explicitly:

```cpp
cfg.fullDutyVelocity = 10795.0f; // [counts/s]
```

A `GET` over the v6 wire on a freshly flashed tovez returns:

```
get full_duty_velocity 4294.967040
```

Every neighbouring field round-trips correctly, so this is **not** display
noise from the `×1000` integer round-trip:

```
get max_duty        100.000008     (set to 100.0f)
get pid_ki            6.000001     (set to 6.0f)
get speed_floor     255.200016     (set to 255.2f)
get default_cruise  150.000000     (sprint 007, correct)
get rotational_slip   0.952000     (sprint 007, correct)
```

`4294.967040` is `4294967040 / 10^6`, and **`4294967040` is `0xFFFFFF00`** —
the bit pattern of `-256` reinterpreted as `uint32`. That is the signature of
a signed value crossing an unsigned boundary, not of a plausible velocity.

## Why this matters beyond a wrong readout

`fullDutyVelocity`'s upstream contract — the one
`vendored-kernel-upstream-rediff.md` (sprint 009) restores from truncated
comment text — is **`0 = uncalibrated → VELOCITY refused`**. The kernel's
`checkCommandable()` refuses velocity-mode commands when it is unset.

A garbage **non-zero** value defeats that guard: velocity commands are not
refused, and the duty↔velocity conversion computes from a nonsense scale.
Sprint 007 ticket 003 deliberately separated the wire's `default_cruise` from
`fullDutyVelocity` precisely so the kernel's refusal logic stayed intact; this
defect undermines it from the other direction.

## Probable mechanism (unconfirmed — do not assume)

This is the same **class** the code review found at the wire boundary in the
other direction: WIRE-08, float→int casts being UB on overflow with a
**host/target sign split**. Sprint 007 ticket 007 fixed the `SET`/inbound
direction with `kWireBoundaryCastCeiling = 2e9` in `wire_adapter.h`. The
`GET`/outbound path may carry the mirror defect, unguarded.

Two candidate explanations, both worth testing before fixing:
1. The outbound `GET` scaling overflows or sign-confuses for values of this
   magnitude (`10795 × 1000 = 10,795,000` is well inside int32, so plain
   overflow alone does not explain it — hence "unconfirmed").
2. The kernel's config was never applied because `begin()` did not complete
   (see the caveat below), so `GET` is reading an uninitialised or sentinel
   field rather than the configured one.

**Explanation 2 is quite likely** and would make this a reporting problem
rather than a scaling bug — but it would still be a defect, because `GET`
would be reporting a fabricated value instead of signalling "unset".

## Reproduction

1. Flash a robot from master (`4e14817` or later).
2. Over USB serial: `GET #1`.
3. Observe `get full_duty_velocity 4294.967040`.

Note the bench state when observed: `STATUS` reported
`ready=0 active=0 connL=0 connR=0 i2cf=0`, i.e. the kernel had not become
ready — see `unpowered-nezha-brick-wedges-program-at-boot.md`'s bench note
from the same session. **Re-check this GET on a robot whose brick is
reachable before concluding which explanation holds.** If the value is
correct once `ready=1`, this is explanation 2 and the fix is to report unset
fields honestly rather than emit a bit pattern.

## Related

- `wire-constants-single-source.md` (sprint 008, closed) — fixed `kVersion`'s
  drift; this is a different field failing in a different way.
- Sprint 007 ticket 007 / WIRE-08 — the inbound cast clamps.
- `vendored-kernel-upstream-rediff.md` (sprint 009) — restores the
  `0 = uncalibrated → VELOCITY refused` contract text this defect defeats.

## RESOLVED AMBIGUITY — it is explanation 1, the outbound GET path (2026-08-24)

The re-check this issue asked for has been done, on the same robot, once its
kernel was healthy. **Explanation 2 (reading an unpromoted/uninitialised
config) is ruled out. This is a real reporting defect.**

Evidence:

```
# fresh boot, kernel never ticked
get full_duty_velocity 4294.967040
status ready=0 ... connL=0 connR=0

# after RUN:straight ticks the kernel 147 cycles
STRAIGHT:end:...
get full_duty_velocity 4294.967040          <-- IDENTICAL
status ready=1 active=0 connL=1 connR=1 flags=31 i2cf=6
```

The value is byte-identical before and after. And critically, `ready=1` is
**itself proof that the internal value is correct**:

```cpp
out_.ready = begun_ && active_.fullDutyVelocity > 0.0f;   // diffdrive.cpp:799
```

`ready` cannot be true unless `active_.fullDutyVelocity > 0`. The kernel
promoted `staged_` (which `ensure()` set to `10795.0f`) into `active_` and is
driving the robot correctly with it — encoders moved, duty was applied, the
straight leg completed. **So the firmware holds the right number and the wire
reports a wrong one.**

## Scope of the defect

This is the **outbound/`GET` mirror** of WIRE-08, the finding sprint 007
ticket 007 fixed for the inbound/`SET` direction with
`kWireBoundaryCastCeiling = 2e9` (`wire_adapter.h`). That ticket bounded
floats *arriving* from the wire; nothing bounds floats *leaving* by `GET`.

`10795.0` is not an extreme value, which is what makes this alarming: the
field is not near any plausible int32 edge at ×1000 scaling
(`10,795,000` is well inside int32). A scaling factor larger than ×1000
somewhere in the outbound path would overflow — `10795 × 10^6 ≈ 1.08e10`
does exceed int32 — and the observed `4294967040` (`0xFFFFFF00`) is
consistent with an overflow/UB artifact rather than a legitimate encoding.
**Find the actual outbound scaling before fixing**; do not assume ×10^6.

## Why it matters, restated with the new evidence

The safety concern in this issue's original text stands and is now sharper: a
host reading `GET full_duty_velocity` to decide whether the robot is
calibrated gets `4294.967040` — a plausible-looking non-zero number — from a
robot whose real value is `10795`. Any host-side logic keyed on the
`0 = uncalibrated → VELOCITY refused` contract is reading fiction. The robot
itself is fine; only what it *says* about itself is wrong.

## Suggested check when fixing

Sweep every `GET`-able field for the same defect rather than patching this one
— the neighbouring fields that round-trip cleanly (`max_duty 100.000008`,
`pid_ki 6.000001`, `default_cruise 150.0`) are all small; this is the largest
value in the table and the only one observed wrong, which is itself a clue.
