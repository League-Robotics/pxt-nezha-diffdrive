// motion_engine_shim.cpp -- extern "C" ctypes surface for sprint 003
// tickets 006/007's own host tests (test_motion_engine_primitives.py,
// test_motion_engine_reductions.py): MotionEngine's geometry
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
#include <cstdint>

#include "diffdrive.h"
#include "encoder_pose_source.h"
#include "fake_ports.h"
#include "fake_pose_source.h"
#include "motion_engine.h"

namespace {

struct Handle {
  FakeMotor left;
  FakeMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  // Sprint 003 ticket 010: the goToW() PoseSource these tests arm via
  // mePoseSourceSetPose() -- NOT constructed over `engine` (PoseSource is
  // passed per-call, not stored; see motion_engine.h's own comment), so
  // its declaration order relative to `engine` above does not matter.
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
int meBegin(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.begin());
}
void meStep(void* handle) { static_cast<Handle*>(handle)->kernel.step(); }
int meOutLeaseExpired(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().leaseExpired ? 1 : 0;
}

// Ticket 009 (regression: post-move neutral delivery, commit 3e919e5):
// exposes the kernel's own MEASURED velocity (diffdrive.h Output.
// velocityLeft/Right -- computed from encoder position deltas across
// two collects, refreshSample(), NOT the commanded duty) so a host test
// can prove that delivering a zero DUTY to the FakeMotor (meMotorLastStagedDuty)
// is a distinct event from the reported velocity actually reading at
// rest -- shims.cpp's own settle-tick loop (Rig::tickDrive()) exists
// precisely because these two can diverge for several ticks after a
// move ends.
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
// Sprint 007 ticket 005 (closing R-14/API-06): exposes the setter
// rotationalSlip_ never had -- see motion_engine.h's own setter/field
// comments for the validation and the load-bearing derivation this
// field's default carries.
void meSetRotationalSlip(void* handle, float slip) {
  static_cast<Handle*>(handle)->engine.setRotationalSlip(slip);
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

// ---- MotionEngine: the move engine (motion-api.md S3.3-S3.5,
// sprint 003 ticket 007) -------------------------------------------------

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
int meProgress(void* handle) {
  return static_cast<Handle*>(handle)->engine.progress();
}
uint32_t meWrongWayCount(void* handle) {
  return static_cast<Handle*>(handle)->engine.wrongWayCount();
}
void meSetDistTaper(void* handle, float counts) {
  static_cast<Handle*>(handle)->engine.setDistTaper(counts);
}
void meSetYawTaper(void* handle, float counts) {
  static_cast<Handle*>(handle)->engine.setYawTaper(counts);
}
void meSetDistFloor(void* handle, float fraction) {
  static_cast<Handle*>(handle)->engine.setDistFloor(fraction);
}
void meSetTurnFloor(void* handle, float fraction) {
  static_cast<Handle*>(handle)->engine.setTurnFloor(fraction);
}
void meSetRampMs(void* handle, float ms) {
  static_cast<Handle*>(handle)->engine.setRampMs(ms);
}

// Arms the NEXT tick()'s reported encoder position directly (bypassing
// any simulated physics -- see fake_ports.h's own FakeMotor comment):
// lets a test place the encoders wherever it wants without hand-rolling
// a duty-to-distance integrator, e.g. to force a segment's completion
// (or a pivot-then-straight phase transition) on a specific tick.
// `sampleTimeUs` must also advance (and be nonzero) each call --
// DifferentialDrive::refreshSample() (src/diffdrive.cpp) only accepts a
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

}  // extern "C"
