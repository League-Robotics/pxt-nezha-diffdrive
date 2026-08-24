---
status: done
sprint: 008
tickets:
- 008-005
---

# `TLM AUTO` and `TLM BUFFER` have no defined telemetry column set

Priority: **Low** — surfaced by sprint 004 ticket 004 while implementing
`WireAdapter::buildSnapshot()`. Not a code review finding; found by an
implementer reading the spec for an answer that was not there.

## What is undefined

`buildSnapshot()` selects the telemetry column set by mode. It special-cases
`mode_ == kFull` (20 columns: POSE's 12 plus 8 more) and otherwise projects
POSE's 12. That means `kAuto` and `kBuffer` silently fall through to the POSE
column set.

That fall-through is a **default chosen by the implementer, not a decision
recorded anywhere**. Neither sprint 004's sprint.md nor
`radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md` defines what
column set `TLM AUTO` or `TLM BUFFER` should emit, so there was nothing to
implement against. It is documented in the code as such.

## Why it matters later, not now

Today the fall-through is harmless: POSE's 12 columns are a sensible default
and no host asks for `AUTO`/`BUFFER` telemetry with an expectation about
width. It becomes a real problem the moment either mode gets genuine
semantics — a host that requests `TLM AUTO` and parses the `thdr` it gets
back will silently bind to whatever the fall-through happens to emit that
day, and changing the default later would break it without any version
signal.

## What to do

Decide and write down, per mode:

- Does `AUTO` mean "the same columns as POSE, emitted on a cadence the robot
  chooses"? Or "whichever set the last explicit `TLM` selected"?
- Does `BUFFER` imply a *narrower* set, given that buffering many frames is
  exactly where line width costs the most?
- If either mode should be an error until it has real semantics, answering
  `err` is better than emitting a column set no one specified.

Whatever is chosen, pin it with a host test on the emitted `thdr` for each
mode, so the column set per mode stops being an implementation accident.

## Related

- `wire-timeout-hardening.md` (sprint 008) — same shape of problem: verbs
  whose edge semantics were never stated, then diverged. Worth fixing in the
  same pass.
- Sprint 004 ticket 004 is where the fall-through was introduced and
  documented.
