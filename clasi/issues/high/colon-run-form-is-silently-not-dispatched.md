---
status: pending
---

# `RUN:<verb>:<arg>` is silently not dispatched — and `test.ts`'s own header documents it as the vocabulary

Priority: **High** — it is a *silent* no-op on the documented form. The
failure mode is indistinguishable from a broken handler, a bad flash, or
dead firmware, and it costs a session every time someone hits it.

MEASURED gopiv 2026-09-08,
`captures/identity-setters-gopiv-20260908/session.log` and `notes.md`
(sprint 037 ticket 007), fw built from that sprint's HEAD.

## What happens

With a handler registered via `diffDrive.onRun("ident", …)` — confirmed
registered, `FUNCS #1` answers `funcs ident` — the colon form produces
nothing at all:

```
--> RUN:ident:set
<-- (silence)
--> RUN:ident:bogus
<-- (silence)
```

Not an error, not a `nack`, not the handler's own fallback branch. The
handler body never runs. The board stays healthy throughout (`pong`
monotonic across the whole exchange, `status … wedge=0 i2cf=0`), so
nothing surfaces as a fault.

The sequenced space form, on the same board in the same session,
works:

```
--> RUN ident bogus #1
<-- ack 1 0 none
<-- IDENT:? want set|ws|long|reset
--> RUN ident set #2
<-- ack 2 0 none
<-- DBG:role role=TESTROLE commonName=testbot trunc=0
<-- IDENT:set role=TESTROLE common=testbot profile=testprofile
```

## Why this is worth an issue rather than a note

**The two in-repo sources disagree, and the one a reader reaches first is
the wrong one.**

- `test/test.ts`'s header comment documents the vocabulary as
  `RUN:<verb>[:arg[:arg...]]` and lists every verb in that form
  (`tour:world`, `straight:100`, `pivot:90`, …). This is the file
  anybody driving a robot opens first.
- `src/blocks/run.ts`'s `onRun()` doc comment documents
  `RUN <name> [<arg>] #<id>`, e.g. `RUN pivot 180 #7`.

`.claude/rules/playfield-testing.md` also states the cleartext `RUN:`
path is a *different parser path* that is NOT sequenced, and that
`RUN:tour:wheels` unsequenced "returns its `DBG:tour=` receipt
normally" — which is the behaviour this measurement did not reproduce
for a freshly registered handler.

So one of three things is true, and which one is a **stakeholder /
maintainer decision**, not something to infer:

1. The colon path regressed at some point and the rule file plus
   `test.ts`'s header now describe behaviour the firmware no longer has.
2. The colon path still works for the handlers `test.ts` registers, and
   something about a *newly* registered handler (registration ordering,
   the catch-all, the arg being non-numeric) excludes it — in which case
   the boundary needs documenting, because it is invisible.
3. The colon form was always meant to be USB/console-only and its
   appearance in `test.ts`'s header is the bug.

## What is NOT in question

The space form works and is what `tools/robotlink.py` and friends already
emit. Nothing operational is blocked. This is about the *documented*
form silently doing nothing.

## Suggested fix

Whichever of the three above is true, the silent-drop is the real
defect: an unrecognised or undispatchable `RUN` line should emit
something (`DBG:run unknown …` or a `nack`) rather than nothing. A
student typing the form their own test program's header documents
currently gets no feedback of any kind.

Related: `.claude/rules/playfield-testing.md`'s "RUN verbs are
string-keyed — numeric RUN is a silent no-op" section, which pins the
adjacent trap in `tests/tools/test_run_verbs.py`. Same failure shape,
different trigger.
