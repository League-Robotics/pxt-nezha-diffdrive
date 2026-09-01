// motion_engine_shim.cpp -- extern "C" ctypes surface for MotionEngine's
// host tests (test_motion_engine_primitives.py,
// test_motion_engine_reductions.py, test_motion_engine_gotow.py,
// test_motion_engine_settle.py): MotionEngine's geometry
// (effectiveTrackWidth/countsPerMm), its two wheel primitives
// (wheelsX/wheelsV), and its move engine (moveX/moveV/goToR/
// serviceMove/...), wired to a REAL DiffDrive::DifferentialDrive kernel
// over FakeMotor -- the same "opaque handle bundling FakeMotor x2/
// FakeClock/FakeSleeper/FakeFiberLauncher plus a real kernel" shape as
// tests/host/kernel_shim.cpp, extended with one MotionEngine instance
// constructed over that same kernel AND the same FakeClock (mirroring
// shims.cpp's own Rig, which likewise constructs its `engine` member
// over its `kernel`/`clock` members). Test scaffolding only: nothing
// under src/ knows this file exists, and it is compiled only into this
// test's own throwaway shared library.
//
// Extend this file's function list -- don't invent a second shim --
// when a later ticket needs another MotionEngine entry point exposed.
#include <cmath>
#include <cstdint>

#include "core/diffdrive.h"
#include "platform/encoder_pose_source.h"
#include "fake_ports.h"
#include "fake_pose_source.h"
#include "motion/motion_engine.h"

namespace {

struct Handle {
  FakeMotor left;
  FakeMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  // The goToW() PoseSource these tests arm via mePoseSourceSetPose() --
  // NOT constructed over `engine` (PoseSource is passed per-call, not
  // stored; see motion_engine.h's own comment), so its declaration
  // order relative to `engine` above does not matter.
  FakePoseSource pose;

  // Sprint 006 ticket 007: backing fields plus a REAL
  // diffDrive::EncoderPoseSource bound to them by const reference --
  // mirrors shims.cpp's own Rig::x/y/heading + Rig::encoderPose wiring
  // exactly, so these tests exercise the production reference-binding
  // shape rather than a stand-in. encoderPose binds to encX_/encY_/
  // encHeading_ at CONSTRUCTION time -- it must therefore be declared
  // AFTER them (members initialize in DECLARATION order regardless of
  // the constructor's own initializer-list order, same rule
  // encoder_pose_source.h's own header comment states).
  float encX_ = 0.0f, encY_ = 0.0f, encHeading_ = 0.0f;
  diffDrive::EncoderPoseSource encoderPose;

  // meProbeRunToCompletion()'s own odometry accumulator [mm]/[mm]/[rad]
  // and its "last consumed" wheel positions [counts] -- same shape as
  // docs/code-review/2026-08-26/raw/goto_probe.cpp's own Rig::x/y/h/pl/pr,
  // kept on Handle (not local to the function) only because a probe run
  // needs to survive across the caller's own already-issued moveX()/
  // goToR() call; a fresh meCreate() handle starts these at zero, which
  // is the only state a probe run ever assumes.
  float probeX_ = 0.0f, probeY_ = 0.0f, probeHeading_ = 0.0f;
  float probePl_ = 0.0f, probePr_ = 0.0f;

  Handle()
      : kernel(left, right, clock, sleeper, launcher),
        engine(kernel, clock),
        encoderPose(encX_, encY_, encHeading_) {}
};

FakeMotor& motorFor(Handle* h, int side) {
  return side == 0 ? h->left : h->right;
}

}  // namespace

