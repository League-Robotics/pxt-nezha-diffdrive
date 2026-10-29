"""tests/host/test_estimator_wiring_source_pin.py -- pins how src/shims.cpp
and src/comms/protocol.cpp wire the PoseEstimator (sprint 044 ticket 004).

Source-text pinning: shims.cpp includes pxt.h and cannot be compiled on the
host. The estimator itself is tested in test_pose_estimator.py.

Run with::

    uv run pytest tests/host/test_estimator_wiring_source_pin.py
"""
import pathlib
import re

from test_bus_guard_source_pin import _function_body, _strip_comments

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
_SHIMS = _strip_comments((_SRC / "shims.cpp").read_text())
_PROTOCOL = _strip_comments((_SRC / "comms" / "protocol.cpp").read_text())


def _shim(signature):
    return _function_body(_SHIMS, signature, signature)


def test_fuse_heading_is_gone_from_the_source_tree():
    for path in _SRC.rglob("*"):
        if path.suffix in {".cpp", ".h"}:
            assert "fuseHeading" not in path.read_text(), path


def test_rig_owns_an_estimator_and_no_odometry():
    assert re.search(r"PoseEstimator\s+estimator\s*\{\s*engine\s*\}", _SHIMS)
    assert "r.odometry" not in _SHIMS and "Odometry odometry" not in _SHIMS


def test_go_to_w_plans_from_the_estimator():
    assert "r.engine.goToW(r.estimator," in _SHIMS


def test_boot_begins_and_probes_the_otos_inside_ensure_under_the_guard():
    body = _shim(r"static Rig& ensure\s*\(\s*\)\s*\{")
    begin = body.find("otosRef().begin()")
    attach = body.find("attachSensors(*rig)")
    acquire = body.find("busGuard.acquire")
    release = body.find("busGuard.release()", attach)
    assert -1 < acquire < begin < attach < release


def test_attach_sensors_probes_with_the_otos_as_both_sources():
    body = _shim(r"static void attachSensors\s*\(\s*Rig&\s*r\s*\)\s*\{")
    assert "probeSensorConfig(&o, &o)" in body
    assert "r.estimator.attachSensors(&o, &o," in body


def test_otos_begin_reattaches_the_sensors_under_the_guard():
    body = _shim(r"\bint\s+otosBegin\s*\(\s*\)\s*\{")
    assert body.find("busGuard.acquire") < body.find("attachSensors(r)") < (
        body.find("busGuard.release()"))


def test_tick_drive_samples_every_fourth_tick_with_the_guard_held():
    body = _shim(r"\bbool\s+tickDrive\s*\(\s*\)\s*\{")
    m = re.search(r"if \(\+\+r\.otosSampleTick >= 4\) \{(.*?)\n  \}", body, re.S)
    assert m, body
    inner = m.group(1)
    assert inner.find("busGuard.acquire") < inner.find("odomUpdate(r, true)") < (
        inner.find("busGuard.release()"))
    assert "isDriving" not in body[body.find("otosSampleTick"):]


def test_only_guarded_callers_pass_sample_sensors():
    sampled = [m.start() for m in re.finditer(r"odomUpdate\(r,\s*true\)", _SHIMS)]
    assert len(sampled) == 3
    for pos in sampled:
        before = _SHIMS[:pos]
        assert before.rfind("busGuard.acquire") > before.rfind("busGuard.release()")


def test_idle_sense_is_nonblocking_rate_limited_and_guarded():
    body = _shim(r"\bvoid\s+idleSense\s*\(\s*\)\s*\{")
    assert "SensorConfig::kEncodersOnly" in body
    assert "busGuard.held()" in body
    assert "commandLooksActive(r)" in body
    assert "kIdleTickQuiet" in body and "kIdleSensePeriod" in body
    order = [body.find(t) for t in ("held()", "busGuard.acquire",
                                    "odomUpdate(r, true)", "busGuard.release()")]
    assert order == sorted(order) and -1 not in order


def test_protocol_idles_the_sensors_only_when_nothing_owns_the_drivetrain():
    m = re.search(r"if \(motionOwner_ == MotionOwner::kNone\) idleSense\(\);",
                  _PROTOCOL)
    assert m
    before = _PROTOCOL[:m.start()]
    assert before.rfind("} else {") > before.rfind("tickDrive();")


def test_seeding_a_pose_reprimes_the_estimator_after_the_otos_write():
    body = _shim(r"\bvoid\s+seedPose\s*\(\s*int\s+x,\s*int\s+y,\s*int\s+heading\s*\)\s*\{")
    assert body.find("estimator.seed(") < body.find("otosRef().setPose(") < (
        body.find("estimator.reprime()"))
    zero = _shim(r"static void applyPendingOtosZero\s*\(\s*Rig&\s*r\s*\)\s*\{")
    assert zero.find("setPose(0.0f, 0.0f, 0.0f)") < zero.find("reprime()")
