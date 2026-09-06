# tests/tools — unit tests for the repo's own Python tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
stable. 31 test files. Section 2 below is an orientation to the ones
whose shape is not obvious from their name, not a complete listing.

---

## 1. Purpose

Plain-Python unit tests over the logic inside this repo's own `tools/`
scripts — no compiler, no network, and (with one stated exception,
`test_ruff_clean.py`, below) no subprocess. The seam that
separates this directory from its sibling
[`tests/host/`](../host/DESIGN.md): `tests/host/` compiles the
extension's portable firmware C++ for the desktop and drives it
through `ctypes` shims; this directory calls plain Python functions
directly, in-process, with `monkeypatch` standing in for anything that
would otherwise shell out or touch the network. Different toolchain,
different fixtures, different failure modes — one shared harness would
fit neither well.

`test_gen_config_field_enum.py` (sprint 033 ticket 003) is the drift
backstop for this repo's one code generator: `src/blocks/motion.ts`'s
`ConfigField` enum is generated from `src/comms/config_fields.h` and
committed, and a generated-and-committed file is only as good as the
discipline of re-running the generator. It regenerates and compares,
and separately exercises the generator's own input contract (every
table row needs its `// ConfigField.<Name>: "<label>"` annotation; no
duplicate names or ordinals) against synthetic headers — the failures
that would otherwise surface as a silently short enum.

A second, smaller family here does not exercise any tool at all: the
**source-level guards**, which read `tools/` and `tests/` as TEXT and
assert a structural property of the tree — that a deleted tool stays
deleted (`test_deleted_tools_stay_deleted.py`), that one `wrap()` has
no lookalikes (`test_angle_wrap_ownership.py`), that every tool has a
line in its design doc (`test_tools_design_inventory.py`), that the
lint gate actually runs (`test_ruff_clean.py`). They cost milliseconds,
they fail on the change rather than on the consequence, and they catch
exactly the class of decay this directory's own subject matter keeps
producing.

`test_make_deploy_triage.py` pins
`tools/make_deploy.py`'s build-checkpoint triage (added sprint 008,
ticket 006) — the logic that decides whether a real `pxt build`
attempt succeeded, hard-failed, or hit a known-benign abort worth
retrying. This subsystem exists because that triage is sprint 008's
own "tests that can fail" theme applied to the tool doing the
checking: three real target-only defects — `Wire::Column`'s C++11
non-aggregate-under-NSDMI break, `setRxBufferSize`'s `uint8_t`
truncation, and three headers missing from `pxt.json`'s `files`
manifest — escaped a fully green host suite across sprints 004-007,
each one caught only because some ticket happened to need real build
evidence. The triage is now the standing mechanism that catches that
class; this file is what makes it fail loudly, instead of silently, if
someone breaks it later.

`test_tlm.py` (sprint 005 ticket 001) applies the same "tests that can
fail" theme to `tools/tlm.py`'s `TlmStream` telemetry parser and its
three fail-loud guards (`require_stream()`, `write_tlm_csv()`, the
`.meta.json` zero-frame refusal) — the parser this sprint introduced
specifically to replace six tools' worth of scattered, silently-broken
arity logic (`tour_watch.py:202`, `tour_capture.py:70`), so it is
pinned here from day one rather than left to drift the same way.
`test_camlink.py`/`test_field.py` (sprint 005 ticket 003, sprint 034
ticket 008) pin `tools/camlink.py`'s `Cam` — its stale-pose-invalidation
contract, its dead-instrument-vs-tag-not-in-frame distinction, and its
one-sample-per-real-frame property — and `tools/field.py`'s playfield
geometry (`wrap()`, the gap-aware `score_corners()`,
`path_deviation()`), against an injected fake daemon client. That is the
consolidation that replaced seven copied `Cam`/`CamStream` scaffolds and
four *disagreeing* corner-scoring implementations with one of each; ticket
008 finished it by deleting the camera subprocess (a second `Cam`, a
hardcoded venv path and an `ERR`/`NOTAG` line protocol, all bridging two
interpreters that are now one) and folding its tests in here.
`test_run_verbs.py` (sprint 005 ticket 006) pins the exact RUN string
four bench tools (`otos_levercal.py`, `pivot_truth.py`,
`rotation_check.py`, `turn_sweep.py`) send against a
fake link, proving each now matches a real `test.ts`/`testrig.ts`
handler instead of a dead numeric offset. All four files import the
module under test directly, in-process; nothing under `tools/` knows
this directory exists.

