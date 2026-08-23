---
status: pending
split_from: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
sprint: '005'
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
