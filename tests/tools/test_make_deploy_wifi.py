"""tests/tools/test_make_deploy_wifi.py -- pins `tools/make_deploy.py`'s
`_inject_wifi_secrets()`: the gitignored `config/wifi_secrets.json`
(`{"ssid": ..., "password": ...}`) is baked into the SCRATCH COPY's
`src/comms/protocol.cpp` `kWifiSsid`/`kWifiPassword` constants, and only
there. Absent file -> both stay empty (WifiLink's own "disabled"
sentinel) and the build proceeds; a present-but-malformed file is fatal.

Run with::

    uv run pytest tests/tools/test_make_deploy_wifi.py
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

_PROTOCOL_CPP = (
    'constexpr const char* kProfile = "unbaked";\n'
    'constexpr const char* kWifiSsid = "";\n'
    'constexpr const char* kWifiPassword = "";\n'
)


def _scratch(tmp_path):
    deploy = tmp_path / "deploy"
    (deploy / "src" / "comms").mkdir(parents=True)
    (deploy / "src" / "comms" / "protocol.cpp").write_text(_PROTOCOL_CPP)
    return deploy


def test_checked_in_protocol_cpp_has_empty_placeholders():
    text = (_REPO_ROOT / "src" / "comms" / "protocol.cpp").read_text()
    assert make_deploy._K_WIFI_SSID_RE.search(text).group(0).endswith('"";')
    assert make_deploy._K_WIFI_PASSWORD_RE.search(text).group(0).endswith('"";')


def test_secrets_are_baked_into_the_scratch_copy_only(tmp_path):
    deploy = _scratch(tmp_path)
    secrets = tmp_path / "wifi_secrets.json"
    secrets.write_text(json.dumps({"ssid": "Busboom Mesh", "password": "p\"w\\d"}))
    assert make_deploy._inject_wifi_secrets(str(deploy), str(secrets)) == "Busboom Mesh"
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    assert 'kWifiSsid = "Busboom Mesh";' in text
    assert 'kWifiPassword = "p\\"w\\\\d";' in text          # C-escaped
    assert 'kProfile = "unbaked";' in text                  # untouched


def test_missing_secrets_file_leaves_the_link_disabled(tmp_path, capsys):
    deploy = _scratch(tmp_path)
    assert make_deploy._inject_wifi_secrets(str(deploy), str(tmp_path / "nope.json")) == ""
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    assert 'kWifiSsid = "";' in text and 'kWifiPassword = "";' in text
    assert "DISABLED" in capsys.readouterr().out


@pytest.mark.parametrize("content", ['{"ssid": ""}', '[]', 'not json', '{"password": "x"}'])
def test_malformed_secrets_file_is_fatal(tmp_path, content):
    deploy = _scratch(tmp_path)
    secrets = tmp_path / "wifi_secrets.json"
    secrets.write_text(content)
    with pytest.raises(SystemExit):
        make_deploy._inject_wifi_secrets(str(deploy), str(secrets))


def test_changed_protocol_cpp_shape_is_loud(tmp_path):
    deploy = _scratch(tmp_path)
    (deploy / "src" / "comms" / "protocol.cpp").write_text("// nothing here\n")
    secrets = tmp_path / "wifi_secrets.json"
    secrets.write_text(json.dumps({"ssid": "x", "password": "y"}))
    with pytest.raises(SystemExit):
        make_deploy._inject_wifi_secrets(str(deploy), str(secrets))
