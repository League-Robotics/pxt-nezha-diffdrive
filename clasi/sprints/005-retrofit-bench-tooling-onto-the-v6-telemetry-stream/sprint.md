---
id: '005'
title: Retrofit bench tooling onto the v6 telemetry stream
status: roadmap
branch: sprint/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream
use-cases: []
issues:
- retrofit-bench-tooling-onto-the-v6-telemetry-stream.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 005: Retrofit bench tooling onto the v6 telemetry stream

> **DO NOT START THIS SPRINT YET.** This sprint must not begin until sprint
> 004 (`004-radio-full-v6-transport-telemetry-frame-firmware`) has **closed**
> and its Phase C bench checkpoint has **passed on real hardware** — a
> flashed robot confirmed to emit `thdr`/`t` frames over radio, not just a
> built hex. The two-sprint split exists specifically so this sprint targets
> a wire format a robot has actually confirmed, rather than one that only
> exists on paper. If the bench run changes the frame shape, scaling, or
> column set, this sprint's plan (and possibly its scope) changes with it —
> re-check this sprint.md against the bench results before detailing.

## Goals

This is the **host-tooling sprint** — the second of a two-sprint arc closing
`retrofit-bench-tooling-onto-the-v6-telemetry-stream.md`. Sprint 004 makes
radio a full v6 transport and gives v6 a `thdr`/`t` telemetry frame; this
sprint retrofits six bench tools onto that frame through one new shared
parser, `tools/tlm.py`, and makes "the instrument returned nothing" a loud,
immediate failure instead of a silent empty CSV.

## Problem

All six bench tools currently parse the retired v5 `TLM:` cleartext line:
`tour_run.py`, `tour_capture.py`, `tour_watch.py`, `truth_check.py`,
`rotation_check.py`, and `tour_practice.py`. Each has its own scattered
`/10.0`, `/100.0`, and field-count arity logic. Two problems make this
sprint's shape non-optional rather than a style preference:

1. **Two of the six tools are already silently dead, independent of v6.**
   `tour_watch.py:202` tests `len(f) == 7` and `tour_capture.py:70` accepts
   only lengths 7, 4, or 3 — but the retired v5 line carried **nine**
   fields. Both branches died when `vl`/`vr` were added and nobody noticed,
   because the failure mode is an empty CSV, not a crash. Six scattered
   parsers is how that kind of breakage hides; one shared parser is the
   fix, not just a refactor for its own sake.
2. **An instrument that returns nothing is indistinguishable from a robot
   that did nothing.** This project's recurring, expensive failure mode is
   a tour scored against an empty or header-only telemetry file producing
   confident, wrong conclusions. Fail-loud guards against that are
   acceptance criteria for this sprint, not polish.

## Solution

