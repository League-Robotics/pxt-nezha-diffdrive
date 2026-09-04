# Code review 2026-09-02 — `tools/`, `tests/`, `pyproject.toml`

Scope: every `tools/*.py` (read in full, `tools/DESIGN.md` first), `tools/field_calibration.json`, the host harness (`tests/host/*.py`, the C++ fakes/shims), `tests/tools/*.py`, `pyproject.toml`. Severity per `docs/code-review/guidelines.md`. Every finding below was verified against the current worktree (branch `claude/code-review-errors-cohesion-1bde6b`, HEAD `50efc2d`); line numbers are from that tree.

**Baseline.** `uv run pytest -q`: **1 failed, 922 passed in 149.42 s**. The one failure is `tests/host/test_typescript_typecheck.py::test_tsc_noemit_is_clean` — `node_modules/.bin/tsc` does not exist in this worktree (no `npm install`), an environment precondition surfacing as a red test (see TL-19f). `uv run ruff check tools tests`: **5 findings** (3 × F401, 1 × B904, 1 × B007), all in `tests/dev/` and `tests/system/` — zero in `tools/` or `tests/tools/`.

## Findings at a glance

| ID | Severity | file:line | Summary |
|---|---|---|---|
| TL-01 | Critical | `tools/robotlink.py:21-22` | `ZAVAZ_CHANNEL=4/GROUP=10` hard-coded; vevov moved to 37/43 on 2026-08-30, so every `open_link(radio=True)` tool tunes the relay at nothing and fails as "instrument is dead" |
| TL-02 | Critical | `tools/camlink.py:55,80-96` | `MOUNTS[53]` is the pre-remount lever and `Cam()` re-registers it into the now-persistent daemon registry on every start; `tools/field_calibration.json` (2026-09-02) disagrees, and `field_dance.py` assumes the raw tag — two calibrations of record for one tag, silently overwriting each other |
| TL-03 | Major | `tools/rotation_check.py:108-109`, `tools/truth_check.py:120-124` | `total_turn()` cannot resolve a ±180° pivot that over-rotates: `round(0.5)=0`, so 183° physical reads −177° and the gyro/commanded ratio flips sign |
| TL-04 | Major | `tools/robotlink.py:120-123` | `_V6_VERBS` names `MOVE/PIVOT/GO_TO/ARC` (not firmware verbs) and omits `MOVE_X/MOVE_V/GO_TO_R`; a `MOVE_X` sent through `Link` gets no `#id` and is silently dropped — the exact bug class the comment above it documents |
| TL-05 | Major | `tools/field.py:42-85` | Geofence (D-08) exists as functions with zero callers; `tour_run.place()`, `reposition.Repositioner.go()`, `tour_closedloop` still drive to arbitrary points unchecked; a second, different field size lives in `tests/host/test_run_tour_programs.py:171-172` |
| TL-06 | Major | `tools/tour_capture.py:128`, `tour_watch.py:212`, `tour_practice.py:147`, `tour_chart.py:107-121` | Three pose-CSV schemas (mm/cdeg vs cm/deg, different column orders) and one positional reader keyed on column COUNT — a `tour_watch` CSV plots 10× small with heading/100, no error |
| TL-07 | Major | `tools/camproc.py:58,73-76`, `tools/camlink.py:1-8` | Q-09 still open (`/Volumes/Cache/User-Eric/...`), and its premise is false: `aprilcam[daemon]` is now a dependency of this venv (`pyproject.toml:9-12`) and `import aprilcam, serial` succeeds under `uv run`; the subprocess/second-venv architecture and the second `Cam` class (Q-06) have no remaining reason to exist |
| TL-08 | Major | `tools/field.py:123-135` | C-16 still open: first corner's search covers the whole remaining run; a late re-pass of an early dot pushes `used` to the tail and starves every later corner |
| TL-09 | Major | `tools/truth_check.py:35-69` | Dead-on-arrival tool listed as live in DESIGN.md: shells `aprilcam tool get_tags` per sample against a hard-coded `127.0.0.1:5280`, reads v1 JSON keys (`id`, `orientation_yaw`, `world_xy`) the v2 client does not emit; duplicates `pivot_truth.py` |
| TL-10 | Minor | `tools/leg_analysis.py:237-243` | A leg inside distance tolerance but outside heading tolerance is labelled `straight-overrun`/`mid-leg-truncation` by the sign of a sub-tolerance distance error |
| TL-11 | Minor | `tools/field_calibration.json` (`heading_offset_deg`) | Stores the fixed +90° AprilCam convention plus 1.1° plate skew as one "fitted from a translation probe" number — the exact recurrence the tag-yaw rule forbids |
| TL-12 | Minor | `field.py:88`, `leg_analysis.py:181`, `field_dance.py:84,130,131,151,167`, `otos_levercal.py:155` | Four surviving `wrap()` implementations after the sprint-005 consolidation, two with different boundary semantics |
| TL-13 | Minor | `robotlink.py`, `fieldlink.py`, `wire_acceptance.py:52-190`, `otos_bench.py:29` | Link layer written four times; three different relay addresses (`zavaz` 4/10, `torture`, `192.168.1.12`+group 10); two sequence-id implementations |
| TL-14 | Minor | `tools/tour_run.py:80-123` vs `tools/reposition.py:44-76` | Two repositioning loops; `place()` documents an ordering bug that `Repositioner.go()` still has |
| TL-15 | Minor | `tour_watch.py:170-179`, `tour_practice.py:81-109`, `practice_chart.py:51-62`, `tour_square.py`, `tour_closedloop.py` | Dead code kept "for reference" in the live tool set, still executable, still pointing at the stale relay address |
| TL-16 | Minor | `tools/DESIGN.md` | Inventory omits 11 of 30 tools (`field`, `camproc`, `fieldlink`, `field_dance`, `park`, `arc_capture`, `wire_acceptance`, `blocks_*`, `publish_extension`, `field_calibration.json`); cites a "Telemetry (tlm.py)" section that does not exist; says `otos_bench.py`'s numeric verbs are a silent no-op (false — `testrig.ts:44-56` answers them); still says "channel 4, group 10 — vevov" |
| TL-17 | Minor | `tools/tour_chart.py:179-192` | `--meta` consumes `start_world_cm[2]` as radians; the only writer is a capture-dir script, no tool writes it, help text does not say the unit |
| TL-18 | Minor | `tests/tools/test_make_deploy_robot_channel.py:99-120` vs `:170`; `make_deploy.py:24` | Test names/docstrings assert "vevov is channel 4" while the same file's derivation table says (37, 43) |
| TL-19 | Minor | `tests/host/` | What the harness does not prove: 7 pxt.h-bound TUs compiled by nothing; C++11 gate uses `-I src` the real build lacks; Python mirrors of `shims.cpp` under test; one assert-less test; 11 identical `motion_lib` compiles/session; tsc gate is an env precondition; `run_tour.py` travelCalib mirror unpinned; ruff not gated |
| TL-20 | Suggestion | `tools/tlm.py:300`, `tools/turn_sweep.py:128,136` | `duty_pct()` has tests and no callers; `turn_sweep` re-derives the ×100 scale inline |
| TL-21 | Suggestion | `tools/field_dance.py:51-56,87-98` | `settle()` degrades to a 0.25 s wait if the record has no `speed`; `_daemon()` finds the connection class by reflection |
| TL-22 | Suggestion | `tools/fieldlink.py:45-54` | `seqd()` returns truthy on `err N`; `field_dance` ignores every return, so a refused `SET` is invisible |
| TL-23 | Suggestion | `tools/robotlink.py:51-72` | `probe_port` worst case ≈ 8 × 30 s before "not found" |
| TL-24 | Suggestion | `tools/tour_chart.py:118,175-176` | `t_cut` compares device-clock pose time with host-clock camera time |
| TL-25 | Suggestion | `tools/rotation_check.py:122-123` | Prints a conclusion scaled by `rotationScrub 1.040`, which its own docstring says was retired |

