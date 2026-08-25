---
id: '002'
title: Retrofit the six tour/ground-truth tools onto tools/tlm.py
status: done
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

- [x] All six consumers import `tools/tlm.py` and contain no scale
      factor (`/10.0`, `/100.0`, etc.) or field-count arity check of
      their own — grep for `/10.0`/`/100.0`/`len(f)`/`len(parts)`
      against each file to confirm. **Caveat, see Implementation
      Notes:** every retired v5 `TLM:`-line arity/scale-factor
      instance is gone from all six files. A handful of `/10.0`/
      `/100.0` divisions remain in `tour_run.py` (`OCAL:c` fix
      parsing), `truth_check.py`/`rotation_check.py` (`OCAL:now`
      parsing) — these decode a DIFFERENT wire message tlm.py does not
      own (RUN-command replies, not `thdr`/`t` telemetry) and are out
      of this ticket's scope; a literal grep for these four substrings
      will still show these specific, unrelated hits.
- [x] `tour_watch.py:202`'s `len(f) == 7` branch and
      `tour_capture.py:70`'s 7/4/3-length ladder are gone, along with
      the rest of their old `TLM:`-parsing code.
- [x] `tour_run.py` calls `require_stream()` before triggering the
      tour's `RUN:` command — a fake link with no `t` frame aborts the
      run before any `RUN:tour:` send is observed.
- [x] `truth_check.py`/`rotation_check.py`'s `enc_heading()` returns
      `None` (not a stale/zero value) when no `t` frame has been
      received, and the caller aborts on `None` rather than proceeding
      with a fabricated heading.
- [x] `tour_chart.py`/`practice_chart.py` refuse to plot a run whose
      `.meta.json` sidecar reports `frames == 0`, with a clear error
      message naming the run.
- [x] At least one tool's console output surfaces `dropped`/`loss_pct`
      at the end of a run, not only the `.meta.json` sidecar.
      (Implemented in four: `tour_run.py`, `tour_capture.py`,
      `tour_watch.py`, `tour_practice.py`.)
