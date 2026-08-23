// kernel_shim.cpp -- extern "C" ctypes surface for the native host test
// harness (this repo's first). Test scaffolding only: nothing under
// src/ knows this file exists, and it is compiled only into this
// test's own throwaway shared library (see test_kernel_harness.py).
//
// ctypes cannot call C++ methods directly, so this file is the thin
// translation layer: one opaque handle bundling a
// DiffDrive::DifferentialDrive kernel with its own private FakeMotor x2/
// FakeClock/FakeSleeper/FakeFiberLauncher, plus free functions Python
// can bind by name -- mirroring
// radio-robot-lib/tests/protocol/protocol_shim.cpp's own shape exactly.
#include <cstdint>

#include "diffdrive.h"
#include "fake_ports.h"

namespace {

struct Handle {
  FakeMotor left;
  FakeMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;

  Handle() : kernel(left, right, clock, sleeper, launcher) {}
};

FakeMotor& motorFor(Handle* h, int side) { return side == 0 ? h->left : h->right; }

}  // namespace

extern "C" {

// ---- lifecycle -----------------------------------------------------------

void* kdCreate() { return new Handle(); }
void kdDestroy(void* handle) { delete static_cast<Handle*>(handle); }

// ---- config setters (the DifferentialDrive::setXxx() fluent surface,
// the subset a host test needs to calibrate the kernel enough to
// command it -- extend this list as later tickets need more knobs). ----

void kdSetMaxDuty(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setMaxDuty(v);
}
void kdSetFullDutyVelocity(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setFullDutyVelocity(v);
}
void kdSetKp(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setKp(v);
}
void kdSetKi(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setKi(v);
}
void kdSetIMax(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setIMax(v);
}
void kdSetKaff(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setKaff(v);
}
void kdSetPidMax(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setPidMax(v);
}
void kdSetTwistHoldGain(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setTwistHoldGain(v);
}
void kdSetSpeedFloor(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setSpeedFloor(v);
}
void kdSetPositionErrorMax(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setPositionErrorMax(v);
}
void kdSetCyclePeriod(void* handle, uint32_t v) {
  static_cast<Handle*>(handle)->kernel.setCyclePeriod(v);
}

// ---- commands --------------------------------------------------------
// Every Status-returning call returns DifferentialDrive::Status's
// DECLARATION-ORDER ordinal (src/diffdrive.h) -- see
// test_kernel_harness.py's STATUS_* constants, which mirror that order.

int kdBegin(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.begin());
}
int kdStart(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.start());
}
int kdDrive(void* handle, float velocity, float twist, uint32_t leaseMs) {
  return static_cast<int>(
      static_cast<Handle*>(handle)->kernel.drive(velocity, twist, leaseMs));
}
int kdDriveDuty(void* handle, float dutyLeft, float dutyRight,
                uint32_t leaseMs) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.driveDuty(
      dutyLeft, dutyRight, leaseMs));
}
void kdNeutral(void* handle) { static_cast<Handle*>(handle)->kernel.neutral(); }
void kdEstop(void* handle) { static_cast<Handle*>(handle)->kernel.estop(); }
void kdEstopClear(void* handle) {
  static_cast<Handle*>(handle)->kernel.estopClear();
}
void kdClearStallLatch(void* handle) {
  static_cast<Handle*>(handle)->kernel.clearStallLatch();
}
void kdRebasePosition(void* handle) {
  static_cast<Handle*>(handle)->kernel.rebasePosition();
}
void kdStep(void* handle) { static_cast<Handle*>(handle)->kernel.step(); }
int kdLastError(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.lastError());
}

// ---- output readback --------------------------------------------------
// One function per Output field a host test currently needs -- extend
// this list (mirroring DifferentialDrive::Output, src/diffdrive.h) as
// later tickets need more of it rather than exposing the whole struct
// at once.

