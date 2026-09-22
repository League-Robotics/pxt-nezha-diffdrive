"""tests/tools/test_make_deploy_board_bake.py -- pins `tools/make_deploy.py`'s
OPT-IN per-robot board-selection bake (`_inject_board()`): which literal
`src/platform/board.h`'s `#define DIFFDRIVE_BOARD ...` gets rewritten to
in the scratch copy, from the robot's `geometry.firmware_bake.board`
key.

Mirrors `test_make_deploy_motors.py`'s shape: a synthetic
`board.h`-shaped scratch file, `RADIO_ROBOT_LIB` monkeypatched to a
`tmp_path` fixture tree, no dependency on a real sibling checkout for
the pure-injection tests. A separate test class at the bottom exercises
the REAL sibling `radio-robot-lib` checkout end to end (skipped when
that checkout is absent), per this ticket's own testing section.

Same opt-in posture as every other `firmware_bake` key (motors,
geometry): no `board` key, byte-identical build -- `board.h` keeps
compiling `DIFFDRIVE_BOARD_NEZHA`, the tracked default
(`src/platform/board.h`).

Run with::

    uv run pytest tests/tools/test_make_deploy_board_bake.py
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

_BOARD_H = """\
#pragma once

#define DIFFDRIVE_BOARD_NEZHA 1
#define DIFFDRIVE_BOARD_CUTEBOT_PRO 2

#ifndef DIFFDRIVE_BOARD
#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_NEZHA
#endif
"""


def _deploy(tmp_path):
    deploy = tmp_path / "deploy"
    (deploy / "src" / "platform").mkdir(parents=True)
    (deploy / "src" / "platform" / "board.h").write_text(_BOARD_H)
    return deploy


def _config(tmp_path, robot, geometry):
    lib = tmp_path / "radio-robot-lib"
    robots = lib / "config" / "robots"
    robots.mkdir(parents=True, exist_ok=True)
    (robots / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return lib


def _read(deploy):
    return (deploy / "src" / "platform" / "board.h").read_text()


def test_tracked_default_matches_the_regex_site():
    """The real board.h must expose exactly one `#define DIFFDRIVE_BOARD`
    site, or the bake would exit at build time on the day it is first
    needed."""
    text = (_REPO_ROOT / "src" / "platform" / "board.h").read_text()
    assert len(make_deploy._BOARD_BAKE_RE.findall(text)) == 1


def test_no_bake_block_at_all_is_a_pure_noop(tmp_path, monkeypatch):
    """Absent `geometry.firmware_bake` entirely: board.h is never even
    opened, let alone written."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "gopiv", {})))
    assert make_deploy._inject_board(str(deploy), "gopiv") == []
    assert _read(deploy) == _BOARD_H


def test_no_board_key_is_a_pure_noop(tmp_path, monkeypatch):
    """A robot with a `firmware_bake` block but no `board` key inside it
    (e.g. tovez's real motors-only bake) leaves board.h untouched."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "tovez", {"firmware_bake": {"trackwidth": 128.0}})))
    assert make_deploy._inject_board(str(deploy), "tovez") == []
    assert _read(deploy) == _BOARD_H


def test_explicit_nezha_still_reports_and_stays_byte_identical(tmp_path, monkeypatch):
    """`"nezha"` is an EXPLICIT no-op: it still opens/re-writes the file
    (so a broken regex site would still be caught) and still reports
    back through the applied list, unlike the absent-key case above."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "gopiv", {"firmware_bake": {"board": "nezha"}})))
    applied = make_deploy._inject_board(str(deploy), "gopiv")
    assert applied == [("board", "nezha")]
    assert _read(deploy) == _BOARD_H
    assert "#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_NEZHA" in _read(deploy)


def test_cutebot_pro_selects_the_cutebot_literal(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {"board": "cutebot-pro"}})))
    applied = make_deploy._inject_board(str(deploy), "zeguz")
    assert applied == [("board", "cutebot-pro")]
    text = _read(deploy)
    assert "#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_CUTEBOT_PRO" in text
    # Only the one site changed -- the two #define lines it selects
    # BETWEEN are untouched.
    assert "#define DIFFDRIVE_BOARD_NEZHA 1" in text
    assert "#define DIFFDRIVE_BOARD_CUTEBOT_PRO 2" in text


@pytest.mark.parametrize("board", [
    "cutebot",           # close but not the recognized spelling
    "Cutebot-Pro",       # case mismatch
    "nezha2",            # typo
    "",                  # empty string
])
def test_unrecognized_string_value_refuses_loudly(tmp_path, monkeypatch, board):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {"board": board}})))
    with pytest.raises(SystemExit) as exc_info:
        make_deploy._inject_board(str(deploy), "zeguz")
    assert repr(board) in str(exc_info.value)


