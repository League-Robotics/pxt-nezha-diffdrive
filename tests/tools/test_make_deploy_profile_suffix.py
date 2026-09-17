"""tests/tools/test_make_deploy_profile_suffix.py -- sprint 039 ticket
002's `--profile-suffix` CLI flag on `tools/make_deploy.py`.

Per that sprint's own Migration Concerns and the project memory
`bump-the-version-before-a-behaviour-flash`: a hardware flash used to
chase the reverse-to-forward `driveTick()` hang
(`docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-
diagnosis.md`) needs to be distinguishable over `ID` from a previous
flash WITHOUT touching the repo's own `close_sprint`-owned version file
(`kVersion`, bumped exactly once per sprint per `.claude/rules/git-
commits.md`'s cadence rule). `--profile-suffix` reuses the existing
`kProfile` provenance-field mechanism `--fault-spin` already established
(`FAULT_SPIN_PROFILE_SUFFIX`, pinned by
`test_make_deploy_fault_spin.py`'s own profile tests) but makes it a
free-form, generically-named runtime pin instead of one fixed string.

This file does not repeat `test_make_deploy_profile.py`'s or
`test_make_deploy_fault_spin.py`'s own coverage of `_inject_profile()`'s
robot-validation and kDrivetrain/kVersion-untouched properties -- it
covers only what THIS ticket adds: the CLI flag's own validation (which
`main()` runs immediately after `argparse.parse_args()`, before any
`sync()`/`build()` work, so it is exercised here with no filesystem or
build mocking at all) and `_inject_profile()`'s new length guard.

Run with::

    uv run pytest tests/tools/test_make_deploy_profile_suffix.py
"""

import pathlib
import re
import sys

import pytest

# tests/tools/test_make_deploy_profile_suffix.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


# --- CLI validation: main() rejects a bad --profile-suffix before any
# --- sync()/build() work runs, so no mocking is needed here at all ------


def test_profile_suffix_combined_with_fault_spin_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["make_deploy.py", "--fault-spin", "--profile-suffix", "-x"])
    with pytest.raises(SystemExit):
        make_deploy.main()


def test_profile_suffix_combined_with_testrig_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["make_deploy.py", "--testrig", "--profile-suffix", "-x"])
    with pytest.raises(SystemExit):
        make_deploy.main()


def test_profile_suffix_combined_with_other_program_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys, "argv",
        ["make_deploy.py", "--program", "linefollow.ts",
         "--profile-suffix", "-x"])
    with pytest.raises(SystemExit):
        make_deploy.main()


@pytest.mark.parametrize("bad", [
    "-nudge hang",      # space -- would split the wire ID reply's fields
    '-nudge"hang',       # breaks the generated C string literal
    "-nudge;rm",          # shell-metacharacter-shaped, reject on principle
])
def test_profile_suffix_with_unsafe_characters_is_rejected(monkeypatch, bad):
    monkeypatch.setattr(
        sys, "argv", ["make_deploy.py", "--profile-suffix", bad])
    with pytest.raises(SystemExit):
        make_deploy.main()


def test_profile_suffix_allows_letters_digits_dash_underscore():
    # The validator itself, exercised directly (not via main(), which
    # would go on to sync()/build() a real scratch copy for a valid
    # suffix) -- confirms the allowed character class is not
    # accidentally narrower than the flag's own documented examples.
    assert re.fullmatch(r"[-\w]+", "-nudgehang0915")
    assert re.fullmatch(r"[-\w]+", "-faultspin")


# --- _inject_profile()'s new length guard --------------------------------

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
    import json
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / f"{name}.json").write_text(
        json.dumps({"connection": {"radio_channel": channel}}))


@pytest.fixture
def scratch_repo(tmp_path, monkeypatch):
    deploy = tmp_path / "deploy-head"
    (deploy / "src" / "comms").mkdir(parents=True)
    (deploy / "src" / "comms" / "protocol.cpp").write_text(
        _PROTOCOL_CPP_FIXTURE)
    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib"))
    return deploy, robots_dir


def test_a_suffix_that_fits_profilebuf_bakes_normally(scratch_repo):
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "vevov")
    baked = make_deploy._inject_profile(
        str(deploy), "vevov", "-nudgehang0915")
    assert baked == "vevov-nudgehang0915"
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    assert 'kProfile = "vevov-nudgehang0915"' in text


def test_a_suffix_that_overflows_profilebuf_fails_loudly(scratch_repo):
    # protocol.cpp's profileBuf_[32] (31 usable bytes + NUL) truncates
    # silently via snprintf() if this guard did not exist -- "vevov" (5)
    # plus a 30-byte suffix is 35 bytes, over the limit.
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "vevov")
    long_suffix = "-" + ("x" * 29)
    with pytest.raises(SystemExit) as exc:
        make_deploy._inject_profile(str(deploy), "vevov", long_suffix)
    assert "profileBuf_" in str(exc.value)
    # And the scratch file must be untouched -- a loud refusal, not a
    # half-applied substitution.
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    assert 'kProfile = "unbaked"' in text