extern "C" {

// ---- lifecycle -----------------------------------------------------------

void* meCreate() { return new Handle(); }
void meDestroy(void* handle) { delete static_cast<Handle*>(handle); }

// ---- kernel config/lifecycle (the subset these tests need -- duty is
// pure feedforward with every other Config field left at its zero/off
// default, the same configuration test_kernel_harness.py's own smoke
// test establishes produces duty = commandedSpeed / fullDutyVelocity
// with no PID/bias/twist-hold contribution). ----------------------------

void meSetMaxDuty(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setMaxDuty(v);
}
void meSetFullDutyVelocity(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setFullDutyVelocity(v);
}
// twistHoldGain defaults to 0.0 (off) in every other test in this tree
// (this file's own comment above), which is exactly why the phase 1 ->
// phase 2 handoff's stale-twist-hold-reference hazard needs its own
// test: only with this gain nonzero does the kernel's twist-hold trim
// (diffdrive.cpp) contribute anything to staged duty at all. Mirrors
// kernel_shim.cpp's kdSetTwistHoldGain.
void meSetTwistHoldGain(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setTwistHoldGain(v);
}
int meBegin(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.begin());
}
void meStep(void* handle) { static_cast<Handle*>(handle)->kernel.step(); }
int meOutLeaseExpired(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().leaseExpired ? 1 : 0;
}
// Output.estopped readback -- mirrors kernel_shim.cpp's own
// kdOutEstopped export (test_cross_fiber_stop_settle_window.py's
// k.out_estopped property is the precedent this follows).
int meOutEstopped(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().estopped ? 1 : 0;
}
// Latches the kernel's e-stop directly (kernel.estop()) -- lets a test
// force Output.estopped WITHOUT going through anything resembling
// shims.cpp's estopAll() ordering (engine.endMove() called BEFORE
// kernel.estop()), which is exactly what masks serviceMove() not
// checking out.estopped on its own.
void meKernelEstop(void* handle) {
  static_cast<Handle*>(handle)->kernel.estop();
}

// Regression guard (post-move neutral delivery, commit 3e919e5):
// exposes the kernel's own MEASURED velocity (diffdrive.h Output.
// velocityLeft/Right -- computed from encoder position deltas across
// two collects, refreshSample(), NOT the commanded duty) so a host test
// can prove that delivering a zero DUTY to the FakeMotor (meMotorLastStagedDuty)
// is a distinct event from the reported velocity actually reading at
// rest -- shims.cpp's own settle-tick loop (tickDrive(), now via
// MotionEngine::settleToRest()) exists precisely because these two can
// diverge for several ticks after a move ends.
float meOutVelocityLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityLeft;
}
float meOutVelocityRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityRight;
}

// ---- FakeClock -- lets a test place the lease-expiry boundary exactly
// (kernel.drive() reads the clock at CALL time to compute
// validUntil = now + lease, so a test that wants to probe a computed
// lease sets the clock, drives, then advances it around the expected
// boundary). ---------------------------------------------------------

void meClockSetNow(void* handle, uint64_t nowUs) {
  static_cast<Handle*>(handle)->clock.nowUs = nowUs;
}

// ---- FakeMotor readback ------------------------------------------------
// `side`: 0 == left, 1 == right.

float meMotorLastStagedDuty(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).lastStagedDuty;
}

// ---- MotionEngine: geometry (motion-api.md S2.1) -----------------------

float meCountsPerMm(void* handle) {
  return static_cast<Handle*>(handle)->engine.countsPerMm();
}
float meEffectiveTrackWidth(void* handle) {
  return static_cast<Handle*>(handle)->engine.effectiveTrackWidth();
}
float meTrackWidth(void* handle) {
  return static_cast<Handle*>(handle)->engine.trackWidth();
}
float meTravelCalib(void* handle) {
  return static_cast<Handle*>(handle)->engine.travelCalib();
}
float meRotationalSlip(void* handle) {
  return static_cast<Handle*>(handle)->engine.rotationalSlip();
}
void meSetTrackWidth(void* handle, float mm) {
  static_cast<Handle*>(handle)->engine.setTrackWidth(mm);
}
void meSetTravelCalib(void* handle, float mmPerDeg) {
  static_cast<Handle*>(handle)->engine.setTravelCalib(mmPerDeg);
}
// Exposes the setter rotationalSlip_ never had -- see motion_engine.h's
// own setter/field comments for the validation and the load-bearing
// derivation this field's default carries.
void meSetRotationalSlip(void* handle, float slip) {
  static_cast<Handle*>(handle)->engine.setRotationalSlip(slip);
}
float mePivotOverrunMm(void* handle) {
  return static_cast<Handle*>(handle)->engine.pivotOverrunMm();
}
void meSetPivotOverrunMm(void* handle, float mm) {
  static_cast<Handle*>(handle)->engine.setPivotOverrunMm(mm);
}