float kdOutVelocity(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocity;
}
float kdOutTwist(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().twist;
}
float kdOutPositionLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().positionLeft;
}
float kdOutPositionRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().positionRight;
}
float kdOutVelocityLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityLeft;
}
float kdOutVelocityRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityRight;
}
float kdOutAppliedDutyLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().appliedDutyLeft;
}
float kdOutAppliedDutyRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().appliedDutyRight;
}
int kdOutReady(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().ready ? 1 : 0;
}
int kdOutEstopped(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().estopped ? 1 : 0;
}
int kdOutLeaseExpired(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().leaseExpired ? 1 : 0;
}
int kdOutStallHalted(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().stallHalted ? 1 : 0;
}
int kdOutSatLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().satLeft ? 1 : 0;
}
int kdOutSatRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().satRight ? 1 : 0;
}
int kdOutConnectedLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().connectedLeft ? 1 : 0;
}
int kdOutConnectedRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().connectedRight ? 1 : 0;
}
uint32_t kdOutCycleCount(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().cycleCount;
}

// ---- FakeMotor control/readback ---------------------------------------
// `side`: 0 == left, 1 == right.

void kdMotorArmPosition(void* handle, int side, float position,
                         uint64_t sampleTimeUs) {
  FakeMotor& m = motorFor(static_cast<Handle*>(handle), side);
  m.nextPositionValue = position;
  m.nextSampleTimeUs = sampleTimeUs;
}
void kdMotorSetCollectSucceeds(void* handle, int side, int succeeds) {
  motorFor(static_cast<Handle*>(handle), side).collectSucceeds = succeeds != 0;
}
void kdMotorSetVelocity(void* handle, int side, float v) {
  motorFor(static_cast<Handle*>(handle), side).velocityValue = v;
}
void kdMotorSetConnected(void* handle, int side, int connected) {
  motorFor(static_cast<Handle*>(handle), side).connectedValue = connected != 0;
}
void kdMotorSetWedged(void* handle, int side, int wedged) {
  motorFor(static_cast<Handle*>(handle), side).wedgedValue = wedged != 0;
}
void kdMotorSetWedgeSuspect(void* handle, int side, int suspect) {
  motorFor(static_cast<Handle*>(handle), side).wedgeSuspectValue = suspect != 0;
}

float kdMotorPosition(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).position();
}
uint64_t kdMotorSampleTime(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).sampleTime();
}
float kdMotorAppliedDuty(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).appliedDuty();
}
float kdMotorLastStagedDuty(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).lastStagedDuty;
}
int kdMotorSetDutyCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).setDutyCalls;
}
int kdMotorTickCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).tickCalls;
}
int kdMotorBeginCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).beginCalls;
}
int kdMotorEmergencyStopCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).emergencyStopCalls;
}
int kdMotorRebaselineCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).rebaselineCalls;
}
int kdMotorRequestSampleCalls(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).requestSampleCalls;
}
int kdMotorEmergencyStopped(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).emergencyStopped ? 1 : 0;
}

// ---- FakeClock ---------------------------------------------------------

void kdClockSetNow(void* handle, uint64_t nowUs) {
  static_cast<Handle*>(handle)->clock.nowUs = nowUs;
}
uint64_t kdClockNow(void* handle) {
  return static_cast<Handle*>(handle)->clock.nowUs;
}

// ---- FakeSleeper / FakeFiberLauncher readback --------------------------

int kdSleeperSleepCalls(void* handle) {
  return static_cast<Handle*>(handle)->sleeper.sleepCalls;
}
int kdSleeperYieldCalls(void* handle) {
  return static_cast<Handle*>(handle)->sleeper.yieldCalls;
}
uint32_t kdSleeperLastSleepMillis(void* handle) {
  return static_cast<Handle*>(handle)->sleeper.lastSleepMillis;
}
int kdLauncherLaunchCalls(void* handle) {
  return static_cast<Handle*>(handle)->launcher.launchCalls;
}

}  // extern "C"
