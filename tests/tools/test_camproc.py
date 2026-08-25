"""tests/tools/test_camproc.py -- pins `tools/camproc.py`'s
interpreter-resolution, `ERR`-surfacing, and stale-pose-invalidation
contract.

**Why this exists.** Sprint 005 ticket 003 closes
`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
issues/tools-link-layer-consolidation.md` (code review R-24/R-26):
seven near-identical `Cam`/`CamStream`/`CamProc` scaffolds across
`tools/*.py` each hardcoded a camera-subprocess spawn (two of them a
STALE interpreter path), most of them silently discarded the
subprocess's `ERR` line, and none of them invalidated a cached pose
once the stream died -- so a dead camera could read as "robot
invisible" instead of "instrument is gone," and a mid-session camera
death could let `place()`/`fix()`-style callers re-seed the robot's
world frame from a frozen, pre-death pose. `tools/camproc.py`
replaces all seven with one `Cam` class; this file pins the exact
behavior the acceptance criteria call out, against a `Cam(_spawn=False)`
double -- no real subprocess, camera, or thread involved.

Run with::

    uv run pytest tests/tools/test_camproc.py
"""
import os
import pathlib
import sys

import pytest

# tests/tools/test_camproc.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import camproc  # noqa: E402  (path must be set up first)


# --- resolve_venv() ----------------------------------------------------

def test_resolve_venv_default_when_unset(monkeypatch):
    """No `APRILTAGS_VENV` in the environment -> the historically-
    correct hardcoded default (tour_run.py's original, working value),
    not the stale path six of the seven scaffolds this module replaces
    used to hardcode."""
    monkeypatch.delenv('APRILTAGS_VENV', raising=False)
    assert camproc.resolve_venv() == camproc._DEFAULT_VENV
    assert 'AprilTags/.venv' not in camproc.resolve_venv()


def test_resolve_venv_honors_env_override(monkeypatch):
    """`APRILTAGS_VENV` overrides the default -- the ONE designated
    resolution source; no hardcoded fallback is reached once it is
    set."""
    monkeypatch.setenv('APRILTAGS_VENV', '/fake/venv/bin/python')
    assert camproc.resolve_venv() == '/fake/venv/bin/python'


# --- Cam._handle_line(): the line-processing core, no subprocess ------

def _cam():
    """A Cam that never spawns a subprocess or thread -- exactly what
    a test needs to drive `_handle_line()` directly."""
    return camproc.Cam(_spawn=False)


def test_good_line_sets_latest_in_canonical_order():
    """camlink.py's raw line is `yaw x y`; `.latest` must come back as
    the DOCUMENTED canonical order, `(x_cm, y_cm, yaw_deg)` -- the
    order this module's and tools/field.py's docstrings both commit
    to, unifying tour_run.py's original `(x, y, yaw)` and
    tour_practice.py's `(yaw, x, y)`."""
    cam = _cam()
    assert cam.latest is None
    cam._handle_line('12.500 1.230 4.560')   # yaw=12.5, x=1.23, y=4.56
    assert cam.latest == (1.23, 4.56, 12.5)


def test_good_line_appends_timestamped_sample():
    cam = _cam()
    assert cam.samples == []
    cam._handle_line('12.500 1.230 4.560')
    assert len(cam.samples) == 1
    t, x, y, yaw = cam.samples[0]
    assert (x, y, yaw) == (1.23, 4.56, 12.5)
    assert isinstance(t, float)


def test_notag_line_does_not_touch_latest_or_samples():
    cam = _cam()
    cam._handle_line('12.500 1.230 4.560')
    before = cam.latest
    cam._handle_line('NOTAG')
    assert cam.latest == before
    assert len(cam.samples) == 1
    assert cam.notag == 1


def test_notag_counter_resets_on_a_good_line():
    cam = _cam()
    cam._handle_line('NOTAG')
    cam._handle_line('NOTAG')
    assert cam.notag == 2
    cam._handle_line('12.500 1.230 4.560')
    assert cam.notag == 0


def test_malformed_line_is_ignored_not_crashed_on():
    """A garbage line (not 3 floats) must not raise -- and must not be
    mistaken for a tag reading."""
    cam = _cam()
    cam._handle_line('not a valid camera line at all')
    assert cam.latest is None
    assert cam.samples == []
    assert cam.err is None


# --- ERR surfacing and stale-pose invalidation (R-26a) -----------------

def test_err_line_is_surfaced_not_swallowed():
    """The acceptance criterion, observed via a test double: 'A
    simulated camera ERR line reaches the calling tool.' Every one of
    the seven scaffolds this module replaces either silently ignored an
    `ERR` line (it fails float-parsing and looks like any other
    malformed line) or, at best, only checked `.err` once at startup."""
    cam = _cam()
    cam._handle_line('ERR aprilcam daemon unreachable: connection refused')
    assert cam.err == 'ERR aprilcam daemon unreachable: connection refused'


def test_err_line_invalidates_a_previously_cached_pose():
    """The acceptance criterion, verified against a fake/mocked stream:
    'A cached pose is invalidated once the camera stream is marked
    dead -- a tool cannot observe a fresh pose after the stream death.'
    Before this module, several scaffolds left `.latest` (or their own
    equivalent) frozen at its last good value after the stream died,
    so a caller polling it kept seeing a plausible-looking but stale
    pose."""
    cam = _cam()
    cam._handle_line('12.500 1.230 4.560')
    assert cam.latest is not None            # a real pose is cached

    cam._handle_line('ERR aprilcam stream died: daemon gone')

    assert cam.err is not None
    assert cam.latest is None, (
        'a cached pose must not survive the stream being marked dead')


def test_handle_line_returns_true_only_for_err():
    cam = _cam()
    assert cam._handle_line('12.500 1.230 4.560') is False
    assert cam._handle_line('NOTAG') is False
    assert cam._handle_line('garbage') is False
    assert cam._handle_line('ERR boom') is True


def test_fix_returns_none_once_err_is_set():
    """fix() must not hand back a stale median computed from
    pre-death samples once the stream has died."""
    cam = _cam()
    cam._handle_line('12.500 1.230 4.560')
    cam._handle_line('ERR aprilcam stream died: daemon gone')
    assert cam.fix(n=2) is None


def test_fix_returns_none_when_stale_after_threshold_exceeded():
    """A camera that stopped seeing the tag (no ERR, just NOTAG after
    NOTAG) must also stop being trusted -- fix() refuses once
    `stale_after` consecutive NOTAG/blank lines have arrived, matching
    the ~2s-with-no-tag threshold one of the seven scaffolds already
    used (this module makes it universal instead of one tool's private
    behavior)."""
    cam = _cam()
    cam._handle_line('12.500 1.230 4.560')
    for _ in range(41):
        cam._handle_line('NOTAG')
    assert cam.notag == 41
    assert cam.fix(n=1, stale_after=40) is None


def test_fix_returns_median_of_good_samples():
    cam = _cam()
    for line in ('0.0 1.0 2.0', '0.0 3.0 2.0', '0.0 2.0 2.0'):
        cam._handle_line(line)
    result = cam.fix(n=3)
    assert result == (2.0, 2.0, 0.0)   # median x, median y, median yaw


def test_fix_returns_none_with_no_samples_yet():
    cam = _cam()
    assert cam.fix(n=1) is None
