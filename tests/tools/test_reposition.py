"""tests/tools/test_reposition.py -- pins `tools/reposition.py`'s
geofence: `Repositioner.go()` refuses a move whose projected path
leaves the playfield margin, and refuses it BEFORE anything reaches
the wire.

**Why this exists.** Sprint 018 ticket 002 added `field.check_path()`
and pinned it -- and then nothing called it. `grep -rn 'check_path' tools
tests` returned `field.py` and its own test file, for three sprints,
while `Repositioner.go()` sent `RUN:goto:{x}:{y}` to any caller-supplied
point. `.claude/rules/playfield-testing.md` is explicit that the check
is mandatory and that driving off the playfield is a failure, not a
synonym for driving. A test that only pinned the pure function was
exactly as much protection as no check at all, so these tests assert on
what the LINK RECEIVED, not on a return value: a refusal that has
already sent the seed has still changed the robot.

Everything here runs against an injected fake link and fake camera --
no robot, no relay, no camera. Nothing in this file is a MEASURED claim
about hardware, because nothing in it touches any.

Run with::

    uv run pytest tests/tools/test_reposition.py
"""
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import field  # noqa: E402  (path must be set up first)
from reposition import Repositioner  # noqa: E402


class FakeLink:
    """Records every line sent. `lines()` replays a canned reply set
    each time it is called, which is enough for `go()`'s two waiters
    (`OCAL:seeded` and `GOTO:end`/`FACE:end`) -- the point of the fake
    is the `sent` list, not the dialogue."""

    def __init__(self, replies=('OCAL:seeded', 'GOTO:end', 'FACE:end')):
        self.sent = []
        self._replies = list(replies)

    def send(self, line):
        self.sent.append(line)

    def lines(self, _secs):
        return list(self._replies)


class FakeCam:
    """Hands back a fixed pose, or a sequence of them."""

    def __init__(self, *poses):
        self._poses = list(poses)

    def fix(self, n=8):
        if len(self._poses) > 1:
            return self._poses.pop(0)
        return self._poses[0]


def _goto_lines(link):
    return [s for s in link.sent if s.startswith('RUN:goto')]


# --- the refusal ---------------------------------------------------------

def test_go_refuses_a_target_outside_the_margin_and_sends_nothing():
    """The whole point: not merely a False return, but an untouched
    wire. `go()` seeds the robot's world frame before it drives, so a
    check placed after the seed would leave the robot re-seeded for a
    move that never ran."""
    link = FakeLink()
    rep = Repositioner(link, FakeCam((0.0, 0.0, 0.0)))
    with pytest.raises(field.PathRefused) as exc:
        rep.go(60.0, 0.0, 90.0, echo=False)
    assert link.sent == [], (
        f'a refused move must send nothing at all; sent {link.sent}')
    assert '60.0' in str(exc.value), 'the refusal does not name the target'


def test_go_refuses_a_legal_target_when_the_robot_starts_outside_the_margin():
    """Target legal, path not: the camera says the robot is currently
    outside the margin, so the leg back in starts out of bounds. A
    tool that validated only its destination would arm this."""
    link = FakeLink()
    rep = Repositioner(link, FakeCam((0.0, 40.0, 0.0)))   # 40 > 32.65
    with pytest.raises(field.PathRefused):
        rep.go(0.0, 0.0, 0.0, echo=False)
    assert link.sent == []


def test_go_refuses_before_the_seed_not_after_it():
    """Stated separately from the `sent == []` assertions because it is
    the ordering that matters, and ordering is what regresses: a check
    dropped in just before `RUN:goto` would still refuse the drive, but
    only after `RUN:seedxy` had rewritten the robot's world frame."""
    link = FakeLink()
    rep = Repositioner(link, FakeCam((0.0, 0.0, 0.0)))
    with pytest.raises(field.PathRefused):
        rep.go(0.0, 60.0, 0.0, echo=False)
    assert not any(s.startswith('RUN:seedxy') for s in link.sent)


def test_check_path_is_callable_on_the_repositioner_itself():
    """The gate lives on the class, so the planner sprint 034 ticket
    009 merges in here (`tour_run.place()`) keeps it rather than
    re-deriving one."""
    rep = Repositioner(FakeLink(), FakeCam((0.0, 0.0, 0.0)))
    assert rep.check_path((0.0, 0.0, 0.0), 50.0, 30.0) is None
    with pytest.raises(field.PathRefused):
        rep.check_path((0.0, 0.0, 0.0), 60.0, 0.0)


# --- the accept path -----------------------------------------------------

def test_go_drives_an_in_bounds_target():
    """The geofence must not block a legal move -- a check that refuses
    everything is as useless as one that refuses nothing. The NE dot
    (50, 30) is a real staging point every tour starts from."""
    link = FakeLink()
    rep = Repositioner(link, FakeCam((0.0, 0.0, 0.0)))
    rep.go(50.0, 30.0, 180.0, tries=1, echo=False)
    assert _goto_lines(link) == ['RUN:goto:50.0:30.0']
    assert link.sent[0].startswith('RUN:seedxy'), (
        'the seed must still precede the drive on an accepted move')


def test_a_target_already_within_tolerance_still_sends_nothing():
    """Unchanged behaviour, pinned because the new check sits right
    beside this early return: arriving is not a reason to command."""
    link = FakeLink()
    rep = Repositioner(link, FakeCam((50.0, 30.0, 180.0)))
    assert rep.go(50.0, 30.0, 180.0, echo=False) == (50.0, 30.0, 180.0)
    assert link.sent == []
