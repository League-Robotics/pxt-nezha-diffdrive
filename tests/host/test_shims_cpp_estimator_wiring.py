"""tests/host/test_shims_cpp_estimator_wiring.py -- executes the pose
estimator's wiring in the real src/shims.cpp (sprint 044 tickets 004-006,
host-compiled by ticket 011): the boot probe, the idle sensor read and its
gates, the every-fourth-tick sample, the re-prime after a seed or rebase, and
bias learning at rest through diagValue().

The hardware under shims.cpp is simulated at the I2C level (SimOtosBus,
SimNezhaBus); see shims_cpp_rig.py for the recipe. What stays a source pin,
and why, is at the bottom.

Run with::

    uv run pytest tests/host/test_shims_cpp_estimator_wiring.py
"""
import math
import pathlib
import re

from shims_cpp_rig import (DIAG_BIAS, DIAG_CONFIG, DIAG_DISTURBS, DIAG_REJECTED,
                           DIAG_STEPS, ENCODERS_ONLY, OPTICAL)
from test_bus_guard_source_pin import _function_body, _strip_comments

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
_PROTOCOL = _strip_comments((_SRC / "comms" / "protocol.cpp").read_text())
_SHIMS = _strip_comments((_SRC / "shims.cpp").read_text())

_DPH = math.radians(1.0) / 3600.0  # [rad/s] per deg/h


def _bursts_over(rig, seconds, step_ms=10, call=None):
    before = rig.otosBurstReads()
    for _ in range(int(seconds * 1000 / step_ms)):
        rig.advance_us(step_ms * 1000)
        (call or rig.idleSense)()
    return rig.otosBurstReads() - before


def test_boot_probe_finds_the_otos_with_no_user_program_call(make_rig):
    rig = make_rig()
    assert rig.diag(DIAG_CONFIG) == OPTICAL
    assert rig.otosGet(6) == 0x5F and rig.otosGet(7) == 1
    assert rig.otosPoseWrites() >= 1
    assert rig.fiberCount() == 1


def test_boot_probe_without_an_otos_is_encoders_only(make_rig):
    rig = make_rig(otos_present=False)
    assert rig.diag(DIAG_CONFIG) == ENCODERS_ONLY
    assert rig.otosBurstReads() == 0


def test_boot_probe_with_an_unreadable_gyro_is_encoders_only(make_rig):
    rig = make_rig()
    rig.otosFailBursts(1)
    assert rig.diag(DIAG_CONFIG) == ENCODERS_ONLY


def test_otos_begin_reattaches_to_a_late_arrival(make_rig):
    rig = make_rig(otos_present=False)
    assert rig.diag(DIAG_CONFIG) == ENCODERS_ONLY
    rig.otosSetPresent(1)
    assert rig.otosBegin() == 0x5F
    assert rig.diag(DIAG_CONFIG) == OPTICAL


def test_idle_sense_reads_at_ten_hertz(make_rig):
    rig = make_rig()
    rig.ensure()
    assert 19 <= _bursts_over(rig, 2.0) <= 21


def test_idle_sense_does_nothing_without_an_otos(make_rig):
    rig = make_rig(otos_present=False)
    rig.ensure()
    assert _bursts_over(rig, 2.0) == 0


def test_idle_sense_stays_off_once_boot_chose_encoders_only(make_rig):
    rig = make_rig()
    rig.otosFailBursts(1)
    assert rig.diag(DIAG_CONFIG) == ENCODERS_ONLY
    rig.otosFailBursts(0)
    assert _bursts_over(rig, 1.0) == 0


