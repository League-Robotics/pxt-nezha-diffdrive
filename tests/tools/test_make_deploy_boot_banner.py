"""tests/tools/test_make_deploy_boot_banner.py -- pins
`tools/make_deploy.py`'s boot-banner injection: this repo's own
`pyproject.toml` version (`0.YYYYMMDD.n`) is read, reformatted to the
on-device `DD.RR` banner string, and substituted -- together with the
target robot's name -- into the scratch copy's `test/test.ts` before
build, via the same substitution mechanism
`tests/tools/test_make_deploy_robot_channel.py` pins for the radio
channel.

The real display behavior (does the banner actually show correctly on
hardware) is NOT testable here -- no TypeScript in this repo is
executed by any test (see `test/test.ts`'s own boot-banner text pin,
`tests/host/test_boot_banner_source_pin.py`, and its docstring for what
that half proves instead). This module only proves the substitution
mechanics: the right value goes into the right placeholder, and a
missing/malformed version source fails loudly rather than silently.

Run with::

    uv run pytest tests/tools/test_make_deploy_boot_banner.py
"""

import pathlib
import sys

import pytest

# tests/tools/test_make_deploy_boot_banner.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


# --- format_boot_version(): pure, no I/O ------------------------------


def test_format_boot_version_matches_the_sprint_s_own_worked_example():
    assert make_deploy.format_boot_version("0.20260826.5") == "26.05"


def test_format_boot_version_zero_pads_single_digit_revisions():
    assert make_deploy.format_boot_version("0.20260101.3") == "01.03"


def test_format_boot_version_keeps_double_digit_revisions():
    assert make_deploy.format_boot_version("0.20261231.42") == "31.42"


def test_format_boot_version_takes_only_the_last_two_digits_of_the_minor():
    assert make_deploy.format_boot_version("0.20260826.5") != "82.05"
    assert make_deploy.format_boot_version("0.20260826.5")[:2] == "26"


def test_format_boot_version_rejects_pxt_json_shaped_version():
    """pxt.json's own `1.0.10` scheme has no day-of-month digit pair in
    its minor -- this is the sprint's own flagged interpretation
    (version comes from pyproject.toml, never pxt.json), enforced
    structurally here: a minor shorter than 2 digits cannot be a day of
    month, so it is rejected rather than silently mis-rendered."""
    with pytest.raises(ValueError):
        make_deploy.format_boot_version("1.0.10")


def test_format_boot_version_rejects_wrong_part_count():
    with pytest.raises(ValueError):
        make_deploy.format_boot_version("0.20260826")
    with pytest.raises(ValueError):
        make_deploy.format_boot_version("0.20260826.5.1")


def test_format_boot_version_rejects_non_numeric_revision():
    with pytest.raises(ValueError):
        make_deploy.format_boot_version("0.20260826.rc1")


# --- _read_repo_version() ------------------------------------------------


def test_read_repo_version_reads_pyproject_toml(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.20260826.5"\n'
    )
    monkeypatch.setattr(make_deploy, "REPO", str(tmp_path))
    monkeypatch.setattr(
        make_deploy, "_PYPROJECT", str(tmp_path / "pyproject.toml")
    )
    assert make_deploy._read_repo_version() == "0.20260826.5"


def test_read_repo_version_fails_loudly_when_pyproject_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        make_deploy, "_PYPROJECT", str(tmp_path / "pyproject.toml")
    )
    with pytest.raises(SystemExit) as exc:
        make_deploy._read_repo_version()
    assert "pyproject.toml" in str(exc.value)


def test_read_repo_version_fails_loudly_when_version_field_missing(
    tmp_path, monkeypatch
):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n')
    monkeypatch.setattr(make_deploy, "_PYPROJECT", str(pyproject))
    with pytest.raises(SystemExit):
        make_deploy._read_repo_version()


# --- _inject_boot_banner(): the scratch-copy substitution ---------------

_TEST_TS_FIXTURE = """\
const BOOT_VERSION = "00.00"
const BOOT_ROBOT = "unknown"

basic.showIcon(IconNames.Rollerskate)
basic.showString(BOOT_ROBOT + " " + BOOT_VERSION)
"""


@pytest.fixture
def scratch_test_ts(tmp_path, monkeypatch):
    """A scratch deploy directory carrying a synthetic test/test.ts,
    plus a synthetic pyproject.toml -- monkeypatched into make_deploy
    so these tests never depend on this repo's own actual version at
    the moment the suite happens to run."""
    deploy = tmp_path / "deploy-head"
    (deploy / "test").mkdir(parents=True)
    (deploy / "test" / "test.ts").write_text(_TEST_TS_FIXTURE)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.20260826.5"\n')
    monkeypatch.setattr(make_deploy, "_PYPROJECT", str(pyproject))
    return deploy