---

## Findings

### TL-01 — Critical — `tools/robotlink.py:21-22` — the radio path is tuned to an address nothing listens on

```python
# zavaz is vevov's relay (channel 4). getez lives on channel 3 and
# belongs to another robot -- never retune it here.
ZAVAZ_CHANNEL = 4
ZAVAZ_GROUP = 10
```

and `open_link()` (`robotlink.py:322-323`) sends `!CG {ZAVAZ_CHANNEL} {ZAVAZ_GROUP}` on every radio open. `.claude/rules/playfield-testing.md` (fleet table, 2026-08-30) has vevov on **37/43**, and this repo's own `tools/field_calibration.json` says `"radio_channel": 37, "radio_group": 43`. The rule file states the consequence: *"Anything still tuned to vevov's old 4/10 now points at nothing."*

**Failure scenario.** `uv run python tools/tour_run.py` → `Cam()` sees the robot → `open_link(radio=True)` handshakes zavaz onto 4/10 → `link.hello()` reads no banner (not fatal by design, `robotlink.py:225-228`) → `tlm.require_stream()` raises `DeadTelemetryError: ... instrument is dead`. The operator debugs telemetry. Every radio consumer inherits it: `tour_run.py:139`, `tour_practice.py:171`, `tour_square.py:55`, `tour_closedloop.py:83`, `tour_watch.py:142`, `pivot_truth.py:78`, `truth_check.py:139`, `turn_sweep.py:108`, and `--radio` in `rotation_check.py`, `otos_levercal.py`, `tour_capture.py`, `arc_capture.py`. `tests/tools/test_robotlink.py:183` asserts the literal `!CG {ZAVAZ_CHANNEL} {ZAVAZ_GROUP}` line, so the test suite pins the stale constant rather than the fleet fact.

**Remedy.** `open_link(robot='vevov', ...)`: derive the pair from the name with `make_deploy.derive_radio_from_name()` (already in this directory, already tested against `("vevov", (37, 43))` in `test_make_deploy_robot_channel.py:170`), honouring the radio-robot-lib config override the same way `make_deploy` does. Delete the hard-coded pair and the "vevov's relay (channel 4)" comment. Note that `fieldlink.FieldLink` already takes `(channel, group)` as arguments — this is the third place the address is chosen (TL-13).

**Dedupe.** Not filed. `grep -rl 'ZAVAZ_CHANNEL\|4/10' clasi/issues` hits only unrelated radio issues; the rule file documents the hazard, not the tool defect. 08-26 review: none.

### TL-02 — Critical — `tools/camlink.py:55,80-96` + `tools/field_calibration.json` + `tools/field_dance.py:77-84` — two calibrations of record for tag 53, and the tools overwrite each other's

`camlink.py:54-57`:
```python
MOUNTS = {
    53: (-3.61, -0.05, 11.8, -math.pi / 2),   # vevov, centre of rotation
```
`camlink.py:80` — `Cam.__init__` calls `self.ensure_registered()`, which `register_tag`s every `MOUNTS` entry; the module docstring (`:10-16`) now correctly says registrations **persist across daemon restarts**, so this write is permanent until something re-registers.

`tools/field_calibration.json` (`_provenance: "MEASURED vevov 2026-09-02"`) records the post-remount lever `"lever_cm": [0.4217, -6.3806]` in the **tag** frame, `"parallax_k": 1.1167`, `"heading_offset_deg": 91.116`, and `field_dance.py:77-83` applies that lever and offset to `r.world.x/y` and `r.yaw_rad` **itself**, i.e. it assumes the daemon serves the raw tag (identity mount). Its `_lever_note` says the raw tag "swings 68 mm across a pivot" — that is the raw tag, not a daemon-corrected centre.

