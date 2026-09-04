"""tests/tools/test_camlink.py -- pins sprint 029 ticket 006's TL-02 fix
in `tools/camlink.py`.

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

No real aprilcam daemon anywhere: `Cam(client=...)`/`Cam.register(...,
client=...)` take an injected double with a `register_tag(tag_id,
params)` method that just records its calls, matching this project's
existing fake-collaborator-via-constructor-injection convention (see
`test_robotlink.py`'s `FakePort`, `test_camproc.py`'s
`Cam(_spawn=False)`).

Run with::

    uv run pytest tests/tools/test_camlink.py
"""
import math
import pathlib
import sys

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
    camlink.Cam(client=client)
    assert client.registered == []


def test_constructing_cam_twice_still_makes_zero_register_tag_calls():
    # Not just "the first construction" -- MOUNTS/ensure_registered()
    # ran on every construction, so a regression that only skips the
    # FIRST one would still pass a single-construction test.
    client = FakeDaemonClient()
    camlink.Cam(client=client)
    camlink.Cam(client=client)
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
    # The real file backing this repo's default_robot must itself carry
    # only a sub-degree residual, matching the TL-11 acceptance
    # criterion (never a probe-fitted absolute like 91.116).
    cal = camlink.load_calibration()
    residual = cal['robots'][cal['default_robot']]['mount_yaw_residual_deg']
    assert abs(residual) < 10.0, (
        f'mount_yaw_residual_deg={residual} looks like an absolute '
        f'heading offset (~90deg), not a sub-degree residual')