// ---- MotionEngine: constant-a acceleration/deceleration shaping
// (sprint 025 ticket 001) plus getters for the five pre-existing
// end-of-move shaping fields (distTaper/yawTaper/distFloor/turnFloor/
// rampMs, setters already exported below) -- see motion_engine.h's own
// field comments for defaults/validation/units. ------------------------

float meAAccelMmS2(void* handle) {
  return static_cast<Handle*>(handle)->engine.aAccelMmS2();
}
void meSetAAccelMmS2(void* handle, float mmS2) {
  static_cast<Handle*>(handle)->engine.setAAccelMmS2(mmS2);
}
float meADecelMmS2(void* handle) {
  return static_cast<Handle*>(handle)->engine.aDecelMmS2();
}
void meSetADecelMmS2(void* handle, float mmS2) {
  static_cast<Handle*>(handle)->engine.setADecelMmS2(mmS2);
}
float meVMaxMmS(void* handle) {
  return static_cast<Handle*>(handle)->engine.vMaxMmS();
}
void meSetVMaxMmS(void* handle, float mmS) {
  static_cast<Handle*>(handle)->engine.setVMaxMmS(mmS);
}
float meBrakeFrac(void* handle) {
  return static_cast<Handle*>(handle)->engine.brakeFrac();
}
void meSetBrakeFrac(void* handle, float frac) {
  static_cast<Handle*>(handle)->engine.setBrakeFrac(frac);
}

// SUC-003: the distance-chosen default-cruise resolver itself --
// MotionEngine::defaultCruiseForDistance(), reading whatever
// aAccelMmS2_/vMaxMmS_/brakeFrac_ the four setters above last wrote.
float meDefaultCruiseForDistance(void* handle, float distanceMm) {
  return static_cast<Handle*>(handle)->engine.defaultCruiseForDistance(
      distanceMm);
}

// SUC-003: the dominant-axis wheel-travel input helper -- a pure pivot
// (distanceMm == 0) still resolves a nonzero D from rotationRad alone.
float meDominantAxisTravelMm(void* handle, float distanceMm,
                             float rotationRad) {
  return static_cast<Handle*>(handle)->engine.dominantAxisTravelMm(
      distanceMm, rotationRad);
}

// ---- MotionEngine: the two primitives (motion-api.md S3.1/S3.2) -------

void meWheelsV(void* handle, float left, float right, uint32_t durationMs) {
  static_cast<Handle*>(handle)->engine.wheelsV(left, right, durationMs);
}
void meWheelsX(void* handle, float left, float right, float cruise,
              uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.wheelsX(left, right, cruise,
                                               timeoutMs);
}

// ---- MotionEngine: the move engine (motion-api.md S3.3-S3.5) ----------

void meMoveX(void* handle, float distance, float rotation, float cruise,
            uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.moveX(distance, rotation, cruise,
                                             timeoutMs);
}
void meMoveV(void* handle, float vx, float omega, uint32_t durationMs) {
  static_cast<Handle*>(handle)->engine.moveV(vx, omega, durationMs);
}
void meGoToR(void* handle, float x, float y, float speed, float arrive,
            uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.goToR(x, y, speed, arrive, timeoutMs);
}

// ---- MotionEngine: goToW (motion-api.md S3.6, sprint 003 ticket 010) --

// Arms the FakePoseSource a following meGoToW() call reads. [mm] [mm]
// [rad] -- see fake_pose_source.h.
void mePoseSourceSetPose(void* handle, float x, float y, float heading) {
  static_cast<Handle*>(handle)->pose.setPose(x, y, heading);
}
void meGoToW(void* handle, float x, float y, float speed, float arrive,
            uint32_t timeoutMs) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.goToW(h->pose, x, y, speed, arrive, timeoutMs);
}

// ---- EncoderPoseSource (motion-api.md S3.6, sprint 006 ticket 007) -----
// Same "arm then read/dispatch" shape as FakePoseSource/meGoToW() above,
// but through the REAL diffDrive::EncoderPoseSource bound to this
// Handle's own encX_/encY_/encHeading_ fields -- proving the production
// reference-binding class itself, not a test double standing in for it.
// No otos_port.h anywhere in this file or its includes.

