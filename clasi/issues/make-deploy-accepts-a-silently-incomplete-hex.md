---
status: pending
sprint: ''
---

# `make_deploy.py`'s triage accepts a silently-incomplete but error-free hex

Priority: **High** — this is the gate the whole per-sprint build-checkpoint
convention rests on. If it can pass a hex that is missing code, then every
"flashable hex confirmed" in the sprint record is weaker than it reads.

## What was observed

Sprint 016's build checkpoint (2026-08-26) hit a stale vendored
`codal-microbit-v2` checkout under `.tmp/deploy-head/built/dockercodal`, not at
its pinned `v0.2.13` / `490a890` revision. A partial cache-clear then produced a
build that reported **no errors at all** and yielded
`built/binary.hex` at **1,046,410 bytes** — against the correct
**1,442,546 bytes** from a clean rebuild. Roughly 400 KB, or 27%, missing, with
a zero exit status and nothing in the log to flag it.

The programmer did not take it at face value: they checked the small hex still
contained this sprint's own strings, then wiped `.tmp/deploy-head` entirely and
rebuilt, which reproduced the correct size with all ten nezha-diffdrive
translation units genuinely visible as `Building CXX object` lines.

## Why the existing triage misses it

`make_deploy.py` (triage-aware since sprint 008) distinguishes three outcomes: a
real `.cpp` compile failure, the two documented benign abort shapes (the legacy
V1 `bbc-microbit-classic-gcc` hex-merge failure, and the nondeterministic
packaging abort surfacing as `TS9283`/`TS9043`/`TS9200`, retried once), and
success. **All three are judged from the build log.** A build whose log is clean
but whose output is short falls straight through into "success".

The existing sprint-014 assertions do not catch it either: zero `:0400000A`
markers and an absent `dockeryt/` are both still true of an incomplete hex. Only
the byte size gives it away, and nothing checks the byte size.

## What to change

At minimum, two cheap post-build assertions in `make_deploy.py`:

1. **A floor on `binary.hex` size.** The last several checkpoints measured
   1,423,241 (sprint 014), 1,434,671 (015) and 1,442,546 (016) bytes — a tight,
   slowly-growing band. A floor well below that but well above a truncated build
   (say 1.2 MB) would have caught this instance, and the number should be a named
   constant with those measurements recorded beside it.
2. **A translation-unit count.** All ten nezha-diffdrive `.cpp` files must appear
   as `Building CXX object` lines. That is already what a human checks by hand at
   every checkpoint; it should be mechanical.

Worth considering additionally: detect the stale-vendored-checkout condition
directly, since that is the actual root cause here — compare the resolved
`dockercodal` revision against the pin in `built/codal.json` and fail loudly on
a mismatch rather than building from whatever happens to be on disk.

## Why this matters more than it looks

The per-sprint build checkpoint exists precisely because the host suite cannot
prove target viability — `tests/host/` compiles at `-std=c++20` for the desktop
while both real targets compile at `-std=c++11`, and `pxt.json` manifest
omissions are invisible to it. Sprints 014, 015 and 016 all had their checkpoint
find something real (an aborted V1 variant, a five-argument shim plus a
line-wrapped signature, this stale checkout). It is a load-bearing gate, and a
load-bearing gate that can silently pass a 27%-short binary needs fixing before
it is trusted again.

Found during sprint 016 ticket 007; full diagnostic trail in that ticket's Build
Evidence section.