def test_idle_sense_skips_while_a_move_is_active(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    rig.startMove(500, 0, 100, 0)
    assert _bursts_over(rig, 1.0) == 0


def test_idle_sense_skips_within_150ms_of_a_fiber_tick(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    rig.tick()
    base = rig.otosBurstReads()
    rig.advance_us(110000)
    rig.idleSense()
    assert rig.otosBurstReads() == base
    rig.advance_us(60000)
    rig.idleSense()
    assert rig.otosBurstReads() == base + 1


def test_idle_sense_skips_while_the_bus_guard_is_held(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    base = rig.otosBurstReads()
    rig.idleSenseDuringNextOtosWrite()
    rig.otosBegin()
    assert rig.hookFires() == 1
    assert rig.otosBurstReads() == base + 1  # the re-probe's own read only
    rig.advance_s(0.2)
    rig.idleSense()
    assert rig.otosBurstReads() == base + 2


def test_otos_read_samples_under_the_bus_guard(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    base = rig.otosBurstReads()
    rig.idleSenseDuringNextOtosWrite()
    assert rig.otosRead() == 1
    assert rig.hookFires() == 1
    assert rig.otosBurstReads() == base + 1


def test_tick_drive_samples_the_sensors_every_fourth_tick(make_rig):
    rig = make_rig()
    rig.ensure()
    base = rig.otosBurstReads()
    seen = []
    for _ in range(12):
        rig.tick()
        seen.append(rig.otosBurstReads() - base)
    assert seen == [0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3]


def _jumps(rig):
    return rig.diag(DIAG_REJECTED), rig.diag(DIAG_STEPS)


def test_seeding_a_pose_does_not_step_the_heading(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    _bursts_over(rig, 0.5)
    before = _jumps(rig)
    rig.seed(100, 50, 9000)
    assert abs(rig.poseHeading() - 9000) <= 5
    assert rig.poseX() == 100 and rig.poseY() == 50
    _bursts_over(rig, 1.0)
    assert abs(rig.poseHeading() - 9000) <= 5
    assert abs(rig.poseX() - 100) <= 3
    assert _jumps(rig) == before  # the 90 deg chip write was not read as a step


def test_rebase_zeroes_the_pose_without_a_heading_step(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    rig.seed(100, 50, 9000)
    _bursts_over(rig, 0.5)
    writes = rig.otosPoseWrites()
    before = _jumps(rig)
    rig.rebase()
    assert rig.poseHeading() == 0
    _bursts_over(rig, 1.0)
    assert rig.otosPoseWrites() == writes + 1
    assert abs(rig.poseHeading()) <= 5
    assert abs(rig.otosChipHeading()) < 0.01
    assert _jumps(rig) == before


def test_a_sitting_robot_learns_the_gyro_bias_and_holds_heading(make_rig):
    rig = make_rig(bias_rad_s=50 * _DPH)
    rig.ensure()
    rig.advance_s(1.0)
    _bursts_over(rig, 300.0, step_ms=20)
    learned = rig.diag(DIAG_BIAS)  # [cdeg/min]
    expected = 50 * 100 / 60.0
    assert abs(learned - expected) <= 0.1 * expected, learned
    assert abs(rig.poseHeading()) <= 20  # uncorrected, 5 min drifts ~120 cdeg


def test_a_sitting_robot_with_no_bias_learns_none(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    _bursts_over(rig, 120.0, step_ms=20)
    assert abs(rig.diag(DIAG_BIAS)) <= 2


def test_a_baked_arm_is_not_overridden_by_the_program():
    port = _strip_comments((_SRC / "platform" / "otos_port.cpp").read_text())
    match = re.search(r"void OtosPort::setOffset\(.*?\n\}", port, re.DOTALL)
    assert match is not None
    body = match.group(0)
    assert re.search(r"bakedArmX_\s*==\s*0\.0f\s*&&\s*bakedArmY_\s*==\s*0\.0f", body)
    assert "offsetYaw_ = yaw" in body


def _idle_for(rig, seconds):
    _bursts_over(rig, seconds, step_ms=20)


def test_a_bump_while_the_wheels_are_still_is_counted_and_followed(make_rig):
    rig = make_rig()
    rig.ensure()
    rig.advance_s(1.0)
    _idle_for(rig, 5.0)
    x, y = rig.poseX(), rig.poseY()
    assert rig.diag(DIAG_DISTURBS) == 0
    rig.otosMoveSensor(40.0, -25.0)
    _idle_for(rig, 3.0)
    assert rig.diag(DIAG_DISTURBS) == 1
    assert abs(rig.poseX() - (x + 40)) <= 3
    assert abs(rig.poseY() - (y - 25)) <= 3


def test_a_hand_turn_while_the_wheels_are_still_reaches_the_heading(make_rig):
    rig = make_rig(bias_rad_s=50 * _DPH)
    rig.ensure()
    rig.advance_s(1.0)
    _idle_for(rig, 60.0)
    before, chip = rig.poseHeading(), rig.otosChipHeading()
    rig.otosSetBias(math.radians(30.0) + 50 * _DPH)
    _idle_for(rig, 1.0)
    rig.otosSetBias(50 * _DPH)
    _idle_for(rig, 4.0)
    turned = math.degrees(rig.otosChipHeading() - chip) * 100  # [cdeg] the sim clock runs on
    assert turned > 2500
    assert abs((rig.poseHeading() - before) - turned) <= 100
    assert rig.diag(DIAG_DISTURBS) == 1


def test_a_sitting_robot_is_never_disturbed(make_rig):
    rig = make_rig(bias_rad_s=150 * _DPH)
    rig.ensure()
    rig.advance_s(1.0)
    _idle_for(rig, 600.0)
    assert rig.diag(DIAG_DISTURBS) == 0


# ---- what stays a source pin ------------------------------------------

def test_fuse_heading_is_gone_from_the_source_tree():
    for path in _SRC.rglob("*"):
        if path.suffix in {".cpp", ".h"}:
            assert "fuseHeading" not in path.read_text(), path


def test_go_to_w_plans_from_the_estimator():
    # A world-frame go-to needs a live move to observe; the planner's
    # pose argument is the one thing worth fixing in text.
    assert "r.engine.goToW(r.estimator," in _SHIMS


def test_only_guarded_callers_pass_sample_sensors():
    # tickDrive() and idleSense() set lastTick or the idle stamp before they
    # sample, which makes every re-entrant probe skip on those gates before
    # it reaches the guard check; the bracket is not observable from here.
    sampled = [m.start() for m in re.finditer(r"odomUpdate\(r,\s*true\)", _SHIMS)]
    assert len(sampled) == 3
    for pos in sampled:
        before = _SHIMS[:pos]
        assert before.rfind("busGuard.acquire") > before.rfind("busGuard.release()")


def test_boot_probe_runs_under_the_bus_guard():
    # The estimator is not attached until the probe returns, so nothing
    # observable on the host distinguishes a guarded boot probe from an
    # unguarded one.
    body = _function_body(_SHIMS, r"static Rig& ensure\s*\(\s*\)\s*\{",
                          "ensure")
    begin = body.find("otosRef().begin()")
    attach = body.find("attachSensors(*rig)")
    acquire = body.find("busGuard.acquire")
    release = body.find("busGuard.release()", attach)
    assert -1 < acquire < begin < attach < release


def test_protocol_idles_the_sensors_only_when_nothing_owns_the_drivetrain():
    # protocol.cpp is the fiber loop and cannot be linked here; the
    # move-owner gate lives in it, not in idleSense().
    m = re.search(r"if \(motionOwner_ == MotionOwner::kNone\) idleSense\(\);",
                  _PROTOCOL)
    assert m
    before = _PROTOCOL[:m.start()]
    assert before.rfind("} else {") > before.rfind("tickDrive();")
