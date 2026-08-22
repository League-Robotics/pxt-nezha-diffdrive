---
status: pending
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

## What to do

1. Update the `testrig.ts` handler to `(name: string, arg: number)`, or
   move it to the named `onRun("...")` form that `test.ts` now uses.
2. Build the repo as the repo actually declares itself, not only via the
   deploy copy, so the two cannot drift apart again unnoticed.
