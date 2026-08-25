---
id: '001'
title: 'tools/tlm.py: shared v6 telemetry parser and fail-loud guards'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on: []
github-issue: ''
issue: retrofit-bench-tooling-onto-the-v6-telemetry-stream.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# tools/tlm.py: shared v6 telemetry parser and fail-loud guards

## Description

Foundation ticket for the whole sprint's telemetry retrofit
(`retrofit-bench-tooling-onto-the-v6-telemetry-stream.md`). All six
tour/ground-truth tools currently parse the retired v5 `TLM:`
cleartext line, each with its own scattered arity check and scale
factor; two of the six (`tour_watch.py:202`, `tour_capture.py:70`) are
already silently dead because the v5 line's field count changed under
them and nobody noticed — the failure mode is an empty CSV, not a
crash. This ticket builds the single replacement, `tools/tlm.py`, that
every consumer will import in ticket 002. No consumer is retrofitted
in this ticket — that is ticket 002's job, kept separate so this
ticket's own tests can pin the parser in isolation first.

Build `TlmStream`, a class that:

- Tracks the most recent `thdr` column-header line (firmware re-emits
  it at ~1 Hz per `kHeaderRefreshFrames = 20`, so a late-attaching
  consumer can resync; an identical re-read is a no-op).
- Feeds `t` lines against the last-seen header, exposing `frames`
  (successfully parsed rows), `orphan_frames` (a `t` before any
  header), `malformed` (a `t` whose value count disagrees with the
  header column count — the defense against `RadioTransport`'s
  200-byte line truncation), and `dropped`/`loss_pct` (from `seq`
  gaps — a 7-bit wrapping counter at 20 Hz, unambiguous up to ~6.4 s of
  loss; must not miscount a 127→0 wraparound as a gap).
- Provides unit-conversion helpers `pose_cm(row)`, `otos_cm(row)`,
  `wheels_mms(row)` — the single place any wire-to-engineering-unit
  scale factor is written for telemetry.

Then the three fail-loud guards (all acceptance criteria, not
polish — this project's recurring, expensive failure mode is a tour
scored against an empty or header-only telemetry file producing
confident, wrong conclusions):

1. `require_stream(link, timeout=3.0)` — sends `TLM POSE` and waits;
   raises **before** any run-triggering command is sent if no `t`
   frame arrives in time.
2. `write_tlm_csv(stream, path, ...)` — raises on zero accumulated
   frames; never writes a header-only CSV. An absent file is
   unambiguous; an empty one is not.
3. A `<stem>_tlm.meta.json` sidecar (frames / dropped / loss_pct /
   orphan_frames / malformed / columns / duration), written alongside
   the CSV whenever `write_tlm_csv()` succeeds.

Real captured hardware frames are available as fixtures — use them,
not only synthetic data, per the sprint's own emphasis: see
`clasi/issues/retrofit-bench-tooling-onto-the-v6-telemetry-stream.md`'s
"Realistic-value capture" section for a widest-observed 75 B `TLM FULL`
frame with real (non-zero) values, and
`tests/host/golden_telemetry.py` for the hand-checkable POSE-shaped
golden frame sprint 004's firmware test already uses as expected
*emitted* bytes — import it here as parser *input* so emitter and
parser are pinned against the same source of truth and cannot silently
drift apart.

## Acceptance Criteria

- [x] `TlmStream.feed(line)` decodes a `thdr` line into the current
      column set and a `t` line into a `dict[name, int]` (or `None` for
      a non-`t`/`thdr` line), using the header for column names — no
      hardcoded column index or position.
- [x] A `t` line arriving before any `thdr` increments `orphan_frames`
      and is not counted into `frames`.
- [x] A `t` line whose value count disagrees with the last `thdr`'s
      column count increments `malformed` and is not counted into
      `frames`; it does not raise (parsing tolerates malformed input,
      fail-loud is `require_stream`/`write_tlm_csv`'s job).
- [x] Re-feeding an identical `thdr` (same names, same order, same hex
      flags) is a no-op — no observable state change beyond having
      re-confirmed the header.
- [x] `seq` gap tracking: consecutive `t` frames with a gap in `seq`
      increment `dropped` by the gap size and `loss_pct` reflects it;
      a `seq` wraparound from 127 to 0 is not miscounted as a gap.
- [x] `pose_cm`/`otos_cm`/`wheels_mms` convert a decoded row's raw wire
      integers to the documented engineering units, verified against
      `tests/host/golden_telemetry.py`'s expected values (not a
      hand-rolled fixture).
- [x] `require_stream(link, timeout=3.0)` raises before any `send()` of
      a run-triggering command is observed on a fake link when no `t`
      frame arrives inside the timeout, and returns normally once one
      does.
- [x] `write_tlm_csv()` raises on zero accumulated frames and leaves no
      CSV file on disk; on one or more frames it writes both the CSV
      and a `<stem>_tlm.meta.json` sidecar whose `frames`/`dropped`/
      `loss_pct`/`orphan_frames`/`malformed`/`columns`/`duration`
      fields match the fed data.
- [x] Fed against the real 75 B `TLM FULL` frame captured on tovez
      (`t 25 988992 31 142 -16 11737 0 0 0 -122 126 3 101 286 3319
      -1300 1800 0 0 0`, from the issue's "Realistic-value capture"
      section) with its preceding `thdr`, `TlmStream` decodes all 20
      columns correctly, including negative values (`vl=-122`,
      `dutl=-1300`) and zero OTOS columns (not treated as a fault).

## Implementation Notes

- Lives at `tools/tlm.py`, following the flat-root, no-subsystems
  convention every other `tools/` script uses (see `tools/DESIGN.md`).
- No CLI of its own — this is a library module imported by the six
  consumer tools (ticket 002) and the two chart tools' zero-frame
  guard.
- Do not implement `require_stream()` against a real `Link`/serial
  object in this ticket's own tests — use a minimal fake with a
  `send()`/`lines()` surface, matching this project's existing
  fake-collaborator convention (`tests/tools/test_make_deploy_triage.py`'s
  `monkeypatch` pattern, `tests/host/`'s fake ports).

## C++11 Gate Coverage

Not applicable — this ticket is pure Python (`tools/tlm.py`,
`tests/tools/test_tlm.py`). No C++ source is touched, so
`test_cxx11_syntax_gate.py` has nothing new to cover here. Stated
explicitly per this sprint's requirement, not omitted.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` (confirm no
  regression to `test_make_deploy_triage.py`); `uv run pytest
  tests/host/test_wire_telemetry_projection.py` (confirm the golden
  fixture this ticket imports is unchanged by this ticket's own work).
- **New tests to write**: `tests/tools/test_tlm.py` — header tracking
  (fresh, no-op re-read, 20-frame memo re-emit), seq-gap counting and
  wraparound, arity/malformed rejection, orphan-frame counting, the
  unit-conversion helpers against `tests/host/golden_telemetry.py`, and
  both fail-loud guards' raising and non-raising paths (see this
  ticket's Acceptance Criteria for the full list).
- **Verification command**: `uv run pytest tests/tools/test_tlm.py`,
  then the full `uv run pytest` before moving this ticket to done.