## 2. Orientation

### `test_make_deploy_triage.py`

Two parts, one file:

- **Fixtures** — module-level string constants holding synthetic and
  saved `pxt build` log text, one per triage outcome: a clean success;
  a real GCC-style compile diagnostic (mirroring the `Wire::Column`
  defect that motivated this triage); a `pxt.json` manifest-omission
  diagnostic (same file:line shape, no separate code path); the legacy
  V1 hex-merge failure; the three observed packaging-abort codes; and
  an unrecognized failure matching none of the above.
- **Tests** — `classify_attempt()` is a pure function, so most tests
  call it directly against a fixture and assert the returned
  `(verdict, reason)`. Three more drive `build()` itself through
  `monkeypatch`, replacing `make_deploy._run_pxt_build` and
  `os.path.exists`/`getsize` so the retry-then-report wiring runs with
  no real subprocess or filesystem state involved.

Run: `uv run pytest tests/tools/test_make_deploy_triage.py`, or as
part of the whole suite (`uv run pytest` from the repo root).

### `test_tlm.py` (sprint 005)

Imports `tools/tlm.py`'s `TlmStream` directly (same `sys.path`-insert
convention as `test_make_deploy_triage.py`) and feeds it synthetic and
captured `thdr`/`t` lines, no serial/radio link involved:

- **Header tracking** — a `thdr` sets the current column set; an
  identical re-read is a no-op; a second `thdr` after 20 frames with an
  unchanged column set is still accepted (the firmware's 1 Hz memo
  re-emit, not an error); a `t` before any `thdr` counts into
  `orphan_frames` and is not added to `frames`.
- **`seq`-gap loss** — consecutive `seq` values with a gap increment
  `dropped`/`loss_pct` by the right amount; a 7-bit wraparound
  (127 → 0) is not miscounted as a gap.
- **Arity/malformed rejection** — a `t` line whose value count disagrees
  with the last `thdr`'s column count counts into `malformed`, is not
  added to `frames`, and does not raise (fail-loud is `require_stream`/
  `write_tlm_csv`'s job, not a parse-time exception here).
- **Unit helpers** — `pose_cm`/`otos_cm`/`wheels_mms` against the
  shared golden frame in
  [`tests/host/golden_telemetry.py`](../host/golden_telemetry.py) (the
  same fixture `tests/host/test_wire_telemetry_projection.py` uses as
  expected *emitted* wire bytes, imported here as parser *input*, so
  emitter and parser are pinned against one shared source of truth and
  cannot silently drift apart from each other).
- **Fail-loud guards** — `require_stream()` raises before any
  run-triggering `send()` is observed on a fake link when no `t` frame
  arrives inside its timeout, and returns normally once one does;
  `write_tlm_csv()` raises on zero accumulated frames and leaves no
  file on disk, and writes normally (with a matching `.meta.json`
  sidecar) otherwise.
- **The pose-CSV codec** (sprint 034 ticket 004) — `write_pose_csv()`/
  `read_pose_csv()`, the one on-disk pose schema. Round-trip in wire
  units (with and without the optional `vl_mms,vr_mms` pair); a header
  whose columns are SHUFFLED still binds correctly, which a positional
  or column-counting reader cannot do; each legacy header this repo
  wrote is converted to the wire integers it came from, asserted
  against the 1/10-scale figure BY NAME (the regression that motivates
  the ticket: a cm/degree CSV has eight columns too, so the old
  column-count branch accepted it and plotted it 10x too small under a
  confident closure figure); an unknown header, an empty file, a blank
  cell and a non-numeric cell are each refused naming the file. The
  consumer checks at the end of the file are TEXT-level on purpose:
  `tour_chart.py`/`practice_chart.py` import matplotlib at module
  scope and this project's test venv has none (it is supplied per-run
  by `uv run --with matplotlib`), the same constraint
  `test_travel_calib_drift.py` works within — what they can still prove
  is that no tool re-derives the schema for itself, that the
  column-count branch is gone, and that `--meta`'s `start_world_cm[2]`
  is converted from its one documented unit (degrees).

Run: `uv run pytest tests/tools/test_tlm.py`, or as part of the whole
suite.

