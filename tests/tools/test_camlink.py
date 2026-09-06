"""tests/tools/test_camlink.py -- pins `tools/camlink.py`: sprint 029
ticket 006's TL-02 registration fix, and sprint 034 ticket 008's ONE
in-process `Cam`.

**Why this exists.** `Cam.__init__` used to call `ensure_registered()`
unconditionally, which sent every entry in a hardcoded `MOUNTS` table to
the aprilcam daemon's `register_tag()` on EVERY tool start. The
daemon's mount registry is PERSISTENT disk state
(`state_dir/mounts/registry.json`), so this silently overwrote a fresh
remount with whatever was baked into `MOUNTS` at the time -- exactly
what happened to the 2026-09-02 tag-53 remount before this fix. This
file pins the two acceptance criteria that close TL-02:

1. Constructing a `Cam` makes zero `register_tag()` calls.
2. `Cam.register(target)` is the ONLY path that calls it, and it
   registers only what `field_calibration.json` says for `target` -- a
   robot name (`cal['robots'][target]`) or the literal `'field'`
   (`cal['field']['tags']`, the fixed ground-truth tags `--check`
   verifies against).

It also pins TL-11: a registered ROBOT tag's `mount_yaw_rad` is the
fixed -90 deg AprilCam convention plus the calibration file's
sub-degree `mount_yaw_residual_deg` -- never a probe-fitted absolute --
via `camlink.mount_yaw_rad()`, the one place that convention is added
back.

Sprint 034 ticket 008 folded the camera-subprocess wrapper into this
same class: the wrapper existed only to bridge two Python interpreters,
and `aprilcam[daemon]` is a declared dependency of this venv, so there
is one `Cam` now, reading the daemon in-process on a reader thread. The
second half of this file pins the surface that move had to preserve --
`latest`, `fix()`, timestamped `samples`, one-yield-per-REAL-frame, and
`CamDown` for a dead instrument as distinct from a tag simply not in
frame.

No real aprilcam daemon anywhere: `Cam(client=...)`/`Cam.register(...,
client=...)` take an injected double, matching this project's existing
fake-collaborator-via-constructor-injection convention (see
`test_robotlink.py`'s `FakePort`).

Run with::

    uv run pytest tests/tools/test_camlink.py
"""
import math
import pathlib
import sys
import types

import pytest

# tests/tools/test_camlink.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import camlink  # noqa: E402  (path must be set up first)


class FakeDaemonClient:
    """Records every `register_tag()` call; nothing else. Constructing
    a `camlink.Cam` around one of these, with no other daemon calls
    made, is exactly what `__init__` must do now (TL-02)."""

    def __init__(self):
        self.registered = []

    def register_tag(self, tag_id, params):
        self.registered.append((tag_id, params))


def _tag(number, yaw_rad, x, y):
    """One tag record, carrying exactly the fields `Cam.frames()`
    reads. `x=None` is a detection with NO world fix -- a real and
    common case (the daemon saw the tag but could not place it), which
    must never reach a caller as a pose of zeros."""
    world = None if x is None else types.SimpleNamespace(x=x, y=y)
    return types.SimpleNamespace(
        tag=types.SimpleNamespace(
            number=number,
            family=types.SimpleNamespace(value='apriltag')),
        world=world,
        yaw_rad=yaw_rad)


def _frame(*tags):
    """One camera frame holding `tags`. An empty frame is a frame in
    which nothing was detected -- still a real frame."""
    return types.SimpleNamespace(tags=list(tags))


class FakeStreamingClient(FakeDaemonClient):
    """`FakeDaemonClient` plus a scripted `stream_tags()`: it yields
    `frames` in order, then either ends or raises `die`. Finite by
    design, so a test can join the reader thread instead of sleeping.
    """

    def __init__(self, frames, die=None):
        super().__init__()
        self.frames = list(frames)
        self.die = die
        self.streamed = []

    def stream_tags(self, cam):
        self.streamed.append(cam)
        for frame in self.frames:
            yield frame
        if self.die is not None:
            raise self.die