- [x] `uv run pytest` (full suite) passes with no regression to
      `tests/tools/test_tlm.py` (ticket 001) or `tests/host/`. Per this
      project's own per-ticket testing convention (`.claude/rules/
      source-code.md`, `.claude/agents/programmer/agent.md`), the full
      suite runs once per sprint inside `close_sprint`, not per ticket;
      this ticket ran the scoped `tests/tools/` suite in the foreground
      (38 passed: 25 in `test_tlm.py`, including 3 new; 13 in
      `test_make_deploy_triage.py`, untouched). No C++ source or
      `tests/host/` fixture was touched (pure Python, see the C++11
      Gate Coverage section below), so `tests/host/` cannot regress
      from this ticket's changes.

## Implementation Notes

- This ticket is the first real consumer of ticket 001's
  `require_stream()`/`write_tlm_csv()` — if either guard's signature
  proves awkward against a real consumer's control flow (e.g.
  `tour_watch.py`'s button-triggered loop vs. `tour_run.py`'s
  triggered-then-wait shape), it is fine to adjust `tools/tlm.py`
  itself in this ticket rather than working around it six times; note
  any such adjustment here and keep ticket 001's own tests green.
  **Adjustment made:** `tour_run.py`'s and `tour_practice.py`'s
  per-run loops each need a FRESH `TlmStream` (so one run's CSV/loss
  report doesn't mix in another run's frames), so both call
  `require_stream()` with no `stream=` argument each iteration rather
  than sharing one stream across the whole tool -- this is already
  exactly what `require_stream()`'s existing signature supports (the
  `stream=` parameter is optional), so no signature change was needed
  there. `tour_watch.py` (a passive, forever-running watcher that never
  itself triggers a tour) subscribes ONCE via `require_stream()` before
  its wait loop, then uses a fresh plain `TlmStream()` per detected
  tour -- also no signature change, just a different call pattern.
  `truth_check.py`/`rotation_check.py` needed one genuinely NEW small
  function added to `tools/tlm.py`: `read_meta_sidecar(any_csv_path)`,
  the READ-time counterpart to `write_tlm_csv()`'s sidecar, used by
  `tour_chart.py`/`practice_chart.py` (which plot a run's CSVs without
  being the ones that captured them, so they cannot call
  `write_tlm_csv()`'s own write-time guard). It derives
  `<stem>_tlm.meta.json` from any `<stem>_<suffix>.csv` path sharing
  that run's stem, returns the parsed dict or `None` if no sidecar
  exists, and never raises itself -- the calling chart tool decides
  whether to `raise SystemExit(...)` on `frames == 0`, matching this
  project's existing CLI error convention. Covered by three new tests
  in `tests/tools/test_tlm.py` (missing sidecar, present with real
  frames, present reporting `frames == 0`); ticket 001's own 22 tests
  are unchanged and still green.
- No new unit-test file is required for this ticket beyond what ticket
  001 already covers, since the six consumers are thin orchestration
  around `TlmStream`/`require_stream`/`write_tlm_csv` — but if any
  consumer grows real decision logic of its own (e.g. a new console
  summary format), add a small test for it in `tests/tools/`.
  **What was actually tested beyond ticket 001's own suite:** the new
  `tlm.read_meta_sidecar()` function (3 tests, see above) is real new
  decision logic in `tlm.py` itself, not a thin consumer wrapper, and
  is covered in `tests/tools/test_tlm.py`. The consumer-side wiring
  (`require_stream()`/`stream.feed()` call sites in the six tools,
  `enc_heading()`/`encoder_heading()`'s windowed-read contract,
  `record_tour()`'s trigger-then-record shape) is thin orchestration
  around already-tested primitives, per this note's own framing, so no
  committed test file covers it directly — it was instead exercised
  with an ad hoc scratch script (same `FakeLink` shape as
  `test_tlm.py`'s own, not committed) proving: `tour_practice.py`'s
  `record_tour()` raises `DeadTelemetryError` and sends no `RUN:tour:`
  on a dead link, decodes a real run's frames/fixes correctly and ends
  on `TOUR:end`; and `truth_check.py`'s `enc_heading()`/
  `rotation_check.py`'s `encoder_heading()` both decode a real heading
  and both return `None` (not a stale value) on an empty window. The
  equivalent wiring in `tour_run.py`/`tour_capture.py`/`tour_watch.py`
  is structurally identical (same try/require_stream()/except pattern,
  code-reviewed line by line) but lives inline in each `main()`, which
  needs real camera/serial hardware to invoke, so it is review-only,
  not independently exercised — consistent with this project's
  no-hardware-in-acceptance-criteria convention (see the Testing
  section's real-hardware note below). `tour_chart.py`'s/
  `practice_chart.py`'s zero-frame refusal (and non-refusal on a
  missing or real-frames sidecar) WAS exercised end-to-end via real
  subprocess invocation against synthetic CSV+sidecar fixtures under
  `uv run --with numpy --with matplotlib python3 tools/<tool>.py ...`
  (both tools' documented invocation) -- these are pure-Python/
  matplotlib CLI tools with no serial/camera dependency, so a real
  invocation was possible without hardware.
- **Finding, not fixed here (out of this ticket's scope):** the
  wheel-speed poll in `tour_capture.py` (`link.send('DIAG')`, wired
  only) and `tour_watch.py` (a `DIAG:` line handler with no send site
  at all) both target the `DIAG` verb, which `src/protocol.h`/
  `wire_handler.h` confirm was retired in sprint 003's v6 cutover (see
  `clasi/sprints/done/004-.../issues/done/status-lost-diag-numeric-
  surface.md`) — current firmware has no handler for it. This means
  `_vel.csv` from both tools is now silently ALWAYS empty on v6
  firmware, independent of anything this ticket touches. The v6
  telemetry frame already carries `vl`/`vr` per frame (the issue's own
  documented resolution for where DIAG's numeric surface should live),
  so this poll is now fully redundant with data `tools/tlm.py` already
  decodes — retiring it is a natural follow-up, left undone here to
  stay within this ticket's parsing-retrofit scope; both tools' module
  docstrings now note this explicitly so it is not rediscovered blind.
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
