---
status: done
sprint: '005'
tickets:
- 005-005
- 005-006
---

# testrig.ts no longer compiles: onRunCommand changed under it

`testrig.ts` has a hard type error and **fails the build**. It is not a
warning: `pxt build` stops and emits no hex.

`testrig.ts` currently does:

```ts
diffDrive.onRunCommand(function (n: number) {
    rigPending = n
})
```

but `onRunCommand` was widened to the named-verb dispatch signature in
`main.ts:204`:

```ts
export function onRunCommand(
    handler: (name: string, arg: number) => void): void
```

so the call no longer type-checks:

```
testrig.ts(44,24): error TS2345:
  Argument of type '(n: number) => void' is not assignable to
  parameter of type '(name: string, arg: number) => void'.
```

`testrig.ts` is the **zeguz** rig harness (drum motor, dummy motor, OTOS
on a 360 degree servo on J1). Nobody has built it since the RUN dispatch
was reworked from a single numeric command into named verbs.

## Why nobody noticed

Not because `testFiles` are unchecked — they are checked. Moving
`testrig.ts` into `testFiles` still fails the build, verified directly.

It went unnoticed because **nothing anyone actually builds contains
this file.** Every hex comes out of the persistent deploy env
(`.tmp/deploy-head/`), which lists only `test.ts` in `files` and has an
empty `testFiles` — `testrig.ts` is not copied there at all. So the
repo's own `pxt build` has effectively not been run in a while, and the
one build path in daily use cannot see the file.

That is the more interesting half of this issue: the working build and
the repo build have silently diverged, and only the working one is
exercised.

## How it surfaced

While test-building a proposed `src/` + `test/` layout, which starts
from the repo's real file list rather than the deploy env's.

## Update from code review 2026-08-23 (R-16: BLK-04 + PY-01, CONFIRMED ×2)

The situation is worse than the type error above — and the type error
description is now stale. The two-arg handler "fix" that landed stores the
**argument** (always 0), never the numeric name: `testrig.ts:47-49`
compiles-ish but `rigExec(0)` matches no branch. And the v6 dispatch
(`main.ts:166-167`) matches RUN by exact *name*, with only 11 named
handlers registered in `test.ts` — so the entire numeric `RUN:<n>`
vocabulary is a **silent no-op** against current firmware. Every command
from `tools/otos_bench.py` and five bench tools (`rotation_check`,
`truth_check`, `pivot_truth`, `turn_sweep`, `otos_levercal`) does nothing,
with no error anywhere. This breakage class is *not* covered by the
sprint-005 TLM retrofit.

Related build-hygiene Minor from the same review: `make_deploy.py`'s
`endswith('test.ts')` filter silently excludes `testrig.ts` from the
deploy env and writes `testFiles=[]` — the exact divergence mechanism
described above, now with line numbers (make_deploy.py:60-69).

## What to do

1. Port the zeguz rig vocabulary to named verbs (or restore a numeric
   compatibility dispatch), and update `otos_bench.py` and the five bench
   tools to speak it — see `tools-link-layer-consolidation.md` for the
   shared-layer shape.
2. Build the repo as the repo actually declares itself, not only via the
   deploy copy, so the two cannot drift apart again unnoticed; fix the
   `make_deploy.py` filter as part of this.