// Scripts the backing x/y/heading a following meEncoderPoseSourceX/Y/
// Heading() read or meGoToWViaEncoder() dispatches with. [mm] [mm] [rad],
// heading UNWRAPPED verbatim -- callers may pass values outside
// (-pi, pi] on purpose (AC 2's own explicit no-wrap check).
void meEncoderPoseSourceSetPose(void* handle, float x, float y,
                                float heading) {
  Handle* h = static_cast<Handle*>(handle);
  h->encX_ = x;
  h->encY_ = y;
  h->encHeading_ = heading;
}

// Direct passthrough reads of EncoderPoseSource's own x()/y()/heading() --
// AC 2's own explicit check that heading() applies no wrap reads this
// back against exactly the value armed above.
float meEncoderPoseSourceX(void* handle) {
  return static_cast<Handle*>(handle)->encoderPose.x();
}
float meEncoderPoseSourceY(void* handle) {
  return static_cast<Handle*>(handle)->encoderPose.y();
}
float meEncoderPoseSourceHeading(void* handle) {
  return static_cast<Handle*>(handle)->encoderPose.heading();
}

// goToW() dispatched with EncoderPoseSource as the `pose` argument --
// AC 1: no OtosPort/otos_port.h anywhere in this link.
void meGoToWViaEncoder(void* handle, float x, float y, float speed,
                       float arrive, uint32_t timeoutMs) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.goToW(h->encoderPose, x, y, speed, arrive, timeoutMs);
}

// ---- selectPoseSource() (encoder_pose_source.h) -- the host-testable
// stand-in for engineGoToW()'s own selection rule (shims.cpp), since
// OtosPort::connected() itself has no host-testable seam. Uses `pose`
// (armed via mePoseSourceSetPose()) and `encoderPose` (armed via
// meEncoderPoseSourceSetPose() above) as the two arms -- a caller sets
// each to a distinguishable x() beforehand, then reads back which one
// selectPoseSource() actually returned via its x(). ------------------

float meSelectPoseSourceX(void* handle, int primaryConnected) {
  Handle* h = static_cast<Handle*>(handle);
  return diffDrive::selectPoseSource(primaryConnected != 0, h->pose,
                                     h->encoderPose)
      .x();
}
int meServiceMove(void* handle) {
  return static_cast<Handle*>(handle)->engine.serviceMove() ? 1 : 0;
}
int meIsMoveActive(void* handle) {
  return static_cast<Handle*>(handle)->engine.isMoveActive() ? 1 : 0;
}
void meEndMove(void* handle) {
  static_cast<Handle*>(handle)->engine.endMove();
}

// ---- stop-move sequence mirrors (ticket: `stop move` must stop a
// continuous drive) ------------------------------------------------------
// shims.cpp cannot be host-compiled (includes pxt.h -- see this test
// tree's own README.md and test_cross_fiber_stop_settle_window.py's
// header comment for the standing convention on that boundary), so these
// two functions hand-mirror shims.cpp's endMove() free function's exact
// call sequence, before and after this ticket's fix, using the same
// host-portable primitives (a real DiffDrive::DifferentialDrive kernel +
// diffDrive::MotionEngine over FakeMotor) shims.cpp itself composes.
// Keep these in sync BY HAND with shims.cpp::endMove() -- there is no
// compiler link between the two.

// Pre-fix sequence: engine.endMove() (a no-op after a continuous-drive
// command -- no move-engine move is active, since wheelsV()/wheelsX()
// call cancelMove() on the way in) plus deliverStopNow()'s port-level
// zero write, WITHOUT kernel.neutral(). Regression pin: this leaves the
// kernel's commanded velocity mode armed (up to kLeaseMax), so the very
// next step() re-commands the pre-stop duty.
void meEndMoveOldStopSequence(void* handle) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.endMove();
  h->left.emergencyStop();
  h->right.emergencyStop();
}