**Failure scenario, both directions.**
- Run any `camproc.Cam` tool once (`tour_run`, `tour_practice`, `pivot_truth`, `turn_sweep`, `tour_watch`, …). The daemon now permanently reports tag 53 as centre-of-rotation using the −3.61 cm lever and yaw+90°. Now run the pre-flight `field_dance.py`: `pose()` adds `HEAD_OFF=91.1°` to an already-corrected heading, so `a[2]` is 91° off; `drive()`'s bearing check (`:150-154`, `abs(dirn) < 25`) fails every drive step with "bearing off +91 deg". The safety check fails on a healthy robot, and the natural "fix" is to re-fit `heading_offset_deg` — the ritual `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` exists to stop.
- The other way: with the daemon holding the identity mount the dance expects, every `Cam.fix()` seed (`tour_run.py:160-163` → `RUN:seedxy`) is computed with a lever that is wrong by the difference between (−3.61, −0.05) and the measured post-remount lever — several cm, rotating with heading — so every pivot draws a hook in the robot's world frame and every camera-scored corner carries it. The memory note `camera-stream-and-telemetry-decode-traps` recorded exactly this clobber on 2026-08-29 (then against −5.34 cm); the plate has since been remounted and the table was not updated.

Neither tool checks what the daemon currently holds (`list_tag_parameters` exists).

