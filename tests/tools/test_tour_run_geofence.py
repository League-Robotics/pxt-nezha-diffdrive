"""tests/tools/test_tour_run_geofence.py -- pins that `tools/tour_run.py`
stages a run through the ONE repositioning loop, with the geofence and
the tolerance that staging needs.

**What changed here, and why the file survived.** Until sprint 034
ticket 009 `tour_run.place()` and `reposition.Repositioner.go()` were
two implementations of the same "put the robot on a world point,
camera-verified" job. Both drove unchecked until ticket 007; both were
then pinned SEPARATELY, in two files, because a gate that only one of
two twins has is how the twins drift. Ticket 009 merged them: `place()`
is gone and `Repositioner.go()` carries `place()`'s ordering.

So the twin-specific assertions moved to `test_reposition.py`, which
now pins the surviving loop's refusal AND its ordering. What is left
here is the half that is genuinely about `tour_run`: that it really
uses the shared class rather than a private copy, that the refusal
still reaches the wire as "nothing sent" when tour_run's own
repositioner is the one asked, and that tour_run's 1.5 deg heading
tolerance -- a deliberate, load-bearing departure from the class
default -- survived the merge.

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
import reposition  # noqa: E402
import tour_run  # noqa: E402


class FakeLink:
    """Records every line sent. `lines()` replays a canned reply set,
    which is enough for the repositioner's two waiters -- the point of
    the fake is the `sent` list, not the dialogue."""

    def __init__(self):
        self.sent = []

    def send(self, line):
        self.sent.append(line)

    def lines(self, _secs):
        return ['OCAL:seeded', 'GOTO:end', 'FACE:end']


class FakeCam:
    def __init__(self, pose):
        self._pose = pose

    def fix(self, n=8):
        return self._pose


# --- the merge actually happened -----------------------------------------

def test_tour_run_has_no_second_repositioning_loop():
    """`place()` is gone, not renamed. A module-level function that
    walks the robot onto a dot is exactly the twin ticket 009 removed."""
    assert not hasattr(tour_run, 'place'), (
        'tour_run.place() is back -- there is one repositioning loop, '
        'reposition.Repositioner, and it carries place()\'s ordering '
        'and its "98 and 94 degrees instead of west" evidence')


def test_tour_run_stages_through_the_shared_repositioner():
    """The same class object, not a lookalike: a private subclass or a
    copied loop would satisfy a name check and not this one."""
    assert tour_run.Repositioner is reposition.Repositioner


# --- what tour_run asks of it --------------------------------------------

def test_tour_run_keeps_its_1_5_degree_heading_tolerance():
    """1.5 deg, not the class default 5 (nor `place()`'s nominal 4): an
    open-loop tour turns start heading error straight into corner error
    (leg x sin theta), so 4 deg on a 100 cm leg is already 7 cm. The
    tolerance was a call-site argument before the merge and is the
    easiest thing to lose in one."""
    rep = tour_run.make_repositioner(FakeLink(), FakeCam((0.0, 0.0, 0.0)))
    assert rep.tol_deg == 1.5
    assert rep.tol_cm == 2.5


def test_tour_run_stages_from_the_ne_dot_facing_west():
    assert tour_run.START == (50.0, 30.0, 180.0)


# --- the geofence, through tour_run's own repositioner -------------------

def test_a_refused_reposition_sends_nothing():
    """Not merely a raised exception: an untouched wire. The seed is
    already a command, so a refusal issued after it has still rewritten
    the robot's world frame."""
    link = FakeLink()
    rep = tour_run.make_repositioner(link, FakeCam((0.0, 0.0, 0.0)))
    with pytest.raises(field.PathRefused) as exc:
        rep.go(60.0, 0.0, 180.0, echo=False)
    assert link.sent == [], (
        f'a refused reposition must send nothing; sent {link.sent}')
    assert '60.0' in str(exc.value)


def test_the_refusal_lands_before_the_seed():
    link = FakeLink()
    rep = tour_run.make_repositioner(link, FakeCam((0.0, 0.0, 0.0)))
    with pytest.raises(field.PathRefused):
        rep.go(0.0, 60.0, 180.0, echo=False)
    assert not any(s.startswith('RUN seedxy') for s in link.sent)


def test_a_legal_dot_is_still_driven():
    """The NE dot, the one every practice run stages from. A gate that
    refuses everything is as useless as one that refuses nothing."""
    link = FakeLink()
    rep = tour_run.make_repositioner(link, FakeCam((0.0, 0.0, 90.0)))
    rep.go(*tour_run.START, tries=1, echo=False)
    assert 'RUN goto 50.0 30.0' in link.sent
    assert link.sent[0].startswith('RUN seedxy')


def test_report_start_pose_flags_a_staging_error(capsys):
    """Staging error is a silent corner error later, so the console
    must say so. `place()` printed this line and the merge must not
    have dropped it."""
    rep = tour_run.make_repositioner(FakeLink(), FakeCam((0.0, 0.0, 0.0)))
    tour_run.report_start_pose(rep, (50.2, 30.1, 179.5), tour_run.START)
    assert '<-- OFF' not in capsys.readouterr().out
    tour_run.report_start_pose(rep, (58.0, 30.0, 180.0), tour_run.START)
    assert '<-- OFF' in capsys.readouterr().out