// Post-fix sequence: adds kernel.neutral() between engine.endMove() and
// the port-level zero write, so the kernel's commanded mode is disarmed
// too -- the next step() computes zero duty instead of re-commanding.
void meEndMoveFixedStopSequence(void* handle) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.endMove();
  h->kernel.neutral();
  h->left.emergencyStop();
  h->right.emergencyStop();
}
int meProgress(void* handle) {
  return static_cast<Handle*>(handle)->engine.progress();
}
uint32_t meWrongWayCount(void* handle) {
  return static_cast<Handle*>(handle)->engine.wrongWayCount();
}
void meSetDistTaper(void* handle, float counts) {
  static_cast<Handle*>(handle)->engine.setDistTaper(counts);
}
float meDistTaper(void* handle) {
  return static_cast<Handle*>(handle)->engine.distTaper();
}
void meSetYawTaper(void* handle, float counts) {
  static_cast<Handle*>(handle)->engine.setYawTaper(counts);
}
float meYawTaper(void* handle) {
  return static_cast<Handle*>(handle)->engine.yawTaper();
}
void meSetDistFloor(void* handle, float fraction) {
  static_cast<Handle*>(handle)->engine.setDistFloor(fraction);
}
float meDistFloor(void* handle) {
  return static_cast<Handle*>(handle)->engine.distFloor();
}
void meSetTurnFloor(void* handle, float fraction) {
  static_cast<Handle*>(handle)->engine.setTurnFloor(fraction);
}
float meTurnFloor(void* handle) {
  return static_cast<Handle*>(handle)->engine.turnFloor();
}
void meSetRampMs(void* handle, float ms) {
  static_cast<Handle*>(handle)->engine.setRampMs(ms);
}
float meRampMs(void* handle) {
  return static_cast<Handle*>(handle)->engine.rampMs();
}

// Arms the NEXT tick()'s reported encoder position directly (bypassing
// any simulated physics -- see fake_ports.h's own FakeMotor comment):
// lets a test place the encoders wherever it wants without hand-rolling
// a duty-to-distance integrator, e.g. to force a segment's completion
// (or a pivot-then-straight phase transition) on a specific tick.
// `sampleTimeUs` must also advance (and be nonzero) each call --
// DifferentialDrive::refreshSample() (src/core/diffdrive.cpp) only accepts a
// new position when Motor::sampleTime() actually CHANGES (and never
// even starts sampling until it is nonzero at all -- see
// test_kernel_harness.py's matching kdMotorArmPosition, which arms the
// same pair together for exactly this reason).
void meMotorArmPosition(void* handle, int side, float positionCounts,
                        uint64_t sampleTimeUs) {
  FakeMotor& motor = motorFor(static_cast<Handle*>(handle), side);
  motor.nextPositionValue = positionCounts;
  motor.nextSampleTimeUs = sampleTimeUs;
}

// ---- settle-tick decision (sprint 008 ticket 004) ----------------------
// MotionEngine::settleToRest() itself, plus its own onSleep-driven test
// script -- closes settle-tick-loop-is-not-host-testable.md: before this
// ticket, the bounded-iteration/break-on-rest DECISION lived only in
// shims.cpp::tickDrive() (pxt.h, uncompilable here); it is now a real
// MotionEngine method this file already links.

// Calls the real settleToRest() once and returns how many kernel.step()
// calls it made internally, via Output.cycleCount's own before/after
// delta -- cycleCount increments unconditionally on every step()
// regardless of caller (src/core/diffdrive.cpp), so this needs no new
// production-code counter.
uint32_t meSettleToRest(void* handle) {
  Handle* h = static_cast<Handle*>(handle);
  const uint32_t before = h->kernel.output().cycleCount;
  h->engine.settleToRest();
  const uint32_t after = h->kernel.output().cycleCount;
  return after - before;
}

