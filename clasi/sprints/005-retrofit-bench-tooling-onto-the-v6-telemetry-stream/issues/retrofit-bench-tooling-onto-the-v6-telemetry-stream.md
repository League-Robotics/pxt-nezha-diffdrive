---
status: in-progress
split_from: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
sprint: '005'
tickets:
- 005-001
- 005-002
---

# Retrofit the bench tooling onto the v6 telemetry stream

## Description

Split from the firmware half so it can be planned against a wire format that a
robot has actually confirmed, rather than one that only exists on paper. Do not
start this until the firmware sprint's bench checkpoint has passed.

Six tools parse the retired v5 `TLM:` line and must move onto v6's `thdr`/`t`
frames: `tour_run.py`, `tour_capture.py`, `tour_watch.py`, `truth_check.py`,
`rotation_check.py`, `tour_practice.py`.

**Two of them are already silently dead, independent of v6.**
`tour_watch.py:202` tests `len(f) == 7` and `tour_capture.py:70` accepts only
lengths 7, 4 or 3 — but the v5 line carried **nine** fields. Both branches died
when `vl`/`vr` were added and nobody noticed, because the failure mode is an
empty CSV rather than a crash. That is the whole argument for a single shared
parser and a loud guard.

## Proposed fix

New `tools/tlm.py` — the single place any scale factor is written:

```python
class TlmStream:
    def feed(self, line) -> dict | None    # 't' -> {name: int}
    columns; frames; orphan_frames; malformed; dropped; loss_pct
    def pose_cm(row); def otos_cm(row); def wheels_mms(row)
```

- Tracks `thdr`; an identical re-read is a no-op (the firmware re-emits the
  header at 1 Hz so a late-attaching consumer can resync).
- A `t` before any header counts `orphan_frames` and returns `None`.
- A `t` whose value count differs from the header count counts `malformed` — the
  defense against a line truncated at `RadioTransport`'s 200-byte cap.
- **`seq` gaps yield `dropped` / `loss_pct`.** Genuinely new capability: the
  tools have never been able to say how much the radio dropped. A 7-bit wrapping
  counter at 20 Hz is unambiguous up to ~6.4 s of loss.

Fail loud, three layers — treat these as acceptance criteria, not polish:

1. `require_stream(link, timeout=3.0)` sends the `TLM POSE` subscribe and aborts
   *before* triggering a run if no `t` arrives. A dead instrument must not cost
   a run.
2. `write_tlm_csv()` raises on zero rows. **Never write a header-only CSV.** An
   absent file is unambiguous; an empty one is what produces confident, wrong
   conclusions.
3. A `<stem>_tlm.meta.json` sidecar carrying frames / dropped / loss_pct /
   orphan_frames / malformed / columns / duration; `tour_chart.py` and
   `practice_chart.py` refuse to plot a run with `frames == 0`.

Then retrofit the six consumers, deleting their scattered `/10.0`, `/100.0` and
arity ladders — that scattering is how the current breakage hid.

`truth_check.py` and `rotation_check.py`'s `enc_heading()` becomes "read `h` from
the last `t` frame", returning `None` so the caller aborts rather than silently
reporting a stale or zero heading.

## Verification

- `tests/tools/test_tlm.py` (must live under `tests/`, per `pyproject.toml`'s
  `testpaths`): header tracking, seq-gap counting, arity rejection, orphan
  frames, unit helpers.
- The shared golden frame in `tests/host/golden_telemetry.py` is imported here as
  parser input and by the firmware test as expected sink bytes, so emitter and
  parser cannot drift apart.
- End to end: a real `tour_run.py --tour world` producing a non-empty CSV and a
  loss report.

## Related

- Split from [[radio-speaks-full-v6-and-v6-gets-its-telemetry-frame]], which
  must land and pass its bench checkpoint first.

## Bench confirmation of the v6 frame — tovez, 2026-08-24

**This issue's blocking precondition is satisfied.** Sprint 005's own
sprint.md says it must not begin until a flashed robot is confirmed to emit
`thdr`/`t` frames over the wire, rather than a format that exists only on
paper. Confirmed on **tovez** (USB serial, `/dev/cu.usbmodem212402`), hex
built from master at `4e14817` (sprints 004+006+007+008 merged).

### The frames a real robot actually emits

```
TLM POSE  → thdr seq now flags x y h ox oy oh vl vr i2cf            (44 B, 12 cols)
            t 1 37973 0 0 0 0 0 0 0 0 0 0                           (29 B)

TLM FULL  → thdr seq now flags x y h ox oy oh vl vr i2cf cyc posl
              posr dutl dutr lexc wrng cycovr                       (85 B, 20 cols)
            t 74 42016 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0          (46 B)
```

- **Column names and order match the host tests exactly** — `tlm.py`'s parser
  can be written against these names with confidence.
