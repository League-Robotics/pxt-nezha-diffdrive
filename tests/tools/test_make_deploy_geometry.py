"""tests/tools/test_make_deploy_geometry.py -- pins
`tools/make_deploy.py`'s OPT-IN per-robot geometry bake
(`_inject_geometry()`), which substitutes `motion_engine.h`'s
`travelCalib_` / `trackWidth_` / `rotationalSlip_` and (sprint 029
ticket 004, extended by ticket 009) `motion_limits.h`'s `lag` /
`stopDistance` in the per-robot scratch copy from the robot's own
`geometry.firmware_bake` block.

The opt-in posture is the whole point and the reason these tests are
worth having. Surveyed 2026-08-28, the fleet's configs do NOT describe
what is actually flashed -- tovez's config says trackwidth 115 / slip
1.0 against firmware defaults of 114.2 / 0.952, and togov's says
126 / 0.92. An unconditional injection would therefore have silently
retuned three robots nobody asked to touch. So: no `firmware_bake`
block means NO substitution and a byte-identical build, and that
absence is not an error.

Sprint 029 ticket 004 (design motion-profile-unification.md S4.7/S8/
S12 open question 2): `pivot_overrun_mm` -> `stop_distance_mm`, and the
regex target for that key MOVED from `motion_engine.h`
(MotionEngine::pivotOverrunMm_, deleted) to `motion_limits.h`
(MotionLimits::stopDistance) -- so `_inject_geometry()` now reads/
patches TWO files, not one, and `_deploy()` below writes both. The old
`pivot_overrun_mm` key is still ACCEPTED as a loudly-warned alias for
`stop_distance_mm` (`_resolve_geometry_bake_aliases()`), since
radio-robot-lib's own robot config files are a cross-repo change this
ticket cannot make directly.

Sprint 029 ticket 009 (design S4.1/S10.2): `lag_s` -- the drivetrain's
own first-order response lag -- joins `stop_distance_mm` as a second
`motion_limits.h`-targeting key, same "opt-in, byte-identical build
when absent" posture, following exactly the same pattern ticket 004
established for `stop_distance_mm`.

Sprint 031 ticket 020: `accel` -- MotionLimits::accel -- joins
`lag_s`/`stop_distance_mm` as a third `motion_limits.h`-targeting key,
same opt-in posture. tovez bakes 800 (fleet default stays 400.0f);
see radio-robot-lib/config/robots/tovez.json's `_accel_provenance` for
the measured numbers and docs/sprint-031-postmortem.md S3a for why the
mechanism is recorded UNVERIFIED.

Every test monkeypatches `make_deploy.RADIO_ROBOT_LIB` to a `tmp_path`
tree, same convention as `test_make_deploy_profile.py` -- nothing here
depends on the real sibling `radio-robot-lib` checkout existing.

Run with::

    uv run pytest tests/tools/test_make_deploy_geometry.py
"""

import json
import pathlib
import sys

import pytest

# tests/tools/test_make_deploy_geometry.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)

_ENGINE_HEADER = """\
  float travelCalib_ = 0.7878f;  // [mm/deg] wheel travel per shaft degree
  float trackWidth_ = 114.2f;
  float rotationalSlip_ = 0.952f;
"""

_LIMITS_HEADER = """\
  float lag = 0.0f;          // [s] drivetrain response lag
  float stopDistance = 0.0f; // [mm] per-wheel coast after the last
  float accel = 400.0f;      // [mm/s^2] dominant-wheel accel ceiling
"""


def _deploy(tmp_path, engine_text=_ENGINE_HEADER, limits_text=_LIMITS_HEADER):
    path = tmp_path / "deploy" / "src" / "motion"
    path.mkdir(parents=True)
    (path / "motion_engine.h").write_text(engine_text)
    (path / "motion_limits.h").write_text(limits_text)
    return tmp_path / "deploy"


def _config(tmp_path, robot, geometry):
    root = tmp_path / "lib" / "config" / "robots"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{robot}.json").write_text(json.dumps({"geometry": geometry}))
    return tmp_path / "lib"


def _read_engine(deploy):
    return (deploy / "src" / "motion" / "motion_engine.h").read_text()


def _read_limits(deploy):
    return (deploy / "src" / "motion" / "motion_limits.h").read_text()


