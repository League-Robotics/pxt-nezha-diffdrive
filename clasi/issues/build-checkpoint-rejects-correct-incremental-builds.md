---
status: pending
---

# The TU checkpoint rejects correct incremental builds, so every `--robot` switch forces a full rebuild

Priority: **Medium** — fail-safe (it errors rather than shipping a bad hex), but it
makes multi-robot deploys cost a full cloud/docker compile per board, and it trains
the operator to reflexively wipe the scratch copy that `tools/DESIGN.md`
deliberately maintains as persistent.

**Found**: 2026-08-27, flashing gopiv and tovez from the mbdeploy farm.

## What `--robot` does

`--robot <name>` is not just a flash-target selector. After `sync()` populates the
scratch copy at `.tmp/deploy-head`, `make_deploy.py` performs three
scratch-copy-only substitutions (the repo's own checked-in source is never
touched):

| injected into | what | source |
|---|---|---|
| `src/comms/radio_transport.h` | `connection.radio_channel` | `radio-robot-lib/config/robots/<robot>.json` |
| `src/comms/protocol.cpp` | `kProfile` (the wire `ID` verb's profile field) | that config's own filename stem |
| `test/test.ts` | boot banner: repo version + robot name | `pyproject.toml` + the robot name |

So a hex is robot-specific and **must not** be flashed to a different board than it
was built for. The `kProfile` injection is the fix for the fleet-wide `"tovez"` bug
described in `identity-comes-from-hardware-not-config`.

## The bug

`_check_translation_units()` (`tools/make_deploy.py`) requires that **all ten**
entries of `EXPECTED_CPP_FILES` appear as `Building CXX object` lines in the
captured build log. That signature is only ever produced by a **from-scratch**
build. `.tmp/deploy-head` is intentionally persistent, so a rebuild there is
**incremental** — CMake correctly recompiles only what changed.

On a `--robot` switch, exactly the injected files change. The check reads that
correct incremental behaviour as a stale cache and hard-fails.

## Reproduction

Artifact: `captures/make-deploy-robot-switch-20260827.log` (this repo,
2026-08-27). Built `--robot gopiv`, then immediately `--robot tovez` in the same
scratch copy:

```
[ 85%] Building CXX object .../nezha-diffdrive/src/comms/radio_transport.cpp.obj
[ 85%] Building CXX object .../nezha-diffdrive/src/comms/protocol.cpp.obj
[ 85%] Building CXX object .../pxtapp/pointers.cpp.obj
...
[100%] Built target MICROBIT_hex

BUILD FAILED: not all nezha-diffdrive translation units were compiled
(missing 'Building CXX object' lines for: src/comms/serial_transport.cpp,
src/comms/wire_adapter.cpp, src/comms/wire_handler.cpp, src/core/diffdrive.cpp,
src/motion/motion_engine.cpp, src/platform/nezha_port.cpp,
src/platform/otos_port.cpp, src/shims.cpp).
```

Exactly the two injected TUs recompiled, plus `pointers.cpp` (pxt regenerates it
from the banner-modified `test.ts`). The other eight were unchanged and legitimately
came from cache. Reproduced twice: `tovez`→`gopiv` and `gopiv`→`tovez`.

## Why it is provably a false positive

The rejected hex is **byte-identical** to the full-build hex that the same
checkpoint accepted, that was flashed to tovez over the farm, and that answered on
hardware:

```
cmp .tmp/deploy-head/built/binary.hex scratchpad/tovez.hex   → identical
                                                    (1,489,166 bytes both)
tovez after flash:  device NEZHA2 robot tovez 2314287040
                    id diffdrive tovez 0.20260827.2 tovez
```

Note the ordering in `build()`: the **artifact** checks — the universal-hex block
count and `MIN_HEX_SIZE_BYTES` — both **passed**. Only the **log-scraping** check
failed. The check infers artifact correctness from a build-log side effect that
depends on cache state, not on the artifact.

## Suggested fix

The property actually wanted is "every expected `.obj` was built from current
sources", not "every expected TU printed a compile line this run". Options, in
rough order of preference:

1. **Check object mtimes against source mtimes** in the scratch copy's build tree —
   catches a genuinely stale object, passes a correct incremental build.
2. **Only require the full TU set when the build tree was absent** (i.e. this run
   was necessarily from-scratch); on an incremental run, require instead that every
   TU whose source is newer than its `.obj` recompiled.
3. **Have `--robot` invalidate deliberately**: if the injected values changed since
   the last build in that scratch copy, wipe automatically rather than making the
   operator do it after a failure.

Option 3 alone would fix the reported symptom but keep the false positive for any
other legitimate incremental build (e.g. editing one `.cpp`).

## Note on a number in earlier reporting

Earlier session notes said "3 of 11 translation units". The correct figure is
**2 of 10** project TUs (`EXPECTED_CPP_FILES` has ten entries); the third compile
line, `pointers.cpp`, is pxt-generated and is not in the checked set.