// Arms a step-indexed encoder position/sample-time SCRIPT that
// FakeSleeper::onSleep (fake_ports.h, sprint 006 ticket 002) plays back
// automatically while a FOLLOWING meSettleToRest() call's own internal
// kernel.step() loop runs -- the only way to feed a decaying (or
// held-high) coast-down velocity profile across settleToRest()'s OWN
// internal steps, which happen inside one C++ call and are not
// otherwise individually steppable from Python (a statically-armed
// FakeMotor position, left un-rearmed, reads back FROZEN after its
// first tick() -- DifferentialDrive::refreshSample() only accepts a
// sample whose Motor::sampleTime() actually changed, fake_ports.h's own
// note). Captures the CURRENT sleeper.sleepCalls count as `baseline` at
// arm time, so the schedule is relative to whenever this is called, not
// to process start -- mirrors FakeSleeper's own comment on call-count
// parity: step() calls sleepMillis() exactly twice per step (once per
// wheel's select->settle->read split), so onSleep's call count maps to
// step index (callNumber - baseline - 1) / 2, landing just before THAT
// wheel's tick() commits positions[stepIndex]/sampleTimesUs[stepIndex]
// -- armed identically for both wheels (this test surface has no need
// to script a left/right skew). A callNumber outside [baseline+1,
// baseline+2*count] is a no-op, leaving the FakeMotor's last-armed
// values in place. `positions`/`sampleTimesUs` are captured BY POINTER,
// not copied -- the caller must keep the backing arrays alive for the
// duration of the following meSettleToRest() call.
void meArmSettleProfile(void* handle, const float* positions,
                        const uint64_t* sampleTimesUs, int count) {
  Handle* h = static_cast<Handle*>(handle);
  const int baseline = h->sleeper.sleepCalls;
  h->sleeper.onSleep = [h, positions, sampleTimesUs, count,
                        baseline](int callNumber) {
    const int stepIndex = (callNumber - baseline - 1) / 2;
    if (stepIndex < 0 || stepIndex >= count) return;
    h->left.nextPositionValue = positions[stepIndex];
    h->left.nextSampleTimeUs = sampleTimesUs[stepIndex];
    h->right.nextPositionValue = positions[stepIndex];
    h->right.nextSampleTimeUs = sampleTimesUs[stepIndex];
  };
}

void meDisarmSettleProfile(void* handle) {
  static_cast<Handle*>(handle)->sleeper.onSleep = nullptr;
}

// ---- run-to-completion probe ---------------------------------------------
// Ideal-wheels tick loop, matching
// docs/code-review/2026-08-26/raw/goto_probe.cpp's own Rig::tick()/run()
// byte-for-byte: each cycle, a wheel's reported position advances by
// exactly its LAST APPLIED duty (FakeMotor::appliedDuty(), landed by the
// PRECEDING kernel.step()) times `fullDutyVelocity` times `dt` -- no
// simulated slip or lag -- so a host test can drive an ALREADY-ISSUED
// moveX()/goToR() call (via meMoveX()/meGoToR() above) to completion and
// read the resulting body-frame endpoint back, the same technique that
// probe used to measure block-go-to-misses-its-target.md's numbers
// against the real firmware. Returns the tick count actually run; equal
// to `maxTicks` means the move never went inactive within budget -- a
// caller must treat that as "did not complete," not as a real landing.
uint32_t meProbeRunToCompletion(void* handle, float fullDutyVelocity,
                                uint32_t periodMs, uint32_t maxTicks) {
  Handle* h = static_cast<Handle*>(handle);
  const float dt = static_cast<float>(periodMs) / 1000.0f;
  uint32_t ticks = 0;
  for (; ticks < maxTicks && h->engine.isMoveActive(); ++ticks) {
    const float dutyLeft = h->left.appliedDuty();
    const float dutyRight = h->right.appliedDuty();
    h->left.nextPositionValue =
        h->left.position() + dutyLeft * fullDutyVelocity * dt;
    h->right.nextPositionValue =
        h->right.position() + dutyRight * fullDutyVelocity * dt;
    h->clock.nowUs += static_cast<uint64_t>(periodMs) * 1000ull;
    h->left.nextSampleTimeUs = h->right.nextSampleTimeUs = h->clock.nowUs;
    h->kernel.step();

    const float cpm = h->engine.countsPerMm();
    const float b = h->engine.effectiveTrackWidth();
    const DiffDrive::DifferentialDrive::Output out = h->kernel.output();
    const float dLeft = (out.positionLeft - h->probePl_) / cpm;
    const float dRight = (out.positionRight - h->probePr_) / cpm;
    h->probePl_ = out.positionLeft;
    h->probePr_ = out.positionRight;
    const float dC = 0.5f * (dLeft + dRight);
    const float dHeading = (dRight - dLeft) / b;
    const float mid = h->probeHeading_ + 0.5f * dHeading;
    h->probeX_ += dC * std::cos(mid);
    h->probeY_ += dC * std::sin(mid);
    h->probeHeading_ += dHeading;

    h->engine.serviceMove();
  }
  return ticks;
}

float meProbeX(void* handle) { return static_cast<Handle*>(handle)->probeX_; }
float meProbeY(void* handle) { return static_cast<Handle*>(handle)->probeY_; }
float meProbeHeading(void* handle) {
  return static_cast<Handle*>(handle)->probeHeading_;
}

}  // extern "C"