- **Header memo confirmed live**: 73 `t` frames to 4 `thdr` in one 4 s window
  ≈ one header per 20 frames, matching `kHeaderRefreshFrames = 20`
  (sprint 004 ticket 003). A parser must therefore tolerate `t` frames
  arriving without a preceding `thdr` in its capture window, and must cache
  the last header seen.
- **Widths**: FULL `thdr` measured **85 B** on hardware against the host
  test's predicted 86 B — effectively exact. `t` frames were 29–47 B here
  because every value was zero (see the caveat below); the host-predicted
  138 B for realistic large values remains the figure to size buffers
  against, and it is comfortably under `RadioTransport::kMaxPayloadBytes`
  (200).

### Caveat on these specific numbers

`STATUS` reported `connL=0 connR=0 ready=0` for this run — the Nezha brick's
wheels were not reporting connected, so **every telemetry column was zero**.
That validates the frame's *shape, cadence, column set and header-memo
behavior*, which is what this issue was blocked on, but it does **not**
exercise realistic value magnitudes or field widths. A follow-up capture with
a powered brick and a moving robot is still wanted before `tlm.py`'s
numeric parsing is considered proven.

### Other v6 behavior confirmed in the same session

Directly relevant to the tools this issue retrofits:

- `VER` → `ver 1.0.10`, matching `pxt.json` (sprint 008 fixed ten bumps of
  drift where it reported `1.0.0`). Deploy verification via VER now works.
- `GET` dumps 18 fields including the new `default_cruise 150.0`,
  `rotational_slip 0.952`, `stall_clear 0.0`.
- `STATUS` → `status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0
  i2cf=0 tlm=off next=2` — `otos=0` is truthful here (tovez has no OTOS),
  which is sprint 004 ticket 004's fix working as intended rather than the
  old hardcoded `false`.
- `TLM BUFFER` → `err 6` (sprint 008 ticket 005; previously accepted silently).
- `WHEELS_X` with `timeout=0` → `err 3` (sprint 008 ticket 001; previously
  left a stale kernel lease armed).

### One tooling defect found immediately, relevant to this issue's scope

`tools/robotlink.py` cannot be imported under this repo's own venv:
`uv run python` has **no `pyserial`**, while the system `python3` has 3.5.
Every bench tool in `tools/` therefore runs only under a different
interpreter than the project's own test/dev environment. This is a concrete
instance of `tools-link-layer-consolidation.md`'s stale-venv complaint and
should be fixed as part of this sprint's link-layer consolidation — declaring
`pyserial` in `pyproject.toml` is the obvious fix.

## Realistic-value capture, tovez, 2026-08-24 (supersedes the all-zero caveat)

The earlier capture's caveat is now discharged. With the kernel awake
(`ready=1 connL=1 connR=1`) and the robot driving, a real `TLM FULL` frame:

```
t 25 988992 31 142 -16 11737 0 0 0 -122 126 3 101 286 3319 -1300 1800 0 0 0
```

- **75 bytes** — the widest observed with live values, against
  `RadioTransport::kMaxPayloadBytes` = 200. Comfortable margin; the host
  test's 138 B realistic-worst-case prediction remains the number to size
  buffers against, and is not exceeded here.
- Columns carry real magnitudes: `flags=31`, pose `x=142 y=-16 h=11737`
  (centidegrees), velocities `vl=-122 vr=126`, `i2cf=3`, `cyc=101`,
  encoder positions `posl=286 posr=3319`, duty `dutl=-1300 dutr=1800`.
- `ox/oy/oh` are 0 — tovez has no OTOS, which is correct, not missing data.
  A parser must not treat zero OTOS columns as a fault.

`tlm.py` can now be written and validated against captured real frames rather
than synthetic ones.

## GO_TO_W confirmed working with no OTOS fitted

Also confirmed this session, relevant to any tool that drives world-frame
moves: `GO_TO_W 120 0 120 25 8000` over the wire **dispatched and drove** on
tovez, which has no OTOS. Before sprint 006 ticket 007 this returned
`err 6` (`kUnimplemented`) on every robot without one — i.e. most of the
fleet. The `EncoderPoseSource` fallback works on real hardware.

## Two wire-behaviour gotchas for the tooling

1. **The v6 `RUN` verb is a deliberate stub.** `WireAdapter::onRun()` returns
   `kUnknown` for every name ("no registration table"), so `RUN gap #1` fails
   while the **legacy `RUN:gap` prefix works** and returns `GAP:0`. Any tool
   that triggers on-robot routines must use the legacy colon form.
2. **A freshly booted robot reports `ready=0 connL=0 connR=0 i2cf=0` until
   something ticks the kernel** — identical to a robot with a dead brick. Tools
   must not treat that state as a hardware fault; issue a block-path command
   (e.g. `RUN:straight:15`) or a motion verb first. See
   `unpowered-nezha-brick-wedges-program-at-boot.md`'s correction note.