_CAL = {
    'robots': {
        'vevov': {
            'tag_family': 'apriltag',
            'tag_number': 53,
            'mount_x_cm': -3.61,
            'mount_y_cm': -0.05,
            'mount_z_cm': 11.8,
            'mount_yaw_residual_deg': 1.116162341754432,
        },
        'tovez': {
            'tag_family': 'apriltag',
            'tag_number': 52,
            'mount_x_cm': -4.10,
            'mount_y_cm': 0.05,
            'mount_z_cm': 11.3,
            'mount_yaw_residual_deg': 0.0,
        },
    },
    'field': {
        'tags': {
            '10': {'tag_family': 'apriltag', 'mount_z_cm': 20.2,
                   'truth_x_cm': -50.0, 'truth_y_cm': 30.0},
            '11': {'tag_family': 'apriltag', 'mount_z_cm': 13.6,
                   'truth_x_cm': -50.0, 'truth_y_cm': -30.0},
        }
    },
}


# --- construction never registers (TL-02) ----------------------------

def test_constructing_cam_makes_zero_register_tag_calls():
    client = FakeDaemonClient()
    camlink.Cam(client=client, stream=False)
    assert client.registered == []


def test_constructing_cam_twice_still_makes_zero_register_tag_calls():
    # Not just "the first construction" -- MOUNTS/ensure_registered()
    # ran on every construction, so a regression that only skips the
    # FIRST one would still pass a single-construction test.
    client = FakeDaemonClient()
    camlink.Cam(client=client, stream=False)
    camlink.Cam(client=client, stream=False)
    assert client.registered == []


def test_constructing_a_STREAMING_cam_also_registers_nothing():
    """The streaming path is the one every bench tool takes (sprint 034
    ticket 008 folded the camera subprocess into it), so the TL-02
    guarantee has to hold there too -- not only on the `stream=False`
    construction the two tests above use."""
    client = FakeStreamingClient([_frame(_tag(53, 0.0, 1.0, 2.0))])
    cam = camlink.Cam(tag=53, client=client)
    cam._thread.join(timeout=5.0)
    assert client.registered == []


def test_mounts_table_is_gone():
    assert not hasattr(camlink, 'MOUNTS')


# --- register(): the ONLY path that calls register_tag() -------------

def test_register_robot_calls_register_tag_exactly_once():
    client = FakeDaemonClient()
    camlink.Cam.register('vevov', calibration=_CAL, client=client)
    assert len(client.registered) == 1


def test_register_robot_sends_only_that_robots_mount():
    client = FakeDaemonClient()
    camlink.Cam.register('vevov', calibration=_CAL, client=client)
    tag_id, params = client.registered[0]
    assert tag_id.number == 53
    assert tag_id.family.value == 'apriltag'
    assert params.mount_x == pytest.approx(-3.61)
    assert params.mount_y == pytest.approx(-0.05)
    assert params.mount_z == pytest.approx(11.8)


def test_register_robot_yaw_is_convention_plus_residual():
    """TL-11: the daemon-facing mount_yaw_rad is -pi/2 (the fixed,
    never-stored AprilCam convention) plus the calibration file's
    sub-degree residual -- never a bare probe-fitted absolute."""
    client = FakeDaemonClient()
    camlink.Cam.register('vevov', calibration=_CAL, client=client)
    _, params = client.registered[0]
    expected = -math.pi / 2 + math.radians(1.116162341754432)
    assert params.mount_yaw_rad == pytest.approx(expected)


def test_register_robot_with_zero_residual_is_exactly_minus_half_pi():
    client = FakeDaemonClient()
    camlink.Cam.register('tovez', calibration=_CAL, client=client)
    _, params = client.registered[0]
    assert params.mount_yaw_rad == pytest.approx(-math.pi / 2)


def test_register_unknown_robot_raises_naming_the_robot():
    client = FakeDaemonClient()
    with pytest.raises(SystemExit, match='zzzzz'):
        camlink.Cam.register('zzzzz', calibration=_CAL, client=client)