**Remedy.** One calibration of record per tag. Either `camlink.MOUNTS` reads `field_calibration.json` (robot → tag, lever converted to the daemon's mount frame, parallax handled by `mount_z`) and `field_dance` stops correcting host-side, or `ensure_registered()` is deleted and every tool reads the daemon's registry and refuses to run if the registered mount disagrees with the JSON. Either way `ensure_registered()`'s docstring ("cheap idempotent insurance … a no-op in the common case") must go — it is an unconditional overwrite.

**Dedupe.** Sprint 027 issue `camlink-mounts-table-is-stale-for-tigez.md` (done) fixed tag 57 and the persistence docstring only; it did not touch 53 and the JSON did not exist yet. Not otherwise filed; the 2026-08-29 clobber lives only in auto-memory.

### TL-03 — Major — `tools/rotation_check.py:105-109`, `tools/truth_check.py:120-124` — ±180° pivots that over-rotate read with the wrong sign

```python
revs = round(commanded / 360.0)
gyro = revs * 360.0 + wrap(after[2] - before[2] - revs * 360.0)
```
For `commanded = ±180`, `round(±0.5)` is **0** (banker's rounding), so the expression is plain `wrap(after − before)`. A physical 183° pivot — over-rotation is the measured norm on this fleet (`WHEELS_X ~+8°/90`, vevov `+0.8°/90`, per the memory notes and `park.py:4-8`) — reads **−177°**; `ratio = gyro / commanded = −0.98`; the printed "mean gyro/commanded" over `PIVOTS = [360, 180, -180]` mixes sign-flipped terms. `truth_check.total_turn()` is the same function and feeds both `gyro` and `wheels`. `pivot_truth.py:104-109` already handles this by choosing the ±360 branch nearest the camera, but only for `abs(commanded) == 180.0` exactly.

**Remedy.** `commanded + wrap(delta - commanded)` — correct for every commanded angle, no `revs`, one line; put it in `field.py` beside `wrap()` and use it in all three tools. Also `pivot_truth.py:117` divides `gyro / camdeg` — `ZeroDivisionError` when the camera saw no rotation, which is precisely the "robot is off" case `.claude/rules/playfield-testing.md` says to check first.

**Dedupe.** Not filed; `tests/tools/test_run_verbs.py` pins only the verb strings, not the arithmetic.

### TL-04 — Major — `tools/robotlink.py:120-123` — the sequenced-verb set does not match the firmware's command table

```python
_V6_VERBS = frozenset((
    'GET', 'SET', 'TLM', 'STOP',
    'MOVE', 'PIVOT', 'WHEELS_V', 'WHEELS_X', 'GO_TO', 'GO_TO_W', 'ARC',
))
```
`src/comms/wire_handler.cpp:314-323` (`kCommandTable`): `GET SET TLM WHEELS_X WHEELS_V MOVE_X MOVE_V GO_TO_R GO_TO_W STOP`. `MOVE`, `PIVOT`, `GO_TO`, `ARC` are not verbs; `MOVE_X`, `MOVE_V`, `GO_TO_R` are missing. `_is_wire()` (`:141-142`) tests the first token against this set, so `link.send('MOVE_X 200 0 150 5000')` goes out with no `#id`, parses as `#0`, and is dropped — the exact mechanism the 45-line comment directly above the set describes. It is latent only because no tool sends v6 motion through `Link` today (`field_dance.py` and `tests/dev/closure.py` use `FieldLink.seqd`, which appends an id unconditionally). `tests/tools/test_robotlink.py:286-303` pins the unsequenced seven and `GET`/`SET`, never the motion verbs.

**Remedy.** Invert the rule: sequenced iff not in the firmware's seven unsequenced exemptions and not cleartext (`RUN:`/`DIAG`). Add a drift test that parses `kCommandTable` out of `wire_handler.cpp` (the pattern `test_wire_constants_drift.py` already uses).

**Dedupe.** Not filed. 08-26 review: none.

### TL-05 — Major — `tools/field.py:42-85` — the geofence exists but nothing calls it (D-08 status: partial)

Sprint 018 ticket 002 added `LIMITS = (67.15, 44.65)`, `MARGIN = 12.0`, `clears_margin(rows)` and `check_path(waypoints)`, pinned by `tests/tools/test_field.py:214-301`. `grep -rn 'check_path\|clears_margin' tools tests` returns only `field.py` and `test_field.py`. The planners the rule file addresses still drive unchecked: `tour_run.place()` (`tour_run.py:99-102`, `RUN:goto`), `reposition.Repositioner.go()` (`reposition.py:65`, `RUN:goto:{x}:{y}` to any caller-supplied point), `tour_closedloop.Robot.goto()` (`:45-47`), `tour_square.py:86`. The recorders (`tour_run`, `tour_watch`, `tour_practice`) never call `clears_margin` on the camera rows they already hold.

A second field definition has appeared since: `tests/host/test_run_tour_programs.py:167-172` — `_FIELD_MM = (600, 400)`, `_MARGIN_MM = 50`, "per the stakeholder 2026-09-01: 120 x 80 cm … Both numbers live here too because this test is what enforces them" — versus `field.py`'s 134.3 × 89.3 cm / 12 cm margin pinned against the rule file. Two field sizes, two margins, both "enforced".

**Remedy.** `Repositioner.go()` and `tour_run.place()` refuse a target that fails `check_path([current, target])`; recorders print `clears_margin` in their score line. Reconcile the two field definitions into `field.py` and have `test_run_tour_programs.py` import them.

**Dedupe.** D-08 (08-26) → sprint 018 issue `geofence-described-in-rules-does-not-exist.md` (done). The functions exist; the wiring the issue's own remedy describes ("a `check_path(waypoints)` the planners call before arming a run") does not. Reported here as the residual, not re-described.

### TL-06 — Major — pose-CSV schema fork: three writers, one positional reader

| writer | header | units |
|---|---|---|
| `tour_capture.py:128-130` | `t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg` | wire (mm, cdeg) |
| `tour_watch.py:212-213` | `t,dev_ms,enc_x_cm,enc_y_cm,enc_h_deg,otos_x_cm,otos_y_cm,otos_h_deg` | cm, deg |
| `tour_practice.py:147-149` | `t,enc_x,enc_y,enc_h,otos_x,otos_y,otos_h,dev_ms,vl_mms,vr_mms` | cm, deg |

`tour_chart.py:107-121` decides the shape by **column count** (`len(pose_all[0]) >= 5`, `>= 8`) and assumes wire units throughout (`MAX_POSE_MM = 2000`, `end_h = pose[-1][3] / 100.0` at `:216`, `oh0 = math.radians(pose[0][3] / 100.0)` at `:185`). A `tour_watch` pose CSV has eight columns, so it is accepted, plotted 10× too small, with heading divided by 100 and the OTOS diamonds landing on the wrong columns — and the title prints a confident "closure N mm". `leg_analysis.py:126-127` hard-codes the `tour_capture` header only. `tlm.py` went to the trouble of binding wire columns **by name** precisely so a shape change is handled; the CSV layer regressed to positions.

**Remedy.** One `tlm.write_pose_csv(stream, path)` writing wire units with the wire's column names, one `tlm.read_pose_csv(path)` that binds by header name and refuses an unknown header; `tour_watch`/`tour_practice` call it; `tour_chart`/`leg_analysis` read through it.

**Dedupe.** Not filed. 08-26 review: none.

### TL-07 — Major — `tools/camproc.py:58,73-76`, `tools/camlink.py:1-8,71` — Q-09 open, and the reason for the subprocess architecture no longer exists

`camproc.py:58`: `_DEFAULT_VENV = '/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'` (Q-09, still present). The class docstring (`:73-76`) says "pyserial and aprilcam do not coexist in one interpreter here"; `camlink.py:1-8` says it "only work[s] under that interpreter". Both are now false: `pyproject.toml:9-12` declares `aprilcam[daemon]` (editable, `../aprilcam`) as a dependency of **this** venv, `field_dance.py:38` imports `aprilcam.mcp.connection` directly under `uv run`, and `uv run python -c "import aprilcam, serial"` succeeds in this worktree (verified 2026-09-02, `.venv/bin/python3`). The subprocess, the reader thread, the `ERR`-line protocol, `APRILTAGS_VENV`, the `--hz` argument that "is ignored", and the second `class Cam` (Q-06) all exist to bridge two interpreters that are now one.

**Remedy.** Minimal: `venv = sys.executable` and delete `_DEFAULT_VENV`/`resolve_venv()`. Better: fold `camlink.Cam.frames()` into `camproc.Cam` as an in-process generator on a thread, delete the subprocess and the line protocol, rename one of the classes. `test_camproc.py:38-53` (two tests) then go with `resolve_venv()`.

**Dedupe.** Q-06 and Q-09 (08-26) both still open; `Q-08` remedy in the same review created the `[tool.ruff]` block — done. No issue file for either.

### TL-08 — Major — `tools/field.py:123-135` — C-16 still open

```python
for tag in order:
    ...
    for i in range(used, len(rows)):          # scans to the END of the run
    ...
    used = besti
```
Unchanged since 08-26. **Scenario.** A `RUN:tour:world` run starts on NE, passes NW at t=5 s (4 cm off), completes the lap, and its closing leg re-approaches NW at t=38 s (1.5 cm off, tour over-closes). NW scores 1.5 cm at index ~760; `used` jumps there; SW, SE, NE each search a handful of tail samples and report tens of cm or `None`. A single good run reads as three bad corners. Also `used = besti` (not `besti + 1`) lets consecutive corners claim the same sample. `test_field.py:139-159` covers only "a later corner cannot reclaim an earlier one's sample" — the docstring's claim, not the reverse.

**Remedy.** Search corner *k* only in `rows[used : first_approach(k+1)]`, where `first_approach` is the first index after `used` at which the robot comes within, say, 15 cm of the next dot; or solve the four corners as one monotone assignment. Add the scenario above as a test.

**Dedupe.** C-16 (08-26), triage row 16 "tooling hygiene… `score_corners` window", Low. Not filed as an issue; still open.

### TL-09 — Major — `tools/truth_check.py:32-69` — a superseded tool that fails as "camera cannot see tag 53"

```python
CAM_ENV = dict(os.environ, APRILCAM_DAEMON_HOST='127.0.0.1', APRILCAM_DAEMON_PORT='5280')
...
out = subprocess.run(['aprilcam', 'tool', 'get_tags', f'source_id={cam}'], ...)
for t in d.get('tags', []):
    if t['id'] == tag:
        yaws.append(t['orientation_yaw'])
        w = t.get('world_xy') or [None, None]
```
Five subprocess launches per fix, a hard-coded daemon port, and v1-shaped JSON keys (`id`, `orientation_yaw`, `world_xy`). The v2 client every other tool uses exposes `t.tag.number`, `t.yaw_rad`, `t.world.x` (`camlink.py:111-117`, `field_dance.py:64,76-78`). Against the current daemon `cam_yaw()` returns `None` and `main()` exits with "camera cannot see tag 53 -- is the robot inside the field of view?" — sending the operator to the lights and the camera. `pivot_truth.py` measures the same thing through `camproc.Cam`. `tools/DESIGN.md` lists both as the ground-truth pair. The threaded `sampler` (`:165-171`, three `noqa: B023`) is the same design `pivot_truth._yaw_mark` replaced.

**Remedy.** Delete `truth_check.py` (and its four tests in `test_run_verbs.py`), or retarget its `cam_read` onto `camproc.Cam` — at which point it is `pivot_truth.py`. Add a check to whichever survives that a `None` fix distinguishes "daemon unreachable" from "tag not in frame" (`camproc` already does; `truth_check` cannot).

**Dedupe.** Not filed. 08-26 Q-08 mentioned the `sampler(prev=…)` default only.

### TL-10 — Minor — `tools/leg_analysis.py:237-243` — a heading miss is reported as a distance verdict

```python
if abs(distance_error_cm) <= tol and abs(heading_error_deg) <= tol_h:
    classification = ON_TARGET
elif distance_error_cm > 0:
    classification = STRAIGHT_OVERRUN
else:
    classification = MID_LEG_TRUNCATION
```
`believed = (100.5 cm, 30°)` vs `commanded = (100 cm, 0°)` → `STRAIGHT_OVERRUN` with `distance_error_cm = +0.5`. The docstring says the two errors are reported separately so the residual signature is visible, but the verdict column — the one the table sorts on — still collapses it. Add `HEADING_MISS` for "distance within tolerance, heading not". (The at-rest heading is the end-pose heading vs the commanded *bearing*; documented at `:77-86`, acceptable.)

**Dedupe.** Not filed.

### TL-11 — Minor — `tools/field_calibration.json` — the +90° convention stored as a fitted number

`"heading_offset_deg": 91.116…`, `_heading_note`: *"Fitted from a translation probe, not assumed: the two candidate conventions differ by 180 deg…"*. `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` uses this literal value as its counter-example: *"A probe move that comes back 'robot heading = tag yaw + 91.12°' has not discovered anything: it has re-measured the convention and added 1.12° of probe noise."* The number is fine; the representation invites the next session to re-fit it, and `field_dance.py:13-15` calls the convention "calibration … re-measure it after any tag remount or camera move". Store `convention_deg: 90` (fixed, cite the rule) and `plate_skew_deg: 1.12` (measured, cite the capture); `HEAD_OFF` is their sum.

**Dedupe.** The rule file itself; no issue.

### TL-12 — Minor — four `wrap()` implementations survive the consolidation

`field.py:88-94` (loop, range `(-180, 180]`); `leg_analysis.py:181-183` `_wrap_deg` = `(d + 180) % 360 - 180` (range `[-180, 180)` — opposite closed end); `field_dance.py:84,130,131,151,167` the same expression inline five times; `otos_levercal.py:155` `atan2(sin, cos)`. `park.py:38-42` carries a comment explaining why not to add a ninth. Import `field.wrap` in all three.

**Dedupe.** Sprint 005 `tools-link-layer-consolidation` (done) removed eight; these are the survivors/re-growth.

### TL-13 — Minor — the link layer is written four times, with three relay addresses

`robotlink.Link` (serial + zavaz handshake, sequence ids, `send_until`), `fieldlink.FieldLink` (TCP to `'torture':8760`, its own `seqd`, one-letter `s` receiver, semicolon-joined statements), `wire_acceptance.RadioLink` (TCP to `'192.168.1.12':8760`, `!CG {channel} 10` — group hard-coded at `:158`) + `UsbLink` + `GautiLink`, `otos_bench.Rig`. `fieldlink.read` and `wire_acceptance.RadioLink.read` are the same 14 lines. `FieldLink` skips `!ECHO OFF`/`!MODE RAW250`/`!P 7` that `robotlink` sends — whichever is right, one is wrong. Consolidate into `tools/link.py`: `SerialLink`, `RelayLink(host, port, channel, group)`, one `Sequencer` (the `robotlink` one — it is the tested one).

**Dedupe.** Not filed; the 08-26 review predates `fieldlink.py` (2026-09-02).

### TL-14 — Minor — two repositioning loops, one with the bug the other documents

`tour_run.place()` (`:80-123`): *"POSITION first, then heading, and never the other way round … a loop that re-checks both and picks one will answer a good heading with another goto and undo it. Two runs started facing 98 and 94 degrees instead of west that way."* `reposition.Repositioner.go()` (`:47-76`) is exactly that loop (goto if `derr > tol`, then face if `herr > tol`, repeat, tolerances 3 cm/5°). `tour_practice.py` uses `Repositioner`; `tour_run.py` uses `place()`. Keep `place()`'s ordering, in `reposition.py`.

**Dedupe.** Not filed.

### TL-15 — Minor — dead code in the live tool set

- `tour_watch.py:170-179`: `vel` is never populated ("not currently plumbed"), while `row['vl']` is decoded two lines later; the chart draws "no wheel-speed samples".
- `tour_practice.wheel_speeds()` (`:81-109`) — "not called anywhere in this file — kept for reference only" (`:16-18`); `practice_chart.py:51-62` differencing fallback and `TRACK_CM = 12.0` in both files.
- `tour_square.py`, `tour_closedloop.py` — DESIGN.md: "earlier variants kept for reference"; still executable, still `open_link(radio=True)` (TL-01), `tour_closedloop.py:30` hard-codes the Shelly URL.
- `truth_check.py` (TL-09); `camproc.py`'s `--hz` plumbing ("ignored", `camlink.py:151-152`).

`tests/DESIGN.md` already states the right policy for `tests/dev/`: "deleted rather than left to rot". Apply it to `tools/`, or move reference scripts under `captures/`.

**Dedupe.** Not filed.

### TL-16 — Minor — `tools/DESIGN.md` is a sprint log, not an inventory

- No entry for `field.py`, `camproc.py`, `fieldlink.py`, `field_dance.py`, `field_calibration.json`, `park.py`, `arc_capture.py`, `wire_acceptance.py`, `blocks_env.py`, `blocks_toolbox.py`, `publish_extension.py` (grep count 0 for each); `tlm.py` appears only inside the `leg_analysis` bullet.
- `tlm.py:70-72` cites "tools/DESIGN.md's 'Telemetry (tlm.py)' section" — no such heading exists.
- "Known limitation — the telemetry gap" says `otos_bench.py`'s numeric `RUN:<n>` is "a silent no-op" because `testrig.ts` "stores the argument, not the name". `test/testrig.ts:44-56` parses the number **from `name`** and dispatches on it — the console works; the paragraph then declares itself stale in a "Sprint 011 update" without being rewritten.
- Link-layer paragraph: "channel 4, group 10 — vevov's assignment" (TL-01).
- Status header: "Last reviewed 2026-08-24".

**Dedupe.** D-03 (08-26, stale status headers) — the same shape, one sprint later.

### TL-17 — Minor — `tools/tour_chart.py:179-192` — `--meta` has no writer and an undocumented unit

`sw = m.get('start_world_cm')`; `wh0 = sw[2]` is used as **radians** (`rot = wh0 - oh0` with `oh0 = math.radians(...)`). The only file in the repo that writes `start_world_cm` is `captures/tour-20260828/tour_orange.py` (yaw in rad: `[50.9, 30.3, 3.155]`). No `tools/` script writes it; every `camproc` sample is `yaw_deg`. A future writer using the tools' own unit gets a 57× rotation and a plausible-looking overlay. Either write the meta from `tour_run`/`tour_capture` (in one documented unit) or state the schema in the `--meta` help.

**Dedupe.** Not filed.

### TL-18 — Minor — `tests/tools/test_make_deploy_robot_channel.py` asserts vevov's channel is 4 by name, 37 by table

`:99` `test_vevov_build_carries_channel_4`, `:113-116` "`main()`'s own `--robot` default is `DEFAULT_ROBOT` ('vevov'), whose configured channel is 4 -- the same value radio_transport.h already carries"; `:170` `("vevov", (37, 43))`. The tests pass because they write their own synthetic config, so the names now teach the wrong fleet fact; `make_deploy.py:24` "build (vevov, ch 4)" and `:41` "vevov's own channel, 4" say the same. Rename/reword to "the configured channel, whatever it is".

**Dedupe.** Not filed.

### TL-19 — Minor — what the host harness does not prove

a. **C++11 gate coverage.** `test_cxx11_syntax_gate.py:72-103` syntax-checks 4 production TUs + 5 header wrappers. Compiled by nothing on the host: `protocol.cpp`, `radio_transport.cpp`, `serial_transport.cpp`, `nezha_port.cpp`, `otos_port.cpp`, `vfp_guard.cpp` (`#include "pxt.h"` at `:5`), `shims.cpp`. Sprint 027's single-serial-producer work landed in `protocol.cpp`; only the hex checkpoint gates it.
b. **Inconsistent include policy.** The C++11 gate compiles production sources with `-I src` (`:119`); `compile_shared_lib()` deliberately gives production sources **no** `-I` (`test_kernel_harness.py:98-105`) to match PXT. `test_include_paths_match_target.py` covers the tree separately, so this is a consistency nit, not a hole.
c. **Mirrors under test.** `test_continuous_drive_command_looks_active.py:_command_looks_active` and `test_continuous_mode_odometry.py:_ChordOdometry` ("kept deliberately identical to that function's math") re-implement `shims.cpp` in Python and test the Python. Both docstrings say so plainly ("WHAT THIS FILE CANNOT PROVE"); recorded here as the honest scope, not a defect.
d. **Vacuous.** `test_wire_grammar.py:1331` `test_kernel_harness_still_importable` — an `import` and no assertion.
e. **Fixture duplication.** Eleven files (`test_motion_engine_*.py` × 9, `test_goto_block_regression.py`, `test_stop_move_zeros_continuous_drive.py`) each define a session-scoped `motion_lib` compiling the identical `diffdrive.cpp + motion_engine.cpp + motion_engine_shim.cpp` list — eleven compiles per run, no `conftest.py`, F811 silenced repo-wide (`pyproject.toml`). One `tests/host/conftest.py` fixture would cut most of the 149 s.
f. **tsc gate = environment precondition.** `test_typescript_typecheck.py:68` asserts `node_modules/.bin/tsc` exists; in a fresh worktree (this one) that is the suite's only failure. Skip with a reason that names `npm ci`, or make `npm ci` part of the harness setup.
g. **Unpinned mirror.** `test_travel_calib_drift.py` compares `motion_engine.h` with `tour_chart.py` only; `tests/system/run_tour.py:72` `TRAVEL_CALIB = 0.7878` is a third copy.
h. **Lint not gated.** Q-08's `[tool.ruff.lint]` exists; nothing in `tests/` or CI runs `ruff`. Today's 5 findings (`tests/dev/closure.py:32` B007, `tests/dev/sweep_tcp.py:12` F401, `tests/system/run_tour.py:21,31` F401 ×2, `tests/system/tourfile.py:124` B904) sit outside the two pytest roots.

**Dedupe.** (a) is `host-tests-compile-newer-standard-than-target.md` (sprint 008, done — the gate is the "partial down payment" its own docstring names). (h) Q-08 done; gating not filed.

### TL-20 — Suggestion — `tools/tlm.py:300`, `tools/turn_sweep.py:128,136`

`duty_pct()` is documented as "the one place that scale is undone", has two tests, and no caller; `turn_sweep.py` reads `TRN:` peak duty and applies `/100` and `>= 9900` inline. Either route `turn_sweep` through it or drop it.

### TL-21 — Suggestion — `tools/field_dance.py:51-56,87-98`

`settle()`: `sp = getattr(r, 'speed', None) or 0.0`; if the client record lacks `speed` (the v2 proto has `optional double speed = 5`, `aprilcam_v2.proto:547`; the Python client was not checked here — UNVERIFIED), `still` increments on every detection and `settle()` returns after four reads (~0.25 s) while the robot is still moving, so `pose()` samples mid-turn. Make a missing `speed` raise. `_daemon()` locates the connection manager by reflection (`isinstance(o, type) and hasattr(o, 'resolve')`) — name the class.

### TL-22 — Suggestion — `tools/fieldlink.py:45-54`

`seqd()` matches `^(ack|err)\s+N` and returns the line either way; `field_dance.py:115,127,142` discard the return, so `SET pivot_overrun 3.7` being refused (`err N`) is invisible and the dance runs on fleet defaults.

### TL-23 — Suggestion — `tools/robotlink.py:34-72`

`probe_port()` → 8 × `_probe_once()` × `timeout=30` + 0.8 s sleeps ≈ 4 minutes before "zavaz relay not found".

### TL-24 — Suggestion — `tools/tour_chart.py:118,175-176`

Pose time is device-clock relative to the first device sample (`(r[1] - t0d) / 1000`); camera rows are host-clock relative to `t0`; both are cut at the same `t_cut`.

### TL-25 — Suggestion — `tools/rotation_check.py:122-123`

`print(f"firmware rotationScrub is 1.040; this run implies {1.040 * mean:.3f}")` — the module docstring (`:9-13`) says 1.040 was retired for `rotationalSlip 0.952`. The printed conclusion is scaled by the retired constant.

---

## Prior findings — status

| Prior ID | Claim | Status now | Evidence |
|---|---|---|---|
| D-05 | `travelCalib` 0.8102 mirrored in `tour_watch`/`tour_chart` | **Fixed** | `tour_chart.py:63` default `0.7878` == `motion_engine.h:667`; `tour_watch.py:170-179` velocity branch removed; `tests/tools/test_travel_calib_drift.py` pins the pair. Residual: `tests/system/run_tour.py:72` third copy unpinned (TL-19g). |
| D-08 | Geofence does not exist | **Partial** | `field.py:42-85` has `LIMITS/MARGIN/clears_margin/check_path` + tests; zero callers in `tools/`; second field definition in `tests/host/test_run_tour_programs.py:171` (TL-05). |
| C-16 | `score_corners` greedy window | **Open** | `field.py:123-135` unchanged (TL-08). |
| Q-06 | Two `Cam` classes | **Open** | `camlink.py:71`, `camproc.py:72` (TL-07). |
| Q-08 | No ruff config | **Fixed** | `pyproject.toml` `[tool.ruff.lint] select = ["F","E9","B"]`, `tests/** = ["F811"]`; 5 residual findings outside `tools/`/`tests/tools`; not gated (TL-19h). |
| Q-09 | Absolute venv path | **Open** | `camproc.py:58` (TL-07 — and the premise for it is gone). |
| `camlink-mounts-table-is-stale-for-tigez` (sprint 027, done) | tag 57 missing; "not persisted" docstring | **Fixed as filed** | `camlink.py:57` tag 57; `:10-24` persistence docstring. Tag 53 has since gone stale the same way (TL-02). |
| `build-checkpoint-rejects-correct-incremental-builds` (high, open) | TU-presence check | Cross-referenced, not re-reported | `make_deploy.py:1026-1041` unchanged. |
| `calibration-skill-emits-a-paste-able-makecode-block`, `measure-vevov-s-true-full-duty-velocity`, `radio-telemetry-loss-is-wifi-interference-at-the-relay-site` | — | Not touched by anything here | — |

## What held up

- **`tools/tlm.py`.** Column binding by name from the last `thdr`; 7-bit `seq` gap math with the wrap case pinned (`test_tlm.py:286-306`); orphan/malformed counted, never raised; `require_stream`/`write_tlm_csv`/`read_meta_sidecar` fail-loud trio; the unit comment (`:252-271`) is correct against `src/shims.cpp:938` (`appliedDutyLeft * 100.0f` on an already-percent value) and the tests use real captured frames plus the shared `golden_telemetry` fixture, so emitter and parser are pinned to one source.
- **`OCAL` units are consistent everywhere.** `test/test.ts:274-284` emits `OCAL:<tag>:<x 0.01cm>:<y 0.01cm>:<h 0.01deg>`; `pivot_truth/rotation_check/truth_check` divide by 10 (→ mm, as their docstrings say) and `tour_square/tour_closedloop` by 100 (→ cm). Both right.
- **`robotlink.Link` sequencing.** `HELLO` unsequenced and a session reset (`hello()` sets `_seq = 0` whether or not the banner arrives); `send_until()` formats once so a resend reuses its id; the seven unsequenced verbs match `wire_handler.cpp:464-562`; `sync_seq`'s `nack N → N-1` is correct and tested. (The sequenced set is TL-04.)
- **`camproc.Cam`.** `ERR` invalidates `latest` before and after the sampling window; `stale_after` on consecutive `NOTAG`; `_handle_line` is testable without a process. `Cam(respawn=True)` records `deaths` and `tour_square` flags scores across them.
- **`park.py`.** Pure geometry; `test_park.py` tests the actual claim (least rotation beats shortest path under a slip model), the sub-tolerance-bearing trap (`:155-173`), and the "standing on the target" regression from hardware.
- **`otos_levercal.py`.** The fit is linear in `(cx, cy, ox, oy)` with gyro headings, `p0` excluded with a cited measurement (`:112-119`), residual printed, `--verify` interpreted as residual not arm.
- **`make_deploy.py`.** Geometry bake opt-in with a survey-backed reason (`:786-801`); every regex substitution asserts `n == 1`; `repr(float(v))` keeps the `.0` so `128f` cannot be emitted; TU-presence phrased as "each expected file found" so an empty log cannot pass; `PXT_COMPILE_SWITCHES` set unconditionally.
- **`field.check_path()`** walks the segments, not just the endpoints, and `test_field.py:290-301` proves it.
- **`test_include_paths_match_target.py`** covers every `#include` under `src/` with no compiler, including the pxt.h-bound files the host suite cannot compile — the right shape for the gap in TL-19a.
- **`wire_acceptance.py`** distinguishes PASS/FAIL/BLOCKED with distinct exit codes, tracks the sequence counter from what the robot says (`next_id`), and runs motion before the latching `ESTOP` cases with the reason written down.

## Comment / docstring hygiene — the worst blocks, one-line replacements

The standard (`guidelines.md` §6): a comment states what the code cannot — a unit, a sign, an invariant, a measured fact, a hazard. Sprint/ticket numbers and "used to be" belong in `git log`.

| # | Block | Replace with |
|---|---|---|
| 1 | `robotlink.py:75-119` — 45 lines above `_V6_VERBS`: pre-sprint-024 capture narrative, "72 keepalive acks", ticket numbers | `# Verbs the firmware sequences (wire_handler.cpp kCommandTable). An unsequenced line parses as #0 and is dropped; a verb listed here that the robot does NOT sequence burns an id and stalls the stream.` |
| 2 | `robotlink.py:157-179` — `sync_seq` docstring, 23 lines of sprint-024 history | `"""Set _seq from a live reply: `ack N` → N, `nack N` → N-1 ("send me N next"). Not used by open_link(); nothing streams passively to read."""` |
| 3 | `robotlink.py:197-228` — `hello` docstring, 30 lines | `"""Session RESET, not a liveness probe: HELLO sets the robot to expectedNext_=1 and answers the boot banner. _seq becomes 0 whether or not the banner is read."""` |
| 4 | `tlm.py:1-73` — module docstring: which sprint retrofitted which consumer, "No consumer is retrofitted here (that is sprint 005 ticket 002's job)" | `"""v6 telemetry parser. `thdr` binds columns by name; `t` rows decode against the last header. Wire units: x/y/ox/oy mm; h/oh centideg; vl/vr mm/s; dutl/dutr percent×100."""` |
| 5 | `camproc.py:1-44` — R-24/R-26 narrative, "seven near-identical copies", "silent 2-way fork" | `"""Runs camlink.py as a subprocess and parses its `yaw x y` lines. latest/fix() → (x_cm, y_cm, yaw_deg), timestamped samples (t, x, y, yaw). An ERR line invalidates latest."""` (or delete with TL-07) |
| 6 | `camlink.py:82-91` — `ensure_registered` docstring "Cheap idempotent insurance … a no-op in the common case" | `"""Overwrites the daemon's PERSISTED mount for every tag in MOUNTS. This table must be the calibration of record (see field_calibration.json) or this call must go."""` — the current text is wrong (TL-02) |
| 7 | `leg_analysis.py:1-93` — sprint 011 ticket 002, "the same shape make_deploy.py's classify_attempt() established — sprint 008 precedent" | `"""Per-leg believed-vs-commanded classification of a tour_capture pose CSV. Legs split on telemetry holds between moves; OTOS columns are cross-checked for a frozen cache. Heading error = end-pose heading − bearing to target."""` |
| 8 | `test_kernel_harness.py:68-86` — `compile_shared_lib` docstring's sprint-017-ticket-009 paragraph | `Production src/ files compile with NO -I (as PXT does); tests/host shims get include_dirs.` |
| 9 | `test_cxx11_syntax_gate.py:1-53` — history of sprint 004 tickets 005/007 and 006 | `Both real targets compile at -std=c++11; the host suite uses c++20. Syntax-check the host-portable sources at c++11 so a C++14+ construct fails here, not at the hex checkpoint.` |
| 10 | `tour_capture.py:9-14`, `test_tour_capture.py:5-14` — "Sprint 005 ticket 006 retargeted five tools … but did not reach this one" | `RUN verbs are string-keyed (test.ts onRun); a numeric RUN:<n> is a silent no-op.` |
| 11 | `make_deploy.py:85-121` — module-docstring copy of DESIGN.md's "Build checkpoint triage" | `Build verdicts: see classify_attempt() and tools/DESIGN.md "Build checkpoint triage".` |
| 12 | `arc_capture.py:157-167` — 11 lines justifying a filter for lines that "can no longer arrive" | `# drop any ack/nack reply sharing the link` |
| 13 | `robotlink.py:19-20` — "zavaz is vevov's relay (channel 4)" | Delete with TL-01; the address comes from the name. |
