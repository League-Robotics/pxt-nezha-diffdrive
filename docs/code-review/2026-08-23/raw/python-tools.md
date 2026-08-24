# Code review — Python tools and host harness

**Scope:** `tools/*.py`, `tests/host/*.py`, and the harness C++ support files
(`fake_ports.h`, `fake_pose_source.h`, `wire_mock_adapter.h`,
`*_shim.cpp` compile recipes). Reviewed 2026-08-23 against
`docs/code-review/guidelines.md`, the CLASI `python` language
instruction, and PEP 8. Every correctness claim below was verified by
reading both sides of the seam (tool ↔ firmware, fake ↔ production).

**Known-issue cross-reference (not re-reported):** the tour/truth
recorders parse the retired v5 `TLM:` stream (dead branches at
`tour_watch.py:202`, `tour_capture.py:70`, the `/10` `/100` ladders in
`tour_run.py`, `tour_practice.py`, and both `enc_heading()`s) — all of
that is one known item, filed as
`clasi/issues/retrofit-bench-tooling-onto-the-v6-telemetry-stream.md`
(sprint 005). `otos_bench.py`'s numeric vocabulary targets
`test/testrig.ts`, whose breakage is
`clasi/issues/testfiles-are-not-type-checked-testrig-is-broken.md`. The
"regression pinned by argument, not execution" gap in the settle loop is
`clasi/issues/settle-tick-loop-is-not-host-testable.md`. Individual
symptoms of those three are cross-referenced below, not re-counted.

---

### PY-01 — Five tools still speak the retired numeric `RUN:<n>` vocabulary (and one polls the removed `DIAG` verb); their command path is dead, and this is NOT covered by the TLM retrofit issue

**File:** `tools/rotation_check.py:30,36,87` · `tools/truth_check.py:31,81` ·
`tools/pivot_truth.py:73,85,115` · `tools/turn_sweep.py:92,98,102` ·
`tools/otos_levercal.py:87-88` · `tools/tour_capture.py:42,59-60`
**Dimension:** 1 (correctness) / 2 (landmine)
**Severity:** Major

