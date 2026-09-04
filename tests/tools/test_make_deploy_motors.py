"""tests/tools/test_make_deploy_motors.py -- pins `tools/make_deploy.py`'s
OPT-IN per-robot motor mapping bake (`_inject_motors()`): which Nezha
port is each side and the sign that makes +command drive it forward,
substituted into the scratch copy of `src/shims.cpp` from the robot's
`geometry.firmware_bake.motors` block.

Why it exists: MEASURED tovez 2026-09-04,
captures/bench-acceptance-029-20260904d/heading-probe.log -- the
tracked default is vevov's wiring, and on tovez (wired the other way
round, as radio-robot-lib's motors block had said since August) it
drove every straight BACKWARDS while pivots still turned the commanded
way. Same opt-in posture as the geometry bake: no block, byte-identical
build.

Run with::

    uv run pytest tests/tools/test_make_deploy_motors.py
"""
import json
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402

_SHIMS = """\
struct Rig {
  NezhaMotorPort left{1, -1};    // left = M1, mirrored
  NezhaMotorPort right{2, +1};   // right = M2
  CodalClock clock;
};
"""


def _deploy(tmp_path):
    deploy = tmp_path / "deploy"
    (deploy / "src").mkdir(parents=True)
    (deploy / "src" / "shims.cpp").write_text(_SHIMS)
    return deploy


def _config(tmp_path, robot, geometry):
    lib = tmp_path / "radio-robot-lib"
    robots = lib / "config" / "robots"
    robots.mkdir(parents=True, exist_ok=True)
    (robots / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return lib


def _read(deploy):
    return (deploy / "src" / "shims.cpp").read_text()


def test_tracked_default_matches_the_regex_sites():
    """The real shims.cpp must expose exactly one site per key, or the
    bake would exit at build time on the day it is first needed."""
    text = (_REPO_ROOT / "src" / "shims.cpp").read_text()
    for key, pattern in make_deploy._MOTOR_BAKE_RES.items():
        assert len(pattern.findall(text)) == 1, key


def test_tovez_wiring_swaps_and_inverts(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "tovez", {"firmware_bake": {"motors": {
            "left_port": 2, "fwd_sign_left": -1,
            "right_port": 1, "fwd_sign_right": 1}}})))
    applied = make_deploy._inject_motors(str(deploy), "tovez")
    text = _read(deploy)
    assert "NezhaMotorPort left{2, -1};" in text
    assert "NezhaMotorPort right{1, +1};" in text
    assert dict(applied) == {"left_port": 2, "fwd_sign_left": -1,
                             "right_port": 1, "fwd_sign_right": 1}


def test_no_motors_block_leaves_shims_untouched(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "vevov", {"firmware_bake": {"trackwidth": 128.0}})))
    assert make_deploy._inject_motors(str(deploy), "vevov") == []
    assert _read(deploy) == _SHIMS


def test_no_bake_block_at_all_leaves_shims_untouched(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "gopiv", {})))
    assert make_deploy._inject_motors(str(deploy), "gopiv") == []
    assert _read(deploy) == _SHIMS


@pytest.mark.parametrize("motors", [
    {"left_port": 2, "fwd_sign_left": -1, "right_port": 1},        # missing a sign
    {"left_port": 2, "fwd_sign_left": -1, "right_port": 2, "fwd_sign_right": 1},  # same port
    {"left_port": 2, "fwd_sign_left": 0, "right_port": 1, "fwd_sign_right": 1},   # bad sign
    {"left_port": 5, "fwd_sign_left": 1, "right_port": 1, "fwd_sign_right": 1},   # bad port
])
def test_half_or_invalid_blocks_refuse(tmp_path, monkeypatch, motors):
    """A port without its sign is exactly the half-fix that reverses
    forward travel (radio-robot-lib's own _port_note); refuse loudly."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "tovez", {"firmware_bake": {"motors": motors}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_motors(str(deploy), "tovez")
