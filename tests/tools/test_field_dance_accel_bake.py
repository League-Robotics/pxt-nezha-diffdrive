"""tests/tools/test_field_dance_accel_bake.py -- pins
`tools/field_dance.py`'s `_dance_accel_decel()` helper (sprint 031
ticket 020).

`field_dance.py`'s mandatory pre-flight dance
(`.claude/rules/field-dance-first.md`: run before ANY commanded motion
on the playfield) used to hardcode `SET accel 400` / `SET decel 400`
on every run, regardless of what the connected robot's firmware was
built with. The dance's own comment says "it must not retune the
robot" -- but a hardcoded 400 does exactly that on any robot baking a
different value via `make_deploy.py`'s opt-in
`geometry.firmware_bake` (ticket 020 bakes `accel: 800` for tovez).
Every mandatory pre-flight run would otherwise silently reset a baked
accel back to the fleet default for the rest of that session (a live
`SET` persists until power-cycle), defeating the bake at exactly the
moment the project's own safety rule requires the dance to run.

`_dance_accel_decel(robot)` reads `robot`'s own baked accel/decel via
`make_deploy._read_robot_firmware_bake()`, falling back to 400 (the
compiled MotionLimits default) for either key the robot's config does
not name. Host-testable with no live robot connection: every test here
monkeypatches `make_deploy.RADIO_ROBOT_LIB` to a `tmp_path` tree, same
convention as `test_make_deploy_geometry.py`.

Run with::

    uv run pytest tests/tools/test_field_dance_accel_bake.py
"""

import json
import pathlib
import sys

import pytest

# tests/tools/test_field_dance_accel_bake.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy    # noqa: E402  (path must be set up first)
import field_dance     # noqa: E402


def _robot_config(tmp_path, robot, geometry):
    root = tmp_path / "lib" / "config" / "robots"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return tmp_path / "lib"


def test_tovez_shaped_bake_returns_baked_accel_and_fallback_decel(
        tmp_path, monkeypatch):
    """A tovez-shaped config with firmware_bake.accel: 800 and no decel
    key returns (800, 400) -- the baked accel, and 400 as the fallback
    for the unbaked decel."""
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_robot_config(tmp_path, "tovez", {
                            "firmware_bake": {"accel": 800},
                        })))
    assert field_dance._dance_accel_decel("tovez") == (800, 400)


def test_robot_with_no_firmware_bake_block_returns_400_400(
        tmp_path, monkeypatch):
    """A robot with no `firmware_bake` block at all (or no config file)
    falls back to (400, 400) -- the compiled MotionLimits default, same
    as the dance's pre-ticket-020 hardcoded behavior."""
    root = tmp_path / "lib" / "config" / "robots"
    root.mkdir(parents=True)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))
    assert field_dance._dance_accel_decel("nosuch") == (400, 400)


def test_robot_with_empty_geometry_returns_400_400(tmp_path, monkeypatch):
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_robot_config(tmp_path, "vevov", {})))
    assert field_dance._dance_accel_decel("vevov") == (400, 400)


def test_both_accel_and_decel_baked_are_both_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_robot_config(tmp_path, "gopiv", {
                            "firmware_bake": {"accel": 600, "decel": 350},
                        })))
    assert field_dance._dance_accel_decel("gopiv") == (600, 350)


def test_other_robots_unaffected_by_tovez_bake(tmp_path, monkeypatch):
    """Cross-robot isolation: baking tovez's accel must not leak into a
    second robot's own (unbaked) result, even though both configs live
    under the same RADIO_ROBOT_LIB tree."""
    root = tmp_path / "lib" / "config" / "robots"
    root.mkdir(parents=True)
    (root / "tovez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"accel": 800},
    }}))
    (root / "tigez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"rotational_slip": 0.9617},
    }}))
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))

    assert field_dance._dance_accel_decel("tovez") == (800, 400)
    assert field_dance._dance_accel_decel("tigez") == (400, 400)