def test_bakes_every_declared_constant(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov", {"firmware_bake": {
                            "travel_calib": 0.7122,
                            "trackwidth": 128.0,
                            "rotational_slip": 0.995,
                            "lag_s": 0.08,
                            "stop_distance_mm": 2.2,
                            "accel": 800.0,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    engine_text = _read_engine(deploy)
    limits_text = _read_limits(deploy)
    assert "float travelCalib_ = 0.7122f;" in engine_text
    # 128.0 must render as `128.0f`, never `128f`: an integer literal
    # cannot carry an `f` suffix and the firmware would not compile.
    assert "float trackWidth_ = 128.0f;" in engine_text
    assert "128f;" not in engine_text
    assert "float rotationalSlip_ = 0.995f;" in engine_text
    # lag_s (vevov's measured 80 ms), stop_distance_mm (2.2 mm) and
    # accel (800) all target motion_limits.h, not motion_engine.h --
    # this ticket's own file split (ticket 004), extended by ticket
    # 009's lag_s key and ticket 020's accel key.
    assert "float lag = 0.08f;" in limits_text
    assert "float stopDistance = 2.2f;" in limits_text
    assert "float accel = 800.0f;" in limits_text
    assert dict(applied) == {"travel_calib": 0.7122, "trackwidth": 128.0,
                             "rotational_slip": 0.995, "lag_s": 0.08,
                             "stop_distance_mm": 2.2, "accel": 800.0}


def test_no_bake_block_leaves_the_files_untouched(tmp_path, monkeypatch):
    """The fleet-safety property: tovez must build exactly as before."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez",
                                    {"trackwidth": 115, "rotational_slip": 1.0})))
    assert make_deploy._inject_geometry(str(deploy), "tovez") == []
    assert _read_engine(deploy) == _ENGINE_HEADER
    assert _read_limits(deploy) == _LIMITS_HEADER


def test_missing_config_file_is_not_an_error(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    (tmp_path / "lib" / "config" / "robots").mkdir(parents=True)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))
    assert make_deploy._inject_geometry(str(deploy), "nosuch") == []
    assert _read_engine(deploy) == _ENGINE_HEADER
    assert _read_limits(deploy) == _LIMITS_HEADER


def test_partial_block_bakes_only_what_it_names(tmp_path, monkeypatch):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": 0.7122}})))
    make_deploy._inject_geometry(str(deploy), "vevov")
    engine_text = _read_engine(deploy)
    assert "float travelCalib_ = 0.7122f;" in engine_text
    assert "float trackWidth_ = 114.2f;" in engine_text          # untouched
    assert "float rotationalSlip_ = 0.952f;" in engine_text      # untouched
    assert _read_limits(deploy) == _LIMITS_HEADER                # untouched


def test_stop_distance_mm_bakes_only_motion_limits(tmp_path, monkeypatch):
    """A bake naming ONLY stop_distance_mm must not touch
    motion_engine.h at all -- proves the two-file split is real, not
    just a shared read/write of both files regardless of which keys
    were actually requested."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"stop_distance_mm": 3.7}})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert dict(applied) == {"stop_distance_mm": 3.7}
    assert _read_engine(deploy) == _ENGINE_HEADER                # untouched
    assert "float stopDistance = 3.7f;" in _read_limits(deploy)


def test_lag_s_bakes_only_motion_limits(tmp_path, monkeypatch):
    """A bake naming ONLY lag_s must not touch motion_engine.h at all --
    same file-split proof as test_stop_distance_mm_bakes_only_motion_limits
    above, for this ticket's own new key."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"lag_s": 0.15}})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert dict(applied) == {"lag_s": 0.15}
    assert _read_engine(deploy) == _ENGINE_HEADER                # untouched
    assert "float lag = 0.15f;" in _read_limits(deploy)
    # stopDistance's own line stays at the fixture's default -- a bake
    # naming only lag_s must not touch it either.
    assert "float stopDistance = 0.0f;" in _read_limits(deploy)


def test_accel_bakes_only_motion_limits(tmp_path, monkeypatch):
    """A bake naming ONLY accel must not touch motion_engine.h at all --
    same file-split proof as test_stop_distance_mm_bakes_only_motion_limits
    / test_lag_s_bakes_only_motion_limits above, for this ticket's
    (031/020) own new key."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"accel": 800.0}})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert dict(applied) == {"accel": 800.0}
    assert _read_engine(deploy) == _ENGINE_HEADER                # untouched
    assert "float accel = 800.0f;" in _read_limits(deploy)
    # lag/stopDistance stay at the fixture's default -- a bake naming
    # only accel must not touch them either.
    assert "float lag = 0.0f;" in _read_limits(deploy)
    assert "float stopDistance = 0.0f;" in _read_limits(deploy)


def test_tovez_accel_bakes_800(tmp_path, monkeypatch):
    """Sprint 031 ticket 020: tovez's accel was MEASURED at 800 on
    2026-09-05 (captures/session-b-20260905/gain-sweep-20260905/
    accel800/ and .../accel800b/, n=8 alternating +-600 mm legs, mean
    |dh| 3.62 -> 1.35 deg vs the accel-300 baseline) and
    radio-robot-lib/config/robots/tovez.json's
    geometry.firmware_bake.accel was set to 800. Pins that the
    existing opt-in _inject_geometry() mechanism bakes exactly that
    value into the scratch copy's motion_limits.h with no `SET` needed
    at boot."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez", {"firmware_bake": {
                            "accel": 800,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "tovez")
    assert dict(applied) == {"accel": 800.0}
    assert "float accel = 800.0f;" in _read_limits(deploy)


def test_no_accel_key_keeps_motion_limits_byte_identical(tmp_path, monkeypatch):
    """Acceptance criterion: a robot with no `firmware_bake.accel` key
    produces a byte-identical motion_limits.h (keeps the compiled
    400.0f default)."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov", {"firmware_bake": {
                            "travel_calib": 0.71,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert "accel" not in dict(applied)
    assert _read_limits(deploy) == _LIMITS_HEADER


def test_other_robots_accel_unaffected_by_tovez_bake(tmp_path, monkeypatch):
    """Cross-robot isolation: baking tovez's accel: 800 must not change
    a second robot's (e.g. tigez's) accel or output, even though both
    configs live under the same RADIO_ROBOT_LIB tree."""
    deploy_tovez = _deploy(tmp_path / "a")
    deploy_tigez = _deploy(tmp_path / "b")
    lib_root = tmp_path / "lib" / "config" / "robots"
    lib_root.mkdir(parents=True)
    (lib_root / "tovez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"accel": 800},
    }}))
    (lib_root / "tigez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"rotational_slip": 0.9617},
    }}))
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))

    applied_tovez = make_deploy._inject_geometry(str(deploy_tovez), "tovez")
    applied_tigez = make_deploy._inject_geometry(str(deploy_tigez), "tigez")

    assert dict(applied_tovez) == {"accel": 800.0}
    assert "accel" not in dict(applied_tigez)
    assert "float accel = 800.0f;" in _read_limits(deploy_tovez)
    assert "float accel = 400.0f;" in _read_limits(deploy_tigez)     # untouched


