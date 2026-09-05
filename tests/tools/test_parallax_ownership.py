"""tests/tools/test_parallax_ownership.py -- sprint 031 ticket 002:
one owner for camera-parallax correction.

**Why this exists.** `tools/camlink.py::Cam.register()` registers a
robot's tag with a `mount_z_cm`, and the aprilcam daemon applies that
tag-height parallax correction itself. `tools/field_dance.py` ALSO used
to divide camera distances by a tool-side `parallax_k` from
`field_calibration.json` -- for tovez every drive read ~12% short until
`parallax_k` was force-set to 1.0 as a stop-gap
(`clasi/issues/parallax-k-and-registered-mount-z-correct-twice.md`).
Same shape as the +90 deg heading double-add fixed in fc5588f
(`tools/field.py::pose_from_registered_samples()`): two layers each
believing they own a correction.

The fix (sprint 031 ticket 002): the daemon's registered `mount_z_cm`
is the SOLE owner. `tools/field.py::registered_pose_distance()` takes
no scaling-factor argument at all -- see `test_field.py`'s tests for
that function, which pin the actual behavior. This file is the other
half: a text-based drift guard that the audited tools never grow a
`parallax_k` division back in, plus a guard on `field_calibration.json`
itself.

Text-based, not an import: `tools/field_dance.py` connects to a real
aprilcam daemon at module scope (`D = _daemon()`), which this test
environment does not have -- importing it here would either hang or
silently depend on whatever happens to be running on the host. Reading
it as plain text needs no daemon and no camera.

Run with::

    uv run pytest tests/tools/test_parallax_ownership.py
"""
import json
import pathlib

import pytest

# tests/tools/test_parallax_ownership.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
_CALIBRATION_PATH = _TOOLS_DIR / 'field_calibration.json'

# The tools this ticket's issue named as needing an audit for a
# camera-distance-divided-by-parallax_k pattern. `field_dance.py` was
# the confirmed offender; the rest were audited and found clean (they
# never read `parallax_k` in the first place) -- this list pins that
# finding so a future edit re-adding the pattern to any of them is
# caught here, not just in field_dance.py.
_AUDITED_TOOLS = [
    'field_dance.py',
    'reposition.py',
    'park.py',
    'leg_analysis.py',
    'pivot_truth.py',
    'tour_capture.py',
    'tour_chart.py',
    'tour_closedloop.py',
    'tour_practice.py',
    'tour_run.py',
    'tour_square.py',
    'tour_watch.py',
]


def _reads_parallax_k_key(text):
    """True if `text` actually looks UP a 'parallax_k' dict key --
    matches `['parallax_k']`/`["parallax_k"]`/`.get('parallax_k'`/
    `.get("parallax_k"` -- as opposed to merely mentioning the string
    in a comment or docstring (this project's own convention is to
    document a removed field by name, e.g. field_dance.py's "no longer
    carries a parallax_k entry" comment, which must not itself trip a
    plain substring check)."""
    import re
    return re.search(r"""\[['"]parallax_k['"]\]|\.get\(['"]parallax_k['"]""",
                      text) is not None


def test_field_dance_no_longer_reads_parallax_k():
    """The confirmed offender: field_dance.py used to do
    `K = _ENTRY['parallax_k']` and `... / K` twice. Neither may remain
    -- see `field.registered_pose_distance()`, which this script now
    calls instead. (Comments are free to still name the removed key,
    e.g. to document why -- this checks the key is never actually
    looked up.)"""
    text = (_TOOLS_DIR / 'field_dance.py').read_text()
    assert not _reads_parallax_k_key(text), (
        "field_dance.py must not read a 'parallax_k' key -- the "
        "daemon's registered mount_z_cm is the sole owner of camera-"
        "parallax correction (sprint 031 ticket 002)")


def test_field_dance_uses_the_shared_unscaled_distance_function():
    """Not just "no parallax_k" -- field_dance.py's two distance
    computations (drive() and the return-home check) must route
    through the one function that structurally cannot be scaled."""
    text = (_TOOLS_DIR / 'field_dance.py').read_text()
    assert text.count('registered_pose_distance(') >= 2, (
        "field_dance.py must compute both its drive distance and its "
        "return-home distance via field.registered_pose_distance()")


def test_no_audited_tool_divides_a_distance_by_parallax_k():
    """Every tool the issue named for audit, checked for the exact
    double-correction shape: reading a 'parallax_k' key at all. None of
    these (other than field_dance.py, covered above) ever did --
    tools/linefollow/ is the one place in this repo that legitimately
    uses parallax_k, and it does so against a RAW/unregistered tag
    reading, not a registered one (see tools/linefollow/DESIGN.md) --
    out of this ticket's scope."""
    offenders = []
    for name in _AUDITED_TOOLS:
        path = _TOOLS_DIR / name
        assert path.exists(), f'audited tool {name} no longer exists'
        if _reads_parallax_k_key(path.read_text()):
            offenders.append(name)
    assert offenders == [], (
        f'these audited tools read parallax_k and must not: {offenders}')


def test_field_calibration_tovez_entry_has_no_parallax_k():
    """AC: tovez's entry no longer needs (or carries) the parallax_k =
    1.0 stop-gap -- the daemon's registered mount_z_cm is sole owner
    for this robot now."""
    cal = json.loads(_CALIBRATION_PATH.read_text())
    tovez = cal['robots']['tovez']
    assert 'parallax_k' not in tovez
    assert tovez['mount_z_cm'] == 11.3


def test_field_calibration_vevov_entry_is_not_silently_changed():
    """AC: vevov's existing entry is flagged for a fast-follow re-fit,
    not silently touched by this ticket -- it still relies on its own
    parallax_k (the tools/linefollow/ raw-tag path), unchanged."""
    cal = json.loads(_CALIBRATION_PATH.read_text())
    vevov = cal['robots']['vevov']
    assert vevov['parallax_k'] == pytest.approx(1.1192)
    assert vevov['mount_z_cm'] == pytest.approx(12.0)