def test_inject_boot_banner_substitutes_version_and_robot(scratch_test_ts):
    make_deploy._inject_boot_banner(str(scratch_test_ts), "tovez")
    text = (scratch_test_ts / "test" / "test.ts").read_text()
    assert 'const BOOT_VERSION = "26.05"' in text
    assert 'const BOOT_ROBOT = "tovez"' in text
    # And nothing else in the fixture was disturbed.
    assert "basic.showIcon(IconNames.Rollerskate)" in text
    assert 'basic.showString(BOOT_ROBOT + " " + BOOT_VERSION)' in text


def test_inject_boot_banner_returns_the_formatted_version(scratch_test_ts):
    version = make_deploy._inject_boot_banner(str(scratch_test_ts), "vevov")
    assert version == "26.05"


def test_inject_boot_banner_fails_loudly_when_pyproject_missing(
    tmp_path, monkeypatch
):
    deploy = tmp_path / "deploy-head"
    (deploy / "test").mkdir(parents=True)
    (deploy / "test" / "test.ts").write_text(_TEST_TS_FIXTURE)
    monkeypatch.setattr(
        make_deploy, "_PYPROJECT", str(tmp_path / "no-such-pyproject.toml")
    )
    with pytest.raises(SystemExit):
        make_deploy._inject_boot_banner(str(deploy), "tovez")


def test_inject_boot_banner_fails_loudly_when_placeholder_missing(
    tmp_path, monkeypatch
):
    """test.ts's own shape drifted (placeholder renamed/removed) --
    must fail loudly rather than silently write nothing."""
    deploy = tmp_path / "deploy-head"
    (deploy / "test").mkdir(parents=True)
    (deploy / "test" / "test.ts").write_text("// no placeholders here\n")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.20260826.5"\n')
    monkeypatch.setattr(make_deploy, "_PYPROJECT", str(pyproject))
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_boot_banner(str(deploy), "tovez")
    assert "BOOT_VERSION" in str(exc.value)


# --- end-to-end: sync(), then both injections, exactly as main() calls --


def test_sync_then_inject_both_end_to_end(tmp_path, monkeypatch):
    """Full pipeline against a fake repo checkout: sync() populates the
    scratch copy, then _inject_radio_channel() and
    _inject_boot_banner() both patch the copy it just wrote -- the
    exact three-step sequence main() runs, so this is the closest this
    suite comes to proving the two injections coexist correctly in one
    scratch copy without one clobbering the other."""
    import json

    repo = tmp_path / "repo"
    (repo / "test").mkdir(parents=True)
    (repo / "pxt_modules").mkdir()
    (repo / "node_modules").mkdir()
    (repo / "src" / "comms").mkdir(parents=True)
    (repo / "src" / "comms" / "radio_transport.h").write_text(
        "static constexpr uint8_t kGroup = 10;\n"
        "static constexpr int kChannel = 4;\n"
        "static constexpr int kTransmitPower = 7;\n"
    )
    (repo / "test" / "test.ts").write_text(_TEST_TS_FIXTURE)
    manifest = {
        "files": ["src/comms/radio_transport.h"],
        "testFiles": ["test/test.ts"],
        "disablesVariants": ["mbdal"],
    }
    (repo / "pxt.json").write_text(json.dumps(manifest))
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.20260826.5"\n')

    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    robots_dir.mkdir(parents=True)
    (robots_dir / "tovez.json").write_text(
        json.dumps({"connection": {"radio_channel": 3}})
    )

    deploy = tmp_path / "deploy-head"
    monkeypatch.setattr(make_deploy, "REPO", str(repo))
    monkeypatch.setattr(make_deploy, "DEPLOY", str(deploy))
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )
    monkeypatch.setattr(make_deploy, "_PYPROJECT", str(repo / "pyproject.toml"))

    make_deploy.sync()
    make_deploy._inject_radio_channel(str(deploy), "tovez")
    make_deploy._inject_boot_banner(str(deploy), "tovez")

    channel_text = (deploy / "src" / "comms" / "radio_transport.h").read_text()
    assert "kChannel = 3;" in channel_text
    assert "kGroup = 10" in channel_text

    banner_text = (deploy / "test" / "test.ts").read_text()
    assert 'const BOOT_VERSION = "26.05"' in banner_text
    assert 'const BOOT_ROBOT = "tovez"' in banner_text
