---
source_file: tools-DESIGN.md
source_hash: 1b06a485258aa8867fdcf88c988edeed35ee30bbdf8396e99b3fc19fa484316c
---
# Diff: tools-DESIGN.md

Adds full documentation for the new `test_tlm.py` (ticket 001),
`test_camproc.py`/`test_field.py` (ticket 003), and `test_run_verbs.py`
(ticket 006) unit test files across every section this doc already
uses for `test_make_deploy_triage.py` — Purpose, Orientation,
Constraints and Invariants, Interfaces, and Coverage — so all four new
files are pinned to the same standard as the existing one from day
one. Ticket 007's own build-checkpoint pass found these last three
files (37 + 13 tests) undocumented here despite already being
committed and passing, and closed the gap.

```diff
--- tools-DESIGN.md (pristine)
+++ tools-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # tests/tools — unit tests for the repo's own Python tooling
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005 adds `test_tlm.py` pinning `tools/tlm.py`'s telemetry parser, `test_camproc.py`/`test_field.py` pinning ticket 003's link-layer consolidation, and `test_run_verbs.py` pinning ticket 006's RUN-string retargeting)
 
 ---
 
@@ -17,7 +17,7 @@
 different fixtures, different failure modes — one shared harness would
 fit neither well.
 
-One file so far: `test_make_deploy_triage.py`, pinning
+Five files: `test_make_deploy_triage.py`, pinning
 `tools/make_deploy.py`'s build-checkpoint triage (added sprint 008,
 ticket 006) — the logic that decides whether a real `pxt build`
 attempt succeeded, hard-failed, or hit a known-benign abort worth
@@ -30,10 +30,33 @@
 each one caught only because some ticket happened to need real build
 evidence. The triage is now the standing mechanism that catches that
 class; this file is what makes it fail loudly, instead of silently, if
-someone breaks it later. Nothing under `tools/` knows this directory
-exists.
+someone breaks it later.
+
+`test_tlm.py` (sprint 005 ticket 001) applies the same "tests that can
+fail" theme to `tools/tlm.py`'s `TlmStream` telemetry parser and its
+three fail-loud guards (`require_stream()`, `write_tlm_csv()`, the
+`.meta.json` zero-frame refusal) — the parser this sprint introduced
+specifically to replace six tools' worth of scattered, silently-broken
+arity logic (`tour_watch.py:202`, `tour_capture.py:70`), so it is
+pinned here from day one rather than left to drift the same way.
+`test_camproc.py`/`test_field.py` (sprint 005 ticket 003) pin
+`tools/camproc.py`'s interpreter-resolution/`ERR`-surfacing/stale-pose-
+invalidation contract and `tools/field.py`'s playfield geometry
+(`wrap()`, the gap-aware `score_corners()`, `path_deviation()`)
+against a `Cam(_spawn=False)` double — the consolidation that replaced
+seven copied `Cam`/`CamStream`/`CamProc` scaffolds and four
+*disagreeing* corner-scoring implementations with one of each.
+`test_run_verbs.py` (sprint 005 ticket 006) pins the exact RUN string
+five bench tools (`otos_levercal.py`, `pivot_truth.py`,
+`truth_check.py`, `rotation_check.py`, `turn_sweep.py`) send against a
+fake link, proving each now matches a real `test.ts`/`testrig.ts`
+handler instead of a dead numeric offset. All five files import the
+module under test directly, in-process; nothing under `tools/` knows
+this directory exists.
 
 ## 2. Orientation
+
+### `test_make_deploy_triage.py`
 
 Two parts, one file:
 
@@ -53,6 +76,98 @@
 
 Run: `uv run pytest tests/tools/test_make_deploy_triage.py`, or as
 part of the whole suite (`uv run pytest` from the repo root).
+
+### `test_tlm.py` (sprint 005)
+
+Imports `tools/tlm.py`'s `TlmStream` directly (same `sys.path`-insert
+convention as `test_make_deploy_triage.py`) and feeds it synthetic and
+captured `thdr`/`t` lines, no serial/radio link involved:
+
+- **Header tracking** — a `thdr` sets the current column set; an
+  identical re-read is a no-op; a second `thdr` after 20 frames with an
+  unchanged column set is still accepted (the firmware's 1 Hz memo
+  re-emit, not an error); a `t` before any `thdr` counts into
+  `orphan_frames` and is not added to `frames`.
+- **`seq`-gap loss** — consecutive `seq` values with a gap increment
+  `dropped`/`loss_pct` by the right amount; a 7-bit wraparound
+  (127 → 0) is not miscounted as a gap.
+- **Arity/malformed rejection** — a `t` line whose value count disagrees
+  with the last `thdr`'s column count counts into `malformed`, is not
+  added to `frames`, and does not raise (fail-loud is `require_stream`/
+  `write_tlm_csv`'s job, not a parse-time exception here).
+- **Unit helpers** — `pose_cm`/`otos_cm`/`wheels_mms` against the
+  shared golden frame in
+  [`tests/host/golden_telemetry.py`](../host/golden_telemetry.py) (the
+  same fixture `tests/host/test_wire_telemetry_projection.py` uses as
+  expected *emitted* wire bytes, imported here as parser *input*, so
+  emitter and parser are pinned against one shared source of truth and
+  cannot silently drift apart from each other).
+- **Fail-loud guards** — `require_stream()` raises before any
+  run-triggering `send()` is observed on a fake link when no `t` frame
+  arrives inside its timeout, and returns normally once one does;
+  `write_tlm_csv()` raises on zero accumulated frames and leaves no
+  file on disk, and writes normally (with a matching `.meta.json`
+  sidecar) otherwise.
+
+Run: `uv run pytest tests/tools/test_tlm.py`, or as part of the whole
+suite.
+
+### `test_camproc.py` (sprint 005 ticket 003)
+
+Imports `tools/camproc.py` directly (same `sys.path`-insert convention)
+and drives its `Cam` class through a `_spawn=False` constructor
+argument, so no real camera subprocess, thread, or interpreter is ever
+started:
+
+- **`resolve_venv()`** — `APRILTAGS_VENV` set overrides the default;
+  unset, falls back to the historically-correct hardcoded path.
+- **`ERR` surfacing** — an `ERR` line fed to the double reaches the
+  calling tool (via a callback/attribute the double lets the test
+  inspect) instead of being discarded the way the old `stderr=DEVNULL`
+  scaffolds did.
+- **Stale-pose invalidation** — once the stream is marked dead,
+  `.latest`/`.fix()` both return `None` rather than a frozen pre-death
+  value, even if a pose was cached moments before.
+
+Run: `uv run pytest tests/tools/test_camproc.py`, or as part of the
+whole suite.
+
+### `test_field.py` (sprint 005 ticket 003)
+
+Imports `tools/field.py` directly:
+
+- **`wrap()`** — parametrized angle-wrap cases into `(-180, 180]`.
+- **`score_corners()`** — the gap-aware forward-only scan, including
+  the exact disagreement `tour_run.py`'s console and
+  `practice_chart.py`'s chart used to produce for the same recorded run
+  (one corner scored from a nearby-but-gap-blind sample, the other
+  correctly reported unobserved) — this file proves the shared
+  implementation reproduces the *correct* outcome for both halves of
+  that disagreement, not just that it runs without raising.
+- **`path_deviation()`** — the PY-08 degenerate-zero-length-segment
+  divide guard.
+
+Run: `uv run pytest tests/tools/test_field.py`, or as part of the
+whole suite.
+
+### `test_run_verbs.py` (sprint 005 ticket 006)
+
+No `tools/`-internal module is imported here beyond each tool's own
+script; each test monkeypatches the tool's `Link`/`send`/`send_until`
+call with a fake that records the exact string sent, then asserts it
+against `test.ts`'s/`testrig.ts`'s real named-verb vocabulary and
+asserts none of the old dead numeric forms (`RUN:8`, `RUN:14`,
+`RUN:10`, `RUN:2`, `RUN:4`, `RUN:5`, `RUN:{57000+rate}`,
+`RUN:{58360+deg}`) appear anywhere in what was sent — a regression back
+to the numeric vocabulary fails loudly instead of silently. Covers
+`otos_levercal.py` (`RUN:cal`/`RUN:cal:1`), `pivot_truth.py`/
+`truth_check.py`/`rotation_check.py` (`RUN:fix`, `RUN:pivot:<deg>`),
+and `turn_sweep.py` (`RUN:turnrate:<rate>` then `RUN:pivot:<deg>`).
+Cannot prove the robot moves — no serial port, no robot — only that
+each tool's own RUN-sending code path targets a real handler.
+
+Run: `uv run pytest tests/tools/test_run_verbs.py`, or as part of the
+whole suite.
 
 ## 3. Constraints and Invariants
 
@@ -82,6 +197,28 @@
   tests replace every collaborator that would otherwise shell out or
   touch disk state. A future test that needs a real `pxt build` does
   not belong in this file.
+- **`test_tlm.py`: an absent CSV is unambiguous; an empty one is not
+  — never assert the opposite.** Every fail-loud-guard test asserts
+  *both* halves of that: the raising path leaves no file on disk, and
+  the non-raising path's file/sidecar actually matches the fed data.
+  Asserting only "it raised" without also checking "and wrote nothing"
+  would leave the guard's whole reason for existing unverified.
+- **`test_tlm.py`: parser input is the emitter's own expected-output
+  fixture, not a hand-rolled one.** `tests/host/golden_telemetry.py`'s
+  `EXPECTED_T_LINE`/`EXPECTED_THDR_LINE` (what `WireHandler` is proven
+  to emit) are fed to `TlmStream` as-is; a test that instead
+  hand-wrote its own "plausible" `t` line could pass while silently
+  disagreeing with what the firmware actually sends.
+- **`test_camproc.py`/`test_field.py`: no real subprocess, camera, or
+  thread, ever.** `Cam(_spawn=False)` is the one seam these tests use
+  to exercise interpreter resolution, `ERR` surfacing, and pose
+  invalidation without ever starting the real AprilTags process this
+  class normally spawns.
+- **`test_run_verbs.py`: asserts both the positive and the negative.**
+  Every test checks the exact string sent AND that none of the old
+  dead numeric forms appear in it — asserting only the positive half
+  would leave a tool that sends both the new named verb and a leftover
+  numeric one (a merge artifact, not a hypothetical) passing.
 
 ## 4. Design
 
@@ -103,13 +240,36 @@
 ### Exposes
 - **`uv run pytest tests/tools/test_make_deploy_triage.py`** — this
   file alone.
-- Also runs as part of **`uv run pytest`** from the repo root, and the
-  once-per-sprint gate `close_sprint` runs.
+- **`uv run pytest tests/tools/test_tlm.py`** (sprint 005) — this file
+  alone.
+- **`uv run pytest tests/tools/test_camproc.py`**,
+  **`tests/tools/test_field.py`** (sprint 005 ticket 003) — each file
+  alone.
+- **`uv run pytest tests/tools/test_run_verbs.py`** (sprint 005 ticket
+  006) — this file alone.
+- All also run as part of **`uv run pytest`** from the repo root, and
+  the once-per-sprint gate `close_sprint` runs.
 
 ### Consumes
 - **`tools/make_deploy.py`**'s `classify_attempt()` and `build()` —
   see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Build checkpoint
   triage" section for the contract this file pins.
+- **`tools/tlm.py`**'s `TlmStream`, `require_stream()`,
+  `write_tlm_csv()`, and the unit-conversion helpers (sprint 005) —
+  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Telemetry
+  (`tlm.py`)" section.
+- **`tests/host/golden_telemetry.py`**'s expected wire-frame constants,
+  as parser input (sprint 005) — the same fixture
+  `tests/host/test_wire_telemetry_projection.py` uses as expected
+  emitted bytes, so `test_tlm.py` cannot silently drift from what the
+  firmware actually sends.
+- **`tools/camproc.py`**'s `Cam`/`resolve_venv()` and **`tools/field.py`**'s
+  `wrap()`/`score_corners()`/`path_deviation()` (sprint 005 ticket 003)
+  — see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Link layer" section.
+- **`otos_levercal.py`**, **`pivot_truth.py`**, **`truth_check.py`**,
+  **`rotation_check.py`**, **`turn_sweep.py`**'s own RUN-sending code
+  paths (sprint 005 ticket 006), each monkeypatched at its `Link`/
+  `send`/`send_until` call.
 
 ## 6. Coverage — what is and is not tested here
 
@@ -119,6 +279,18 @@
 manifest-omission-caught-via-the-same-path case; `build()`'s
 retry-then-succeed path, its bounded-retry failure path (the benign
 shape recurring on retry), and its no-retry-on-hard-failure path.
+`TlmStream`'s header tracking (fresh, no-op re-read, 20-frame memo
+re-emit), `seq`-gap loss counting and 7-bit wraparound, arity/malformed
+rejection, orphan-frame counting, the unit-conversion helpers against
+the shared golden frame, and both fail-loud guards' raising and
+non-raising paths. `camproc.py`'s `resolve_venv()` env-var override/
+default, `ERR` surfacing, and stale-pose invalidation against a
+`Cam(_spawn=False)` double. `field.py`'s `wrap()`, `score_corners()`'s
+gap-aware scan (including the historical console-vs-chart
+disagreement), and `path_deviation()`'s degenerate-segment guard. The
+exact RUN string each of the five retargeted tools sends, and the
+absence of every old dead numeric form, for both the fix/pivot/
+turnrate path and the `cal`/`cal:1` rename.
 
 Not covered, by design: `sync()` (manifest promotion/rewrite),
 `flash()` (the `mbdeploy` subprocess), and `main()` — none of them are
@@ -127,4 +299,12 @@
 which this subsystem's whole purpose is to avoid needing. A real build
 against a sprint's own combined final state is verified manually and
 recorded in `tools/DESIGN.md`'s "Build checkpoint triage" section, not
-exercised here.
+exercised here. For `test_tlm.py`: a live radio link's actual loss
+behavior is not exercised here either — that is the sprint's
+real-hardware end-to-end check (`tour_run.py --tour world` against a
+real robot), not a unit test; this file only pins the parsing/guard
+*logic* against synthetic and captured-but-replayed frames. For
+`test_camproc.py`/`test_field.py`/`test_run_verbs.py`: none of them
+exercise a real camera daemon, a real robot, or a real radio link
+either — that is this sprint's own bench handoff checklist (ticket
+007), not a unit test.
```
