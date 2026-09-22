"""tests/tools/test_make_deploy_board_seam.py -- the scratch-copy
byte-identity claim sprint 040 ticket 001's own acceptance criteria and
testing section call for: for a robot with no
`geometry.firmware_bake.board` key (every fleet robot today), the
board-composition seam must leave `make_deploy.py`'s generated build
inputs unaffected.

WHAT "BYTE-IDENTICAL" CAN AND CANNOT MEAN HERE. This ticket adds two
new tracked files (`src/platform/board.h`, `src/platform/board_nezha.cpp`)
and moves code out of `src/shims.cpp`/`src/platform/nezha_port.cpp` into
them -- so the generated scratch-copy `src/` tree as a WHOLE cannot
diff empty against a pre-ticket tree; the files on disk are genuinely
different because the source moved. What CAN be proven, and is proven
here, is that this move changed nothing about the BAKE ITSELF: absent a
`board` key, `board.h` still selects Nezha (no injector exists for that
key yet -- ticket 005 adds one), and `board_nezha.cpp` still carries
the exact `NezhaMotorPort` construction literal `src/shims.cpp` used to
carry inline, at the one site `_MOTOR_BAKE_RES` bakes over when a robot
DOES declare a `motors` block (proven separately by
`test_make_deploy_motors.py`, retargeted to this same file). Together
these are the strongest claim available without compiling two hexes
and diffing them, which is `tools/test_make_deploy_triage.py`'s /
ticket 007's job, not this one's.

Run with::

    uv run pytest tests/tools/test_make_deploy_board_seam.py
"""

import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402

# The tracked default construction (src/platform/board_nezha.cpp) as of
# this ticket -- vevov's wiring, unchanged by the board-composition
# seam itself. Mirrors test_make_deploy_motors.py's own
# DEFAULT_LEFT/DEFAULT_RIGHT constants.
_TRACKED_LEFT = "NezhaMotorPort left{1, -1};"
_TRACKED_RIGHT = "NezhaMotorPort right{2, +1};"


def _fake_robot_lib(tmp_path, robot, geometry):
    """A minimal fake radio-robot-lib config tree, same shape
    test_make_deploy_motors.py's own `_config()` helper builds -- no
    dependency on a real sibling checkout."""
    lib = tmp_path / "radio-robot-lib"
    robots = lib / "config" / "robots"
    robots.mkdir(parents=True, exist_ok=True)
    (robots / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return lib


def test_scratch_copy_carries_both_new_files(tmp_path, monkeypatch):
    """The real pxt.json's files[] (test_pxt_manifest_completeness.py
    keeps this list honest) must actually copy board.h/board_nezha.cpp
    into a scratch build -- a manifest entry alone does not prove
    _sync_scratch() picks it up."""
    deploy = tmp_path / "deploy"
    make_deploy._sync_scratch(str(deploy), "test.ts")
    assert (deploy / "src" / "platform" / "board.h").is_file()
    assert (deploy / "src" / "platform" / "board_nezha.cpp").is_file()


def test_no_board_key_leaves_board_h_at_the_nezha_default(tmp_path, monkeypatch):
    """No injector exists for `geometry.firmware_bake.board` yet (that
    is ticket 005's job) -- so for EVERY fleet robot today, board.h in
    the scratch copy must be byte-identical to the checked-in source,
    still defaulting DIFFDRIVE_BOARD to Nezha."""
    deploy = tmp_path / "deploy"
    make_deploy._sync_scratch(str(deploy), "test.ts")
    scratch_board_h = (deploy / "src" / "platform" / "board.h").read_text()
    tracked_board_h = (_REPO_ROOT / "src" / "platform" / "board.h").read_text()
    assert scratch_board_h == tracked_board_h
    assert "#define DIFFDRIVE_BOARD DIFFDRIVE_BOARD_NEZHA" in scratch_board_h


def test_no_motors_block_leaves_board_nezha_cpp_at_the_tracked_default(
    tmp_path, monkeypatch
):
    """gopiv's real config (geometry.firmware_bake with no `motors` key)
    shape, reproduced as a fake lib: `_inject_motors()` must be a
    no-op, and the scratch copy's board_nezha.cpp must still carry the
    tracked NezhaMotorPort construction verbatim -- the exact claim
    this ticket's acceptance criteria call "byte-identical" for a robot
    with no board-bake key."""
    deploy = tmp_path / "deploy"
    make_deploy._sync_scratch(str(deploy), "test.ts")
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB",
        str(_fake_robot_lib(tmp_path, "gopiv", {
            "firmware_bake": {"trackwidth": 128.0},
        })),
    )
    assert make_deploy._inject_motors(str(deploy), "gopiv") == []

    scratch_text = (deploy / "src" / "platform" / "board_nezha.cpp").read_text()
    tracked_text = (_REPO_ROOT / "src" / "platform" / "board_nezha.cpp").read_text()
    assert scratch_text == tracked_text
    assert _TRACKED_LEFT in scratch_text
    assert _TRACKED_RIGHT in scratch_text


def test_expected_cpp_files_all_land_in_the_scratch_copy(tmp_path):
    """Every file `EXPECTED_CPP_FILES` names -- including the two this
    ticket added -- must actually exist in a fresh scratch copy, or the
    real build log check it backs (`_check_translation_units()`) is
    checking for something that was never there to find."""
    deploy = tmp_path / "deploy"
    make_deploy._sync_scratch(str(deploy), "test.ts")
    missing = [
        rel for rel in make_deploy.EXPECTED_CPP_FILES
        if not (deploy / rel).is_file()
    ]
    assert not missing, f"EXPECTED_CPP_FILES entries missing from scratch copy: {missing}"
