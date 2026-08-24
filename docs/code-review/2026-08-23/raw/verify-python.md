# Adversarial verification — python-tools.md findings

Verifier: independent re-derivation from source, 2026-08-23. Mandate was
to refute; every claim below was re-checked against the code (and, for
PY-02, by re-running the import probe). Verdicts use the
`docs/code-review/guidelines.md` severity rubric.

| ID | Verdict | Justification (one line) |
|----|---------|--------------------------|
| PY-01 | CONFIRMED | `main.ts:166-167` routes RUN by exact name; `test/test.ts` registers only 11 named handlers (no numeric, no `pivot`, no `TRN:` emitter anywhere in `test/` or `src/`), so `RUN:10`/`RUN:2/4/5/8/14`/`RUN:57xxx/58xxx` match nothing; DESIGN.md:76-82 is the wrong side. |
| PY-02 | CONFIRMED | Re-ran the probe: `AprilTags/.venv/bin/python3 -c "import aprilcam"` → `ModuleNotFoundError`; pipx venv imports fine; six tools hardcode the dead path, all spawn with `stderr=DEVNULL`, and `tour_watch.py:180-182` checks `cam.err` once at +1.5 s. |
| PY-03 | CONFIRMED | All three drifts re-derived on both sides: shim 337-338 `wedgeLeft/Right` vs `shims.cpp:688-689` `wedgeSuspectLeft/Right`; shim 182-191 `kernel.drive()` vs `shims.cpp:285` `engine.wheelsV()` whose first act is `cancelMove()` (`motion_engine.cpp:21`); shim 261 truncates vs `shims.cpp:832` `std::lround`. |
| PY-04 | CONFIRMED | `tour_run.py:64` drops `ERR` lines (camlink emits them at `camlink.py:112`); `latest` set at :71 is never invalidated and `fix()` (:74-85) has no timestamp check; `place()` seeds `RUN:seedxy` from it at :179/:191; `tour_square.py:40-66` has the respawn+`deaths` machinery `tour_run` lacks. |
| PY-05 | CONFIRMED | Spot checks pass: `tour_run.py:71` `latest=(x,y,yaw)` vs `tour_practice.py:84` `latest=(yaw,x,y)` with `reposition.py:45`'s compensating `med(1),med(2),med(0)`; scorer divergence real — `tour_practice.py:157-176` scores every corner (printed `{t} {sc[t]:.1f}cm` at :261) while `practice_chart.py:84-105` refuses gap-adjacent corners (`unobserved` at :186). |
| PY-06 (minor, spot) | CONFIRMED | Docstring (`make_deploy.py:10-14`) claims "nothing left to forget to copy" but `sync()`'s `endswith('test.ts')` filter (:60-61) excludes `test/testrig.ts` (ends `…trig.ts`) and sets `testFiles=[]` (:69) — testrig is neither copied nor visible to the deploy build. |
| PY-08 (minor, spot) | CONFIRMED | `truth_check.py:183` (`gyro / cam`) and `pivot_truth.py:140` (`gyro / camdeg`) divide by camera-measured rotation unguarded (0.0 float division raises `ZeroDivisionError`); `pivot_truth.py:157` applies `abs(r[1]) > 30` only to the summary, exactly as claimed. |

No verdict is REFUTED, DOWNGRADE, UPGRADE, or UNVERIFIABLE. Two small
factual corrections that do not change any verdict are recorded below.

---

## Notes

### PY-01 — numeric RUN vocabulary is dead (CONFIRMED)

Attempted refutations, all failed:

1. **"Maybe a numeric-compat path survives in the wire layer."** The
   cleartext carve-out does survive — `protocol.cpp:228-234` detects the
   literal `RUN:` prefix and `handleRun()` (:106-152) forwards the
   payload text verbatim to MessageBus. But `protocol.cpp:112-113` is
   explicit that "the TS layer owns the vocabulary", and
   `main.ts:157-172`'s dispatcher matches `runNames[i] == name` exactly.
   So `RUN:10` is *transported* fine and then dispatched to a handler
   named `"10"` — which does not exist.