**Scenario:** The RUN dispatch was reworked to named verbs only —
`src/main.ts:143-154` ("The wire therefore reads as what it does —
RUN:pivot:180, not RUN:4") — and `test/test.ts` registers only named
handlers (`tour`, `straight`, `cal`, `fix`, `arm`, `probe`, `gap`,
`seed`, `seedxy`, `goto`, `face`; no numeric handler, no pivot verb at
all). Concretely:

- `rotation_check.py --radio`: `fix()` sends `RUN:10` expecting
  `OCAL:now` (now emitted by `RUN:fix`, `test/test.ts:326`); no handler
  named "10" exists, so every pivot prints "no fix -- skipping" and the
  tool completes having measured nothing. Its `RUN:2/4/5` pivot verbs
  are equally dead.
- `truth_check.py` and `pivot_truth.py`: same `RUN:10` fix plus
  `PIVOT_VERB = {180: 4, -180: 5, 360: 2}` — every rep is skipped.
- `turn_sweep.py`: `RUN:{57000+rate}` / `RUN:{58360+deg}` encoded-number
  verbs, and it waits for a `TRN:` reply that `test.ts` no longer emits
  anywhere. A default sweep (6 rates × 4 angles × 2 reps) is 48
  dead waits of `budget` seconds each with the robot never moving.
- `otos_levercal.py`: `RUN:8` / `RUN:14` were renamed `RUN:cal` /
  `RUN:cal:1` (`test/test.ts:13-14`). This one at least fails loudly
  ("robot never acknowledged RUN:8").
- `tour_capture.py:42`: `RUN:{a.run}` (numeric tour trigger) never
  starts a tour; and its `DIAG` poll at line 59-60 gets nothing — the
  v6 wire "has no DIAG verb at all" (`src/wire_adapter.cpp:197`), so
  the `vel` CSV is header-only even before the TLM gap.

The retrofit issue covers only the telemetry *stream*; this is the
*command* half dying in the same rework, and `tools/DESIGN.md:76-82`'s
claim that "The `RUN:` command path … still work[s]" is true only of
the named verbs the tour tools use — the document is wrong for these
five tools.

**Remedy:** Fold into sprint 005's retrofit scope: switch `otos_fix()`
to `RUN:fix`, `otos_levercal` to `RUN:cal[:1]`, and either add the
named `RUN:pivot:<deg>` handler `main.ts:150` already advertises as the
canonical example (plus a named turn-sweep verb or retirement of
`turn_sweep.py`), or retire the pivot tools explicitly. Correct
`tools/DESIGN.md`'s claim either way.
**Confidence:** High — dispatch verified in `main.ts`, handler
inventory verified in `test.ts`, DIAG absence verified in
`wire_adapter.cpp`.

---

### PY-02 — Five tools hardcode a camlink venv that can no longer import `aprilcam`; `tour_watch.py` degrades to silently recording no camera truth

**File:** `tools/tour_watch.py:31` · `tools/tour_practice.py:32` ·
`tools/pivot_truth.py:28` (and its docstring, lines 14-15) ·
`tools/turn_sweep.py:31` · `tools/tour_square.py:20` ·
`tools/tour_closedloop.py:29` — vs. `tools/tour_run.py:31` (correct)
**Dimension:** 1 (correctness) / 3 (duplication consequence)
**Severity:** Major

**Scenario:** Verified directly:
`/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3 -c
"import aprilcam"` → `ModuleNotFoundError` (that venv was rebuilt
2026-08-19); the pipx venv `tour_run.py` and `camlink.py`'s docstring
name does import it. When camlink is spawned under the dead venv it
crashes on import: the traceback goes to `stderr=DEVNULL`, stdout hits
EOF with **no `ERR` line ever printed**, so:

- `tour_watch.py` sleeps a fixed 1.5 s, checks `cam.err` (still
  `None`), prints "watching for a tour", and then records every tour of
  the session with **zero camera samples** — charts render with no
  truth track, no closure, and the operator finds out after the runs
  are burned.
- `tour_practice.py`, `turn_sweep.py`, `tour_closedloop.py` stall their
  full 15 s startup deadline and then abort with the misleading
  "camera not usable: no tag" — the tag may be in plain view.
- `pivot_truth.py`'s docstring instructs running the tool itself under
  that venv ("it has the aprilcam package" — no longer true).

Root cause is PY-05's duplication: six copies of the `VENV` constant,
two values, only one of them right.

**Remedy:** One venv constant, owned by `camlink.py` (or the shared
camera-process module proposed in PY-05); have the wrapper treat
unexpected subprocess exit as an error (`Popen.poll()` + captured
stderr surfaced in the message) instead of silence.
**Confidence:** High — import failure reproduced; code paths traced.

---

### PY-03 — The WaHandle test doubles have drifted from `shims.cpp` despite "mirrors field-for-field" claims; STATUS `wedge` means a different thing in the harness than on the robot

**File:** `tests/host/wire_motion_verb_shim.cpp:182-191,261,337-338` vs
`src/shims.cpp:280-287,688-689,832` and `src/wire_adapter.cpp:138-139,212-227`
**Dimension:** harness fidelity (charter §"Secondary") / 2 (landmine)
**Severity:** Major

**Rationale (all three verified on both sides):**

1. **`diagValue` ordinals 6/7.** Production `shims.cpp:688-689` returns
   `out.wedgeSuspectLeft/Right`; the harness double
   (`wire_motion_verb_shim.cpp:337-338`) returns
   `out.wedgeLeft/wedgeRight`. `wire_adapter.cpp` names those ordinals
   `kDiagWedgeLeft/Right` and folds them into the v6 STATUS reply's
   `wedge` field (`status()`, lines 212-227). So on hardware
   `STATUS … wedge=1` actually reports wedge-*suspicion*, while a host
   test would pin wedge-*latched* semantics. No current test drives the
   wedge path through WaHandle (grep: `wedge` appears in the Python
   suites only as canned zeros), so the divergence is invisible to the
   220-test suite — precisely the "test that can't fail" class. One of
   the two C++ sides is wrong (`wire_adapter`'s naming or `shims.cpp`'s
   field choice — that call belongs to the src reviewer); the harness
   must match whichever is declared correct, and a test should drive it.
2. **`setWheelsTimed` bypasses the motion engine.** Production
   (`shims.cpp:280-287`) routes through `engine.wheelsV()`, whose first
   act is `cancelMove()` ("wheels_* clears the planner",
   `motion_engine.cpp:20-26`, motion-api.md S6). The double
   (`wire_motion_verb_shim.cpp:182-191`) calls `kernel.drive()`
   directly: a harness test dispatching `MOVE_X` then `WHEELS_V` would
   see the move survive where the robot supersedes it. The comment
   claims it "Mirrors shims.cpp's real setWheelsTimed() exactly" — it
   mirrors the *ticket-003* shape; production moved underneath it in
   ticket 011, and the WaHandle has owned a real `engine` member since
   then that the double simply doesn't use.
3. **`getConfigValue` rounding.** Production rounds
   (`std::lround(v * 1000.0)`, `shims.cpp:832`); the double truncates
   (`static_cast<int>(v * 1000.0f)`, line 261). Any config value whose
   float ×1000 lands just below the integer (e.g. 2.3 → 2299.9998f)
   reads back off-by-one in the harness only.

**Remedy:** Route the double's `setWheelsTimed` through
`h->engine.wheelsV()` (countsPerMm=1.0 is preserved — the engine's
geometry is the handle's own), copy production's `lround`, settle the
6/7 semantic with the src reviewer and then add one WaHandle test that
drives a wedge flag through STATUS so the seam can never drift silently
again.
**Confidence:** High — all six function bodies compared line by line.

---

### PY-04 — `tour_run.py` swallows camlink's `ERR` lines and never detects a dead camera stream, misdiagnosing instrument failure as "camera cannot see the robot" and re-seeding the robot from a stale pose

**File:** `tools/tour_run.py:64` (ERR skipped), `74-85` (`fix()` has no
staleness check), `160-203` (`place()` seeds from `fix()`); contrast
`tools/tour_square.py:40-66` and `tools/camlink.py:103-113`
**Dimension:** 1 (correctness — swallowed error path)
**Severity:** Major

**Scenario:** Two escalating failures from the same line:

- *Startup:* the aprilcam daemon is down. camlink prints
  `ERR aprilcam daemon unreachable…` and exits; `Cam.run()` skips any
  line starting with `ERR`, waits out its 15 s, and `main()` raises
  `SystemExit('camera cannot see the robot')` — sending the operator to
  check the field, tag, and lighting instead of the daemon. (This rig's
  documented failure mode is exactly instrument faults masquerading as
  robot faults; camlink prints `ERR` *specifically so* consumers can
  tell them apart, and this consumer throws it away.)
- *Mid-run:* the stream dies between runs (`CamDown` — measured
  happening in practice; `tour_square.py`'s comment records phantom
  53/69 cm corner errors from it). `Cam.latest` is sticky and never
  invalidated, `run()` simply ends, and there is no respawn. The next
  `place()` call medians eight identical stale samples and
  **`RUN:seedxy`'s the robot with a pose from the past**, actively
  corrupting the robot's world frame before the next scored run.
  `tour_square.py` (the "kept for reference" variant) already grew
  respawn + blind-window bookkeeping for this exact event; `tour_run.py`
  — the canonical tool — never got it.

**Remedy:** In `Cam.run()`, record `ERR` lines and stream EOF into an
`err` field checked by `fix()`/startup (as `tour_practice.CamProc`
already does); make `fix()` refuse samples older than ~1 s (timestamps
are already collected in `samples`); adopt `tour_square`'s respawn +
`deaths` window refusal. All three collapse into the shared wrapper of
PY-05.
**Confidence:** High — code paths traced end to end; staleness is
structural (`latest` has no timestamp check anywhere in the file).

---

### PY-05 — Seven hand-rolled camera wrappers, eight `wrap()`s, six dot tables, four corner scorers: the tour/truth family is a copy-paste field, and the copies have already diverged in behavior

**File:** representative pairs below; the whole `tools/tour_*`,
`truth_*`, `*_check`, `reposition.py` family
**Dimension:** 3 (duplication / information hiding)
**Severity:** Major

**Rationale — the inventory, with divergences that already bit:**

- **Camera subprocess wrapper — 7 copies:** `tour_run.py:46-92`,
  `tour_watch.py:48-83`, `tour_practice.py:48-96`,
  `tour_square.py:27-87`, `tour_closedloop.py:46-98`,
  `pivot_truth.py:32-71`, `turn_sweep.py:43-87`. Each spawns
  `camlink.py` under its own `VENV` constant (two different values —
  PY-02), each handles `ERR`/`NOTAG` differently (skip / store / end
  thread; `pivot_truth._pump` filters neither and relies on
  `float('NOTAG')` raising), each waits for first-sample differently
  (15 s poll vs the fixed 1.5 s sleep that `tour_practice.py:61-64`'s
  own comment records as a bug already found and fixed — the fix never
  propagated back to `tour_watch.py:180`). Only `tour_square` respawns
  a dead stream. And the `latest` tuple order differs:
  `tour_run.Cam.latest` is `(x, y, yaw)` while
  `tour_practice.CamProc.latest` is `(yaw, x, y)` —
  `reposition.fix()`'s `med(1), med(2), med(0)` silently compensates;
  copying `fix()` between wrappers transposes coordinates. (Related
  trap: `CamProc.read(tag=53)` ignores its `tag` argument, so
  `Repositioner(tag=…)` with a non-default tag would silently read
  whatever tag the subprocess was started with.)
- **`wrap()` — 8 copies:** `tour_run.py:38`, `practice_chart.py:27`,
  `reposition.py:18`, `truth_check.py:102`, `pivot_truth.py:76`,
  `turn_sweep.py:35`, `tour_closedloop.py:38`,
  `rotation_check.py:59` (as `unwrap`).
- **`DOTS`/`ORDER`/`RECT` field constants — 6 copies:**
  `tour_run.py:33-35`, `tour_watch.py:36-38`, `practice_chart.py:15-18`,
  `tour_practice.py:35-39`, `tour_square.py:22-24`,
  `tour_closedloop.py:33-35`.
- **Corner scorer (closest approach in visit order) — 4 copies with
  diverging semantics:** `tour_run.analyse():131-139`,
  `tour_practice.score():163-171`, `tour_square.py:180-188`,
  `practice_chart.score():84-105`. Only the last refuses corners that
  abut a tracking gap. Consequence: for the same run,
  `tour_practice.main()` prints the discredited number on the console
  (e.g. "SW 31.3cm") while its own chart subprocess prints
  "SW=unobserved" — the exact fiction `practice_chart`'s docstring was
  written to kill survives in the caller's summary.
- **`OCAL` fix parsing — 4 copies, two unit conventions:**
  `truth_check.py:81-86`, `pivot_truth.py:84-90`,
  `rotation_check.py:33-42` (÷10 → mm) vs `tour_square.py:90-100`
  (÷100 → cm). Both are *currently* correct against `test.ts`'s
  0.01 cm wire units, but nothing marks the two conventions, and the
  next copy-paste across that line is a silent 10× error.
- **`seedxy` + `OCAL:seeded` handshake — 6 copies:** `tour_run.py`
  (twice), `reposition.py:47-52`, `tour_practice.py:234-237`,
  `tour_square.py:117-120`, `tour_closedloop.py:106-111`.
- **Rectangle-deviation scoring — 2 copies:** `tour_run.py:141-151`,
  `tour_square.py:189-198`.
- **Calibration constants re-typed per file:** `0.8102` (travel calib)
  in `tour_chart.py:48` and hardcoded as `k = 0.8102/100` in
  `tour_watch.py:217`; `TRACK_CM = 12.0` in `tour_practice.py:41` and
  `practice_chart.py:19` — all four also independent of the firmware's
  own values (guidelines dimension 2's "protocol values defined
  independently" case, host-side edition).

**Are `robotlink.py`/`camlink.py` the shared layer?** Partially, and
the tools bypass them: `tour_capture.py:62-67` reads `link.p.readline()`
raw and re-implements the relay's `'< '` prefix strip that
`Link.lines()` already owns; `truth_check.py:37-66` bypasses `camlink`
entirely for per-sample `aprilcam tool get_tags` *subprocess CLI calls*
(one process spawn per sample, its own daemon-address env plumbing) —
the slow polling pattern `camlink`'s docstring exists to replace.

**Remedy (proposed shared-module shape):**

- `tools/camproc.py` — the one camera-subprocess wrapper: owns the venv
  constant, spawn, pump thread, `err` surfacing (including subprocess
  death), first-sample wait, staleness-aware `fix()`, optional respawn
  with blind-window log. One `latest` convention.
- `tools/field.py` — `DOTS`/`ORDER`/`RECT`, `wrap()`, the gap-refusing
  corner scorer, rectangle deviation. The one place a score is defined,
  so console and chart cannot disagree.
- `tools/tlm.py` — already specified in the sprint-005 retrofit issue;
  the scale-factor and arity single source belongs there.
- `Link.lines()` stays the only line reader (`tour_capture` moves onto
  it); calibration constants move next to their firmware counterparts'
  documentation or are read back from the robot (`GET`).

**Confidence:** High — all cited blocks read; the console-vs-chart
divergence follows directly from the two `score()` bodies.

---

### PY-06 — `make_deploy.py`'s docstring claims manifest-driven sync ended the testrig drift, but `sync()` still excludes `testrig.ts` from the deploy copy

**File:** `tools/make_deploy.py:10-14` vs `60-62,68-69`
**Dimension:** 2 (landmine) / 6 (comment accuracy)
**Severity:** Minor

**Rationale:** The docstring: the hand-maintained copy "omitted
`testrig.ts` entirely, which is how that file sat uncompilable without
anyone noticing. Generating it from the repo's own manifest is the fix
-- there is nothing left to forget to copy." But `sync()` promotes only
`testFiles` entries ending in `test.ts` (`'test/testrig.ts'` does not
match), copies only `files + promoted`, and sets
`manifest['testFiles'] = []` — so the deploy build still cannot see
`testrig.ts`, and the repo/deploy divergence persists exactly as
before. (In effect this is currently *load-bearing*: including
testrig.ts would fail the build, per the filed issue.) The comment
promises a guarantee the code does not provide; the next person to
trust it repeats the original incident.

**Remedy:** Either copy all `testFiles` into the deploy tree (even
unpromoted, so `pxt build` type-checks them once testrig is fixed) or
rewrite the docstring to state the real contract ("test.ts only;
testrig is deliberately excluded until
`testfiles-are-not-type-checked-testrig-is-broken` lands").
Cross-reference that issue.
**Confidence:** High — `pxt.json` `testFiles` verified as
`['test/test.ts', 'test/testrig.ts']`; the endswith filter verified.

---

### PY-07 — `Repositioner.go()` and `tour_run.place()` exhaust their tries and report success without converging

**File:** `tools/reposition.py:54-86` · `tools/tour_run.py:160-203`
**Dimension:** 1 (correctness — silent failure) / 4 (API)
**Severity:** Minor

**Scenario:** Both loops retry `fix → seed → goto/face` up to `tries`
times; if tolerance is never met they fall through — `go()` returns the
final pose, `place()` returns `True` (with only a printed `<-- OFF`
flag). Callers treat any non-`None`/`True` as "positioned": a
mis-registered tag or drivetrain fault produces three futile
repositioning rounds and then a scored run started off-dot, graded as a
robot failure. The failure signal exists (the final error is computed)
but is not returned.

**Remedy:** Return the final `(pose, converged)` (or `None`/`False` on
non-convergence) and let callers skip the run, consistent with how both
already abort on camera loss.
**Confidence:** High.

---

### PY-08 — `truth_check`/`pivot_truth` divide by the camera-measured rotation with no zero guard

**File:** `tools/truth_check.py:183` (`gyro / cam`) ·
`tools/pivot_truth.py:140` (`gyro / camdeg`)
**Dimension:** 1 (correctness)
**Severity:** Minor

**Scenario:** If the camera saw no motion during a pivot (sampler got
no frames — CLI hiccup in `truth_check`'s subprocess-per-sample
sampler, or a dead `CamStream` returning stale marks so
`t1 - t0 == 0.0`), the ratio print raises `ZeroDivisionError` and
kills the session after the robot already drove. Both tools are
currently unreachable past PY-01, but the guard should ride along with
that fix.

**Remedy:** Skip (and say why) when `abs(cam) < a few degrees` —
`pivot_truth.py:157` already applies exactly that guard to its summary
(`if abs(r[1]) > 30`), just not to the per-row print.
**Confidence:** High on the code path; Medium on field frequency.

---

### PY-09 — `tour_watch.py` checks `cam.err` once, 1.5 s after spawn — a race its sibling documents as an already-found bug

**File:** `tools/tour_watch.py:180-182` vs `tools/tour_practice.py:61-69`
**Dimension:** 1 (correctness) / 3 (fix not propagated)
**Severity:** Minor

**Scenario:** A daemon-unreachable `ERR` from camlink can take longer
than 1.5 s to arrive (spawn + import + gRPC connect timeout).
`tour_watch` checks `cam.err` exactly once after `time.sleep(1.5)` and
never again; a late `ERR` is stored and unread, and the session watches
forever recording camera-less tours (compounding PY-02's silent mode).
`tour_practice.CamProc.__init__` polls latest-or-err for up to 15 s
*because this exact 1.5 s assumption already failed once* (its comment
says so) — the fix never reached `tour_watch`. Absorbed by PY-05's
shared wrapper.

**Remedy:** Use the poll-until-`latest`-or-`err` startup from
`CamProc`, and re-check `err` inside the recording loop.
**Confidence:** High.

---

### PY-10 — `robotlink.send_until()`'s docstring overclaims: a lost *reply* still duplicates delivered work

**File:** `tools/robotlink.py:48-54`
**Dimension:** 2 (landmine) / 6 (comment accuracy)
**Severity:** Minor

**Rationale:** "Loss-tolerant without ever duplicating work that did
land -- the reply IS the delivery receipt." True only when the loss is
on the command's leg. The radio drops both directions: if the command
landed and the *receipt* line was lost, `send_until` resends and the
work runs twice. Current call sites are idempotent-ish (re-seed, goto
to the same target) or receipt-at-start (`OCAL:begin`), so nothing
breaks today — but the module's own `send()` docstring teaches students
that a duplicated RUN re-runs the whole test, and this docstring then
tells them `send_until` cannot do that. A student wrapping `RUN:tour`
in `send_until('TOUR:end')` gets a double tour on one lost line.

**Remedy:** One honest sentence: resend-on-missing-reply means an
at-least-once guarantee — use it only for idempotent commands or
commands whose receipt is emitted at start.
**Confidence:** High.

---

### PY-11 — Minor style and hygiene group (CLASI python instruction + PEP 8)

**Dimension:** style / 5 (readability) / dead code — **Severity:** Minor.
Per the charter these are grouped; within-file consistency was
respected (the tools are uniformly `os.path`-based, hint-free scripts —
flagged once, not per file).

- **No type hints anywhere in `tools/`** (instruction: hints on all
  public signatures). The link/cam layer (`robotlink.open_link`,
  `Cam.frames`, `Repositioner.go`) would benefit most; the harness
  suites are internally consistent without them.
- **`pathlib` unused; `os.path` + string paths throughout** —
  `make_deploy.py` especially (`REPO`, `DEPLOY`, `HEX` juggling).
- **`sys.path.insert` bootstrap duplicated in 9 scripts** (three
  spellings: `os.path.dirname(os.path.abspath(__file__))`,
  `__file__.rsplit('/', 1)[0]`, and `pivot_truth.py:25`'s absolute
  repo path — the last breaks on any checkout at a different path). A
  `tools/` package or `pyproject` script entries removes all of them.
- **Wall clock for deadlines**: every timeout loop uses `time.time()`
  (`robotlink.lines()`, all capture loops); `time.monotonic()` is the
  correct tool — an NTP step mid-run stretches or truncates captures.
- **Resource handling**: `make_deploy.py:44,71` `json.load(open(...))`
  / `json.dump(..., open(..., 'w'))` without context managers;
  `tour_chart.read_csv():36-39` `next(r)` raises bare `StopIteration`
  on an empty file.
- **Dead/vestigial code**: `camlink.py:58` `self._stream = None` never
  used (and shadows the module function `_stream`);
  `tour_watch.chart()`'s `fixes` parameter unused (line 86 — corner
  fixes are collected, then never plotted); `practice_chart.score()`
  computes `res['endhdg']` (line 101) that `main()` never displays;
  `tour_closedloop.py:207`'s `hasattr(cam, 'since_all')` is always
  false (no such method — the else branch is the only live path);
  `otos_bench.py:22` imports `argparse` and then hand-parses
  `sys.argv` (missing sub-arguments die as `IndexError` tracebacks:
  `otos_bench.py PORT servo`).
- **PEP 8 nits**: lambdas assigned to names (E731) at
  `tour_run.py:84`, `reposition.py:44`, `truth_check.py:69`,
  `tour_square.py:78`, `tour_closedloop.py:94`; semicolon compound
  statements (`tour_run.py:232,287`, `tour_square.py:33-34,133,158,180,188`);
  old-style `%` formatting `rotation_check.py:101`; f-string without
  placeholder `tour_practice.py:260`; `tour_square.py:16`'s
  eight-module single-line import.
- **Comment accuracy, small**: `src/motion_engine.h:131` names
  `tests/host/fake_pose_source.h`, while that file and
  `tests/host/DESIGN.md` both promise "nothing under src/ knows this
  file exists" — one side should yield (the reference is helpful; the
  absolutist claim is what's wrong).
- **Student readability**: the tour tools' one-letter locals (`a`, `p`,
  `r`, `s`, `f2`, `p2` in `tour_run.main()`) are dense for advanced
  students; the tools otherwise carry excellent explanatory comments —
  the measured-number war stories are exactly the keep-class of
  comment the guidelines describe.

---

## Not findings (cleared suspicions)

- **Fake ports match the real port contracts.** `FakeMotor` honors both
  sharp `Motor` semantics (`sampleTime` stamps only on successful
  collect; `rebaseline` is bus-silent) per `src/diffdrive.h:32-50`; no
  mirroring belongs in `Motor` — `fwdSign_` lives inside
  `NezhaMotorPort` (`nezha_port.cpp:174`), so the fakes' lack of
  mirroring is correct fidelity, not a gap.
- **`FakePoseSource` units** ([mm], [mm], [rad] CCW+) match
  `PoseSource`'s declared contract (`motion_engine.h:133-140`) exactly.
- **`tour_closedloop`'s `ESTOP` stop path is alive** under v6:
  unsequenced and maximally forgiving (`wire_handler.cpp:353-360`), so
  the camera-lost `bot.stop()` still halts the robot.
- **The `OCAL` scale split is not a unit bug**: `rotation_check`'s ÷10
  (mm) and `tour_square`'s ÷100 (cm) both check out against
  `test.ts:68`'s 0.01 cm wire units (flagged only as duplication risk,
  PY-05).
- **Compile recipes are sound**: every suite routes through
  `compile_shared_lib()` with a source list matching its class under
  test (`test_wire_motion_verbs.py:56-61` links diffdrive +
  motion_engine + wire_handler + wire_adapter + shim); no stale or
  missing source found, and only portable sources appear.
- **`Link.send(repeat>1)`** — the documented-dangerous blind repeat has
  no caller passing `repeat > 1`; the warning comment is doing its job.
- **`Link.lines()`'s `'< '` strip** is correct relay control-plane
  handling, not corruption; `tour_capture`'s reimplementation of it is
  PY-05, not a separate bug.
- **`WaHandle`'s process-wide active-handle singleton** is documented,
  matched by the DESIGN.md constraint, and safe under the repo's serial
  pytest config — not re-reported.