def test_fails_loudly_when_the_accel_declaration_moves(tmp_path, monkeypatch):
    """Same recurrence guard as the lag/stopDistance declaration-move
    tests above, for motion_limits.h's own `accel` declaration (this
    ticket's own new key)."""
    deploy = _deploy(tmp_path, limits_text="  float accelMmS2_ = 400.0f;\n")
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"accel": 800.0}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_pivot_overrun_mm_alias_bakes_stop_distance_with_warning(
        tmp_path, monkeypatch, capsys):
    """The RETIRED `pivot_overrun_mm` key (a robot config not yet
    migrated cross-repo to radio-robot-lib's new name) still bakes
    `stop_distance_mm` -- loudly, not silently (design S12 open
    question 2: this repo cannot edit radio-robot-lib's own config
    files, so the fallback has to carry the weight until that migration
    happens)."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"pivot_overrun_mm": 2.2}})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert dict(applied) == {"stop_distance_mm": 2.2}
    assert "float stopDistance = 2.2f;" in _read_limits(deploy)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "pivot_overrun_mm" in out
    assert "stop_distance_mm" in out


def test_both_old_and_new_key_prefers_new_and_warns(tmp_path, monkeypatch,
                                                     capsys):
    """A config carrying BOTH keys (mid-migration) keeps the new one and
    warns that the old one is now dead weight, rather than silently
    picking one with no explanation."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov", {"firmware_bake": {
                            "pivot_overrun_mm": 9.9,
                            "stop_distance_mm": 2.2,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "vevov")
    assert dict(applied) == {"stop_distance_mm": 2.2}
    assert "float stopDistance = 2.2f;" in _read_limits(deploy)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "pivot_overrun_mm" in out


@pytest.mark.parametrize("bad", [0, -1, "0.71", None])
def test_rejects_a_nonpositive_or_nonnumeric_value(tmp_path, monkeypatch, bad):
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": bad}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_fails_loudly_when_the_declaration_moves(tmp_path, monkeypatch):
    """If motion_engine.h stops matching, the build must stop -- a
    geometry bake that silently did nothing is the defect this whole
    mechanism exists to prevent."""
    deploy = _deploy(tmp_path, engine_text="  float travelCalibration_ = 0.7878f;\n")
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"travel_calib": 0.7122}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_fails_loudly_when_the_limits_declaration_moves(tmp_path, monkeypatch):
    """Same recurrence guard as test_fails_loudly_when_the_declaration_
    moves above, for motion_limits.h's own stopDistance declaration --
    this ticket's own new file/key, so it needs its own regression
    guard against the same silent-no-op failure mode."""
    deploy = _deploy(tmp_path, limits_text="  float stopDistanceMm_ = 0.0f;\n")
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"stop_distance_mm": 2.2}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_fails_loudly_when_the_lag_declaration_moves(tmp_path, monkeypatch):
    """Same recurrence guard, for motion_limits.h's own `lag` declaration
    (sprint 029 ticket 009's own new key)."""
    deploy = _deploy(tmp_path, limits_text="  float lagS_ = 0.0f;\n")
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "vevov",
                                    {"firmware_bake": {"lag_s": 0.08}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(deploy), "vevov")


