---
status: in-progress
sprint: '014'
tickets:
- 014-001
- 014-002
---

# Never build the V1 (`mbdal`) variant — build `mbcodal` only, via `csv-mbcodal`

The fleet is nRF52833 (micro:bit V2). Nothing we ship runs on V1, yet
every `pxt build` compiles the `mbdal` variant first and throws its hex
away. That wasted build is also the single thing blocking local C++
compilation.

## Why now

With `PXT_FORCE_LOCAL=1` (compile C++ in Docker instead of the MakeCode
cloud) the deploy build **cannot produce a hex at all**:

1. `pxt` builds `mbdal` first.
2. V1 compiles and links, then dies at its own hex-merge:
   `srec_cat: pxt-microbit-app.hex: 9220: contradictory 0x0003C000 value`
   — the shape `tools/make_deploy.py` already documents as benign.
3. In the **cloud** that comes back as data and `pxt` carries on to
   `mbcodal`. **Locally it is a subprocess exit → `INTERNAL ERROR` that
   aborts `pxt build` before `mbcodal` ever starts.** No
   `mbcodal-binary.hex`, and the retry-once triage just repeats it.

## The mechanism, and why this is NOT the `disablesVariants` trap

`pxt-microbit` declares `alwaysMultiVariant: true` and
`multiVariants: ["mbdal", "mbcodal"]`. In `Package.buildAsync`
(`pxt-core/built/pxt.js`):

```js
if (pxt.appTargetVariant) {
    variants = [pxt.appTargetVariant];        // <-- explicit: build ONLY this
} else if (pxt.appTarget.alwaysMultiVariant || ...) {
    variants = pxt.appTarget.multiVariants;   // <-- what we get today
}
if (!pxt.appTarget.alwaysMultiVariant && disabledVariants) { ... }
```

That last guard is the whole story behind the standing
"`disablesVariants: ["mbdal"]` produces a hex that is DEAD ON THE
DEVICE" warning in `tools/make_deploy.py` and in the deploy notes.
Because `alwaysMultiVariant` is true, `disablesVariants` does **not**
remove `mbdal` from the list. It instead makes `mbdal` build with our
extension **dropped from `mainDeps`** (`pkg.disablesVariant(...)  →
continue`), so the V1 section of the universal hex is a build of the
program *without our C++*. The warning is correct and must stand.

Setting `appTargetVariant` is a **different** mechanism: it selects the
variant list up front, before any dep filtering, so the one variant that
does get built keeps every dependency. `pxt.setCompileSwitch` exposes it:

```js
function setCompileSwitch(name, value) {
    if (/^csv-/.test(name)) pxt.setAppTargetVariant(name.replace(/^csv-*/, ""));
    ...
}
```

and the CLI feeds it from the environment
(`pxt.setCompileSwitches(process.env["PXT_COMPILE_SWITCHES"])`).

So: **`PXT_COMPILE_SWITCHES=csv-mbcodal`**.

## Measured 2026-08-25/26

Built the normal deploy scratch (`disablesVariants` correctly dropped)
with `PXT_FORCE_LOCAL=1 PXT_COMPILE_SWITCHES=csv-mbcodal pxt build`:

- **No `built/dockeryt/` directory at all** — V1 was never built.
- Clean completion. No `srec_cat`, no `INTERNAL ERROR`, no benign-abort
  retry needed.
- All ten extension translation units compiled in: `protocol.cpp`,
  `radio_transport.cpp`, `serial_transport.cpp`, `wire_adapter.cpp`,
  `wire_handler.cpp`, `diffdrive.cpp`, `motion_engine.cpp`,
  `nezha_port.cpp`, `otos_port.cpp`, `shims.cpp`.
- Output is **`built/binary.hex`**, 1 423 241 bytes.

## The output-filename footgun this introduces

`einfo.outputPrefix = variants.length == 1 || !v ? "" : v + "-"`. With a
single variant the prefix is empty, so the artifact is `binary.hex`, not
`mbcodal-binary.hex`. `tools/make_deploy.py` hardcodes
`HEX = built/mbcodal-binary.hex` and would find nothing.

Worse, `built/binary.hex` then means two different things depending on
whether the switch was set:

| build mode | `built/binary.hex` is | `:0400000A` block markers |
|---|---|---|
| multi-variant (today) | **universal** hex (V1+V2) | 2 |
| `csv-mbcodal` | plain V2 hex | 0 |

Both verified by inspection. Flashing the wrong one is exactly the class
of stale/mismatched-hex bug that has already cost hours here, so the
build should **assert** which kind it produced rather than trust the
filename.

## Scope

- `tools/make_deploy.py`: set `PXT_COMPILE_SWITCHES=csv-mbcodal` (and
  `PXT_FORCE_LOCAL=1`) in the build subprocess env rather than relying on
  ambient environment; point `HEX`/`HEX_TESTRIG` at the single-variant
  artifact; guard against a universal hex being mistaken for a V2 one.
- The V1-specific triage in `classify_attempt()` (`_V1_HEXMERGE_RE`, and
  the V1 half of the TS9283 note) becomes unreachable once V1 never
  builds — decide deliberately whether to delete it or keep it as a
  tripwire that fires if V1 ever comes back.
- The module docstring's two documented traps and `tools/DESIGN.md` both
  describe the multi-variant world and need rewriting.
- `tests/tools/test_make_deploy_triage.py` pins the current triage
  behaviour and moves with it.
- Deploy docs/notes that say "flash `built/mbcodal-binary.hex`".

## Acceptance

`uv run python tools/make_deploy.py` produces a flashable V2 hex with no
V1 build attempted, works with the local Docker compiler, and the
resulting hex boots on vevov and answers `STATUS`.