@pytest.mark.parametrize("board", [1, 2.0, True, ["cutebot-pro"], {"x": 1}])
def test_malformed_type_refuses_loudly(tmp_path, monkeypatch, board):
    """A non-string `board` value (an int, a bool, a list, an object)
    must exit loudly rather than being coerced or silently ignored."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {"board": board}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_board(str(deploy), "zeguz")


def test_bad_regex_site_count_refuses_loudly(tmp_path, monkeypatch):
    """If `board.h` ever grows a second (or zero) `#define
    DIFFDRIVE_BOARD` site, the bake must refuse rather than patch the
    wrong -- or no -- line."""
    deploy = tmp_path / "deploy"
    (deploy / "src" / "platform").mkdir(parents=True)
    (deploy / "src" / "platform" / "board.h").write_text(
        "#pragma once\n// no DIFFDRIVE_BOARD define here at all\n"
    )
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {"board": "cutebot-pro"}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_board(str(deploy), "zeguz")


def test_motors_block_on_a_cutebot_pro_build_refuses(tmp_path, monkeypatch):
    """A robot declaring BOTH `board: "cutebot-pro"` and a Nezha
    `motors` bake is a stale-config trap (`_inject_motors()`'s own
    substitution site sits behind `#if DIFFDRIVE_BOARD ==
    DIFFDRIVE_BOARD_NEZHA` and would compile out entirely) -- refused
    loudly rather than silently doing nothing."""
    board_nezha_cpp = tmp_path / "deploy2" / "src" / "platform" / "board_nezha.cpp"
    board_nezha_cpp.parent.mkdir(parents=True)
    board_nezha_cpp.write_text(
        "struct NezhaBoard {\n"
        "  NezhaMotorPort left{1, -1};    // left = M1, mirrored\n"
        "  NezhaMotorPort right{2, +1};   // right = M2\n"
        "};\n"
    )
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {
            "board": "cutebot-pro",
            "motors": {"left_port": 2, "fwd_sign_left": -1,
                       "right_port": 1, "fwd_sign_right": 1},
        }})))
    with pytest.raises(SystemExit):
        make_deploy._inject_motors(str(board_nezha_cpp.parent.parent.parent),
                                    "zeguz")


def test_cutebot_pro_board_alone_does_not_trip_the_motors_refusal(tmp_path, monkeypatch):
    """`board: "cutebot-pro"` with NO `motors` block (zeguz's own real
    shape) must not trip the new cross-check -- `_inject_motors()`
    stays a plain no-op."""
    deploy = tmp_path / "deploy3"
    (deploy / "src" / "platform").mkdir(parents=True)
    (deploy / "src" / "platform" / "board_nezha.cpp").write_text(
        "struct NezhaBoard {\n"
        "  NezhaMotorPort left{1, -1};    // left = M1, mirrored\n"
        "  NezhaMotorPort right{2, +1};   // right = M2\n"
        "};\n"
    )
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(_config(
        tmp_path, "zeguz", {"firmware_bake": {"board": "cutebot-pro"}})))
    assert make_deploy._inject_motors(str(deploy), "zeguz") == []


class TestRealSiblingConfig:
    """End-to-end: `tools/make_deploy.py --robot zeguz` (a real scratch
    sync + injection, no build/compile) resolves the fleet-JSON `board`
    key to the Cutebot literal, against the REAL `radio-robot-lib`
    checkout this ticket also writes `config/robots/zeguz.json` into.
    Skips cleanly when that sibling checkout -- or the zeguz config
    specifically -- is absent, since it is a sibling repo this repo
    does not vendor or require for its own tests to pass."""

    def _zeguz_config_path(self):
        return (pathlib.Path(make_deploy.RADIO_ROBOT_LIB)
                / "config" / "robots" / "zeguz.json")

    def _skip_if_absent(self):
        lib = pathlib.Path(make_deploy.RADIO_ROBOT_LIB)
        if not lib.is_dir():
            pytest.skip(f"sibling repo radio-robot-lib not found at "
                        f"{lib} -- this test only runs in a checkout "
                        f"where it is cloned alongside this one")
        if not self._zeguz_config_path().is_file():
            pytest.skip(f"{self._zeguz_config_path()} not found -- "
                        f"zeguz's fleet config has not been created "
                        f"(or the assigned board's name changed) in "
                        f"this radio-robot-lib checkout")

    def test_read_robot_firmware_bake_resolves_cutebot_pro(self):
        self._skip_if_absent()
        bake = make_deploy._read_robot_firmware_bake("zeguz")
        assert bake.get("board") == "cutebot-pro"

    def test_inject_board_selects_the_cutebot_literal(self, tmp_path):
        self._skip_if_absent()
        deploy = _deploy(tmp_path)
        applied = make_deploy._inject_board(str(deploy), "zeguz")
        assert applied == [("board", "cutebot-pro")]
        assert ("#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_CUTEBOT_PRO"
                in _read(deploy))

    def test_zeguz_json_declares_no_measured_geometry_keys(self):
        """Sprint 041's job, not this ticket's -- no travel_calib,
        trackwidth, motors, or lag_s invented ahead of the bench
        measurements."""
        self._skip_if_absent()
        with open(self._zeguz_config_path()) as f:
            config = json.load(f)
        bake = config.get("geometry", {}).get("firmware_bake", {})
        measured_keys = {"trackwidth", "motors", "lag_s",
                          "stop_distance_mm", "rotational_slip", "accel"}
        assert not (measured_keys & set(bake)), (
            f"zeguz.json's firmware_bake declares measured geometry "
            f"keys ahead of sprint 041's bench measurements: "
            f"{measured_keys & set(bake)}"
        )

    def test_real_sync_scratch_plus_inject_board_selects_cutebot_pro(
        self, tmp_path
    ):
        """A real `_sync_scratch()` (the real `pxt.json` manifest, the
        real tracked `board.h`) followed by `_inject_board()` against
        the real `radio-robot-lib` checkout -- the closest this test
        gets to `python tools/make_deploy.py --robot zeguz` without
        invoking Docker/the pxt build itself (that full checkpoint is
        this sprint's own last-ticket build gate, not this test)."""
        self._skip_if_absent()
        deploy = tmp_path / "deploy-zeguz"
        make_deploy._sync_scratch(str(deploy), "test.ts")
        applied = make_deploy._inject_board(str(deploy), "zeguz")
        assert applied == [("board", "cutebot-pro")]
        text = (deploy / "src" / "platform" / "board.h").read_text()
        assert "DIFFDRIVE_BOARD DIFFDRIVE_BOARD_CUTEBOT_PRO" in text