def test_tovez_rotational_slip_bakes_0962(tmp_path, monkeypatch):
    """Sprint 031 ticket 018: tovez's rotational_slip was MEASURED at
    0.962 on 2026-09-05 (captures/session-b-20260905/ticket016/
    g1-slip0962/, 12 alternating +-90 deg pivots, mean|err| 1.531 deg
    vs 4.604 deg uncalibrated) and radio-robot-lib/config/robots/
    tovez.json's geometry.firmware_bake.rotational_slip was updated
    from the earlier 1.01 to 0.962. Pins that the existing opt-in
    _inject_geometry() mechanism bakes exactly that value into the
    scratch copy's motion_engine.h with no `SET` needed at boot."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez", {"firmware_bake": {
                            "rotational_slip": 0.962,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "tovez")
    assert dict(applied) == {"rotational_slip": 0.962}
    assert "float rotationalSlip_ = 0.962f;" in _read_engine(deploy)


def test_other_robots_rotational_slip_unaffected_by_tovez_bake(tmp_path, monkeypatch):
    """Sprint 031 ticket 018 acceptance criterion: baking tovez's
    0.962 must not change any other robot's rotational_slip. tigez's
    own independently measured 0.9617 (tigez-turn-calibration-20260903.md)
    and vevov's own bake are each read from THAT robot's own config
    file -- tovez's presence in the same config tree must not leak
    into either."""
    deploy_tovez = _deploy(tmp_path / "a")
    deploy_tigez = _deploy(tmp_path / "b")
    lib_root = tmp_path / "lib" / "config" / "robots"
    lib_root.mkdir(parents=True)
    (lib_root / "tovez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"rotational_slip": 0.962},
    }}))
    (lib_root / "tigez.json").write_text(json.dumps({"geometry": {
        "firmware_bake": {"rotational_slip": 0.9617},
    }}))
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB", str(tmp_path / "lib"))

    applied_tovez = make_deploy._inject_geometry(str(deploy_tovez), "tovez")
    applied_tigez = make_deploy._inject_geometry(str(deploy_tigez), "tigez")

    assert dict(applied_tovez) == {"rotational_slip": 0.962}
    assert dict(applied_tigez) == {"rotational_slip": 0.9617}
    assert "float rotationalSlip_ = 0.962f;" in _read_engine(deploy_tovez)
    assert "float rotationalSlip_ = 0.9617f;" in _read_engine(deploy_tigez)


def test_robot_without_the_key_keeps_the_fleet_default(tmp_path, monkeypatch):
    """A robot with no rotational_slip in its firmware_bake block (or
    no firmware_bake block at all) must keep motion_engine.h's tracked
    fleet default (0.952) byte-identical -- this ticket deliberately
    does NOT touch that default, since tigez (0.9617) and vevov differ
    from tovez's 0.962 and a shared default would be wrong for at
    least one other board the moment it's read."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "togov", {"firmware_bake": {
                            "travel_calib": 0.71,
                        }})))
    applied = make_deploy._inject_geometry(str(deploy), "togov")
    assert "rotational_slip" not in dict(applied)
    assert "float rotationalSlip_ = 0.952f;" in _read_engine(deploy)


def test_measured_zero_is_a_legal_bake_for_the_motion_limits_keys(tmp_path, monkeypatch):
    """stop_distance_mm 0 / lag_s 0 are MEASURED values (tovez 2026-09-04),
    not absent ones; the geometry scales stay strictly positive."""
    deploy = _deploy(tmp_path)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez", {"firmware_bake": {
                            "stop_distance_mm": 0.0, "lag_s": 0.0}})))
    applied = make_deploy._inject_geometry(str(deploy), "tovez")
    assert dict(applied) == {"stop_distance_mm": 0.0, "lag_s": 0.0}
    assert "float stopDistance = 0.0f;" in _read_limits(deploy)
    monkeypatch.setattr(make_deploy, "RADIO_ROBOT_LIB",
                        str(_config(tmp_path, "tovez", {"firmware_bake": {
                            "trackwidth": 0.0}})))
    with pytest.raises(SystemExit):
        make_deploy._inject_geometry(str(_deploy(tmp_path / "b")), "tovez")
