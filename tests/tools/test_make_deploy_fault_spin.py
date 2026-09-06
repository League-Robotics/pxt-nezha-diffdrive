"""tests/tools/test_make_deploy_fault_spin.py -- pins
`tools/make_deploy.py --fault-spin`, the DIFFDRIVE_FAULT_SPIN debug
build (sprint 031 ticket 013).

Two translation units carry `#ifdef DIFFDRIVE_FAULT_SPIN` branches --
`src/comms/protocol.cpp`'s `paintStackCanary()` and
`src/platform/nezha_port.cpp`'s `diffdriveFaultReport()` -- and until
this ticket neither enabled branch had ever been through the ARM
toolchain: sprint 030 reviewed them by reading, which is not the same
thing (`.claude/rules/measurement-citations.md`). Nothing in the host
suite can compile ARM, so what IS testable here, and what these tests
pin, is the build *plumbing* around it:

* the macro is actually defined, in each file that has a branch to
  enable, ahead of the includes;
* the debug build never shares a scratch directory or a hex path with
  the plain flashable deploy -- ticket 014 turns on the two binaries
  being distinguishable, and a shared build cache would make them the
  same file;
* it announces itself over the wire, so a board left on the debug build
  cannot silently be measured against (`kProfile` gains `-faultspin`);
* the injector fails loudly rather than silently producing a binary
  that is byte-identical to the plain build.

Run with::

    uv run pytest tests/tools/test_make_deploy_fault_spin.py
"""

import json
import pathlib
import re
import sys

import pytest

# tests/tools/test_make_deploy_fault_spin.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


_PROTOCOL_CPP_FIXTURE = """\
#include "protocol.h"

namespace diffDrive {
namespace {
constexpr const char* kDrivetrain = "diffdrive";
constexpr const char* kProfile = "unbaked";
}  // namespace

#ifdef DIFFDRIVE_FAULT_SPIN
void Protocol::paintStackCanary() { /* fill */ }
#else
void Protocol::paintStackCanary() {}
#endif
}  // namespace diffDrive
"""

_NEZHA_PORT_CPP_FIXTURE = """\
#include "nezha_port.h"

void diffdriveFaultReport(uint32_t* frame) {
  (void)frame;
#ifdef DIFFDRIVE_FAULT_SPIN
  while (true) {
  }
#else
  NVIC_SystemReset();
#endif
}
"""


def _write_robot_config(robots_dir, name, channel=55):
    robots_dir.mkdir(parents=True, exist_ok=True)
    (robots_dir / f"{name}.json").write_text(
        json.dumps({"connection": {"radio_channel": channel}})
    )


@pytest.fixture
def scratch_repo(tmp_path, monkeypatch):
    """A scratch deploy carrying synthetic copies of both files that
    have a DIFFDRIVE_FAULT_SPIN branch, plus a synthetic
    RADIO_ROBOT_LIB tree -- the real sibling checkout is never read."""
    deploy = tmp_path / "deploy-faultspin"
    (deploy / "src" / "comms").mkdir(parents=True)
    (deploy / "src" / "platform").mkdir(parents=True)
    (deploy / "src" / "comms" / "protocol.cpp").write_text(
        _PROTOCOL_CPP_FIXTURE
    )
    (deploy / "src" / "platform" / "nezha_port.cpp").write_text(
        _NEZHA_PORT_CPP_FIXTURE
    )
    robots_dir = tmp_path / "radio-robot-lib" / "config" / "robots"
    monkeypatch.setattr(
        make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "radio-robot-lib")
    )
    return deploy, robots_dir


# --- the macro actually gets defined, in both files ----------------------


def test_defines_the_macro_in_every_listed_source(scratch_repo):
    deploy, _ = scratch_repo
    applied = make_deploy._inject_fault_spin(str(deploy))
    assert set(applied) == set(make_deploy._FAULT_SPIN_SOURCES)
    for rel in make_deploy._FAULT_SPIN_SOURCES:
        text = (deploy / rel).read_text()
        assert make_deploy._FAULT_SPIN_DEFINE in text, rel


def test_the_define_precedes_the_includes(scratch_repo):
    """A `-D` flag is in effect before the first line of the file; the
    injected define has to land in the same place, or a header that
    itself branches on the macro would see it undefined."""
    deploy, _ = scratch_repo
    make_deploy._inject_fault_spin(str(deploy))
    for rel in make_deploy._FAULT_SPIN_SOURCES:
        text = (deploy / rel).read_text()
        assert text.startswith(make_deploy._FAULT_SPIN_DEFINE + "\n"), rel
        assert text.index(make_deploy._FAULT_SPIN_DEFINE) < text.index(
            "#include"
        ), rel


def test_the_rest_of_each_file_is_untouched(scratch_repo):
    deploy, _ = scratch_repo
    before = {
        rel: (deploy / rel).read_text()
        for rel in make_deploy._FAULT_SPIN_SOURCES
    }
    make_deploy._inject_fault_spin(str(deploy))
    for rel, original in before.items():
        after = (deploy / rel).read_text()
        assert after == f"{make_deploy._FAULT_SPIN_DEFINE}\n{original}"


# --- it fails loudly rather than producing a silently-plain binary -------


