---
source_file: tools-DESIGN.md
source_hash: 73566ca193c28ae6e6ef0fd5c53e8405dfc32891c8be050527a50c82d078ae6d
---
# Diff: tools-DESIGN.md

Comparison of the sprint overlay copy of `tools-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- tools-DESIGN.md (pristine)
+++ tools-DESIGN.md (current)
@@ -1,13 +1,16 @@
 # tests/tools — unit tests for the repo's own Python tooling
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005 adds `test_tlm.py` pinning `tools/tlm.py`'s telemetry parser, `test_camproc.py`/`test_field.py` pinning ticket 003's link-layer consolidation, and `test_run_verbs.py` pinning ticket 006's RUN-string retargeting)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
+stable. 31 test files. Section 2 below is an orientation to the ones
+whose shape is not obvious from their name, not a complete listing.
 
 ---
 
 ## 1. Purpose
 
 Plain-Python unit tests over the logic inside this repo's own `tools/`
-scripts — no compiler, no subprocess, no network. The seam that
+scripts — no compiler, no network, and (with one stated exception,
+`test_ruff_clean.py`, below) no subprocess. The seam that
 separates this directory from its sibling
 [`tests/host/`](../host/DESIGN.md): `tests/host/` compiles the
 extension's portable firmware C++ for the desktop and drives it
@@ -27,7 +30,18 @@
 duplicate names or ordinals) against synthetic headers — the failures
 that would otherwise surface as a silently short enum.
 
-Five files: `test_make_deploy_triage.py`, pinning
+A second, smaller family here does not exercise any tool at all: the
+**source-level guards**, which read `tools/` and `tests/` as TEXT and
+assert a structural property of the tree — that a deleted tool stays
+deleted (`test_deleted_tools_stay_deleted.py`), that one `wrap()` has
+no lookalikes (`test_angle_wrap_ownership.py`), that every tool has a
+line in its design doc (`test_tools_design_inventory.py`), that the
+lint gate actually runs (`test_ruff_clean.py`). They cost milliseconds,
+they fail on the change rather than on the consequence, and they catch
+exactly the class of decay this directory's own subject matter keeps
+producing.
+
+`test_make_deploy_triage.py` pins
 `tools/make_deploy.py`'s build-checkpoint triage (added sprint 008,
 ticket 006) — the logic that decides whether a real `pxt build`
 attempt succeeded, hard-failed, or hit a known-benign abort worth
@@ -49,18 +63,22 @@
 specifically to replace six tools' worth of scattered, silently-broken
 arity logic (`tour_watch.py:202`, `tour_capture.py:70`), so it is
 pinned here from day one rather than left to drift the same way.
-`test_camproc.py`/`test_field.py` (sprint 005 ticket 003) pin
-`tools/camproc.py`'s interpreter-resolution/`ERR`-surfacing/stale-pose-
-invalidation contract and `tools/field.py`'s playfield geometry
-(`wrap()`, the gap-aware `score_corners()`, `path_deviation()`)
-against a `Cam(_spawn=False)` double — the consolidation that replaced
-seven copied `Cam`/`CamStream`/`CamProc` scaffolds and four
-*disagreeing* corner-scoring implementations with one of each.
+`test_camlink.py`/`test_field.py` (sprint 005 ticket 003, sprint 034
+ticket 008) pin `tools/camlink.py`'s `Cam` — its stale-pose-invalidation
+contract, its dead-instrument-vs-tag-not-in-frame distinction, and its
+one-sample-per-real-frame property — and `tools/field.py`'s playfield
+geometry (`wrap()`, the gap-aware `score_corners()`,
+`path_deviation()`), against an injected fake daemon client. That is the
+consolidation that replaced seven copied `Cam`/`CamStream` scaffolds and
+four *disagreeing* corner-scoring implementations with one of each; ticket
+008 finished it by deleting the camera subprocess (a second `Cam`, a
+hardcoded venv path and an `ERR`/`NOTAG` line protocol, all bridging two
+interpreters that are now one) and folding its tests in here.
 `test_run_verbs.py` (sprint 005 ticket 006) pins the exact RUN string
-five bench tools (`otos_levercal.py`, `pivot_truth.py`,
-`truth_check.py`, `rotation_check.py`, `turn_sweep.py`) send against a
+four bench tools (`otos_levercal.py`, `pivot_truth.py`,
+`rotation_check.py`, `turn_sweep.py`) send against a
 fake link, proving each now matches a real `test.ts`/`testrig.ts`
-handler instead of a dead numeric offset. All five files import the
+handler instead of a dead numeric offset. All four files import the
 module under test directly, in-process; nothing under `tools/` knows
 this directory exists.
 
@@ -118,47 +136,146 @@
   `write_tlm_csv()` raises on zero accumulated frames and leaves no
   file on disk, and writes normally (with a matching `.meta.json`
   sidecar) otherwise.
+- **The pose-CSV codec** (sprint 034 ticket 004) — `write_pose_csv()`/
+  `read_pose_csv()`, the one on-disk pose schema. Round-trip in wire
+  units (with and without the optional `vl_mms,vr_mms` pair); a header
+  whose columns are SHUFFLED still binds correctly, which a positional
+  or column-counting reader cannot do; each legacy header this repo
+  wrote is converted to the wire integers it came from, asserted
+  against the 1/10-scale figure BY NAME (the regression that motivates
+  the ticket: a cm/degree CSV has eight columns too, so the old
+  column-count branch accepted it and plotted it 10x too small under a
+  confident closure figure); an unknown header, an empty file, a blank
+  cell and a non-numeric cell are each refused naming the file. The
+  consumer checks at the end of the file are TEXT-level on purpose:
+  `tour_chart.py`/`practice_chart.py` import matplotlib at module
+  scope and this project's test venv has none (it is supplied per-run
+  by `uv run --with matplotlib`), the same constraint
+  `test_travel_calib_drift.py` works within — what they can still prove
+  is that no tool re-derives the schema for itself, that the
+  column-count branch is gone, and that `--meta`'s `start_world_cm[2]`
+  is converted from its one documented unit (degrees).
 
 Run: `uv run pytest tests/tools/test_tlm.py`, or as part of the whole
 suite.
 
-### `test_camproc.py` (sprint 005 ticket 003)
-
-Imports `tools/camproc.py` directly (same `sys.path`-insert convention)
-and drives its `Cam` class through a `_spawn=False` constructor
-argument, so no real camera subprocess, thread, or interpreter is ever
-started:
-
-- **`resolve_venv()`** — `APRILTAGS_VENV` set overrides the default;
-  unset, falls back to the historically-correct hardcoded path.
-- **`ERR` surfacing** — an `ERR` line fed to the double reaches the
-  calling tool (via a callback/attribute the double lets the test
-  inspect) instead of being discarded the way the old `stderr=DEVNULL`
-  scaffolds did.
-- **Stale-pose invalidation** — once the stream is marked dead,
-  `.latest`/`.fix()` both return `None` rather than a frozen pre-death
-  value, even if a pose was cached moments before.
-
-Run: `uv run pytest tests/tools/test_camproc.py`, or as part of the
+### `test_camlink.py` (sprint 029 ticket 006, sprint 034 ticket 008)
+
+Imports `tools/camlink.py` directly (same `sys.path`-insert convention)
+and drives its `Cam` against an injected fake daemon client, so no real
+camera, daemon or thread of the daemon's is ever started. Two halves:
+
+- **Registration (TL-02/TL-11)** — construction makes zero
+  `register_tag()` calls, `Cam.register()` is the only path that makes
+  any, and a robot mount's `mount_yaw_rad` is the fixed −90° AprilCam
+  convention plus the calibration file's sub-degree residual.
+- **The in-process reader (ticket 008)** — a dead instrument raises
+  `CamDown` (construction) or lands in `err` (mid-stream) and
+  invalidates the cached pose, while a tag merely absent from a frame
+  only advances `notag`; a detection with no world fix is skipped
+  rather than published as zeros; and two identical frames produce two
+  samples, because one sample per REAL frame is what keeps a duty-cycle
+  score measuring the robot rather than the camera's frame rate.
+
+Run: `uv run pytest tests/tools/test_camlink.py`, or as part of the
 whole suite.
 
 ### `test_field.py` (sprint 005 ticket 003)
 
 Imports `tools/field.py` directly:
 
-- **`wrap()`** — parametrized angle-wrap cases into `(-180, 180]`.
+- **`wrap()`** — parametrized angle-wrap cases into `(-180, 180]`, plus
+  (sprint 034 ticket 009) the boundary asserted as a **convention**:
+  exactly half a revolution is `+180`, never `−180`, at every multiple
+  of it. Three of the four copies the repo carried closed the other end
+  of the interval, so this is the one value the consolidation could
+  have changed and ±180 is a value the fleet commands.
+- **`turn_total()`** (sprint 034 ticket 001) — the ±180 wrap-boundary
+  regression: 183° physical against a 180° command must report **+183**,
+  not −177, and `turn / commanded` must stay POSITIVE for an
+  over-rotating pivot. Also under-rotation, full revolutions, a
+  commanded 0 with a small drift, an already-unwrapped measurement, and
+  a source-level assertion that the replaced `round()`/`revs` form has
+  not come back.
 - **`score_corners()`** — the gap-aware forward-only scan, including
   the exact disagreement `tour_run.py`'s console and
   `practice_chart.py`'s chart used to produce for the same recorded run
   (one corner scored from a nearby-but-gap-blind sample, the other
   correctly reported unobserved) — this file proves the shared
   implementation reproduces the *correct* outcome for both halves of
-  that disagreement, not just that it runs without raising.
+  that disagreement, not just that it runs without raising. Sprint 034
+  ticket 002 adds the **per-corner window** (TL-08): the TL-08 lap is
+  written out as an explicit leg list — NE start, NW passed 4 cm off at
+  t = 5 s, SW/SE/NE touched 1 cm off, then a closing leg that
+  re-approaches NW 1.5 cm off at t = 38 s — and all four corners must
+  score their own approach, where the unbounded scan gave
+  `NW 1.5 / SW 60.0 / SE 115.3 / NE 98.5`. A second test pins
+  `used = besti + 1` by giving two corners one shared closest row and
+  requiring the second to take the next one.
 - **`path_deviation()`** — the PY-08 degenerate-zero-length-segment
   divide guard.
+- **the geofence** (sprint 034 ticket 007) — `usable_half_extent()` is
+  DERIVED from `LIMITS`/`MARGIN` and agrees with `clears_margin()` to a
+  millimetre on both axes; `require_clear_path()` raises `PathRefused`
+  naming the refused move, the offending points and the extent applied,
+  walks multi-leg routes, and never rewrites the caller's waypoints. A
+  drift guard fails if `tests/host/test_run_tour_programs.py` grows a
+  private field size again, and a source-level test asserts
+  `tools/field.py` imports nothing but `math` — the invariant that lets
+  `tests/calibration/*` and `tests/host/*` import it with no robot
+  attached.
 
 Run: `uv run pytest tests/tools/test_field.py`, or as part of the
 whole suite.
+
+### `test_reposition.py` / `test_tour_run_geofence.py` (sprint 034 tickets 007, 009)
+
+Driven with an injected fake link and fake camera, asserting on **what
+the link received**, not on a return value: a refusal that has already
+sent `RUN:seedxy` has still changed the robot's world frame, so every
+refusal case checks `link.sent == []` and one test pins the refusal's
+position ahead of the seed explicitly. Accept cases are pinned too (the
+NE staging dot must still drive) — a gate that refuses everything is as
+useless as one that refuses nothing.
+
+Ticket 007 wrote these as two files because `tour_run.place()` and
+`Repositioner.go()` were twins and a gate only one twin has is how
+twins drift. Ticket 009 merged the twins, and the split changed
+meaning rather than disappearing:
+
+- **`test_reposition.py`** pins the surviving loop — the geofence, and
+  now the **ordering**: a good heading is never re-commanded, and no
+  `RUN:goto` follows a `RUN:face`. Those two tests name the "98 and 94
+  degrees instead of west" measurement they descend from, and they
+  discriminate: replaying the pre-merge interleaved loop against the
+  same fake camera issues a fresh `goto` after the pivot.
+- **`test_tour_run_geofence.py`** pins the `tour_run` half — that
+  `place()` is gone rather than renamed, that `tour_run.Repositioner`
+  **is** `reposition.Repositioner` (a copied loop would pass a name
+  check and fail this), that the geofence still holds through
+  `tour_run`'s own repositioner, and that its deliberate 1.5° heading
+  tolerance survived the merge.
+
+Run: `uv run pytest tests/tools/test_reposition.py
+tests/tools/test_tour_run_geofence.py`.
+
+### `test_angle_wrap_ownership.py` (sprint 034 ticket 009)
+
+Source-level, text- and `ast`-based (several audited files open a
+daemon connection or a serial link at module scope, so importing them
+here would hang or depend on the host). Scans `tools/` and
+`tests/calibration/` and asserts: no file but `tools/field.py` defines
+a `wrap`/`_wrap_deg`; nobody writes the modulo idiom inline; every file
+that used to carry a copy now actually imports the shared one; and
+`field.wrap()` states its interval and its ±180 result in its own
+docstring. The owner and this file are the only two allowed to *name*
+the retired idiom in prose — a guard that forbade the owner from
+explaining the convention would delete the documentation the ticket
+existed to write. `tests/host/`'s radians-domain `_wrap_to_pi` is out
+of scope by design: a different function against the C++ kernel's own
+convention, not a copy of this one.
+
+Run: `uv run pytest tests/tools/test_angle_wrap_ownership.py`.
 
 ### `test_run_verbs.py` (sprint 005 ticket 006)
 
@@ -171,13 +288,121 @@
 `RUN:{58360+deg}`) appear anywhere in what was sent — a regression back
 to the numeric vocabulary fails loudly instead of silently. Covers
 `otos_levercal.py` (`RUN:cal`/`RUN:cal:1`), `pivot_truth.py`/
-`truth_check.py`/`rotation_check.py` (`RUN:fix`, `RUN:pivot:<deg>`),
+`rotation_check.py` (`RUN:fix`, `RUN:pivot:<deg>`),
 and `turn_sweep.py` (`RUN:turnrate:<rate>` then `RUN:pivot:<deg>`).
 Cannot prove the robot moves — no serial port, no robot — only that
 each tool's own RUN-sending code path targets a real handler.
 
+Sprint 034 ticket 001 adds a second, unrelated-to-verbs group here
+(the file already imports both tools, so a new file would only split
+the same fixtures): source-level assertions that `rotation_check.py`
+carries neither the retired `rotationScrub`/`1.040` constant nor a
+private copy of the turn arithmetic, that `pivot_truth.py` dropped its
+±180 wrap-boundary special case, and a synthetic **still-camera** run —
+a fake `Cam` whose samples never change yaw, paired with an OTOS that
+reports the full commanded ±180 — driving `pivot_truth.main()` to
+completion. It must print "camera saw no rotation" and name the
+robot-is-switched-OFF check, where it used to raise
+`ZeroDivisionError`.
+
 Run: `uv run pytest tests/tools/test_run_verbs.py`, or as part of the
 whole suite.
+
+### `test_ruff_clean.py` (sprint 034 ticket 010)
+
+The lint gate, and this directory's one deliberate subprocess. `ruff`
+had been configured in `pyproject.toml` since sprint 017 ticket 007 and
+declared as a dev dependency, and nothing ever ran it — ten findings had
+accumulated, most of them in `tests/dev/` and `tests/system/`, which
+`uv run pytest` does not collect, so no amount of running the suite
+would have surfaced them. It shells the concrete `ruff` binary
+(resolved from `PATH`, then `.venv/bin/`, never a bare name — the same
+reasoning `tests/host/test_typescript_typecheck.py` spells out for
+`tsc`) over `tools/` and `tests/`, passes no `--select` of its own so
+the rule set stays a one-line `pyproject.toml` change, and folds ruff's
+own output into the assertion message. A missing `ruff` **skips** with
+a reason naming `uv sync` rather than failing: an uninstalled linter is
+an environment precondition, not a finding. It lints itself.
+
+A test rather than a CI workflow on purpose: this repo has one GitHub
+workflow (`publish-extension.yml`) and the developer signal here is
+`uv run pytest`.
+
+Run: `uv run pytest tests/tools/test_ruff_clean.py`.
+
+### `test_travel_calib_drift.py`
+
+Pins the two host-side hand-typed mirrors of
+`src/motion/motion_engine.h`'s `travelCalib_`: `tools/tour_chart.py`'s
+`--travel-calib` default, and (sprint 034 ticket 010)
+`tests/system/run_tour.py`'s `TRAVEL_CALIB`. The second was a third
+copy nothing checked, and it is the one holding the constant that has
+already drifted once (0.8102 stayed mirrored past the 0.7878
+camera-measured update) — and it is not decoration: `CPM = 10.0 /
+TRAVEL_CALIB` is the mm-to-counts scale every tour is commanded and
+scored in, and `tests/system/` is never run by `uv run pytest`, so the
+guard has to live here. Text-based, not imports: `tour_chart.py` needs
+matplotlib and `run_tour.py` opens a socket to a robot.
+
+Run: `uv run pytest tests/tools/test_travel_calib_drift.py`.
+
+### `test_link.py` (sprint 034 ticket 006)
+
+Pins `tools/link.py`, the one sequenced-wire protocol every carrier
+shares. Three groups: `LineBuffer` (a line split across `recv()`
+boundaries reassembles; a trailing partial is held, not emitted; the
+relay's `'< '` receive prefix is stripped; blank lines drop),
+`Sequencer` (the first id is 1; a resend reuses its id and a re-format
+of an already-numbered line takes no fresh one; `ack N` → N while
+`nack N` → N−1; unsequenced verbs and the cleartext `RUN:` form go out
+bare; `reset()` is HELLO's counterpart), and `relay_setup_lines()` (all
+four lines, in `robotlink`'s order, `!GO` excluded).
+
+Everything is driven through an injected `FakeSocket` handing back
+canned byte chunks — no robot, no relay, no network, and therefore no
+MEASURED claim anywhere in the file. Four source-level assertions close
+the loop on the ticket's consolidation: that all four callers import
+`link.py`; that no `!CG` string is BUILT in `wire_acceptance.py` any
+more (parsed via `ast`, docstrings excluded, so a comment may still
+quote the defect); that `turn_calibration.py`'s `radio_group` fallback
+to 10 is gone; and that `tools/rogo/rogo.py` imports nothing from
+`tools/` — its duplicate is deliberate (`tools/rogo/DESIGN.md`).
+
+Run: `uv run pytest tests/tools/test_link.py`.
+
+### `test_deleted_tools_stay_deleted.py` (sprint 034 ticket 003)
+
+Four tools were deleted outright — a ground-truth checker that read v1
+JSON keys and reported the failure as "camera cannot see the tag",
+sending the operator to the lights; two tour variants nothing imported,
+one of them the camera-in-the-loop experiment this repo's doctrine
+forbids; and the camera-subprocess wrapper, which carried a second
+`Cam` class to bridge two Python interpreters that are now one.
+
+The guard asserts BOTH halves: the paths are gone, and no file under
+`tools/` or `tests/` mentions their stems. A deleted file is only half
+deleted while a docstring or a design-doc bullet still names it — the
+next session reads the reference as an instruction and runs something
+that is not there. `docs/` and `clasi/sprints/done/` are deliberately
+out of scope: a dated code review citing a file that existed that day
+is a true statement, and rewriting it to keep a grep quiet would
+destroy the audit trail `.claude/rules/measurement-citations.md`
+depends on.
+
+### `test_tools_design_inventory.py` (sprint 034 ticket 012)
+
+`tools/DESIGN.md` must name every `*.py` under `tools/` (recursively —
+`rogo/` and `linefollow/` included) plus `field_calibration.json`,
+parametrized one case per file so a failure names the tool. It also
+checks the reverse: no inventory row may point at a path that does not
+exist. Modelled on `tests/host/test_pxt_manifest_completeness.py`, and
+for the same reason — a list maintained by discipline alone drifts, and
+the drift is invisible because nobody reads a doc looking for gaps.
+
+The third test guards the guard: if the inventory tables parse to fewer
+rows than there are files, the table format has changed and the other
+assertions would pass vacuously. This directory keeps finding that
+failure mode in its own checks, so it is asserted rather than assumed.
 
 ## 3. Constraints and Invariants
 
@@ -207,6 +432,12 @@
   tests replace every collaborator that would otherwise shell out or
   touch disk state. A future test that needs a real `pxt build` does
   not belong in this file.
+- **`test_ruff_clean.py` is the one subprocess in this directory, and
+  it stays the only one.** It shells a linter, which reads source text
+  and touches nothing else — no build, no device, no network. That is
+  the whole exception: a test that needs a compiler belongs in
+  `tests/host/`, and one that needs a robot belongs in
+  `tests/system/`.
 - **`test_tlm.py`: an absent CSV is unambiguous; an empty one is not
   — never assert the opposite.** Every fail-loud-guard test asserts
   *both* halves of that: the raising path leaves no file on disk, and
@@ -219,11 +450,12 @@
   to emit) are fed to `TlmStream` as-is; a test that instead
   hand-wrote its own "plausible" `t` line could pass while silently
   disagreeing with what the firmware actually sends.
-- **`test_camproc.py`/`test_field.py`: no real subprocess, camera, or
-  thread, ever.** `Cam(_spawn=False)` is the one seam these tests use
-  to exercise interpreter resolution, `ERR` surfacing, and pose
-  invalidation without ever starting the real AprilTags process this
-  class normally spawns.
+- **`test_camlink.py`/`test_field.py`: no real camera or daemon,
+  ever.** `Cam(client=...)` is the one seam these tests use — a fake
+  daemon client scripted with a finite list of frames — to exercise
+  registration, pose invalidation and the reader loop without ever
+  connecting to a daemon (which needs a Terminal launch for camera
+  permission and will not come up from an agent process tree).
 - **`test_run_verbs.py`: asserts both the positive and the negative.**
   Every test checks the exact string sent AND that none of the old
   dead numeric forms appear in it — asserting only the positive half
@@ -252,11 +484,13 @@
   file alone.
 - **`uv run pytest tests/tools/test_tlm.py`** (sprint 005) — this file
   alone.
-- **`uv run pytest tests/tools/test_camproc.py`**,
-  **`tests/tools/test_field.py`** (sprint 005 ticket 003) — each file
-  alone.
+- **`uv run pytest tests/tools/test_camlink.py`**,
+  **`tests/tools/test_field.py`** (sprint 005 ticket 003, sprint 034
+  ticket 008) — each file alone.
 - **`uv run pytest tests/tools/test_run_verbs.py`** (sprint 005 ticket
   006) — this file alone.
+- **`uv run pytest tests/tools/test_ruff_clean.py`** (sprint 034 ticket
+  010) — the lint gate alone.
 - All also run as part of **`uv run pytest`** from the repo root, and
   the once-per-sprint gate `close_sprint` runs.
 
@@ -273,10 +507,13 @@
   `tests/host/test_wire_telemetry_projection.py` uses as expected
   emitted bytes, so `test_tlm.py` cannot silently drift from what the
   firmware actually sends.
-- **`tools/camproc.py`**'s `Cam`/`resolve_venv()` and **`tools/field.py`**'s
-  `wrap()`/`score_corners()`/`path_deviation()` (sprint 005 ticket 003)
-  — see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Link layer" section.
-- **`otos_levercal.py`**, **`pivot_truth.py`**, **`truth_check.py`**,
+- **`tools/camlink.py`**'s `Cam`/`mount_yaw_rad()` and
+  **`tools/field.py`**'s `wrap()`/`score_corners()`/`path_deviation()`
+  (sprint 005 ticket 003, sprint 034 ticket 008) — see
+  [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Link layer" section for
+  `Cam`, and its "One `wrap()`" / "Scoring a corner" sections for the
+  `field.py` half.
+- **`otos_levercal.py`**, **`pivot_truth.py`**,
   **`rotation_check.py`**, **`turn_sweep.py`**'s own RUN-sending code
   paths (sprint 005 ticket 006), each monkeypatched at its `Link`/
   `send`/`send_until` call.
@@ -293,12 +530,13 @@
 re-emit), `seq`-gap loss counting and 7-bit wraparound, arity/malformed
 rejection, orphan-frame counting, the unit-conversion helpers against
 the shared golden frame, and both fail-loud guards' raising and
-non-raising paths. `camproc.py`'s `resolve_venv()` env-var override/
-default, `ERR` surfacing, and stale-pose invalidation against a
-`Cam(_spawn=False)` double. `field.py`'s `wrap()`, `score_corners()`'s
+non-raising paths. `camlink.py`'s registration guarantees, stale-pose
+invalidation, dead-instrument-vs-tag-not-in-frame distinction and
+one-sample-per-real-frame property, against an injected fake daemon
+client. `field.py`'s `wrap()`, `score_corners()`'s
 gap-aware scan (including the historical console-vs-chart
 disagreement), and `path_deviation()`'s degenerate-segment guard. The
-exact RUN string each of the five retargeted tools sends, and the
+exact RUN string each of the four retargeted tools sends, and the
 absence of every old dead numeric form, for both the fix/pivot/
 turnrate path and the `cal`/`cal:1` rename.
 
@@ -314,7 +552,7 @@
 real-hardware end-to-end check (`tour_run.py --tour world` against a
 real robot), not a unit test; this file only pins the parsing/guard
 *logic* against synthetic and captured-but-replayed frames. For
-`test_camproc.py`/`test_field.py`/`test_run_verbs.py`: none of them
+`test_camlink.py`/`test_field.py`/`test_run_verbs.py`: none of them
 exercise a real camera daemon, a real robot, or a real radio link
 either — that is this sprint's own bench handoff checklist (ticket
 007), not a unit test.
```
