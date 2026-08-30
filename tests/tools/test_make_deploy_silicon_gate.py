"""tests/tools/test_make_deploy_silicon_gate.py -- pins
`tools/make_deploy.py`'s silicon gate (`_verify_robot_silicon()`),
added in sprint 025 ticket 003 to replace the retired per-robot radio
channel injection (`_inject_radio_channel()`, deleted this same
ticket -- see `tests/tools/test_make_deploy_robot_channel.py`, also
retired).

With the firmware now deriving its own radio channel/group at boot
from its own silicon name (sprint 025 ticket 002), `--robot <name>` is
no longer substituted into anything -- it is only compared against
what the attached board's own silicon says its name is
(`mbdeploy.devices.read_board_name()`, the only identity authority).
Trusting `--robot` unchecked would just move the staleness that used
to live in `connection.radio_channel` onto `--robot` itself, which is
exactly what this gate exists to prevent.

`_verify_robot_silicon()` gets its UID candidate from
`_resolve_robot_uid()`, which reuses `flash()`'s OWN resolution
mechanism: `mbdeploy.devices.resolve_target()` against the same
registry file (`<ELITE>/config/devices.json`) `flash()`'s `mbdeploy
deploy <robot>` subprocess call resolves `robot` against internally --
rather than a second, invented way to go from a name to a UID. A
resolved-but-not-currently-attached UID needs no separate check here:
`read_board_name(uid)` already returns `None` on its own when pyOCD
cannot find that UID among live probes, which lands in exactly the
same "could not confirm" branch as every other reason the gate could
not run.

Every test here monkeypatches `make_deploy.load_devices`,
`make_deploy.resolve_target`, and `make_deploy.read_board_name`
directly -- the module-level names `make_deploy.py` binds at import
time via its `sys.path.insert()` + `from mbdeploy.devices import ...`
seam -- rather than requiring the real sibling `mbdeploy` checkout,
the real `radio-robot-elite/config/devices.json` registry, real
pyOCD, or real hardware to be present on whatever machine runs `uv run
pytest`. Same posture the retired `test_make_deploy_robot_channel.py`
used for `make_deploy.RADIO_ROBOT_LIB`.

Also covers `_print_derived_radio_address()`, the unconditional
deploy-summary line reporting the `(channel, group)` pair `--robot`'s
name derives (via `tools/radio_address.py`'s `name_to_address()`).

Run with::

    uv run pytest tests/tools/test_make_deploy_silicon_gate.py
"""

import os
import pathlib
import sys

import pytest

# tests/tools/test_make_deploy_silicon_gate.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


def _registry(**name_by_uid):
    """Build a `load_devices()`-shaped registry: `{uid: {"uid": uid,
    "board_name": name}}`, matching the real
    `<ELITE>/config/devices.json` shape closely enough for
    `mbdeploy.devices.resolve_target()`'s own `board_name`/
    `device_name` matching to work against it."""
    return {
        uid: {"uid": uid, "board_name": name}
        for uid, name in name_by_uid.items()
    }


def _stub_resolution(monkeypatch, registry, *, importable=True):
    """Wire `make_deploy.load_devices`/`make_deploy.resolve_target` to
    resolve against a synthetic in-memory `registry` -- never the real
    sibling `mbdeploy` checkout or `<ELITE>/config/devices.json`.
    `importable=False` simulates the module-level `except ImportError`
    sentinel (`load_devices`/`resolve_target` both `None`)."""
    if not importable:
        monkeypatch.setattr(make_deploy, "load_devices", None)
        monkeypatch.setattr(make_deploy, "resolve_target", None)
        return

    def fake_load_devices(config_path):
        return registry

    def fake_resolve_target(token, devices):
        token_lower = token.lower()
        for entry in devices.values():
            if entry.get("board_name", "").lower() == token_lower:
                return entry
        raise ValueError(f"No device found matching {token!r}")

    monkeypatch.setattr(make_deploy, "load_devices", fake_load_devices)
    monkeypatch.setattr(make_deploy, "resolve_target", fake_resolve_target)


# --- _verify_robot_silicon(): the four branches -------------------------


def test_match_proceeds_and_prints_confirmation(monkeypatch, capsys):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "vevov")

    make_deploy._verify_robot_silicon("vevov", require=False)

    out = capsys.readouterr().out
    assert "vevov" in out
    assert "confirmed" in out.lower()


def test_match_proceeds_under_flash_too(monkeypatch, capsys):
    """The gate applies whether or not --flash was passed -- `require`
    only changes the fail-vs-warn split for the "could not check"
    branches, never whether a match is checked at all."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "tovez"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "tovez")

    make_deploy._verify_robot_silicon("tovez", require=True)  # must not raise/exit

    assert "tovez" in capsys.readouterr().out


def test_mismatch_exits_naming_both_requested_and_actual(monkeypatch):
    """A registry mismap (uid-1 registered as "vevov" but its silicon
    actually answers "togov") is exactly the wrong-board condition the
    gate exists to catch -- it does not matter whether the mismatch
    originated in a stale registry or a swapped board."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "togov")

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("vevov", require=False)
    msg = str(exc.value)
    assert "vevov" in msg
    assert "togov" in msg


