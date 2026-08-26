"""tests/tools/test_make_deploy_robot_channel.py -- pins
`tools/make_deploy.py`'s per-robot radio-channel injection: `--robot`
now selects the radio channel compiled into the hex, not just the
flash target, read from radio-robot-lib's canonical per-robot config
(`radio-robot-lib/config/robots/<robot>.json`, `connection.
radio_channel`) rather than any table kept in this repo.

Every test here monkeypatches `make_deploy.RADIO_ROBOT_LIB` to a
`tmp_path` fixture tree, so none of this depends on the real sibling
`radio-robot-lib` checkout being present on whatever machine runs
`uv run pytest` -- the loud-failure tests in particular need to control
exactly what is (and is not) on disk.

Run with::

    uv run pytest tests/tools/test_make_deploy_robot_channel.py
"""

import json
import pathlib
import re
import sys

import pytest

# tests/tools/test_make_deploy_robot_channel.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


# A trimmed but structurally real radio_transport.h -- only the three
# constants classify_attempt()/_inject_radio_channel() actually care
# about need to be present and shaped correctly.
_RADIO_TRANSPORT_H_FIXTURE = """\
#pragma once
namespace diffDrive {
class RadioTransport {
 private:
  static constexpr uint8_t kGroup = 10;
  static constexpr int kChannel = 4;
  static constexpr int kTransmitPower = 7;
};
}  // namespace diffDrive
"""


def _write_robot_config(robots_dir, name, channel):
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / f"{name}.json").write_text(
        json.dumps({"connection": {"radio_channel": channel}})
    )


def _kchannel(deploy):
    text = (deploy / "src" / "comms" / "radio_transport.h").read_text()
    m = re.search(r"kChannel = (\d+);", text)
    assert m, "kChannel constant not found in scratch radio_transport.h"
    return int(m.group(1))


@pytest.fixture
def scratch_repo(tmp_path, monkeypatch):
    """A scratch deploy directory carrying a synthetic
    src/comms/radio_transport.h, and RADIO_ROBOT_LIB monkeypatched to a
    synthetic config tree under the same tmp_path -- neither the real
    sibling checkout nor this repo's own working tree is ever touched."""
    deploy = tmp_path / "deploy-head"
    (deploy / "src" / "comms").mkdir(parents=True)
    (deploy / "src" / "comms" / "radio_transport.h").write_text(
        _RADIO_TRANSPORT_H_FIXTURE
    )
    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )
    return deploy, robots_dir


# --- the acceptance criteria's own three builds -----------------------


def test_vevov_build_carries_channel_4(scratch_repo):
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "vevov", 4)
    make_deploy._inject_radio_channel(str(deploy), "vevov")
    assert _kchannel(deploy) == 4


def test_tovez_build_carries_channel_3(scratch_repo):
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez", 3)
    make_deploy._inject_radio_channel(str(deploy), "tovez")
    assert _kchannel(deploy) == 3


def test_unspecified_robot_default_carries_channel_4(scratch_repo):
    """main()'s own --robot default is DEFAULT_ROBOT ('vevov'), whose
    configured channel is 4 -- the same value radio_transport.h already
    carries checked in, so a build with no --robot is unchanged."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, make_deploy.DEFAULT_ROBOT, 4)
    make_deploy._inject_radio_channel(str(deploy), make_deploy.DEFAULT_ROBOT)
    assert _kchannel(deploy) == 4


def test_kgroup_is_never_touched(scratch_repo):
    """kGroup is fleet-wide, not per-robot -- _inject_radio_channel()
    must not parameterise it even though it sits one line away from
    kChannel in the same class."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez", 3)
    make_deploy._inject_radio_channel(str(deploy), "tovez")
    text = (deploy / "src" / "comms" / "radio_transport.h").read_text()
    assert "kGroup = 10" in text
    assert "kTransmitPower = 7" in text


# --- the loud-failure path ---------------------------------------------


def test_missing_robot_config_fails_loudly_naming_robot_and_path(scratch_repo):
    deploy, robots_dir = scratch_repo
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_radio_channel(str(deploy), "ghostbot")
    msg = str(exc.value)
    assert "ghostbot" in msg
    assert str(robots_dir / "ghostbot.json") in msg


def test_unreadable_robot_config_fails_loudly(scratch_repo):
    deploy, robots_dir = scratch_repo
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / "brokenbot.json").write_text("{not valid json")
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_radio_channel(str(deploy), "brokenbot")
    assert "brokenbot" in str(exc.value)


def test_robot_config_missing_radio_channel_field_fails_loudly(scratch_repo):
    deploy, robots_dir = scratch_repo
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / "fieldless.json").write_text(
        json.dumps({"connection": {}})
    )
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_radio_channel(str(deploy), "fieldless")
    msg = str(exc.value)
    assert "radio_channel" in msg
    assert "fieldless" in msg


def test_robot_config_missing_connection_block_fails_loudly(scratch_repo):
    """No 'connection' key at all, not just an empty one -- the same
    .get(...).get(...) chain must not raise an unrelated AttributeError
    for this shape; it must still report the loud, named failure."""
    deploy, robots_dir = scratch_repo
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / "noconn.json").write_text(json.dumps({}))
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_radio_channel(str(deploy), "noconn")
    msg = str(exc.value)
    assert "radio_channel" in msg
    assert "noconn" in msg


# --- end-to-end: sync() then inject, exactly as main() calls them -----


def test_sync_then_inject_channel_end_to_end(tmp_path, monkeypatch):
    """Full pipeline against a fake repo checkout: sync() populates the
    scratch copy from pxt.json's own files[] list, then
    _inject_radio_channel() patches the copy it just wrote -- the exact
    two-step sequence main() runs. Regression coverage for the seam
    itself, not just the substitution function in isolation."""
    repo = tmp_path / "repo"
    (repo / "test").mkdir(parents=True)
    (repo / "pxt_modules").mkdir()
    (repo / "node_modules").mkdir()
    (repo / "src" / "comms").mkdir(parents=True)
    (repo / "src" / "comms" / "radio_transport.h").write_text(
        _RADIO_TRANSPORT_H_FIXTURE
    )
    (repo / "test" / "test.ts").write_text("// test.ts\n")
    manifest = {
        "files": ["src/comms/radio_transport.h"],
        "testFiles": ["test/test.ts"],
        "disablesVariants": ["mbdal"],
    }
    (repo / "pxt.json").write_text(json.dumps(manifest))

    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    _write_robot_config(robots_dir, "tovez", 3)

    deploy = tmp_path / "deploy-head"
    monkeypatch.setattr(make_deploy, "REPO", str(repo))
    monkeypatch.setattr(make_deploy, "DEPLOY", str(deploy))
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )

    make_deploy.sync()
    make_deploy._inject_radio_channel(str(deploy), "tovez")

    assert _kchannel(deploy) == 3
