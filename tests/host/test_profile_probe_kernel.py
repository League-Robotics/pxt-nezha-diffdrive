"""tests/host/test_profile_probe_kernel.py -- promotes the two
probe-derived scenarios sprint 029 ticket 001's own acceptance criteria
name (E3d, E5) to an automated test, using the REAL kernel + REAL
MotionEngine through profile_probe.cpp's own Rig construction (fleet
bake, ideal wheels) rather than the hand-scripted, isolated scenarios in
test_kernel_reference_handling.py:

  E3d -- a 90 deg pivot at cruise 100 with the twist-hold servo ON must
         show no negative right duty on any tick (review MK-02 / design
         §4.5 K1).
  E5  -- a frozen right-encoder tick mid-cruise must show a duty step of
         (near) zero on the tick immediately after the freeze (review
         MK-03 / design §4.5 K2).

tests/host/profile_probe_kernel_check.cpp holds a duplicated (not
#included -- see its own header comment) copy of
docs/code-review/2026-09-02/raw/profile_probe.cpp's Rig, compiled here
as a standalone executable and run via subprocess; its stdout is a pair
of "OK ..."/"FAIL ..." lines this test asserts on, and its exit code is
0 only if both scenarios passed. Ticket 003 owns the full
test_profile_probe.py the design's own §9.3 item 2 describes (all of
E1-E11, VelocityShaper-level assertions); this file is deliberately
scoped to the two scenarios this ticket's acceptance criteria name.

Run with::

    uv run pytest tests/host/test_profile_probe_kernel.py
"""

import pathlib
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def probe_check_binary(tmp_path_factory):
    """Compiles profile_probe_kernel_check.cpp + diffdrive.cpp +
    motion_engine.cpp into a standalone executable once per session --
    mirrors test_kernel_harness.py's own compile_shared_lib() session
    fixture, but linking a `main()` instead of building a shared
    library (this file has no ctypes surface; it just runs and reads
    stdout/exit code)."""
    build_dir = tmp_path_factory.mktemp("profile_probe_kernel_check_build")
    out_path = build_dir / "probe_check"
    cmd = [
        "/usr/bin/c++", "-std=c++20", "-O1", "-w",
        "-I", str(_SRC_DIR), "-I", str(_TEST_DIR),
        str(_TEST_DIR / "profile_probe_kernel_check.cpp"),
        str(_SRC_DIR / "core" / "diffdrive.cpp"),
        str(_SRC_DIR / "motion" / "motion_engine.cpp"),
        "-o", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"host compile failed:\ncommand: {' '.join(cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return out_path


def test_probe_kernel_check_e3d_and_e5(probe_check_binary):
    result = subprocess.run(
        [str(probe_check_binary)], capture_output=True, text=True)
    assert "OK E3d" in result.stdout, (
        f"E3d (no negative right duty during a floored pivot) failed:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert "OK E5" in result.stdout, (
        f"E5 (frozen-tick duty step) failed:\n{result.stdout}{result.stderr}"
    )
    assert result.returncode == 0, (
        f"probe_check exited {result.returncode}:\n"
        f"{result.stdout}{result.stderr}"
    )
