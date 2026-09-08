---
status: pending
---

# Consumers report `ver unbaked` — the checked-in kVersion is a placeholder

Priority: **High** — it is the whole consumer population. Reported by the
stakeholder 2026-09-07: a downstream user building and flashing to
robots gets "version is unbaked."

## What happens

`src/comms/protocol.cpp:72` ships `kVersion = "unbaked"`. Exactly one
thing ever replaced it: `tools/make_deploy.py::_inject_version()`
(`tools/make_deploy.py:833`), which substitutes `pyproject.toml`'s
version into a **scratch copy** at deploy time — this repo's own
bench/farm tooling, never a consumer's path.

Consumers reach the source two ways, and **both** carry the placeholder:

- **Directly from GitHub** — they clone or reference this repo and build
  it in MakeCode's cloud compiler.
- **Via the generated extension** — `tools/publish_extension.py::assemble()`
  copies every entry of `pxt.json`'s `files` verbatim
  (`shutil.copyfile(repo / rel, dst)`), and `src/comms/protocol.cpp` is
  in that list. There is no `kVersion` handling in `publish_extension.py`.

So the fix cannot live in the publish step alone (an earlier draft of
this issue proposed exactly that — it would have missed every direct
GitHub consumer). **The checked-in source itself has to be
self-describing.**

## The fix (stakeholder's direction, 2026-09-07)

Bake `kVersion` at **version-bump** time, so whatever revision anyone
pulls says which revision it is.

dotconfig already has the mechanism: `src/dotconfig/event_hooks.py`
fires `config/hooks/<event>` scripts, and `versioning.py:568-570` fires

```
config/hooks/version_bump <project_dir> <old_version> <new_version>
```

after writing `pyproject.toml` / `package.json` / `config/dotconfig.yaml`.
This repo **already has** that hook — it exists because dotconfig's
built-in `version_sync` only understands `pyproject.toml` and
`package.json`, so `pxt.json` is synced there by hand. `kVersion` is the
same kind of sync and belongs in the same place.

**DONE 2026-09-07:** `config/hooks/version_bump` extended to rewrite
`protocol.cpp`'s `kVersion` in place and `git add` it (staging matters —
`bump --push` runs the hook before its own commit and stages only the
files it wrote itself). It reuses `make_deploy.py`'s `_K_VERSION_RE`
shape deliberately, stops at the closing `";` so the trailing comment
survives, and fails loudly if the declaration count is not exactly 1.
Verified against a throwaway copy of `pxt.json` + `protocol.cpp`: a
first bump rewrote `unbaked` -> `1.20260908.1`, a second rewrote the
already-baked value -> `1.20260908.2` (the steady state), `kProfile`
untouched at `unbaked` in both.

`make_deploy.py::_inject_version()` stays. It now writes the same string
the hook already wrote, which is harmless, and it still covers a tree
whose `pyproject.toml` was hand-edited between bumps.

## What is still open

Both items are outside team-lead write scope (`src`, `tests`) — they
need OOP or a programmer ticket:

1. **`tests/host/test_wire_constants_drift.py::test_k_version_is_the_uninjected_placeholder`
   must invert.** It currently asserts `kVersion == "unbaked"` and will
   fail on the next bump. Replace the placeholder assertion with
   `kVersion == config/dotconfig.yaml's version` (equivalently
   `pxt.json`'s, which `check_version()` already pins to it). That is a
   **stronger** guard than the one it replaces: the old test's stated
   fear was "a stale, hand-edited version string" shipping instead of
   the injected one, and pinning the constant to the project's own
   version catches exactly that, on every host run.
   `test_make_deploy_can_still_find_k_version` needs no change — it
   tests the regex, not the value.

2. **The trailing comment on `protocol.cpp:72` is now stale.** It reads
   `// injected by make_deploy.py;` — it should say the version_bump
   hook bakes it and make_deploy re-injects the same value at deploy.
   The `kProfile`/`kVersion` block comment above it
   (`protocol.cpp:49-62`) needs the same correction.

## `kProfile` is deliberately NOT baked

`kProfile` answers a different question — which robot's config the hex
is running — and for a plain checkout that has not loaded a config,
`unbaked` is the **true** answer. Once a program DOES load one at
runtime it stops being true, which is
`kprofile-needs-a-runtime-setter.md`, not this issue. It also inherits the "did this hex come through `make_deploy`?"
signal that `kVersion` used to carry, which is the field that should
have carried it all along. See
`calibration-skill-emits-a-paste-able-makecode-block.md` for the
separate, unsolved problem that a consumer board runs fleet defaults.
