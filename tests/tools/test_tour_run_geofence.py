"""tests/tools/test_tour_run_geofence.py -- pins the same geofence on
the OTHER planner: `tour_run.place()` refuses to reposition along a
path that leaves the playfield margin, and refuses before sending.

`place()` and `reposition.Repositioner.go()` are two implementations of
the same "put the robot on a world point, camera-verified" job (sprint
034 ticket 009 merges them). Both drove unchecked until ticket 007;
both are pinned, separately, until they are one function -- a gate that
only one of two twins has is how the twins drift.

Injected fake link and fake camera; no robot, no relay, no camera, and
so no MEASURED claim of any kind.

Run with::

    uv run pytest tests/tools/test_tour_run_geofence.py
"""
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import field  # noqa: E402  (path must be set up first)
import tour_run  # noqa: E402


class FakeLink:
    """`place()` talks through `send_until()` only. Records the command
    of every call and reports success, so a run that is NOT refused
    walks its normal path."""

    def __init__(self):
        self.sent = []

    def send_until(self, cmd, _marker, tries=1, wait=0, echo=False):
        self.sent.append(cmd)
        return [_marker]


class FakeCam:
    def __init__(self, pose):
        self._pose = pose

    def fix(self, n=8):
        return self._pose


def test_place_refuses_an_out_of_bounds_dot_and_sends_nothing():
    link, cam = FakeLink(), FakeCam((0.0, 0.0, 0.0))
    with pytest.raises(field.PathRefused) as exc:
        tour_run.place(link, cam, 60.0, 0.0, 180.0)
    assert link.sent == [], (
        f'a refused reposition must send nothing; sent {link.sent}')
    assert '60.0' in str(exc.value)


def test_place_refuses_before_the_seed():
    """`place()` seeds the robot's world frame from the camera before
    it drives. The gate has to sit ahead of that, not between the seed
    and the goto."""
    link, cam = FakeLink(), FakeCam((0.0, 0.0, 0.0))
    with pytest.raises(field.PathRefused):
        tour_run.place(link, cam, 0.0, 60.0, 180.0)
    assert not any(s.startswith('RUN:seedxy') for s in link.sent)


def test_place_still_drives_to_a_legal_dot():
    """The NE dot, the one every practice run stages from."""
    link, cam = FakeLink(), FakeCam((0.0, 0.0, 90.0))
    assert tour_run.place(link, cam, 50.0, 30.0, 180.0, tries=1) is True
    assert 'RUN:goto:50:30' in link.sent
    assert link.sent[0].startswith('RUN:seedxy')
