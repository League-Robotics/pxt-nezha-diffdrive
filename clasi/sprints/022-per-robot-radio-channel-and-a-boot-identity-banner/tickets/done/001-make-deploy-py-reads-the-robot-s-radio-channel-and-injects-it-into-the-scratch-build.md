---
id: '001'
title: make_deploy.py reads the robot's radio_channel and injects it into the scratch
  build
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: firmware-hardcodes-one-radio-channel-for-a-multi-channel-fleet.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# make_deploy.py reads the robot's radio_channel and injects it into the scratch build

## Description

`src/comms/radio_transport.h` hardcodes:

```cpp
static constexpr uint8_t kGroup = 10;
static constexpr int kChannel = 4;
static constexpr int kTransmitPower = 7;
```

but the fleet is not on one channel. The canonical per-robot truth lives in
`radio-robot-lib/config/robots/<robot>.json` at `connection.radio_channel`:
**vevov = 4**, **tovez = 3**. Every hex this repo builds currently lands on
channel 4 regardless of which robot it is for, which is how tovez ended up
sitting on vevov's channel.

`tools/make_deploy.py`'s `--robot` argument (default `'vevov'`) currently
selects only the **flash target** via `flash(a.robot)`. It reads `pxt.json`
and never reads robot configuration, so there is no per-robot build path at
all — `--robot` picks where a hex goes, not what is in it.

This ticket makes `--robot` also drive the **build**: `make_deploy.py` reads
the target robot's `radio_channel` from
`radio-robot-lib/config/robots/<robot>.json` and injects it into the build
so the resulting hex carries the correct channel for that robot.

## Constraints (load-bearing)

- `make_deploy.py` already builds from a **scratch copy** — `sync()` copies
  the repo into `.tmp/deploy-head` before building. Build-time injection into
  that copy is the suggested seam: it gets a per-robot channel into the hex
  without making the repo's own checked-in source per-robot. The implementer
  may choose a different mechanism (e.g. a generated header) instead, but
  must justify the choice against this constraint set in the ticket's
  closing notes.
- Any **new** file added under `src/` must be added to `pxt.json`'s `files`
  array or it never reaches a build. `tests/host/test_pxt_manifest_completeness.py`
  enforces this in **both directions** (a file present but not listed, and a
  listed file that no longer exists) — run it after any new-file approach.
- The **checked-in default must stay channel 4** — a build invoked with no
  `--robot` must behave exactly as it does today. This is a hard regression
  guard, not a preference.
- `kGroup` (10) is **fleet-wide**, not per-robot. Do not parameterise it —
  only `kChannel` is per-robot in this ticket's scope. `kTransmitPower` is
  also out of scope unless robot config data forces the question.
- If the robot's JSON is missing, unreadable, or has no `radio_channel`,
  **fail loudly** — raise/exit with the robot name and the exact path that
  was tried. A silent fallback to channel 4 is the exact failure mode that
  put tovez on the wrong channel; do not reintroduce it under a different
  name.

## Repo-wide constraints (apply to every ticket in this sprint)

- `src/core/diffdrive.{h,cpp}` is **vendored and byte-stable** — do not edit.
- The comment-standard ratchet test forbids sprint/ticket/issue IDs in source
  comments (e.g. no "ticket 001" or "sprint 022" inside `.h`/`.cpp`/`.ts`
  comments).
- Any `//%` block-definition shim takes at most **four** parameters, with the
  signature on **one line**.

## Acceptance Criteria

- [x] `make_deploy.py --robot vevov` (and the no-`--robot` default) produce a
      scratch build (`.tmp/deploy-head`) whose radio channel constant is
      **4**.
- [x] `make_deploy.py --robot tovez` produces a scratch build whose radio
      channel constant is **3**, read from
      `radio-robot-lib/config/robots/tovez.json`'s `connection.radio_channel`
      — not from any table or constant inside this repo.
- [x] `kGroup` remains `10` in every build; it is not parameterised by robot.
- [x] A robot name with no matching JSON file, an unreadable JSON file, or a
      JSON file missing `connection.radio_channel` causes `make_deploy.py` to
      fail with a clear error naming the robot and the path it tried — it
      does not silently fall back to channel 4 or any other default.
- [x] If a new `src/` file was introduced, it is present in `pxt.json`'s
      `files` array and `tests/host/test_pxt_manifest_completeness.py`
      passes in both directions. (No new `src/` file was introduced — see
      Notes below.)
