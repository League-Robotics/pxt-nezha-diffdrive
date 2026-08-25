---
id: '002'
title: Retrofit the six tour/ground-truth tools onto tools/tlm.py
status: open
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: retrofit-bench-tooling-onto-the-v6-telemetry-stream.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Retrofit the six tour/ground-truth tools onto tools/tlm.py

## Description

Retrofits `tour_run.py`, `tour_capture.py`, `tour_watch.py`,
`truth_check.py`, `rotation_check.py`, and `tour_practice.py` onto
ticket 001's `tools/tlm.py`, deleting every scattered `/10.0`/`/100.0`
scale factor and arity ladder — including the two already-dead
field-count branches (`tour_watch.py:202`'s `len(f) == 7`,
`tour_capture.py:70`'s 7/4/3-length ladder), which died silently when
the v5 line's field count changed under them. `tour_chart.py` and
`practice_chart.py` gain the zero-frame refusal against the new
`.meta.json` sidecar.

Per consumer:

- **`tour_run.py`** — trigger via `require_stream()` before the tour's
  `RUN:tour:<name>` is sent; record telemetry via `TlmStream`; write
  the CSV/sidecar via `write_tlm_csv()`.
- **`tour_capture.py`** / **`tour_watch.py`** — same retrofit; delete
  their own field-count arity branches entirely, they no longer exist
  once `TlmStream` owns arity.
- **`truth_check.py`** / **`rotation_check.py`** — `enc_heading()`
  becomes "read `h` from the last `t` frame via `TlmStream`," returning
  `None` (so the caller aborts) rather than silently reporting a stale
  or zero heading — do not fall back to a cached/default value.
- **`tour_practice.py`** — same retrofit as the tour family.
- **`tour_chart.py`** / **`practice_chart.py`** — read the run's
  `<stem>_tlm.meta.json` sidecar (written by ticket 001's
  `write_tlm_csv()`) and refuse to plot (raise or print-and-exit,
  match this project's existing CLI error convention) a run whose
  `frames == 0`.

New capability worth calling out on its own: `seq`-gap tracking gives
`dropped`/`loss_pct` for the first time — surface it in at least one
tool's console output (e.g. `tour_run.py`'s end-of-run summary), not
only the `.meta.json` sidecar. A column nothing consumes is decoration.

## Acceptance Criteria

- [ ] All six consumers import `tools/tlm.py` and contain no scale
      factor (`/10.0`, `/100.0`, etc.) or field-count arity check of
      their own — grep for `/10.0`/`/100.0`/`len(f)`/`len(parts)`
      against each file to confirm.
- [ ] `tour_watch.py:202`'s `len(f) == 7` branch and
      `tour_capture.py:70`'s 7/4/3-length ladder are gone, along with
      the rest of their old `TLM:`-parsing code.
- [ ] `tour_run.py` calls `require_stream()` before triggering the
      tour's `RUN:` command — a fake link with no `t` frame aborts the
      run before any `RUN:tour:` send is observed.
- [ ] `truth_check.py`/`rotation_check.py`'s `enc_heading()` returns
      `None` (not a stale/zero value) when no `t` frame has been
      received, and the caller aborts on `None` rather than proceeding
      with a fabricated heading.
- [ ] `tour_chart.py`/`practice_chart.py` refuse to plot a run whose
      `.meta.json` sidecar reports `frames == 0`, with a clear error
      message naming the run.
- [ ] At least one tool's console output surfaces `dropped`/`loss_pct`
      at the end of a run, not only the `.meta.json` sidecar.
- [ ] `uv run pytest` (full suite) passes with no regression to
      `tests/tools/test_tlm.py` (ticket 001) or `tests/host/`.

## Implementation Notes

- This ticket is the first real consumer of ticket 001's
  `require_stream()`/`write_tlm_csv()` — if either guard's signature
  proves awkward against a real consumer's control flow (e.g.
  `tour_watch.py`'s button-triggered loop vs. `tour_run.py`'s
  triggered-then-wait shape), it is fine to adjust `tools/tlm.py`
  itself in this ticket rather than working around it six times; note
  any such adjustment here and keep ticket 001's own tests green.
- No new unit-test file is required for this ticket beyond what ticket
  001 already covers, since the six consumers are thin orchestration
  around `TlmStream`/`require_stream`/`write_tlm_csv` — but if any
  consumer grows real decision logic of its own (e.g. a new console
  summary format), add a small test for it in `tests/tools/`.
- Real-hardware end-to-end verification (`tour_run.py --tour world`
  producing a non-empty CSV and a loss report) is this sprint's final
  handoff ticket's job (ticket 007's checklist), not a blocking
  acceptance criterion here — this ticket's own acceptance criteria are
  all verifiable against a fake link, per this sprint's no-robot
  constraint.

## C++11 Gate Coverage

Not applicable — pure Python, no C++ source touched.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` and the full
  `uv run pytest` — confirm ticket 001's `test_tlm.py` and the rest of
  the host suite are unaffected by this ticket's Python-only changes.
- **New tests to write**: none required beyond ticket 001's coverage
  unless a consumer grows new decision logic (see Implementation
  Notes) — the six consumers are thin wrappers around an already-tested
  `TlmStream`.
- **Verification command**: `uv run pytest`.
