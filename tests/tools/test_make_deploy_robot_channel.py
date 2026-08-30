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
  static constexpr int kChannel = 4;
  static constexpr int kGroup = 10;
  static constexpr int kTransmitPower = 7;
};
}  // namespace diffDrive
"""


def _write_robot_config(robots_dir, name, channel, group=None):
    """Write a synthetic robot config. `group=None` omits
    `radio_group` entirely -- the legacy shape every config had before
    2026-08-30, which must still build."""
    robots_dir.mkdir(parents=True, exist_ok=True)
    connection = {"radio_channel": channel}
    if group is not None:
        connection["radio_group"] = group
    (robots_dir / f"{name}.json").write_text(
        json.dumps({"connection": connection})
    )


def _kgroup(deploy):
    text = (deploy / "src" / "comms" / "radio_transport.h").read_text()
    m = re.search(r"kGroup = (\d+);", text)
    assert m, "kGroup constant not found in scratch radio_transport.h"
    return int(m.group(1))


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


def test_group_is_injected_from_config_alongside_channel(scratch_repo):
    """Both constants are per-robot as of 2026-08-30 (stakeholder
    ruling): the robot does NOT derive its address at boot, it is baked
    from the robot's config. This REPLACES an earlier test asserting
    kGroup was never touched."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "gopiv", 47, group=60)
    assert make_deploy._inject_radio_channel(str(deploy), "gopiv") == (47, 60)
    assert _kchannel(deploy) == 47
    assert _kgroup(deploy) == 60


def test_a_config_with_no_group_keeps_the_fleet_default(scratch_repo):
    """Absence is not an error: no config carried a group before
    2026-08-30 and the whole fleet is on 10 by radio-robot-elite's
    proto contract, so a legacy config must still build, unchanged."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez", 3)          # no radio_group
    assert make_deploy._inject_radio_channel(str(deploy), "tovez") == (
        3, make_deploy.DEFAULT_RADIO_GROUP)
    assert _kgroup(deploy) == 10


def test_transmit_power_is_still_never_touched(scratch_repo):
    """kTransmitPower sits beside the two injected constants and has no
    per-robot surface -- it must stay outside both regexes' reach."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez", 3, group=108)
    make_deploy._inject_radio_channel(str(deploy), "tovez")
    assert "kTransmitPower = 7" in (
        deploy / "src" / "comms" / "radio_transport.h").read_text()


def test_a_non_integer_group_fails_loudly(scratch_repo):
    deploy, robots_dir = scratch_repo
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / "tovez.json").write_text(json.dumps(
        {"connection": {"radio_channel": 3, "radio_group": "108"}}))
    with pytest.raises(SystemExit, match="expected an integer"):
        make_deploy._inject_radio_channel(str(deploy), "tovez")


# --- the derivation: how a pair is ASSIGNED, never how one is read ------


@pytest.mark.parametrize("name,pair", [
    ("gopiv", (47, 60)),
    ("vevov", (37, 43)),
    ("tovez", (55, 108)),
    ("zeguz", (25, 19)),      # channel 25 is INCLUSIVE
    ("zuzuz", (25, 1)),       # n = 0, the floor
    ("tatat", (73, 126)),     # n = 3124, the ceiling
    ("zuzuv", (27, 1)),       # n = 1 -- reverses to vuzuz under a
                              # little-endian encoder, so this vector
                              # catches a reversed digit order that
                              # palindromes (zavaz, zuzuz) cannot.
])
def test_derive_radio_from_name_matches_the_spec(name, pair):
    assert make_deploy.derive_radio_from_name(name) == pair


@pytest.mark.parametrize("name", [
    "", "tove", "tovezz", "robot1", "GAUTI".lower(), "uzuzu", "zuzuq", None,
])
def test_a_name_outside_the_codebook_derives_nothing(name):
    """base5 is undefined outside the five-letter CVCVC codebook, so
    there is no address to invent. `gauti` is the trap -- a real
    hostname on this rig whose position 2 is a vowel."""
    assert make_deploy.derive_radio_from_name(name) is None


def test_the_derivation_never_emits_a_reserved_channel_or_group():
    """3/4/7 keep the legacy fleet convention and MakeCode's
    unconfigured default clear; 0/10 keep the relay's !C space clear."""
    consonants, vowels = "zvgpt", "uoiea"
    pairs = [make_deploy.derive_radio_from_name(a + b + c + d + e)
             for a in consonants for b in vowels for c in consonants
             for d in vowels for e in consonants]
    assert len(pairs) == 3125 and None not in pairs
    assert len(set(pairs)) == 3125                       # bijective
    assert not ({3, 4, 7} & {ch for ch, _ in pairs})
    assert not ({0, 10} & {gp for _, gp in pairs})


def test_config_wins_over_the_derivation_because_names_can_collide(
        scratch_repo):
    """The whole reason the config is authoritative: a name is 32 bits
    of DEVICEID reduced to 3125 values, so two boards CAN share one and
    derive the same pair. Config is the escape hatch, and the build
    must honour it over the computed value."""
    deploy, robots_dir = scratch_repo
    assert make_deploy.derive_radio_from_name("gopiv") == (47, 60)
    _write_robot_config(robots_dir, "gopiv", 61, group=77)   # hand override
    assert make_deploy._inject_radio_channel(str(deploy), "gopiv") == (61, 77)
    assert (_kchannel(deploy), _kgroup(deploy)) == (61, 77)


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