def test_mismatch_exits_even_without_flash(monkeypatch):
    """A NAME MISMATCH is always a hard failure regardless of
    `require` -- a board is physically attached and it is the WRONG
    one, which is worth stopping for even on a plain build."""
    _stub_resolution(monkeypatch, _registry(**{"uid-9": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "zeguz")

    with pytest.raises(SystemExit):
        make_deploy._verify_robot_silicon("vevov", require=False)


def test_mismatch_exits_under_flash_too(monkeypatch):
    """Same mismatch, `require=True` this time -- still exits, and for
    the same reason (name mismatch, not "could not check"), proving the
    two failure paths are independent of `require`."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "togov")

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("vevov", require=True)
    msg = str(exc.value)
    assert "vevov" in msg
    assert "togov" in msg


def test_none_with_flash_is_a_hard_failure_unknown_robot_name(monkeypatch):
    """--robot names no board the registry has ever heard of -- there
    is no UID candidate to even try reading."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "tovez"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "vevov")

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("ghostbot", require=True)
    assert "ghostbot" in str(exc.value)


def test_none_without_flash_warns_and_continues_unknown_robot_name(
    monkeypatch, capsys
):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "tovez"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: "vevov")

    make_deploy._verify_robot_silicon("ghostbot", require=False)  # must not exit

    out = capsys.readouterr().out
    assert "ghostbot" in out
    assert "cannot confirm" in out.lower()


def test_none_with_flash_is_a_hard_failure_resolved_uid_not_attached(monkeypatch):
    """The registry knows a UID for `--robot`, but nothing currently
    live answers to it -- read_board_name() returns None on its own
    (pyOCD can't open a session against a UID no probe presents), with
    no separate liveness check needed here."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: None)

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("vevov", require=True)
    assert "vevov" in str(exc.value)


def test_none_without_flash_warns_resolved_uid_not_attached(monkeypatch, capsys):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: None)

    make_deploy._verify_robot_silicon("vevov", require=False)  # must not raise/exit
    assert "cannot confirm" in capsys.readouterr().out.lower()


def test_none_with_flash_is_a_hard_failure_read_board_name_returns_none(monkeypatch):
    """pyOCD unavailable or the probe is busy -- read_board_name()
    itself returns None even for a UID the registry does resolve."""
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: None)

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("vevov", require=True)
    assert "vevov" in str(exc.value)


def test_none_without_flash_warns_read_board_name_returns_none(monkeypatch, capsys):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    monkeypatch.setattr(make_deploy, "read_board_name", lambda uid: None)

    make_deploy._verify_robot_silicon("vevov", require=False)  # must not raise/exit
    assert "cannot confirm" in capsys.readouterr().out.lower()


def test_none_with_flash_is_a_hard_failure_mbdeploy_not_importable(monkeypatch):
    """The import-failure case (sibling `mbdeploy` checkout missing or
    moved) is folded into the exact same branch as every other "could
    not check" outcome -- simulated here the same way the module-level
    `except ImportError:` sets things up: `load_devices`/
    `resolve_target` both `None`."""
    _stub_resolution(monkeypatch, registry=None, importable=False)

    with pytest.raises(SystemExit) as exc:
        make_deploy._verify_robot_silicon("vevov", require=True)
    assert "vevov" in str(exc.value)


def test_none_without_flash_warns_mbdeploy_not_importable(monkeypatch, capsys):
    _stub_resolution(monkeypatch, registry=None, importable=False)

    make_deploy._verify_robot_silicon("vevov", require=False)  # must not raise/exit
    assert "cannot confirm" in capsys.readouterr().out.lower()


# --- _resolve_robot_uid(): reuses flash()'s own registry/resolver -------


def test_resolve_robot_uid_uses_the_same_registry_path_flash_would():
    """`_MBDEPLOY_REGISTRY` must be `<ELITE>/config/devices.json` --
    the same CWD-relative path mbdeploy's own default config resolves
    to when `flash()`'s subprocess runs with `cwd=ELITE`."""
    assert make_deploy._MBDEPLOY_REGISTRY == os.path.join(
        make_deploy.ELITE, "config", "devices.json"
    )


def test_resolve_robot_uid_returns_none_for_unknown_name(monkeypatch):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov"}))
    assert make_deploy._resolve_robot_uid("ghostbot") is None


def test_resolve_robot_uid_returns_the_matching_uid(monkeypatch):
    _stub_resolution(monkeypatch, _registry(**{"uid-1": "vevov", "uid-2": "tovez"}))
    assert make_deploy._resolve_robot_uid("tovez") == "uid-2"


# --- _print_derived_radio_address(): the deploy-summary line ------------


def test_derived_address_line_matches_radio_address_module(capsys):
    """The printed pair must be exactly what tools/radio_address.py's
    own name_to_address() computes -- not a hand-copied duplicate that
    could drift from the reference implementation ticket 001 wrote."""
    channel, group = make_deploy.radio_address.name_to_address("vevov")

    make_deploy._print_derived_radio_address("vevov")

    out = capsys.readouterr().out
    assert "vevov" in out
    assert f"channel={channel}" in out
    assert f"group={group}" in out


def test_derived_address_line_printed_unconditionally(capsys):
    """No --flash/build gating in this function itself -- main() always
    calls it once the silicon gate passes, per the acceptance criteria
    ("Printed unconditionally (build and --flash both)")."""
    make_deploy._print_derived_radio_address("tovez")
    assert "tovez derives radio channel=" in capsys.readouterr().out


def test_malformed_robot_name_fails_loudly_not_a_nonsense_pair():
    """A non-CVCVC name has no address (docs/radio-addressing.md) --
    name_to_address() raises ValueError, and this function must turn
    that into a named sys.exit, not a raw traceback or a silently
    skipped print."""
    with pytest.raises(SystemExit) as exc:
        make_deploy._print_derived_radio_address("notaname")
    assert "notaname" in str(exc.value)