### `test_camlink.py` (sprint 029 ticket 006, sprint 034 ticket 008)

Imports `tools/camlink.py` directly (same `sys.path`-insert convention)
and drives its `Cam` against an injected fake daemon client, so no real
camera, daemon or thread of the daemon's is ever started. Two halves:

- **Registration (TL-02/TL-11)** — construction makes zero
  `register_tag()` calls, `Cam.register()` is the only path that makes
  any, and a robot mount's `mount_yaw_rad` is the fixed −90° AprilCam
  convention plus the calibration file's sub-degree residual.
- **The in-process reader (ticket 008)** — a dead instrument raises
  `CamDown` (construction) or lands in `err` (mid-stream) and
  invalidates the cached pose, while a tag merely absent from a frame
  only advances `notag`; a detection with no world fix is skipped
  rather than published as zeros; and two identical frames produce two
  samples, because one sample per REAL frame is what keeps a duty-cycle
  score measuring the robot rather than the camera's frame rate.

Run: `uv run pytest tests/tools/test_camlink.py`, or as part of the
whole suite.

### `test_field.py` (sprint 005 ticket 003)

Imports `tools/field.py` directly:

- **`wrap()`** — parametrized angle-wrap cases into `(-180, 180]`, plus
  (sprint 034 ticket 009) the boundary asserted as a **convention**:
  exactly half a revolution is `+180`, never `−180`, at every multiple
  of it. Three of the four copies the repo carried closed the other end
  of the interval, so this is the one value the consolidation could
  have changed and ±180 is a value the fleet commands.
- **`turn_total()`** (sprint 034 ticket 001) — the ±180 wrap-boundary
  regression: 183° physical against a 180° command must report **+183**,
  not −177, and `turn / commanded` must stay POSITIVE for an
  over-rotating pivot. Also under-rotation, full revolutions, a
  commanded 0 with a small drift, an already-unwrapped measurement, and
  a source-level assertion that the replaced `round()`/`revs` form has
  not come back.
- **`score_corners()`** — the gap-aware forward-only scan, including
  the exact disagreement `tour_run.py`'s console and
  `practice_chart.py`'s chart used to produce for the same recorded run
  (one corner scored from a nearby-but-gap-blind sample, the other
  correctly reported unobserved) — this file proves the shared
  implementation reproduces the *correct* outcome for both halves of
  that disagreement, not just that it runs without raising. Sprint 034
  ticket 002 adds the **per-corner window** (TL-08): the TL-08 lap is
  written out as an explicit leg list — NE start, NW passed 4 cm off at
  t = 5 s, SW/SE/NE touched 1 cm off, then a closing leg that
  re-approaches NW 1.5 cm off at t = 38 s — and all four corners must
  score their own approach, where the unbounded scan gave
  `NW 1.5 / SW 60.0 / SE 115.3 / NE 98.5`. A second test pins
  `used = besti + 1` by giving two corners one shared closest row and
  requiring the second to take the next one.
- **`path_deviation()`** — the PY-08 degenerate-zero-length-segment
  divide guard.
- **the geofence** (sprint 034 ticket 007) — `usable_half_extent()` is
  DERIVED from `LIMITS`/`MARGIN` and agrees with `clears_margin()` to a
  millimetre on both axes; `require_clear_path()` raises `PathRefused`
  naming the refused move, the offending points and the extent applied,
  walks multi-leg routes, and never rewrites the caller's waypoints. A
  drift guard fails if `tests/host/test_run_tour_programs.py` grows a
  private field size again, and a source-level test asserts
  `tools/field.py` imports nothing but `math` — the invariant that lets
  `tests/calibration/*` and `tests/host/*` import it with no robot
  attached.

Run: `uv run pytest tests/tools/test_field.py`, or as part of the
whole suite.

### `test_reposition.py` / `test_tour_run_geofence.py` (sprint 034 tickets 007, 009)

Driven with an injected fake link and fake camera, asserting on **what
the link received**, not on a return value: a refusal that has already
sent `RUN:seedxy` has still changed the robot's world frame, so every
refusal case checks `link.sent == []` and one test pins the refusal's
position ahead of the seed explicitly. Accept cases are pinned too (the
NE staging dot must still drive) — a gate that refuses everything is as
useless as one that refuses nothing.

