---
id: '003'
title: 'Link-layer consolidation: pyserial fix, tools/camproc.py, tools/field.py'
status: open
use-cases:
- SUC-004
- SUC-005
depends-on:
- '002'
github-issue: ''
issue: tools-link-layer-consolidation.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Link-layer consolidation: pyserial fix, tools/camproc.py, tools/field.py

## Description

Closes `tools-link-layer-consolidation.md` (code review R-24/R-26):
stale hardcoded venvs, a swallowed camera `ERR` channel, and seven
copied `Cam` wrapper scaffolds with two incompatible `latest` tuple
orders. Sequenced after ticket 002 because both touch the same
tour/ground-truth tool files (`tour_run.py`, `tour_practice.py`,
`tour_watch.py`, `truth_check.py`, `pivot_truth.py`) — landing the
telemetry retrofit first avoids this ticket's camera-consolidation
edits needing to be redone against files ticket 002 also rewrites.

Three independent pieces:

1. **`pyproject.toml` gains a `pyserial` dependency.** Today `uv run
   python` has no `pyserial`; only the system `python3` does, so every
   bench tool in `tools/` runs only under a different interpreter than
   the project's own test/dev environment (found live, this session:
   `tools/robotlink.py` cannot be imported under `uv run python`).
2. **`tools/camproc.py`** — owns camera-subprocess lifecycle: resolve
   the AprilTags interpreter **once**, in one place (env var or a small
   config — implementer's choice, per the issue's own wording; the only
   firm requirement is "never hardcoded per spawn site"), replacing six
   hardcoded spawn sites; surface a spawned camera's `ERR` lines to the
   calling tool instead of `stderr=DEVNULL`-discarding them; invalidate
   a cached pose once the stream is marked dead, so `place()`/`fix()`
   cannot re-seed the robot's world frame from a frozen, stale value
   after a mid-session camera death.
3. **`tools/field.py`** — playfield constants, `wrap()`, and corner
   scoring, replacing 7 copied `Cam` wrapper scaffolds (two
   incompatible `latest` tuple orders: `tour_run.py`'s `(x,y,yaw)` vs.
   `tour_practice.py`'s `(yaw,x,y)`), 8 `wrap()`s, 6 playfield-constant
   blocks, and 4 corner scorers whose outputs already disagree (console
   "SW 31.3cm" vs. chart "SW=unobserved" for the same run). Consumes
   `camlink.py`'s existing shared `Cam` — does not re-wrap it.

Also sweep in the tool Minors the issue names: `make_deploy.py`'s
`endswith('test.ts')` filter (PY-06) is ticket 005's job, not this
one — do not fix it here, to keep this ticket's scope to the link
layer. Unguarded rotation divides (PY-08): fix inline wherever found
during this ticket's own edits to `field.py`'s `wrap()` consolidation,
since that is exactly where scattered rotation-wrap code is being
collected into one place anyway.

## Acceptance Criteria

- [ ] `pyproject.toml` declares `pyserial`; `uv run python -c "import
      sys; sys.path.insert(0, 'tools'); import robotlink"` exits zero.
- [ ] No `tools/*.py` file hardcodes the AprilTags venv path directly —
      every camera spawn site routes through `tools/camproc.py`'s
      single resolution point (grep for the venv path string across
      `tools/` to confirm zero hardcoded occurrences outside
      `camproc.py` itself).
- [ ] A simulated camera `ERR` line reaches the calling tool (observed
      via a test double), not silently discarded.
- [ ] A cached pose is invalidated once the camera stream is marked
      dead — a tool cannot observe a "fresh" pose after the stream
      death, verified against a fake/mocked stream.
- [ ] The 7 copied `Cam` wrapper scaffolds are gone; every consumer
      uses `camlink.py`'s shared `Cam` directly or through
      `tools/camproc.py`.
- [ ] The two incompatible `latest` tuple orders are unified to one
      (document the chosen order in `tools/field.py`'s own docstring);
      every consumer that reads `latest` is updated to match.
- [ ] Corner-scoring logic lives in `tools/field.py` alone; the 4
      corner scorers whose outputs previously disagreed for the same
      run now agree (verified with a shared test fixture, not just
      code inspection).
- [ ] `uv run pytest` (full suite) passes.

## Implementation Notes

- `tour_run.py`'s docstring-documented camera doctrine ("used exactly
  twice: seed at start, score at end") must not change — this ticket
  consolidates *how* the camera is reached and scored, not *when* it
  is consulted. Preserve `docs/design/design.md`'s "camera is
  diagnostic, never a control input" doctrine.
- `camproc.py`/`field.py` are new modules with no CLI of their own,
  matching `tools/tlm.py`'s (ticket 001) shape — library code imported
  by the tour/ground-truth tools.
- If the interpreter-resolution mechanism (env var vs. config file)
  interacts with how CI/agents invoke these tools, prefer whichever
  option needs no change to how a bench operator already runs them
  today (e.g. an env var with the current hardcoded path as its
  default, rather than a new required config file) — a completely
  silent migration is preferable to one that requires every operator to
  update their invocation.

## C++11 Gate Coverage

Not applicable — pure Python, no C++ source touched.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` and the full
  `uv run pytest` — confirm no regression to ticket 001/002's telemetry
  work or the existing build-triage tests.
- **New tests to write**: `tests/tools/test_camproc.py` (or similar) —
  interpreter resolution reads from the one designated source (no
  hardcoded fallback reached in a test environment with the resolution
  source set); a simulated `ERR` line is surfaced, not swallowed; a
  cached pose is invalidated after a simulated stream death.
  `tests/tools/test_field.py` (or similar) — `wrap()`'s boundary
  behavior, and the 4 corner scorers producing consistent output
  against one shared fixture.
- **Verification command**: `uv run pytest`.
