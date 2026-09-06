---
id: 008
title: One in-process Cam; delete camproc.py
status: open
use-cases:
- SUC-005
depends-on:
- '003'
github-issue: ''
issue: tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One in-process Cam; delete camproc.py

## Description

`camproc.py`'s subprocess architecture exists to bridge two Python
interpreters that are now one.

    _DEFAULT_VENV = '/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'

and the class docstring says "pyserial and aprilcam do not coexist in
one interpreter here"; `camlink.py`'s module docstring says it "only
work[s] under that interpreter". **Both are false.** `pyproject.toml`
declares `aprilcam[daemon]` as a direct dependency of *this* venv --
editable, sourced from the sibling `../aprilcam` checkout -- and
`tests/calibration/field_dance.py` imports `aprilcam.mcp.connection`
directly under `uv run`. So the subprocess, the reader thread, the
`ERR`-line protocol, `APRILTAGS_VENV`, the ignored `--hz` argument and
the **second `class Cam`** all exist for nothing.

## Acceptance Criteria

- [ ] `tools/camproc.py` is deleted.
- [ ] One `Cam` class remains, in `tools/camlink.py`, in-process.
- [ ] It serves `camproc.Cam`'s consumers on the same surface --
      `latest`, `fix()`, timestamped samples, and `CamDown` distinguishing
      "daemon unreachable" from "tag not in frame". **Preserve that
      interface rather than redesigning it**; five modules depend on it.
- [ ] `_DEFAULT_VENV`, `resolve_venv()` and `APRILTAGS_VENV` are gone,
      along with the two `test_camproc.py` tests that pin them.
- [ ] `camlink.py`'s module docstring no longer claims a second
      interpreter (lines 1-8 today). The rest of that docstring -- the
      "THE DAEMON DOES THE CORRECTING, AND IT REMEMBERS" section, the
      units table, and the fixed-90-degree-convention paragraph -- is
      **correct and stays**.
- [ ] `deaths` (the subprocess-respawn counter) is **dropped**, not
      carried over. Its only reader was `tour_square.py`, which ticket
      003 deleted, and a respawn count is a subprocess concept with no
      in-process meaning. If you find a live reader, keep it as a daemon
      *reconnect* counter and say so in a comment.

### The camera-convention invariant -- do not break this

- [ ] **`field.pose_from_registered_samples()` keeps its exact
      semantics.** A *registered* sample's `yaw_rad` is already the
      robot's heading, corrected by the daemon; it must **not** be run
      through `robot_heading_from_tag_yaw()`. Read
      `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` §"Registered
      vs raw" before writing a line of this ticket.
- [ ] No new call site adds the +90 deg convention a second time. Doing
      so is the bug that produced sprint 029's consistent
      **+87 / +91 / +86 deg** bearing errors across three drives while
      three pivots looked nearly clean -- a heading *delta* cancels a
      constant offset, so pivots pass and every absolute-bearing check
      fails. `tests/tools/test_field.py::test_pose_from_registered_samples_*`
      must stay green.
- [ ] Construction still **never** registers a mount. `Cam.register()`
      is the explicit, opt-in path and stays that way -- the old
      unconditional `ensure_registered()` silently overwrote a fresh
      remount on every tool start, and that fix (TL-02) predates this
      sprint. Do not reintroduce it.

## Implementation Plan

### Approach

The review names two options: minimal (`venv = sys.executable`, keep the
subprocess) and full (fold `camlink.Cam.frames()` into an in-process
generator on a thread, delete the subprocess and the line protocol).
**Take the full one** -- the sprint's Design Rationale 5 records why: the
minimal option keeps a line protocol, a reader thread, a respawn path and
an `ERR` vocabulary to bridge nothing.

`camlink.Cam.frames()` already yields one dict per **real** frame, and
its comment explains why that matters (polling faster than the camera
made ~70% of samples repeats, so anything scoring per-sample motion
measured the camera's frame rate instead of the robot's). Preserve that
property: the thread must not synthesise samples.

### Files

- Deleted: `tools/camproc.py`, `tests/tools/test_camproc.py` (or the two
  venv tests plus whatever else no longer has a subject -- read it and
  decide, keeping any test that still pins live behaviour).
- `tools/camlink.py` -- absorb the consumer-facing surface; fix the
  docstring.
- Consumers: `tools/tour_run.py`, `tools/pivot_truth.py`,
  `tools/turn_sweep.py`, `tools/reposition.py`, `tools/tour_watch.py`,
  `tools/field.py` (check whether its `camproc` mention is a real import
  or only a docstring).
- `tests/tools/test_camlink.py`, `tests/tools/test_parallax_ownership.py`,
  `tests/tools/test_field.py`.

### Re-anchoring

Line numbers in the issue are from 2026-09-02 and `camlink.py` has
changed substantially since (the `MOUNTS` table is gone, `register()`
landed). Grep for `_DEFAULT_VENV`, `resolve_venv`, `class Cam`,
`APRILTAGS_VENV`, `deaths`.

### No daemon is required to do this ticket

Every test here uses `Cam(client=...)` with an injected fake daemon
client -- that seam already exists and `tests/tools/test_camlink.py`
already uses it. Do **not** try to start an aprilcam daemon: it needs a
Terminal launch for camera TCC permission and will not come up from an
agent process tree.

### Depends on

Ticket 003.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_camlink.py
  tests/tools/test_field.py tests/tools/test_parallax_ownership.py -q`
  (foreground, scoped).
- **New tests to write**: the in-process `Cam` against an injected fake
  client -- `latest` is invalidated when the stream raises; a frame with
  no world fix is skipped rather than yielded as zeros; `CamDown` is
  raised for an unreachable daemon and is distinguishable from "tag not
  seen"; the one-yield-per-real-frame property holds (feed two identical
  frames and assert two yields, not deduplication -- or whatever the
  existing contract is; read it first and pin what is there).
- **Verification command**: `uv run pytest tests/tools -q`