Ticket 007 wrote these as two files because `tour_run.place()` and
`Repositioner.go()` were twins and a gate only one twin has is how
twins drift. Ticket 009 merged the twins, and the split changed
meaning rather than disappearing:

- **`test_reposition.py`** pins the surviving loop — the geofence, and
  now the **ordering**: a good heading is never re-commanded, and no
  `RUN:goto` follows a `RUN:face`. Those two tests name the "98 and 94
  degrees instead of west" measurement they descend from, and they
  discriminate: replaying the pre-merge interleaved loop against the
  same fake camera issues a fresh `goto` after the pivot.
- **`test_tour_run_geofence.py`** pins the `tour_run` half — that
  `place()` is gone rather than renamed, that `tour_run.Repositioner`
  **is** `reposition.Repositioner` (a copied loop would pass a name
  check and fail this), that the geofence still holds through
  `tour_run`'s own repositioner, and that its deliberate 1.5° heading
  tolerance survived the merge.

Run: `uv run pytest tests/tools/test_reposition.py
tests/tools/test_tour_run_geofence.py`.

### `test_angle_wrap_ownership.py` (sprint 034 ticket 009)

Source-level, text- and `ast`-based (several audited files open a
daemon connection or a serial link at module scope, so importing them
here would hang or depend on the host). Scans `tools/` and
`tests/calibration/` and asserts: no file but `tools/field.py` defines
a `wrap`/`_wrap_deg`; nobody writes the modulo idiom inline; every file
that used to carry a copy now actually imports the shared one; and
`field.wrap()` states its interval and its ±180 result in its own
docstring. The owner and this file are the only two allowed to *name*
the retired idiom in prose — a guard that forbade the owner from
explaining the convention would delete the documentation the ticket
existed to write. `tests/host/`'s radians-domain `_wrap_to_pi` is out
of scope by design: a different function against the C++ kernel's own
convention, not a copy of this one.

Run: `uv run pytest tests/tools/test_angle_wrap_ownership.py`.

### `test_run_verbs.py` (sprint 005 ticket 006)

No `tools/`-internal module is imported here beyond each tool's own
script; each test monkeypatches the tool's `Link`/`send`/`send_until`
call with a fake that records the exact string sent, then asserts it
against `test.ts`'s/`testrig.ts`'s real named-verb vocabulary and
asserts none of the old dead numeric forms (`RUN:8`, `RUN:14`,
`RUN:10`, `RUN:2`, `RUN:4`, `RUN:5`, `RUN:{57000+rate}`,
`RUN:{58360+deg}`) appear anywhere in what was sent — a regression back
to the numeric vocabulary fails loudly instead of silently. Covers
`otos_levercal.py` (`RUN:cal`/`RUN:cal:1`), `pivot_truth.py`/
`rotation_check.py` (`RUN:fix`, `RUN:pivot:<deg>`),
and `turn_sweep.py` (`RUN:turnrate:<rate>` then `RUN:pivot:<deg>`).
Cannot prove the robot moves — no serial port, no robot — only that
each tool's own RUN-sending code path targets a real handler.

Sprint 034 ticket 001 adds a second, unrelated-to-verbs group here
(the file already imports both tools, so a new file would only split
the same fixtures): source-level assertions that `rotation_check.py`
carries neither the retired `rotationScrub`/`1.040` constant nor a
private copy of the turn arithmetic, that `pivot_truth.py` dropped its
±180 wrap-boundary special case, and a synthetic **still-camera** run —
a fake `Cam` whose samples never change yaw, paired with an OTOS that
reports the full commanded ±180 — driving `pivot_truth.main()` to
completion. It must print "camera saw no rotation" and name the
robot-is-switched-OFF check, where it used to raise
`ZeroDivisionError`.

Run: `uv run pytest tests/tools/test_run_verbs.py`, or as part of the
whole suite.

### `test_ruff_clean.py` (sprint 034 ticket 010)

The lint gate, and this directory's one deliberate subprocess. `ruff`
had been configured in `pyproject.toml` since sprint 017 ticket 007 and
declared as a dev dependency, and nothing ever ran it — ten findings had
accumulated, most of them in `tests/dev/` and `tests/system/`, which
`uv run pytest` does not collect, so no amount of running the suite
would have surfaced them. It shells the concrete `ruff` binary
(resolved from `PATH`, then `.venv/bin/`, never a bare name — the same
reasoning `tests/host/test_typescript_typecheck.py` spells out for
`tsc`) over `tools/` and `tests/`, passes no `--select` of its own so
the rule set stays a one-line `pyproject.toml` change, and folds ruff's
own output into the assertion message. A missing `ruff` **skips** with
a reason naming `uv sync` rather than failing: an uninstalled linter is
an environment precondition, not a finding. It lints itself.