def test_register_field_registers_every_field_tag():
    client = FakeDaemonClient()
    camlink.Cam.register('field', calibration=_CAL, client=client)
    assert len(client.registered) == 2
    numbers = sorted(tag_id.number for tag_id, _ in client.registered)
    assert numbers == [10, 11]


def test_register_field_tags_carry_no_yaw_convention():
    """Field furniture has no forward direction -- its registered yaw
    is 0, not the robot -pi/2 convention (a field tag is not a robot,
    so mount_yaw_rad() never runs for it)."""
    client = FakeDaemonClient()
    camlink.Cam.register('field', calibration=_CAL, client=client)
    for _, params in client.registered:
        assert params.mount_yaw_rad == 0.0


def test_register_field_sends_the_right_heights():
    client = FakeDaemonClient()
    camlink.Cam.register('field', calibration=_CAL, client=client)
    by_number = {tag_id.number: params for tag_id, params in
                 client.registered}
    assert by_number[10].mount_z == pytest.approx(20.2)
    assert by_number[11].mount_z == pytest.approx(13.6)


def test_register_field_with_no_field_tags_raises():
    client = FakeDaemonClient()
    empty_cal = {'robots': {}, 'field': {'tags': {}}}
    with pytest.raises(SystemExit):
        camlink.Cam.register('field', calibration=empty_cal, client=client)


# --- mount_yaw_rad(): the ONE place the +90 convention is applied ----

def test_mount_yaw_rad_zero_residual_is_minus_half_pi():
    assert camlink.mount_yaw_rad(0.0) == pytest.approx(-math.pi / 2)


def test_mount_yaw_rad_adds_residual_in_radians():
    assert camlink.mount_yaw_rad(1.0) == pytest.approx(
        -math.pi / 2 + math.radians(1.0))


# --- load_calibration(): reads the real repo file without error ------

def test_load_calibration_reads_the_real_file():
    cal = camlink.load_calibration()
    assert 'vevov' in cal['robots']
    assert 'heading_offset_deg' not in cal['robots']['vevov'], (
        'TL-11: the probe-fitted absolute must be gone, replaced by '
        'mount_yaw_residual_deg')
    assert 'mount_yaw_residual_deg' in cal['robots']['vevov']


def test_real_calibration_file_has_no_mounts_table_leftovers():
    # The real file backing this repo's default_robot must carry a
    # PHYSICAL residual, matching the TL-11 acceptance criterion (never
    # a probe-fitted absolute like the pre-sprint-029 91.116). A
    # physical residual is either near 0 deg (a normally-mounted plate)
    # or near +-180 deg (a plate mounted backward -- a real, distinct
    # physical state: sprint 029 ticket 007 MEASURED tovez's plate
    # mounted 180 deg from the fleet convention, captures/
    # bench-acceptance-029-20260904d/heading-probe.log). Only a value
    # near +-90 deg is the TL-11 regression signature this test guards
    # against: someone re-storing the whole probe-fitted ABSOLUTE
    # convention value here by mistake, instead of the sub-degree
    # residual the design calls for.
    cal = camlink.load_calibration()
    residual = cal['robots'][cal['default_robot']]['mount_yaw_residual_deg']
    near_zero = abs(residual) < 10.0
    near_180 = abs(abs(residual) - 180.0) < 10.0
    assert near_zero or near_180, (
        f'mount_yaw_residual_deg={residual} looks like an absolute '
        f'heading offset (~90deg), not a physical residual')


# --- the in-process Cam (sprint 034 ticket 008) -----------------------

def _reader(client, tag=53):
    """A Cam whose reader loop is run to completion IN THIS THREAD.

    The scripted stream is finite, so `_run()` returns on its own and
    every assertion afterward sees a settled object -- no sleeping, no
    race, and no real daemon. (`start()` is exercised separately, in
    `test_the_reader_thread_publishes_without_being_driven`.)
    """
    cam = camlink.Cam(tag=tag, client=client, stream=False)
    cam._run()
    return cam


