---
id: '001'
title: Retarget tour_capture.py off numeric RUN onto the named RUN:tour vocabulary
status: open
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: otos-on-vevov-move-goto-world-pose-square-tours.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Retarget tour_capture.py off numeric RUN onto the named RUN:tour vocabulary

## Description

`tools/tour_capture.py` still selects which tour to run with a numeric
`RUN:<n>` verb (`tour_capture.py:58`, `link.send_until(f'RUN:{a.run}',
...)`, `--run` defaulting to `1`). Current firmware's `test/test.ts`
registers only named `diffDrive.onRun(...)` handlers
(`test.ts:307-399`: `tour`, `straight`, `cal`, `fix`, `arm`, `probe`,
`gap`, `seed`, `seedxy`, `goto`, `face` — confirmed against `test.ts`'s
own authoritative header comment, lines 9-14) — no numeric name is
registered anywhere, so `RUN:1` (or any other number) is a silent
no-op against current hardware. `tour_run.py` already sends
`RUN:tour:{a.tour}` (`--tour world|robot|wheels`); this ticket brings
`tour_capture.py` to the same vocabulary.

**Verified not already covered elsewhere.** Sprint 005 ticket 006
("test.ts named pivot/turn-rate verbs; retarget five ground-truth tools
off dead numeric RUN") retargets `otos_bench.py`, `pivot_truth.py`,
`truth_check.py`, `rotation_check.py`, `turn_sweep.py`, and
`otos_levercal.py` — six names, `tour_capture.py` is not among them.
Sprint 005 ticket 002 (in progress at planning time — `tour_capture.py`
already imports `tools/tlm.py` and calls `require_stream()`/
`write_tlm_csv()` in the working tree) retrofits `tour_capture.py`'s
*telemetry parsing* only, not which `RUN:` verb it sends. This ticket
is the one piece of the original roadmap's "fix the two stale bench
tools" item that no other sprint claims.

**Sequencing risk — read before starting.** Sprint 005 is executing
concurrently and its ticket 002 touches this same file (telemetry
parsing only, not the RUN verb). Check `git log -- tools/tour_capture.py`
and the file's current content before editing: if ticket 002 has
already landed (merged to whatever branch this ticket starts from), the
`tlm`-retrofit parts of the file are already correct and this ticket
only needs to change the verb-selection lines. If ticket 002 has not
yet landed, coordinate with the team-lead rather than editing a file
another sprint's ticket is actively changing — this sprint's own
concurrency rule (touch only this sprint's own paths) does not license
racing another sprint's in-flight ticket on a shared file.

## Acceptance Criteria

- [ ] `tour_capture.py` gains a `--tour {world,robot,wheels}` argument
      (matching `tour_run.py`'s existing flag shape) replacing `--run
      N`.
- [ ] The tool sends `RUN:tour:world` / `RUN:tour:robot` /
      `RUN:tour:wheels` — never a bare numeric `RUN:<n>`.
- [ ] Verified against a fake/mock link: a unit test in `tests/tools/`
      asserts the exact string passed to `send_until()` for each of the
      three tour names — no robot required.
- [ ] No change to the file's telemetry-parsing logic (the `tlm`
      import, `require_stream()`, `write_tlm_csv()` calls) beyond
      whatever sprint 005 ticket 002 has already landed — this ticket's
      diff should be small and confined to argument parsing and the
      `RUN:` verb construction.
- [ ] `uv run pytest` (full suite) passes.

## Implementation Plan

**Approach:** Change `ap.add_argument('--run', type=int, default=1)` to
`ap.add_argument('--tour', default='world', choices=['world', 'robot',
'wheels'])`, and change `link.send_until(f'RUN:{a.run}', 'TOUR:', ...)`
to `link.send_until(f'RUN:tour:{a.tour}', 'TOUR:', ...)`. Update the
module docstring's `Usage:` line to match. Leave every other line
untouched — this is a narrow, surgical retarget, not a rewrite.

**Files to modify:**
- `tools/tour_capture.py`

**Testing plan:**
- New: `tests/tools/test_tour_capture.py` (or add to an existing
  `tests/tools/` file if a natural home exists by execution time) — a
  fake link object capturing what `send_until()` was called with;
  assert `RUN:tour:world` for the default, and `RUN:tour:robot`/
  `RUN:tour:wheels` for the other two choices.
- Existing: `uv run pytest tests/tools/` and the full `uv run pytest`.
- **Verification command:** `uv run pytest`.

**Documentation updates:** none beyond this sprint's own `design/`
overlay (`design/tools-root-DESIGN.md`'s "Tour family" section already
documents this retarget at planning time — confirm it still matches
what actually shipped; if the flag name or verb shape changed during
implementation, update the overlay copy and regenerate its `.diff.md`
by hand, per the `architecture-authoring` skill's in-place revision
convention).

## C++11 Gate Coverage

Not applicable — pure Python, no C++ source touched.