A test rather than a CI workflow on purpose: this repo has one GitHub
workflow (`publish-extension.yml`) and the developer signal here is
`uv run pytest`.

Run: `uv run pytest tests/tools/test_ruff_clean.py`.

### `test_travel_calib_drift.py`

Pins the two host-side hand-typed mirrors of
`src/motion/motion_engine.h`'s `travelCalib_`: `tools/tour_chart.py`'s
`--travel-calib` default, and (sprint 034 ticket 010)
`tests/system/run_tour.py`'s `TRAVEL_CALIB`. The second was a third
copy nothing checked, and it is the one holding the constant that has
already drifted once (0.8102 stayed mirrored past the 0.7878
camera-measured update) — and it is not decoration: `CPM = 10.0 /
TRAVEL_CALIB` is the mm-to-counts scale every tour is commanded and
scored in, and `tests/system/` is never run by `uv run pytest`, so the
guard has to live here. Text-based, not imports: `tour_chart.py` needs
matplotlib and `run_tour.py` opens a socket to a robot.

Run: `uv run pytest tests/tools/test_travel_calib_drift.py`.

### `test_link.py` (sprint 034 ticket 006)

Pins `tools/link.py`, the one sequenced-wire protocol every carrier
shares. Three groups: `LineBuffer` (a line split across `recv()`
boundaries reassembles; a trailing partial is held, not emitted; the
relay's `'< '` receive prefix is stripped; blank lines drop),
`Sequencer` (the first id is 1; a resend reuses its id and a re-format
of an already-numbered line takes no fresh one; `ack N` → N while
`nack N` → N−1; unsequenced verbs and the cleartext `RUN:` form go out
bare; `reset()` is HELLO's counterpart), and `relay_setup_lines()` (all
four lines, in `robotlink`'s order, `!GO` excluded).

Everything is driven through an injected `FakeSocket` handing back
canned byte chunks — no robot, no relay, no network, and therefore no
MEASURED claim anywhere in the file. Four source-level assertions close
the loop on the ticket's consolidation: that all four callers import
`link.py`; that no `!CG` string is BUILT in `wire_acceptance.py` any
more (parsed via `ast`, docstrings excluded, so a comment may still
quote the defect); that `turn_calibration.py`'s `radio_group` fallback
to 10 is gone; and that `tools/rogo/rogo.py` imports nothing from
`tools/` — its duplicate is deliberate (`tools/rogo/DESIGN.md`).

Run: `uv run pytest tests/tools/test_link.py`.

### `test_deleted_tools_stay_deleted.py` (sprint 034 ticket 003)

Four tools were deleted outright — a ground-truth checker that read v1
JSON keys and reported the failure as "camera cannot see the tag",
sending the operator to the lights; two tour variants nothing imported,
one of them the camera-in-the-loop experiment this repo's doctrine
forbids; and the camera-subprocess wrapper, which carried a second
`Cam` class to bridge two Python interpreters that are now one.

The guard asserts BOTH halves: the paths are gone, and no file under
`tools/` or `tests/` mentions their stems. A deleted file is only half
deleted while a docstring or a design-doc bullet still names it — the
next session reads the reference as an instruction and runs something
that is not there. `docs/` and `clasi/sprints/done/` are deliberately
out of scope: a dated code review citing a file that existed that day
is a true statement, and rewriting it to keep a grep quiet would
destroy the audit trail `.claude/rules/measurement-citations.md`
depends on.

### `test_tools_design_inventory.py` (sprint 034 ticket 012)

`tools/DESIGN.md` must name every `*.py` under `tools/` (recursively —
`rogo/` and `linefollow/` included) plus `field_calibration.json`,
parametrized one case per file so a failure names the tool. It also
checks the reverse: no inventory row may point at a path that does not
exist. Modelled on `tests/host/test_pxt_manifest_completeness.py`, and
for the same reason — a list maintained by discipline alone drifts, and
the drift is invisible because nobody reads a doc looking for gaps.

The third test guards the guard: if the inventory tables parse to fewer
rows than there are files, the table format has changed and the other
assertions would pass vacuously. This directory keeps finding that
failure mode in its own checks, so it is asserted rather than assumed.

## 3. Constraints and Invariants

- **A real compile diagnostic wins, unconditionally.**
  `classify_attempt()` checks for a genuine GCC/Clang diagnostic
  (`file.(cpp|cc|cxx|h|hpp):line:[col:] error|fatal error:`) *before*
  it ever looks at `hex_exists` — a hex produced by one build variant
  must never excuse a compile error surfaced by another.
  `test_compile_error_wins_even_if_a_hex_exists` pins this ordering
  explicitly, not just the individual outcomes.
- **Retry is bounded, not infinite.** A `BENIGN` verdict is retried
  exactly once; a `BENIGN` recurrence on that retry is promoted to
  `HARD_FAILURE` rather than retried again.
- **`UNKNOWN` is fail-closed and never retried — a known, stated
  limitation, not an oversight.** Output matching none of the
  documented shapes (no hex, no compile diagnostic, neither benign
  pattern) is reported as a failure immediately. This means a
  genuinely benign abort shape that has not been observed and
  documented yet is indistinguishable, by this logic, from a real
  defect, and gets reported as one — a false alarm, not a false pass.
  The alternative (retry anything unrecognized) risks silently
  retrying past an actual failure, which is the one thing this triage
  exists to stop. See [`tools/DESIGN.md`](../../tools/DESIGN.md)'s
  "Build checkpoint triage" section for the full decision table this
  file pins.
- **No real toolchain, no network, anywhere in this file.** `build()`'s
  tests replace every collaborator that would otherwise shell out or
  touch disk state. A future test that needs a real `pxt build` does
  not belong in this file.
- **`test_ruff_clean.py` is the one subprocess in this directory, and
  it stays the only one.** It shells a linter, which reads source text
  and touches nothing else — no build, no device, no network. That is
  the whole exception: a test that needs a compiler belongs in
  `tests/host/`, and one that needs a robot belongs in
  `tests/system/`.
- **`test_tlm.py`: an absent CSV is unambiguous; an empty one is not
  — never assert the opposite.** Every fail-loud-guard test asserts
  *both* halves of that: the raising path leaves no file on disk, and
  the non-raising path's file/sidecar actually matches the fed data.
  Asserting only "it raised" without also checking "and wrote nothing"
  would leave the guard's whole reason for existing unverified.
- **`test_tlm.py`: parser input is the emitter's own expected-output
  fixture, not a hand-rolled one.** `tests/host/golden_telemetry.py`'s
  `EXPECTED_T_LINE`/`EXPECTED_THDR_LINE` (what `WireHandler` is proven
  to emit) are fed to `TlmStream` as-is; a test that instead
  hand-wrote its own "plausible" `t` line could pass while silently
  disagreeing with what the firmware actually sends.
- **`test_camlink.py`/`test_field.py`: no real camera or daemon,
  ever.** `Cam(client=...)` is the one seam these tests use — a fake
  daemon client scripted with a finite list of frames — to exercise
  registration, pose invalidation and the reader loop without ever
  connecting to a daemon (which needs a Terminal launch for camera
  permission and will not come up from an agent process tree).
- **`test_run_verbs.py`: asserts both the positive and the negative.**
  Every test checks the exact string sent AND that none of the old
  dead numeric forms appear in it — asserting only the positive half
  would leave a tool that sends both the new named verb and a leftover
  numeric one (a merge artifact, not a hypothetical) passing.

## 4. Design

`test_make_deploy_triage.py` is not a package member of `tools/` — it
inserts `tools/` onto `sys.path` at import time (`tools/` has no
`__init__.py` and is not installed as a package) and then
`import make_deploy` directly. `classify_attempt()` tests call the
function against fixture text with no indirection. `build()` tests use
`monkeypatch` to replace `make_deploy._run_pxt_build` (returns fixture
text instead of running `pxt build`) and
`make_deploy.os.path.exists`/`getsize` (reports hex presence and size
keyed to a fake per-call attempt counter, instead of touching the real
filesystem) — the same caller-driven-fake pattern `tests/host/`'s
fakes use for the firmware's ports, applied at Python function-call
granularity instead of a C++ vtable.

## 5. Interfaces

### Exposes
- **`uv run pytest tests/tools/test_make_deploy_triage.py`** — this
  file alone.
- **`uv run pytest tests/tools/test_tlm.py`** (sprint 005) — this file
  alone.
- **`uv run pytest tests/tools/test_camlink.py`**,
  **`tests/tools/test_field.py`** (sprint 005 ticket 003, sprint 034
  ticket 008) — each file alone.
- **`uv run pytest tests/tools/test_run_verbs.py`** (sprint 005 ticket
  006) — this file alone.
- **`uv run pytest tests/tools/test_ruff_clean.py`** (sprint 034 ticket
  010) — the lint gate alone.
- All also run as part of **`uv run pytest`** from the repo root, and
  the once-per-sprint gate `close_sprint` runs.

### Consumes
- **`tools/make_deploy.py`**'s `classify_attempt()` and `build()` —
  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Build checkpoint
  triage" section for the contract this file pins.
- **`tools/tlm.py`**'s `TlmStream`, `require_stream()`,
  `write_tlm_csv()`, and the unit-conversion helpers (sprint 005) —
  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Telemetry
  (`tlm.py`)" section.
- **`tests/host/golden_telemetry.py`**'s expected wire-frame constants,
  as parser input (sprint 005) — the same fixture
  `tests/host/test_wire_telemetry_projection.py` uses as expected
  emitted bytes, so `test_tlm.py` cannot silently drift from what the
  firmware actually sends.
- **`tools/camlink.py`**'s `Cam`/`mount_yaw_rad()` and
  **`tools/field.py`**'s `wrap()`/`score_corners()`/`path_deviation()`
  (sprint 005 ticket 003, sprint 034 ticket 008) — see
  [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Link layer" section for
  `Cam`, and its "One `wrap()`" / "Scoring a corner" sections for the
  `field.py` half.
- **`otos_levercal.py`**, **`pivot_truth.py`**,
  **`rotation_check.py`**, **`turn_sweep.py`**'s own RUN-sending code
  paths (sprint 005 ticket 006), each monkeypatched at its `Link`/
  `send`/`send_until` call.

## 6. Coverage — what is and is not tested here

Covered: all four `classify_attempt()` verdicts (`SUCCESS`,
`HARD_FAILURE`, `BENIGN`, `UNKNOWN`) across seven fixture shapes,
including the compile-error-wins-over-hex-existence ordering and the
manifest-omission-caught-via-the-same-path case; `build()`'s
retry-then-succeed path, its bounded-retry failure path (the benign
shape recurring on retry), and its no-retry-on-hard-failure path.
`TlmStream`'s header tracking (fresh, no-op re-read, 20-frame memo
re-emit), `seq`-gap loss counting and 7-bit wraparound, arity/malformed
rejection, orphan-frame counting, the unit-conversion helpers against
the shared golden frame, and both fail-loud guards' raising and
non-raising paths. `camlink.py`'s registration guarantees, stale-pose
invalidation, dead-instrument-vs-tag-not-in-frame distinction and
one-sample-per-real-frame property, against an injected fake daemon
client. `field.py`'s `wrap()`, `score_corners()`'s
gap-aware scan (including the historical console-vs-chart
disagreement), and `path_deviation()`'s degenerate-segment guard. The
exact RUN string each of the four retargeted tools sends, and the
absence of every old dead numeric form, for both the fix/pivot/
turnrate path and the `cal`/`cal:1` rename.

Not covered, by design: `sync()` (manifest promotion/rewrite),
`flash()` (the `mbdeploy` subprocess), and `main()` — none of them are
part of the triage this file exists to pin, and none can be exercised
without either a real `pxt.json`/filesystem or a real subprocess,
which this subsystem's whole purpose is to avoid needing. A real build
against a sprint's own combined final state is verified manually and
recorded in `tools/DESIGN.md`'s "Build checkpoint triage" section, not
exercised here. For `test_tlm.py`: a live radio link's actual loss
behavior is not exercised here either — that is the sprint's
real-hardware end-to-end check (`tour_run.py --tour world` against a
real robot), not a unit test; this file only pins the parsing/guard
*logic* against synthetic and captured-but-replayed frames. For
`test_camlink.py`/`test_field.py`/`test_run_verbs.py`: none of them
exercise a real camera daemon, a real robot, or a real radio link
either — that is this sprint's own bench handoff checklist (ticket
007), not a unit test.