# CamDown: the instrument is gone, vs the tag merely not in frame -----

def test_unreachable_daemon_raises_camdown(monkeypatch):
    """The wrapper this replaced turned a dead daemon into an `ERR`
    line that several spawn sites discarded, so a dead camera read as
    'robot invisible'. Construction now fails loudly instead."""
    class Refusing:
        def connect(self):
            raise OSError('connection refused')

    monkeypatch.setattr(camlink, 'Discovery', lambda: Refusing())
    with pytest.raises(camlink.CamDown, match='daemon unreachable'):
        camlink.Cam()


def test_tag_not_in_frame_is_not_a_dead_daemon():
    """Frames arriving with no tag 53 in them: `notag` counts them,
    `err` stays None. Conflating these two is the failure this
    distinction exists to prevent -- a stopped daemon was once read as
    a lost robot."""
    cam = _reader(FakeStreamingClient([_frame(), _frame(_tag(99, 0, 1, 2))]))
    assert cam.notag == 2
    assert cam.err is None
    assert cam.samples == []


def test_stream_death_lands_in_err_as_camdown_text():
    client = FakeStreamingClient([], die=RuntimeError('daemon gone'))
    cam = _reader(client)
    assert cam.err is not None
    assert 'stream died' in cam.err
    assert 'daemon gone' in cam.err


# latest / samples: canonical tuple order, and stale-pose invalidation

def test_a_frame_sets_latest_in_canonical_order():
    """The daemon reports yaw in RADIANS and the tuple order this repo
    documents is `(x_cm, y_cm, yaw_deg)` -- `tools/field.py`'s
    convention, which every `rows`-taking function there assumes."""
    cam = _reader(FakeStreamingClient(
        [_frame(_tag(53, math.radians(12.5), 1.23, 4.56))]))
    assert cam.latest == pytest.approx((1.23, 4.56, 12.5))


def test_a_frame_appends_a_timestamped_sample():
    cam = _reader(FakeStreamingClient(
        [_frame(_tag(53, math.radians(12.5), 1.23, 4.56))]))
    assert len(cam.samples) == 1
    t, x, y, yaw = cam.samples[0]
    assert (x, y) == pytest.approx((1.23, 4.56))
    assert yaw == pytest.approx(12.5)
    assert isinstance(t, float)


def test_a_detection_with_no_world_fix_is_skipped_not_zeroed():
    """The daemon saw the tag but could not place it. That is not a
    pose -- publishing it would put the robot at the field centre."""
    cam = _reader(FakeStreamingClient([_frame(_tag(53, 0.0, None, None))]))
    assert cam.latest is None
    assert cam.samples == []
    assert cam.notag == 1
    assert cam.err is None


def test_stream_death_invalidates_a_previously_cached_pose():
    """A caller re-seeding the robot's world frame must not be able to
    do it from a frozen, pre-death pose."""
    client = FakeStreamingClient([_frame(_tag(53, 0.0, 1.23, 4.56))],
                                 die=RuntimeError('daemon gone'))
    cam = _reader(client)
    assert cam.err is not None
    assert cam.latest is None, (
        'a cached pose must not survive the stream being marked dead')
    assert cam.samples, 'the recorded history itself is not erased'


def test_notag_counter_resets_on_a_frame_that_has_the_tag():
    cam = _reader(FakeStreamingClient(
        [_frame(), _frame(), _frame(_tag(53, 0.0, 1.0, 2.0))]))
    assert cam.notag == 0


# one yield per REAL frame -------------------------------------------

def test_two_identical_frames_produce_two_samples():
    """One sample per REAL frame, never deduplicated and never
    synthesised: a stationary robot must be visible AS stationary. The
    inverse error is what mattered historically -- polling faster than
    the camera made ~70% of samples repeats, so anything scoring
    per-sample motion measured the camera's frame rate instead of the
    robot's."""
    frame = _frame(_tag(53, 0.0, 1.0, 2.0))
    cam = _reader(FakeStreamingClient([frame, frame]))
    assert len(cam.samples) == 2


