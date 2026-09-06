---
title: "turn_calibration.py's wire_get() returns a stale reading, so every gate banner can lie"
status: pending
created: 2026-09-05
---

# `wire_get()` returns a stale reading

`tests/playfield/turn_calibration.py`'s `wire_get()` looks BACK 2.5
seconds and returns the FIRST matching line, so any second `GET` of the
same field inside that window re-reports the earlier answer:

```python
def wire_get(link, field, default=None):
    link.seqd(f'GET {field}', wait=2.0)
    t0 = time.time() - 2.5
    for _, s in link.since(t0, f'get {field} '):
        return float(s.split()[2])
    return default
```

MEASURED tovez 2026-09-05, `captures/session-b-20260905/notes.md`
("Slip correction, and an instrument defect found doing it"): five
different writes read back as one unchanging value through `wire_get()`,
while the same five round-tripped EXACTLY when the raw `get` line was
read with the window defeated. The firmware is correct; the helper is
not.

## Why it matters

Every gate mode prints `rotational_slip=... pivot_overrun=... (live)`
from this helper. That banner is the only record of what the robot was
configured to when a capture was taken, so a wrong one silently
misattributes a measurement to the wrong constant -- exactly the class
of error `.claude/rules/measurement-citations.md` exists to prevent,
except here the fabricated number comes from a tool rather than a
person. Sprint 031 ticket 016's own G1 runs are affected: two runs
printed `1.01` and `0.952` around a write of `0.958`, and at most one of
those can be true. The fix for that session was to verify the live value
with a raw read before driving; the tool should not need that.

## Fix

Window the search FORWARD from the send, not backward, and take the
LAST match rather than the first -- or give `Link` a request/response
correlation for `GET` the way `seqd()` already has one for acks.

## Also in the same function's neighbourhood

`wire_get(link, 'pivot_overrun', 0.0)` reads a field that no longer
exists: design S4.7 renamed it `stop_distance`. The call errors and
returns its DEFAULT of 0.0, which is indistinguishable from a real
reading of zero. Every banner that ever printed `pivot_overrun=0.0` was
printing the default, not the robot. `GET stop_distance` is the live
field and must be what the banner reads. (On tovez `stop_distance` does
genuinely read 0.000000, so that particular conclusion survived -- but
it survived by luck, not by measurement.)

## Acceptance

- [ ] `wire_get()` cannot return a value older than its own request.
- [ ] A regression test writes two different values in quick succession
      and asserts the second read-back is the second value.
- [ ] The banner reads `stop_distance`, and an unknown field name is
      reported as unknown rather than silently becoming the default.
