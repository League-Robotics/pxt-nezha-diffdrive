"""tests/tools/test_make_deploy_radio_link.py -- pins the v6 radio link's
deploy-time switch (2026-09-02): `test/test.ts` keeps
`const BOOT_RADIO_LINK = false`, and `tools/make_deploy.py`'s
`_inject_radio_link()` flips it to `true` in the SCRATCH COPY only when
`--radio-link` is given or the robot config says
`connection.v6_radio_link: true`. Off means the radio is never touched,
so MakeCode's own `radio` blocks keep working in the same program.

Run with::

    uv run pytest tests/tools/test_make_deploy_radio_link.py
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


def test_checked_in_test_ts_has_the_radio_link_off():
    text = (_REPO_ROOT / "test" / "test.ts").read_text()
    m = make_deploy._BOOT_RADIO_LINK_RE.search(text)
    assert m is not None and m.group(2) == "false"
    assert "if (BOOT_RADIO_LINK) diffDrive.enableRadioLink()" in text
    # No unconditional call survives.
    assert "\ndiffDrive.enableRadioLink()" not in text


def _scratch(tmp_path):
    deploy = tmp_path / "deploy"
    (deploy / "test").mkdir(parents=True)
    (deploy / "test" / "test.ts").write_text(
        'const BOOT_RADIO_LINK = false\nif (BOOT_RADIO_LINK) diffDrive.enableRadioLink()\n')
    return deploy


@pytest.mark.parametrize("enabled", [True, False])
def test_inject_radio_link_flips_only_the_placeholder(tmp_path, enabled):
    deploy = _scratch(tmp_path)
    assert make_deploy._inject_radio_link(str(deploy), enabled) is enabled
    text = (deploy / "test" / "test.ts").read_text()
    assert f"const BOOT_RADIO_LINK = {'true' if enabled else 'false'}" in text
    assert "if (BOOT_RADIO_LINK) diffDrive.enableRadioLink()" in text


def test_changed_test_ts_shape_is_loud(tmp_path):
    deploy = _scratch(tmp_path)
    (deploy / "test" / "test.ts").write_text("// nothing\n")
    with pytest.raises(SystemExit):
        make_deploy._inject_radio_link(str(deploy), True)


def test_robot_config_key_selects_the_default(tmp_path, monkeypatch):
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path))
    robots = tmp_path / "config" / "robots"
    robots.mkdir(parents=True)
    (robots / "on.json").write_text(json.dumps({"connection": {"v6_radio_link": True}}))
    (robots / "off.json").write_text(json.dumps({"connection": {"radio_channel": 55}}))
    assert make_deploy._read_robot_radio_link("on") is True
    assert make_deploy._read_robot_radio_link("off") is False
    assert make_deploy._read_robot_radio_link("missing") is False
