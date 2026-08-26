---
status: done
sprint: '017'
tickets:
- 017-007
- 017-008
---

# No lint gate and no TypeScript check: 6 real ruff findings hide behind 205, and `tsconfig.json` cannot run

Priority: **Low** for the lint noise, **higher** for the TypeScript gap -- which
is why `block-go-to-misses-its-target.md` survived six sprints.

## ruff: 211 findings, no configuration

`uvx ruff check tools tests` with nothing in `pyproject.toml`:

| Rule | Count | Real? |
|---|---:|---|
| `F811` redefined-while-unused | 91 | **No** -- pytest fixture shadowing |
| `I001` unsorted imports | 39 | Style (the `sys.path.insert` prelude makes this awkward by construction) |
| `EXE001` shebang not executable | 17 | Style |
| `RUF100` unused noqa | 12 | Housekeeping |
| `RUF059`, `PLW1510`, `RUF007` | 27 | Mostly intentional |
| **`F401` unused import** | **4** | **Yes** |
| **`B904` raise-without-from** | **2** | **Yes** |
| `B023` loop-variable closure | 2 | No -- thread joined within the iteration |
| `B008` call in default arg | 1 | Deliberate, but obscure |

Actionable: `pytest` unused in `tests/host/test_wire_motion_completion.py:38`;
`os`/`pytest` in `tests/tools/test_camproc.py:24,28`; `argparse` in
`tools/otos_bench.py:22`; `raise SystemExit(str(e))` inside `except` at
`tools/tour_watch.py:150` and `tools/truth_check.py:144` -- which loses the
`DeadTelemetryError` chain, the one exception the fail-loud guard exists to
raise; and `def sampler(prev=math.degrees(c0))` at `tools/truth_check.py:165`.

**Fix**: a `[tool.ruff.lint]` block selecting `F, E9, B`, with `F811` ignored
under `tests/` (or `flake8-pytest-style` enabled so fixtures are understood).
Then `ruff check` is a gate that means something.

## `tsconfig.json` cannot run

It maintains a hand-edited `files` array -- correctly updated by sprints 012 and
013 -- but `package.json` has one dependency (`pxt-microbit`) and no
`typescript`; `node_modules/typescript` does not exist. **Nothing can execute
it.**

So the 1149 lines of student-facing TypeScript are type-checked only by a full
`pxt build`, once per sprint in the build-checkpoint ticket. That is a real
gate, but: it runs once per sprint, it type-checks rather than executes (the
`goTo` geometry defect type-checks perfectly), and nothing guards
`tsconfig.json`'s own file list the way `test_pxt_manifest_completeness.py`
guards `pxt.json`'s -- precisely because nothing reads it.

**Fix**: decide. Either add `typescript` as a dev dependency plus a pytest
wrapper shelling `tsc --noEmit`, or delete `tsconfig.json` so nobody maintains a
file with no consumer.

**The larger gap** -- no TypeScript is *executed* by any test -- is worth its
own conversation. A minimal harness (node, a stub `diffDrive` namespace
capturing `startMove` calls) would have caught all three arc defects in one
assertion each.

## C++ warnings

`test_kernel_harness.py` compiles `-Wall -Wextra` and tolerates ~16
`-Wdeprecated-volatile` warnings from the vendored kernel's `++cfgSeq_` at
C++20. Upstream owns that code and it is byte-stable by design, so the right
move is a targeted `-Wno-deprecated-volatile` on `diffdrive.cpp` with a one-line
comment -- leaving the warning stream meaningful for everything else.

## Two smaller ones

- **`sim.ts:99`** divides by 115 where hardware divides by
  `effectiveTrackWidth() = 114.2 / 0.952 = 119.96` -- 4.3% off. Sprint 007 fixed
  the 10x error here and picked the wrong one of the two geometry numbers; the
  comment is also wrong about which quantity hardware uses.
- **`field.py:72` `score_corners()`** scans `range(used, len(rows))` for each
  corner's *global* minimum. That stops a later corner reclaiming an earlier
  one's sample (as documented) but not the reverse: the first corner's search
  covers the whole remaining run, so a closed lap returning near its start can
  send `used` to the tail and leave every later corner scoring from a handful of
  final samples. A per-corner window would fix it.