def test_no_samples_are_invented_between_frames():
    cam = _reader(FakeStreamingClient(
        [_frame(_tag(53, 0.0, 1.0, 2.0)),
         _frame(_tag(53, 0.0, 3.0, 4.0)),
         _frame(_tag(53, 0.0, 5.0, 6.0))]))
    assert [(s[1], s[2]) for s in cam.samples] == [(1.0, 2.0), (3.0, 4.0),
                                                   (5.0, 6.0)]


def test_frames_yields_one_dict_per_frame_keyed_by_tag_number():
    cam = camlink.Cam(client=FakeStreamingClient(
        [_frame(_tag(53, 0.0, 1.0, 2.0), _tag(10, 0.0, -50.0, 30.0)),
         _frame()]), stream=False)
    got = list(cam.frames())
    assert len(got) == 2
    assert sorted(got[0]) == [10, 53]
    assert got[1] == {}


# fix(): median, and the two refusals --------------------------------

def test_fix_returns_the_median_of_recorded_samples():
    cam = _reader(FakeStreamingClient(
        [_frame(_tag(53, 0.0, 1.0, 2.0)),
         _frame(_tag(53, 0.0, 3.0, 2.0)),
         _frame(_tag(53, 0.0, 2.0, 2.0))]))
    assert cam.fix(n=3) == pytest.approx((2.0, 2.0, 0.0))


def test_fix_returns_none_once_the_stream_has_died():
    client = FakeStreamingClient([_frame(_tag(53, 0.0, 1.0, 2.0))],
                                 die=RuntimeError('daemon gone'))
    assert _reader(client).fix(n=2) is None


def test_fix_returns_none_once_the_tag_has_been_missing_too_long():
    """No `err` -- just frame after frame with no tag. A camera that
    stopped seeing the robot must stop being trusted too, or `fix()`
    hands back a pose from before the robot left frame."""
    frames = [_frame(_tag(53, 0.0, 1.0, 2.0))] + [_frame()] * 41
    cam = _reader(FakeStreamingClient(frames))
    assert cam.err is None
    assert cam.notag == 41
    assert cam.fix(n=1, stale_after=40) is None


def test_fix_returns_none_with_no_samples_yet():
    cam = camlink.Cam(client=FakeStreamingClient([]), stream=False)
    assert cam.fix(n=1) is None


def test_since_returns_only_samples_at_or_after_t0():
    cam = _reader(FakeStreamingClient(
        [_frame(_tag(53, 0.0, 1.0, 2.0)),
         _frame(_tag(53, 0.0, 3.0, 4.0))]))
    cut = cam.samples[1][0]
    assert cam.since(cut) == [cam.samples[1]]
    assert cam.since(0.0) == cam.samples


# the reader thread ---------------------------------------------------

def test_the_reader_thread_publishes_without_being_driven():
    """`start()` (which the constructor calls) must actually wire the
    thread up: every bench tool constructs a `Cam` and reads `latest`
    on the next line, with nothing in between to pump it."""
    client = FakeStreamingClient([_frame(_tag(53, 0.0, 1.0, 2.0))])
    cam = camlink.Cam(tag=53, client=client)
    assert cam.latest == pytest.approx((1.0, 2.0, 0.0))
    assert client.streamed == [camlink.CAM]
    cam.close()
    cam._thread.join(timeout=5.0)


def test_start_waits_for_a_first_sample_rather_than_returning_empty():
    """The constructor's wait is the reason a tool can test `latest`
    immediately instead of sleeping a fixed, guessed amount."""
    cam = camlink.Cam(tag=53, client=FakeStreamingClient(
        [_frame(), _frame(_tag(53, 0.0, 7.0, 8.0))]))
    assert cam.latest is not None
    cam._thread.join(timeout=5.0)


def test_a_default_cam_follows_the_documented_default_tag():
    cam = camlink.Cam(client=FakeStreamingClient([]), stream=False)
    assert cam.tag == camlink.DEFAULT_TAG == 53