def test_refuses_a_source_with_no_branch_to_enable(scratch_repo):
    """Defining the macro in a file that has no `#ifdef` for it would
    compile fine and change nothing -- exactly the "clean log, wrong
    binary" shape build() already fails closed on elsewhere."""
    deploy, _ = scratch_repo
    (deploy / "src" / "platform" / "nezha_port.cpp").write_text(
        "#include \"nezha_port.h\"\nvoid f() {}\n"
    )
    with pytest.raises(SystemExit) as e:
        make_deploy._inject_fault_spin(str(deploy))
    assert "no #ifdef DIFFDRIVE_FAULT_SPIN" in str(e.value)


def test_refuses_to_define_the_macro_twice(scratch_repo):
    deploy, _ = scratch_repo
    make_deploy._inject_fault_spin(str(deploy))
    with pytest.raises(SystemExit) as e:
        make_deploy._inject_fault_spin(str(deploy))
    assert "already contains" in str(e.value)


def test_refuses_a_missing_source(scratch_repo):
    deploy, _ = scratch_repo
    (deploy / make_deploy._FAULT_SPIN_SOURCES[0]).unlink()
    with pytest.raises(SystemExit) as e:
        make_deploy._inject_fault_spin(str(deploy))
    assert "missing from the scratch copy" in str(e.value)


# --- the real sources still have the branches this injector assumes ------


def test_the_repos_own_sources_still_carry_the_branches():
    """`_FAULT_SPIN_SOURCES` is a hand-maintained list; if the fault or
    canary code moves, the injector would define a macro nothing reads
    and the ticket-014 scan would come back empty on a build that
    looked fine. Checked against this repo's real sources, not a
    fixture."""
    for rel in make_deploy._FAULT_SPIN_SOURCES:
        path = _REPO_ROOT / rel
        assert path.is_file(), f"{rel} named in _FAULT_SPIN_SOURCES is gone"
        text = path.read_text()
        assert "#ifdef DIFFDRIVE_FAULT_SPIN" in text, rel
        assert make_deploy._FAULT_SPIN_DEFINE not in text, (
            f"{rel} defines DIFFDRIVE_FAULT_SPIN in the checked-in source "
            f"-- a routine build would get the debug branches"
        )


# --- the two builds can never be confused for one another ----------------


def test_scratch_dir_and_hex_are_distinct_from_the_plain_deploy():
    assert make_deploy.DEPLOY_FAULT_SPIN != make_deploy.DEPLOY
    assert make_deploy.DEPLOY_FAULT_SPIN != make_deploy.DEPLOY_TESTRIG
    assert make_deploy.HEX_FAULT_SPIN != make_deploy.HEX
    assert make_deploy.HEX_FAULT_SPIN != make_deploy.HEX_TESTRIG
    # and the canary hex lives under its own scratch dir, so a stale
    # build cache in one cannot serve the other
    assert make_deploy.HEX_FAULT_SPIN.startswith(
        make_deploy.DEPLOY_FAULT_SPIN
    )
    assert not make_deploy.HEX_FAULT_SPIN.startswith(make_deploy.DEPLOY + "/")


def test_sync_fault_spin_promotes_test_ts_into_its_own_dir(monkeypatch):
    seen = {}

    def fake(deploy_dir, promote_name):
        seen["deploy_dir"] = deploy_dir
        seen["promote_name"] = promote_name
        return []

    monkeypatch.setattr(make_deploy, "_sync_scratch", fake)
    make_deploy.sync_fault_spin()
    assert seen["deploy_dir"] == make_deploy.DEPLOY_FAULT_SPIN
    assert seen["promote_name"] == "test.ts"


# --- it announces itself on the wire -------------------------------------


def _kprofile(deploy):
    text = (deploy / "src" / "comms" / "protocol.cpp").read_text()
    m = re.search(r'kProfile = "([^"]*)"', text)
    assert m, "kProfile constant not found in scratch protocol.cpp"
    return m.group(1)


def test_the_canary_build_bakes_a_distinguishable_profile(scratch_repo):
    """Ticket 014 requires the canary build be confirmed running before
    the scan, and confirmed OFF before session C. `kProfile` is the
    build-provenance field `ID` reports, so that is where the marker
    goes -- identity itself still comes from the chip via HELLO."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez")
    baked = make_deploy._inject_profile(
        str(deploy), "tovez", make_deploy.FAULT_SPIN_PROFILE_SUFFIX
    )
    assert baked == "tovez-faultspin"
    assert _kprofile(deploy) == "tovez-faultspin"


def test_the_plain_build_profile_is_unchanged_by_the_new_parameter(
    scratch_repo,
):
    """The suffix is opt-in: an ordinary build must bake exactly the
    robot name, as test_make_deploy_profile.py already pins."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez")
    assert make_deploy._inject_profile(str(deploy), "tovez") == "tovez"
    assert _kprofile(deploy) == "tovez"


def test_the_suffix_does_not_change_which_config_is_validated(scratch_repo):
    """`tovez-faultspin` is not a fleet member; validation must still be
    against `tovez`, or the debug build could not be made at all."""
    deploy, robots_dir = scratch_repo
    _write_robot_config(robots_dir, "tovez")
    make_deploy._inject_profile(
        str(deploy), "tovez", make_deploy.FAULT_SPIN_PROFILE_SUFFIX
    )
    with pytest.raises(SystemExit):
        make_deploy._inject_profile(
            str(deploy), "tovez-faultspin"
        )
