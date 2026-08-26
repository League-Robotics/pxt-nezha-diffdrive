"""tests/tools/test_make_deploy_profile.py -- pins
`tools/make_deploy.py`'s per-robot wire-identity ("`kProfile`")
injection: `--robot` now selects the `id <drivetrain> <profile>
<version>` reply's `profile` field compiled into the hex, not just the
flash target and radio channel. The value baked is the target robot's
own fleet name -- radio-robot-lib's per-robot config filename stem
(`radio-robot-lib/config/robots/<robot>.json`), per the reference
design in `radio-robot-elite/src/firm/main.cpp`
(`Config::kRobotProfileName`, "baked from the robot JSON's own ...
filename stem"). No field is read OUT of that file; its mere existence
and readability is what `_read_robot_profile()` checks, same posture as
`_read_robot_radio_channel()`.

This closes the defect where `src/comms/protocol.cpp`'s `kProfile` was
a hand-written constant frozen fleet-wide at `"tovez"` -- every board,
including vevov, reported `"tovez"` over the wire `ID` verb regardless
of which robot it actually was.

Every test here monkeypatches `make_deploy.RADIO_ROBOT_LIB` to a
`tmp_path` fixture tree, same convention as
`test_make_deploy_robot_channel.py` -- none of this depends on the real
sibling `radio-robot-lib` checkout being present on whatever machine
runs `uv run pytest`.

Run with::

    uv run pytest tests/tools/test_make_deploy_profile.py
"""

import json
import pathlib
import re
import sys

import pytest

# tests/tools/test_make_deploy_profile.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


# A trimmed but structurally real protocol.cpp -- only the identity
# constants classify_attempt()/_inject_profile() actually care about
# need to be present and shaped correctly. kDrivetrain and kVersion
# sit right next to kProfile, each also a quoted
# `constexpr const char*`, so the fixture pins that the injection
# regex targets kProfile specifically and leaves its neighbors alone.
_PROTOCOL_CPP_FIXTURE = """\
namespace diffDrive {
namespace {
constexpr const char* kDrivetrain = "diffdrive";
constexpr const char* kProfile = "unbaked";
constexpr const char* kVersion = "1.0.10";
}  // namespace
}  // namespace diffDrive
"""


def _write_robot_config(robots_dir, name, channel=4):
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / f"{name}.json").write_text(
        json.dumps({"connection": {"radio_channel": channel}})
    )


def _kprofile(deploy):
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    m = re.search(r'kProfile = "([^"]*)"', text)
    assert m, "kProfile constant not found in scratch protocol.cpp"
    return m.group(1)


@pytest.fixture
def scratch_repo(tmp_path, monkeypatch):
    """A scratch deploy directory carrying a synthetic
    src/comms/protocol.cpp, and RADIO_ROBOT_LIB monkeypatched to a
    synthetic config tree under the same tmp_path -- neither the real
    sibling checkout nor this repo's own working tree is ever touched."""
    deploy = tmp_path / "deploy-head"
    (deploy / "src" / "comms").mkdir(parents=True)
    (deploy / "src" / "comms" / "protocol.cpp").write_text(
        _PROTOCOL_CPP_FIXTURE
    )
    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )
    return deploy, robots_dir


# --- the acceptance criteria's own property: a build for robot X bakes
# --- profile X ----------------------------------------------------------


def test_vevov_build_bakes_profile_vevov(scratch_repo):
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "vevov")
    make_deploy._inject_profile(str(deploy), "vevov")
    assert _kprofile(deploy) == "vevov"


def test_tovez_build_bakes_profile_tovez(scratch_repo):
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez")
    make_deploy._inject_profile(str(deploy), "tovez")
    assert _kprofile(deploy) == "tovez"


def test_checked_in_default_is_not_any_fleet_robot_name():
    """protocol.cpp's own checked-in kProfile literal (this repo's real
    source, not a fixture) must not be mistakable for a real board --
    the exact property the fix requires. Enumerates the known fleet
    (radio-robot-lib/config/robots/*.json) rather than hard-coding just
    vevov/tovez, so a fleet member added later is still covered."""
    path = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
    text = path.read_text()
    m = re.search(r'kProfile = "([^"]*)"', text)
    assert m, "kProfile constant not found in this repo's protocol.cpp"
    checked_in_default = m.group(1)

    robots_dir = pathlib.Path(make_deploy.RADIO_ROBOT_LIB) / "config" / "robots"
    if robots_dir.is_dir():
        fleet_names = {p.stem for p in robots_dir.glob("*.json")}
        assert checked_in_default not in fleet_names
    # Always true regardless of whether the sibling checkout is present:
    # neither robot this ticket flashes may equal the checked-in default.
    assert checked_in_default not in ("vevov", "tovez")


def test_kdrivetrain_and_kversion_are_never_touched(scratch_repo):
    """kDrivetrain and kVersion sit one line away from kProfile, each
    also a quoted `constexpr const char*` -- _inject_profile() must not
    parameterise either of them."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez")
    make_deploy._inject_profile(str(deploy), "tovez")
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    assert 'kDrivetrain = "diffdrive"' in text
    assert 'kVersion = "1.0.10"' in text


# --- the loud-failure path -----------------------------------------------


def test_missing_robot_config_fails_loudly_naming_robot_and_path(scratch_repo):
    deploy, robots_dir = scratch_repo
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_profile(str(deploy), "ghostbot")
    msg = str(exc.value)
    assert "ghostbot" in msg
    assert str(robots_dir / "ghostbot.json") in msg


def test_unreadable_robot_config_fails_loudly(scratch_repo):
    deploy, robots_dir = scratch_repo
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / "brokenbot.json").write_text("{not valid json")
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_profile(str(deploy), "brokenbot")
    assert "brokenbot" in str(exc.value)


# --- end-to-end: sync() then inject, exactly as main() calls them -------


def test_sync_then_inject_profile_end_to_end(tmp_path, monkeypatch):
    """Full pipeline against a fake repo checkout: sync() populates the
    scratch copy from pxt.json's own files[] list, then
    _inject_profile() patches the copy it just wrote -- the exact
    sequence main() runs (alongside _inject_radio_channel() and
    _inject_boot_banner(), each tested for this same seam in their own
    modules). Regression coverage for the seam itself, not just the
    substitution function in isolation."""
    repo = tmp_path / "repo"
    (repo / "test").mkdir(parents=True)
    (repo / "pxt_modules").mkdir()
    (repo / "node_modules").mkdir()
    (repo / "src" / "comms").mkdir(parents=True)
    (repo / "src" / "comms" / "protocol.cpp").write_text(
        _PROTOCOL_CPP_FIXTURE
    )
    (repo / "test" / "test.ts").write_text("// test.ts\n")
    manifest = {
        "files": ["src/comms/protocol.cpp"],
        "testFiles": ["test/test.ts"],
        "disablesVariants": ["mbdal"],
    }
    (repo / "pxt.json").write_text(json.dumps(manifest))

    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    _write_robot_config(robots_dir, "tovez")

    deploy = tmp_path / "deploy-head"
    monkeypatch.setattr(make_deploy, "REPO", str(repo))
    monkeypatch.setattr(make_deploy, "DEPLOY", str(deploy))
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )

    make_deploy.sync()
    make_deploy._inject_profile(str(deploy), "tovez")

    assert _kprofile(deploy) == "tovez"