New `tools/tlm.py` — the single place any scale factor is written. A
`TlmStream` class tracks the `thdr` column header (re-emitted by firmware
at ~1 Hz so a late-attaching consumer can resync; an identical re-read is a
no-op) and feeds `t` lines, exposing `frames`, `orphan_frames` (a `t` before
any header), `malformed` (a `t` whose value count disagrees with the
header — the defense against `RadioTransport`'s 200-byte line truncation),
and `dropped`/`loss_pct` (from `seq` gaps — a 7-bit wrapping counter at
20 Hz, unambiguous up to ~6.4 s of loss). Unit-conversion helpers
(`pose_cm`, `otos_cm`, `wheels_mms`) live here too, so no consumer computes
its own scale factor again.

Three fail-loud guards, all acceptance criteria:

1. `require_stream(link, timeout=3.0)` subscribes (`TLM POSE`) and aborts
   **before** a run is triggered if no `t` frame arrives — a dead
   instrument must not cost a run.
2. `write_tlm_csv()` raises on zero rows. Never write a header-only CSV. An
   absent file is unambiguous; an empty one produces confident, wrong
   conclusions.
3. A `<stem>_tlm.meta.json` sidecar records frames / dropped / loss_pct /
   orphan_frames / malformed / columns / duration; `tour_chart.py` and
   `practice_chart.py` refuse to plot a run with `frames == 0`.

Then retrofit the six consumers onto `TlmStream`, deleting their scattered
arity ladders and scale factors. `truth_check.py` and `rotation_check.py`'s
`enc_heading()` becomes "read `h` from the last `t` frame," returning
`None` (so the caller aborts) rather than silently reporting a stale or
zero heading.

New capability worth calling out on its own: `seq`-gap tracking gives
`dropped`/`loss_pct` for the first time — the tools have never before been
able to say how much the radio link dropped. The loss report is an
acceptance criterion of the retrofit, not a nice-to-have; a column nothing
consumes is decoration.

## Success Criteria

- `tools/tlm.py` is the only place a telemetry scale factor is written;
  all six consumers import it instead of parsing lines themselves.
- All three fail-loud guards are implemented and tested: `require_stream`
  aborts before a run on a dead instrument; `write_tlm_csv` raises rather
  than writing a header-only CSV; the chart tools refuse a zero-frame run.
- `seq`-gap tracking produces a real `dropped`/`loss_pct` figure, surfaced
  in the `.meta.json` sidecar and in at least one tool's console output.
- The two pre-existing dead branches (`tour_watch.py:202`,
  `tour_capture.py:70`) are gone along with the rest of the per-tool arity
  logic they belonged to.
- `tests/tools/test_tlm.py` passes: header tracking, seq-gap counting,
  arity rejection, orphan frames, unit helpers.
- End-to-end: a real `tour_run.py --tour world` run against actual
  hardware produces a non-empty CSV and a loss report.

## Scope

### In Scope

- New `tools/tlm.py`: `TlmStream`, header tracking, `frames` /
  `orphan_frames` / `malformed` / `dropped` / `loss_pct`, and the
  `pose_cm`/`otos_cm`/`wheels_mms` unit helpers.
- The three fail-loud guards: `require_stream()`, a raising
  `write_tlm_csv()`, and the `<stem>_tlm.meta.json` sidecar plus the
  zero-frame refusal in `tour_chart.py` and `practice_chart.py`.
- Retrofitting all six consumers: `tour_run.py`, `tour_capture.py`,
  `tour_watch.py`, `truth_check.py`, `rotation_check.py`,
  `tour_practice.py` — including removing the two already-dead
  field-count branches (`tour_watch.py:202`, `tour_capture.py:70`) and
  every scattered `/10.0`/`/100.0` scale factor.
- `tests/tools/test_tlm.py` (lives under `tests/`, per `pyproject.toml`'s
  `testpaths = ["tests"]` — not under `tools/`), importing the shared
  golden frame from `tests/host/golden_telemetry.py` as parser input.
- An end-to-end real-hardware `tour_run.py --tour world` check producing a
  non-empty CSV and a loss report.

### Out of Scope

- Anything in sprint 004: the `WireHandler`/`RadioSink` radio transport
  work, the `thdr`/`t` frame emitter, `STATUS i2cf=`, or any firmware
  change. This sprint only consumes the wire format sprint 004 produces.
- Starting this sprint's detail planning or ticket work before sprint 004
  has closed and its Phase C bench checkpoint has passed on real
  hardware (see the notice above).
- Any change to `radio-robot-lib` (spec authority, out of this project's
  scope regardless of sprint).

## Test Strategy

`tests/tools/test_tlm.py` (under `tests/`, not `tools/`, per
`pyproject.toml`'s `testpaths`): header tracking (including the 1 Hz
re-emit no-op case), seq-gap counting and wraparound, arity/malformed
rejection, orphan-frame counting before any header, and the unit-helper
conversions. The shared golden frame in `tests/host/golden_telemetry.py`
is imported here as parser input — the same fixture sprint 004's firmware
test uses as expected sink bytes, so emitter and parser cannot drift apart
even though they're built in different sprints. Beyond unit tests, an
end-to-end check: a real `tour_run.py --tour world` against hardware
producing a non-empty CSV and a non-trivial loss report — the fail-loud
guards are only proven by trying to break them on a live, imperfect radio
link, not just by unit tests against synthetic data.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.
