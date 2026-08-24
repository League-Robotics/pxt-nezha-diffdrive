---
status: in-progress
sprint: '007'
tickets:
- 007-003
---

# Wire cruise==0 "configured default" resolves to a full-duty ~875 mm/s lunge

Priority: **High** — code review 2026-08-23, R-11 (BLK-03 + API-03; both
CONFIRMED; 874.6 mm/s re-computed independently).

The wire grammar documents `0` as "use the configured default" for
cruise/speed on all four motion verbs. `engineDefaultCruiseMmS()`
(`shims.cpp:340-346`) resolves it to `fullDutyVelocity` ≈ 875 mm/s
(10795/(10/0.8102)); no downstream clamp — the dominant wheel lands exactly
at the duty rail. That is ~1.5× the 60 cm/s the project's own bench notes
record as "unusable" (`test.ts:229-230`). A spec-following host that sends
`MOVE_X 500 0 0 5000` gets a flat-out lunge.

Provenance detail: the comment audit recovered upstream radio-robot's
truncated comment on `fullDutyVelocity` — upstream, `0` means
"uncalibrated → VELOCITY commands refused". The vendoring step truncated
the comment (`diffdrive.h:91`) and the refuse-semantics were lost; the
sentinel inverted from *refuse* to *floor it*.

There is also no `default_cruise` in `kFields`, so the "configured default"
is not configurable.

## What to do

- Resolve `0` to a sane default (e.g. the block layer's `defaultSpeed`
  equivalent) or refuse the command — not the duty ceiling.
- Add a `default_cruise` config field so the sentinel's name is true.
- Host-test the sentinel on all four verbs.