- [x] A build invoked with no `--robot` argument is behaviourally unchanged
      from before this ticket (channel 4, same defaults).

## Notes (implementation report)

**Mechanism chosen: regex substitution into the scratch copy, no new
file.** `_inject_radio_channel(deploy_dir, robot)` (`tools/make_deploy.py`)
reads `robot`'s `connection.radio_channel` via
`_read_robot_radio_channel()` and substitutes it into `deploy_dir`'s own
copy of `src/comms/radio_transport.h`'s `kChannel` line with a single,
exact-count regex (`_K_CHANNEL_RE`, asserts exactly one match or fails
loudly). `main()` calls this after `sync()`, before `build()`. This was
chosen over a generated header because: (1) it needs no `pxt.json`
manifest change at all — no new `src/` file means
`test_pxt_manifest_completeness.py` has nothing new to check either
direction; (2) the repo's own checked-in `radio_transport.h` is never
touched, so a build with no `--robot` is provably byte-identical to
before this ticket (verified: `DEFAULT_ROBOT` is `'vevov'`, whose
configured channel is 4, the pre-existing checked-in value); (3) it
keeps the "one new seam" shape the architecture review approved —
`make_deploy.py` gains a read dependency on `radio-robot-lib`'s JSON,
nothing inside `src/` changes its own dependency direction.

**Canonical source confirmed directly**, not assumed from the ticket
brief: `radio-robot-lib/config/robots/vevov.json` ->
`connection.radio_channel: 4`; `.../tovez.json` -> `3`.

**Loud-failure coverage**: missing config file, unreadable/malformed
JSON, and a config present but missing `connection.radio_channel`
(both an empty `connection: {}` and a `connection` key absent
entirely) all `sys.exit` naming both the robot and the exact path
tried — see `tests/tools/test_make_deploy_robot_channel.py`. No
robot->channel table exists anywhere in this repo;
`_read_robot_radio_channel()` is the only place a channel number is
read from, and it always resolves through
`radio-robot-lib/config/robots/<robot>.json`.

**Verified against the real sibling checkout** (not just synthetic
fixtures): ran `sync()` + `_inject_radio_channel()` against the actual
`/Volumes/Proj/proj/RobotProjects/radio-robot-lib` tree for both
`vevov` (-> 4) and `tovez` (-> 3), confirming the injection resolves
correctly outside the test suite's monkeypatched fixtures too.

**Tests**: `tests/tools/test_make_deploy_robot_channel.py` (new) covers
the three required builds (vevov/tovez/default), the `kGroup`/
`kTransmitPower` non-parameterisation guard, four loud-failure shapes,
and one full `sync()` -> `_inject_radio_channel()` end-to-end pipeline
test against a fake repo checkout. All monkeypatch `RADIO_ROBOT_LIB` to
a `tmp_path` fixture tree rather than depending on the real sibling
checkout being present, except the one real-repo sanity check run
manually (not part of the automated suite, see above).

## Implementation Plan

**Approach**: Extend `make_deploy.py`'s build path so that, after `sync()`
populates `.tmp/deploy-head`, the target robot's `radio_channel` is read from
`radio-robot-lib/config/robots/<robot>.json` and substituted into the
scratch copy's `radio_transport.h` (or injected via whatever mechanism the
implementer justifies against the constraints above) before the build step
runs. `flash(a.robot)` already exists for the flash target; the new code
path is the build-time counterpart.

**Files likely to change**:
- `tools/make_deploy.py` — read robot config, locate
  `radio-robot-lib/config/robots/<robot>.json` relative to this repo's
  checkout layout, extract `connection.radio_channel`, inject into the
  scratch copy pre-build, and fail loudly on any missing/malformed input.
- `src/comms/radio_transport.h` — only if the chosen injection mechanism
  requires a substitution marker or a factored-out constant; the checked-in
  value must remain `kChannel = 4`.
- `pxt.json` — only if a new file is introduced.

**Testing plan**: No hardware required. Build for each known robot (at least
vevov and tovez) via `make_deploy.py`'s build path and assert the resulting
`.tmp/deploy-head` copy carries the expected channel constant for that
robot. Add a negative test for the missing-config / missing-field case,
asserting a loud failure rather than a fallback. Run
`tests/host/test_pxt_manifest_completeness.py` if any `src/` file was added.

**Documentation updates**: Note the new `--robot`-drives-the-build behavior
wherever `make_deploy.py --robot` is currently documented (e.g. tool
docstring/help text). No CLASI architecture doc changes beyond what sprint
022's Architecture section already records.
