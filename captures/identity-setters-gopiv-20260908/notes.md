# Runtime identity setters on hardware — gopiv, 2026-09-08

Sprint 037 ticket 007. Artifact for every MEASURED claim about
`setDeviceRole()` / `setProfile()`.

- **Board**: gopiv (micro:bit UID `…049d38a46da36a83…`), on farm node
  **loki**, reached over `_mbserial._tcp` at `192.168.1.149:44475`.
- **Firmware**: built from sprint/037 HEAD, `--robot gopiv --program identity.ts`.
- **Carrier**: farm USB serial daemon, raw TCP. One socket for the whole
  session — `mbdeploy connect` resets the board per invocation, which
  would wipe each setter call before the read meant to prove it.
- **Raw log**: `session.log` (this directory).
- **Program**: `test/identity.ts`, committed. Re-run with
  `uv run python tools/make_deploy.py --robot <name> --program identity.ts`.
- No motion. The motors were never driven, so no geofence or
  pre-flight path check applies and none was run.

## Which program was running — the version string could NOT tell me

`ID` reported `1.20260907.5` both before and after the flash: the sprint
branch carries the same `kVersion` as master, so **the version string
does not discriminate the two firmwares**. That is the trap
`bump-the-version-before-a-behaviour-flash` warns about, walked into
here.

`FUNCS` settled it instead. On the verification build it answers
`funcs ident` (one handler); on the restored `test.ts` build it answers
the full 21-verb list. Every result below was taken while `FUNCS`
returned `funcs ident`.

## Results

All MEASURED, gopiv, 2026-09-08, `session.log` in this directory.

| # | check | result |
|---|---|---|
| 1 | baseline, no setter called | `device NEZHA2 robot gopiv 2175407711` / `id diffdrive gopiv 1.20260907.5 gopiv` — byte-identical to the pre-sprint firmware |
| 2 | `setDeviceRole("TESTROLE","testbot")` + `setProfile("testprofile")` | `device TESTROLE testbot gopiv 2175407711` / `id diffdrive testprofile …` |
| 3 | whitespace `"my robot"` / `"the bot"` | **stripped and accepted** → `device myrobot thebot gopiv …` / profile `thebot`. Banner stays a well-formed 5-field line |
| 4 | over-length (36/36/47 chars) | clipped to `ROLEROLEROLEROLEROLEROL` (23) / `commoncommoncommoncommo` (23) / `profileprofileprofileprofilepro` (31); `DBG:role … trunc=3`, `DBG:profile … trunc=1`. Banner still well-formed, no corruption, no crash |
| 5 | reset to baked defaults | back to `device NEZHA2 robot gopiv 2175407711` — byte-identical to row 1 |
| 6 | board survived | `pong` monotonic 40271 → 93367 across the session, `status … wedge=0 i2cf=0`. No reset, no wedge |

### Late call succeeds — the design's central claim

Every call in rows 2–5 landed **after** the first banner had already gone
out (the board booted at flash time; the session connected later). All
took effect. This is the property that distinguishes these setters from
`setupWifi()`, which needs a late-call guard because `WifiLink::Config`
borrows into its credential buffers and `serviceJoin()` re-reads them on
every retry. Identity has no live-read hazard, so no guard — confirmed
on silicon, not just pinned in source.

### Boot-ordering — the race the constructor seeding exists to prevent

Separate flash. `identity.ts` temporarily called
`setDeviceRole("BOOTROLE","bootbot")` + `setProfile("bootprofile")` as
the **first statements** of `on start`, before the carriers came up. The
very first banner already read:

```
device BOOTROLE bootbot gopiv 2175407711
id diffdrive bootprofile 1.20260907.5 gopiv
```

So a setter called before anything else is *not* overwritten by the
baked defaults. Had the owned buffers been seeded inside
`buildIdentity()` at fiber start instead of in `Protocol`'s constructor,
this call could have landed before the seed and been lost. The probe was
reverted after capture; `test/identity.ts` as committed does not contain
it.

## Two process traps hit in this session, both worth not repeating

**The colon RUN form is silently not dispatched on this build.**
`RUN:ident:set` produced no reply, no effect, and no error — while
`FUNCS` confirmed the handler was registered. The handler body never
ran, not even its fallback branch. The sequenced space form
`RUN ident set #1` works. Roughly an hour went into diagnosing a
firmware fault that was a wire-syntax mistake. `test.ts`'s own header
documents the `RUN:<verb>:<arg>` form, so the two disagree — worth its
own issue, and untouched here since it is outside sprint 037's scope.

**`HELLO` between sequenced verbs desyncs the link.** `HELLO` is a
session RESET (`expectedNext_ = 1`). A capture loop that reads the
banner between `RUN`s and keeps incrementing its own ids gets
`nack 1 0 none` for everything after the first. The fix is to restart
the id counter wherever `HELLO` is sent. The first capture run was lost
to this and is not in `session.log`.

**A build failure did not stop the flash.** `make_deploy.py` failed the
build checkpoint on a stale scratch cache, and because the build and
flash were issued in one shell invocation the flash proceeded with the
*previous* hex. Gates run alone, foreground, result read first —
`never-pipe-a-hardware-gate`, hit again. Recovered by wiping
`.tmp/deploy-identity`, rebuilding, confirming the hex size changed and
the new string was present in `binary.asm`, and only then flashing.

## Board left as found

gopiv was reflashed to the standard `--robot gopiv` `test.ts` build.
Verified after: `device NEZHA2 robot gopiv 2175407711`,
`id diffdrive gopiv 1.20260907.5 gopiv`, and the full 21-verb `FUNCS`
list.