2. **"Maybe test.ts has a catch-all."** It does not. Full `onRun()`
   inventory in `test/test.ts`: `tour`(:307), `straight`(:317),
   `cal`(:321), `fix`(:325), `arm`(:329), `probe`(:333), `gap`(:338),
   `seed`(:342), `seedxy`(:358), `goto`(:367), `face`(:384). No
   `onRunCommand` in test.ts; no handler named "pivot"; no numeric name.
3. **"Maybe testrig.ts catches it."** `testrig.ts:47` does register
   `onRunCommand`, but it stores the *argument* (`n = runArg(0)`), not
   the name — for `RUN:10` the name is "10" and there is no argument,
   so `rigPending = 0` and `rigExec(0)` matches no branch. Even on the
   rig build (which is broken and not deployed anyway), the numeric
   verbs do nothing.
4. **"Maybe TRN: is still emitted."** `grep TRN` across `test/` and
   `src/` returns nothing. `turn_sweep.py:102`'s `until='TRN:'` wait can
   never be satisfied; the per-turn `budget` (:101) confirms the
   48-dead-waits arithmetic.
5. **Per-tool checks:** `rotation_check.py:30` `PIVOTS=[(2,360),(4,180),
   (5,-180)]`, `:36` `RUN:10`, skip messages at `:84`/`:93` ("no fix --
   skipping") — as described. `truth_check.py:31`/`pivot_truth.py:73`
   `PIVOT_VERB={180:4,-180:5,360:2}`; in truth_check every rep dies even
   *earlier* than the review states — `otos_fix` (RUN:10) fails before
   the pivot, so "lost a reading before the pivot -- skipping" (:144).
   `otos_levercal.py:87-91` fails loudly ("robot never acknowledged
   RUN:8"), matching the review's concession. `tour_capture.py:30`
   `--run type=int default=1` → `RUN:1`, dead; its `DIAG` poll (:59-60)
   goes to the v6 stack, which "has no DIAG verb at all"
   (`wire_adapter.cpp:197`) — nothing feeds the `vel` CSV.
6. **DESIGN.md verdict:** `tools/DESIGN.md:76-82` says "The `RUN:`
   command path … still work[s]". The *transport* path works; the
   numeric *vocabulary* these five tools speak has no registered
   handler, so for them the claim is false. The code is the correct
   side; the document is wrong — exactly as the finding states.

Severity Major is right: user-visible misbehavior with a demonstrated
scenario in every tool.

### PY-02 — dead camlink venv (CONFIRMED, one count nit)

- Re-ran the probe (read-only):
  `/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3 -c
  "import aprilcam"` → `ModuleNotFoundError: No module named
  'aprilcam'`. The pipx interpreter
  (`/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python`)
  imports it from `/Volumes/Proj/proj/RobotProjects/aprilcam/src/`.
- Stale constant verified at all six cited sites: `tour_watch.py:31`,
  `tour_practice.py:32`, `pivot_truth.py:28` (+ docstring :14-15
  instructing use of that venv), `turn_sweep.py:31`, `tour_square.py:20`,
  `tour_closedloop.py:29`. Correct value: `tour_run.py:31` and
  `camlink.py:4` (docstring).
- Failure mode verified: every spawn uses `stderr=subprocess.DEVNULL`
  (tour_watch:58, tour_practice:54, turn_sweep:54, tour_closedloop:51,
  tour_run:51, pivot_truth:42). An interpreter that dies on import
  prints only a traceback to the discarded stderr — camlink's `ERR`
  line (`camlink.py:112`) is printed by code that never runs. So
  `tour_watch.Cam.run()` (:62-68) ends at EOF with `err` still `None`;
  `main()` checks `cam.err` exactly once after `time.sleep(1.5)`
  (:180-182) and then watches forever with zero camera samples.
  `tour_practice.py:65-69` polls 15 s and aborts via :216-217 with the
  misleading `camera not usable: no tag`. All as claimed.
- **Nit (not verdict-changing):** the prose says "six copies of the
  `VENV` constant, two values" — there are seven copies across two
  values (six stale + `tour_run.py`'s correct one). The finding's own
  File: line lists the sites correctly.

### PY-03 — test-double drift (CONFIRMED on all three)

This one got the most adversarial attention, since a false positive
here would defame a healthy harness. All three sub-claims hold.

1. **Wedge ordinals 6/7.** Both field families exist on the kernel
   Output struct (`diffdrive.h:147-148`: `wedgeLeft/wedgeRight` and
   `wedgeSuspectLeft/wedgeSuspectRight`), so this is not a compile-time
   impossibility — the double compiles while reading the *other* pair.
   Production `shims.cpp:688-689` → `wedgeSuspectLeft/Right`; double
   `wire_motion_verb_shim.cpp:337-338` → `wedgeLeft/Right`.
   `wire_adapter.cpp:138-139` names ordinals 6/7 `kDiagWedgeLeft/Right`
   and `status()` folds them into the STATUS `wedge` field (:217-227)
   and flag bits (:243-244). Coverage claim also verified: `wedge`
   appears in the Python suites only in `test_wire_grammar.py` /
   `test_wire_reliability.py`, which link the *mock adapter* shim with
   canned booleans; `test_wire_motion_verbs.py` (the WaHandle suite)
   never touches wedge. The divergence is real and untestable-by-
   accident, exactly as reported.
2. **`setWheelsTimed` bypasses the engine.** Production
   (`shims.cpp:280-287`) calls `r.engine.wheelsV(...)`;
   `MotionEngine::wheelsV()`'s first statement is `cancelMove()`
   (`motion_engine.cpp:20-21`, comment cites motion-api.md S6). The
   double (`wire_motion_verb_shim.cpp:182-191`) computes the same
   velocity/twist split but calls `kernel.drive()` directly — no
   `cancelMove()`. The dispatch chain is live: `WireAdapter::onWheelsV`
   → `setWheelsTimed` (`wire_adapter.cpp:257`), and the WaHandle owns a
   real `engine` member the double already uses for `engineWheelsX`
   (:275) — so routing through it is trivially possible, which defeats
   any "the double can't reach an engine" excuse. The comment at
   :184 ("Mirrors shims.cpp's real setWheelsTimed() exactly") is
   verified inaccurate.
3. **`getConfigValue` truncate vs round.** Double:
   `return static_cast<int>(v * 1000.0f);`
   (`wire_motion_verb_shim.cpp:261`) — float multiply, truncate.
   Production: `return static_cast<int>(std::lround(v * 1000.0));`
   (`shims.cpp:832`) — double multiply, round. For v=2.3f:
   2.3f×1000.0f ≈ 2299.9995 → 2299 (double's path) vs
   lround(2299.99995…) = 2300 (production). Off-by-one, harness only.

Severity Major (harness-fidelity landmine, "test that can't fail")
stands.

### PY-04 — tour_run swallows ERR / stale re-seed (CONFIRMED)

Read loop traced: `Cam.run()` (`tour_run.py:61-72`) —
`if line in ('NOTAG', '') or line.startswith('ERR'): continue`. There
is no `err` attribute on this class at all, so nothing downstream could
check one. camlink really does emit the distinguishing line
(`camlink.py:111-113`: `except CamDown as e: print(f'ERR {e}')`), and
`tour_run` really does discard it.

- *Startup path:* constructor waits 15 s for `latest` (:57-59); with
  camlink dead, `main()` hits `raise SystemExit('camera cannot see the
  robot')` (:217-218) — the exact misdiagnosis quoted.
- *Stale-seed path:* `latest` is assigned at :71 and never cleared;
  `fix()` (:74-85) reads it 8× at 60 ms spacing with **no timestamp
  check anywhere in the file** (timestamps exist only in `samples`,
  which `fix()` ignores); `run()` returning on EOF ends sampling with
  no respawn. `place()` then sends
  `RUN:seedxy:{p[0]}:{p[1]}:{p[2]}` (:179, :191) from that frozen
  median. `tour_square.py:40-66` (the "kept for reference" file)
  contains the respawn + `deaths` bookkeeping and the measured phantom
  53/69 cm comment, confirming both the field reality and the
  fix-never-propagated claim.

Considered an upgrade to Critical ("lose or corrupt state" — the tool
actively seeds a false world frame into the robot). Declined: the
corruption is a recoverable pose estimate on a bench tool, not firmware
state, hardware damage, or a safety bypass. Major is the right box.

### PY-05 — copy-paste field (CONFIRMED via spot checks)

- **Tuple orders:** `tour_run.py:71` `self.latest = (x, y, yaw)`;
  `tour_practice.py:84` `self.latest = (yaw, x, y)`. And
  `reposition.py:44-45`: `return med(1), med(2), med(0)` — the silent
  compensating transpose, exactly as described. Bonus trap verified
  too: `CamProc.read(self, tag=53)` (`tour_practice.py:87-89`) ignores
  `tag` entirely.
- **Diverging corner scorers:** `tour_practice.score()`
  (:157-176) scores every corner unconditionally and `main()` prints
  `f'{t} {sc[t]:.1f}cm'` (:261); `practice_chart.score()` (:84-105)
  computes tracking gaps (:85) and refuses gap-adjacent corners
  (:96-97, `None`), rendered as `unobserved` (:186). Same run, two
  verdicts — the console/chart contradiction follows directly.
- **Inventory sanity check:** `def wrap`/`def unwrap` found in exactly
  the 8 cited files (tour_run, practice_chart, reposition, truth_check,
  pivot_truth, turn_sweep, tour_closedloop, rotation_check). The VENV
  copies were independently confirmed under PY-02.

Spot checks pass with line-number precision; the full inventory stands.

### Minor spot checks

- **PY-06 (CONFIRMED):** `make_deploy.py:10-14` promises "there is
  nothing left to forget to copy," but `sync()` promotes only
  `testFiles` entries `endswith('test.ts')` (:60-61) —
  `'test/testrig.ts'` ends in `trig.ts` and does not match — copies
  only `files + promoted` (:62-66), and writes `testFiles = []` (:69).
  `pxt.json:34-37` confirms `testFiles` is
  `['test/test.ts', 'test/testrig.ts']`. The deploy tree neither
  contains nor type-checks testrig.ts; the docstring's guarantee is
  false. Minor (comment accuracy over a currently-load-bearing
  exclusion) is the right severity.
- **PY-08 (CONFIRMED):** `truth_check.py:183` prints `gyro / cam`
  (`cam = cam_total[0]`, a camera-integrated float that is exactly 0.0
  if the sampler saw nothing; :188's summary `g / c` shares the
  hazard). `pivot_truth.py:140` prints `gyro / camdeg` unguarded, while
  :157 guards the *summary* with `abs(r[1]) > 30` — precisely the
  asymmetry the finding describes. Python raises `ZeroDivisionError`
  for `x / 0.0` on floats, so the crash-after-drive scenario is real.
  Minor (currently unreachable past PY-01) is correct.

### Corrections to carry into the consolidated report

1. PY-02 prose: "six copies of the `VENV` constant" → seven copies
   (six stale + one correct); the File: list is already accurate.
2. PY-01, truth_check detail: reps are skipped at the *pre-pivot* fix
   ("lost a reading before the pivot"), i.e. the tool dies even earlier
   than the finding's "every rep is skipped" implies. Strengthens, not
   weakens, the finding.
