"""tests/tools/test_make_deploy_geometry.py -- pins
`tools/make_deploy.py`'s OPT-IN per-robot geometry bake
(`_inject_geometry()`), which substitutes `motion_engine.h`'s
`travelCalib_` / `trackWidth_` / `rotationalSlip_` in the per-robot
scratch copy from the robot's own
`geometry.firmware_bake` block.

The opt-in posture is the whole point and the reason these tests are
worth having. Surveyed 2026-08-28, the fleet's configs do NOT describe
what is actually flashed -- tovez's config says trackwidth 115 / slip
1.0 against firmware defaults of 114.2 / 0.952, and togov's says
126 / 0.92. An unconditional injection would therefore have silently
retuned three robots nobody asked to touch. So: no `firmware_bake`
block means NO substitution and a byte-identical build, and that
absence is not an error.

Every test monkeypatches `make_deploy.RADIO_ROBOT_LIB` to a `tmp_path`
tree, same convention as `test_make_deploy_profile.py` -- nothing here
depends on the real sibling `radio-robot-lib` checkout existing.

Run with::

    uv run pytest tests/tools/test_make_deploy_geometry.py
"""

import json
import pathlib
import sys

import pytest

# tests/tools/test_make_deploy_geometry.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)

_HEADER = """\
  float travelCalib_ = 0.7878f;  // [mm/deg] wheel travel per shaft degree
  float trackWidth_ = 114.2f;
  float rotationalSlip_ = 0.952f;
"""


def _deploy(tmp_path, text=_HEADER):
    path = tmp_path / "deploy" / "src" / "motion"
    path.mkdir(parents=True)
    (path / "motion_engine.h").write_text(text)
    return tmp_path / "deploy"


def _config(tmp_path, robot, geometry):
    root = tmp_path / "lib" / "config" / "robots"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return tmp_path / "lib"


def _read(deploy):
    return (deploy / "src" / "motion" / "motion_engine.h").read_text()


def test_bakes_every_declared_constant(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov", {"firmware_bake": {
                            "travel_calib": 0.7122,
                            "trackwidth": 128.0,
                            "rotational_slip": 0.995,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    text = _read(deploy)
    assert "float travelCalib_ = 0.7122f;" in text
    # 128.0 must render as `128.0f`, never `128f`: an integer literal
    # cannot carry an `f` suffix and the firmware would not compile.
    assert "float trackWidth_ = 128.0f;" in text
    assert "128f;" not in text
    assert "float rotationalSlip_ = 0.995f;" in text
    assert dict(applied) == {"travel_calib": 0.7122, "trackwidth": 128.0,
                             "rotational_slip": 0.995}


def test_no_bake_block_leaves_the_file_untouched(tmp_path, monkeypatch):
    """The fleet-safety property: tovez must build exactly as before."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez",
                                    {"trackwidth": 115, "rotational_slip": 1.0})))
    assert make_deploy._inject_geometry(str(deploy), "tovez") == []
    assert _read(deploy) == _HEADER


def test_missing_config_file_is_not_an_error(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    (tmp_path / "lib" / "config" / "robots").mkdir(parents=True)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))
    assert make_deploy._inject_geometry(str(deploy), "nosuch") == []
    assert _read(deploy) == _HEADER


def test_partial_block_bakes_only_what_it_names(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": 0.7122}})))
    make_deploy._inject_geometry(str(deploy), "vevov")
    text = _read(deploy)
    assert "float travelCalib_ = 0.7122f;" in text
    assert "float trackWidth_ = 114.2f;" in text          # untouched
    assert "float rotationalSlip_ = 0.952f;" in text      # untouched


@pytest.mark.parametrize("bad", [0, -1, "0.71", None])
def test_rejects_a_nonpositive_or_nonnumeric_value(tmp_path, monkeypatch, bad):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": bad}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_fails_loudly_when_the_declaration_moves(tmp_path, monkeypatch):
    """If motion_engine.h stops matching, the build must stop -- a
    geometry bake that silently did nothing is the defect this whole
    mechanism exists to prevent."""
    deploy = _deploy(tmp_path, text="  float travelCalibration_ = 0.7878f;\n")
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": 0.7122}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")
