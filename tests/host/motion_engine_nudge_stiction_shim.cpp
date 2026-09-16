// motion_engine_nudge_stiction_shim.cpp -- extern "C" ctypes surface for
// sprint 039 ticket 004's own behavioral host tests
// (test_motion_engine_nudge_stiction.py): MotionEngine's nudge stepper
// (beginNudge()/serviceNudge(), dispatched through service()) wired to a
// REAL DiffDrive::DifferentialDrive kernel over a StictionMotor double
// defined in THIS file, not fake_ports.h's FakeMotor.
//
// A SEPARATE shim from motion_engine_shim.cpp (which conftest.py's
// `motion_lib` fixture already compiles for the other thirteen files in
// this directory) rather than an extension of it, because the nudge
// stepper's own acceptance criteria -- "pulses fire only when settled",
// "the ledger converges", "a target reachable in N pulses does not take
// N+1" -- all need a Motor double that AUTONOMOUSLY integrates position
// from applied duty across repeated tick() calls. `firePulseAndSettle()`
// drives its own internal, synchronous kernel.step() loop with no
// per-tick control point from Python (the same reason
// test_motion_engine_pulse.py needed FakeMotor's dutyHistory rather than
// re-arming a position by hand between steps) -- so the physics has to
// live IN the double, not be scripted from outside it one step() at a
// time the way every other file in this directory's FakeMotor tests do.
// fake_ports.h's own FakeMotor deliberately has NO such physics ("No
// timer, no clock, deterministic, caller-driven": that file's own header
// comment) -- adding it there would change behavior for the other twelve
// consuming test files. wire_motion_verb_shim.cpp and
// sim_robot_shim.cpp are this test tree's own precedent for a second,
// purpose-built shim when the double itself is fundamentally different
// in kind, not merely another entry point on the same handle
// (motion_engine_shim.cpp's own header comment, "don't invent a second
// shim ... when a later ticket needs another MotionEngine entry point
// exposed", is about THAT case, not this one).
//
// StictionMotor's model: no motion at all while |appliedDuty| stays
// below breakawayDuty; once a tick's applied duty clears that threshold,
// position advances by exactly one signed, fixed quantized increment
// (stepCounts) for THAT tick -- "no motion below a breakaway duty,
// quantized increments above" (ticket 004's own description, echoing the
// sprint plan's SUC-004 stiction-plant shape). The constants below are a
// synthetic test model chosen for a clean, round, host-test-friendly
// magnitude -- NOT a hardware measurement, and not intended to
// reproduce captures/039-003-pulse-gate-20260916/notes.md's own
// per-pulse figures (that file's numbers are the real, measured
// operating point this stepper's DEFAULTS are seeded from; this file's
// stiction constants are chosen only to make the STEPPER's own logic
// exercisable deterministically on a host).
#include <cmath>
#include <cstdint>

#include "core/diffdrive.h"
#include "fake_ports.h"  // FakeClock/FakeSleeper/FakeFiberLauncher only
#include "motion/motion_engine.h"

namespace {

// [1] duty fraction -- see fake_ports.h's own FakeMotor::setDuty() for
// why Motor::setDuty() itself takes a [-1, 1] fraction, not a percent.
constexpr float kDefaultBreakawayDuty = 0.10f;
// [counts] per qualifying tick -- see this file's own header comment on
// why this is a round test constant, not a hardware figure.
constexpr float kDefaultStepCounts = 10.0f;
// [us] StictionMotor's own self-advancing sample clock, independent of
// FakeClock (which MotionEngine's now()/deadline logic reads instead --
// see this file's own header comment on why the two must be
// independent): DifferentialDrive::refreshSample() (src/core/
// diffdrive.cpp) only accepts a new position when Motor::sampleTime()
// actually CHANGES, and a pulse's own internal kernel.step() loop runs
// with FakeClock frozen (nothing in that loop advances it, mirroring
// pulseWheels()'s own existing host tests) -- so this motor stamps its
// own monotonically increasing sample time on every tick() regardless.
constexpr uint64_t kSampleIntervalUs = 2000;  // [us] ~2 ms/tick

class StictionMotor : public DiffDrive::Motor {
 public:
  void begin() override { began = true; }
  void requestSample() override {}

  void setDuty(float duty) override {
    lastStagedDuty = duty;
    if (dutyHistoryCount < kMaxDutyHistory) dutyHistory[dutyHistoryCount] = duty;
    ++dutyHistoryCount;
  }

  void emergencyStop() override {
    lastStagedDuty = 0.0f;
    appliedDutyValue_ = 0.0f;
  }

  void tick(uint64_t /*nowUs*/) override {
    appliedDutyValue_ = lastStagedDuty;
    ++tickCount;
    sampleTimeValue_ += kSampleIntervalUs;
    if (appliedDutyValue_ >= breakawayDuty) {
      positionValue_ += stepCounts;
    } else if (appliedDutyValue_ <= -breakawayDuty) {
      positionValue_ -= stepCounts;
    }
    // Below breakaway magnitude: pure stiction, no motion at all.
  }

  float position() const override { return positionValue_; }
  // Unread by the kernel's own Output (Output::velocityLeft/Right are
  // computed by DifferentialDrive::refreshSample() from position()/
  // sampleTime() deltas -- see fake_ports.h's own FakeMotor::velocity()
  // comment, which applies identically here).
  float velocity() const override { return 0.0f; }
  float appliedDuty() const override { return appliedDutyValue_; }
  bool connected() const override { return true; }
  uint64_t sampleTime() const override { return sampleTimeValue_; }
  void rebaseline() override { ++rebaselineCalls; }
  bool wedged() const override { return false; }
  bool wedgeSuspect() const override { return false; }

  void clearDutyHistory() {
    dutyHistoryCount = 0;
    for (float& v : dutyHistory) v = 0.0f;
  }

  // ---- stiction model parameters, test-armed before firing ----
  float breakawayDuty = kDefaultBreakawayDuty;
  float stepCounts = kDefaultStepCounts;

  // ---- readback ----
  float lastStagedDuty = 0.0f;
  int tickCount = 0;
  int rebaselineCalls = 0;
  bool began = false;

  static constexpr int kMaxDutyHistory = 512;
  float dutyHistory[kMaxDutyHistory] = {};
  int dutyHistoryCount = 0;

 private:
  float positionValue_ = 0.0f;
  float appliedDutyValue_ = 0.0f;
  uint64_t sampleTimeValue_ = 1000;  // nonzero from the first tick
};

struct Handle {
  StictionMotor left;
  StictionMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;

  Handle()
      : kernel(left, right, clock, sleeper, launcher), engine(kernel, clock) {}
};

StictionMotor& motorFor(Handle* h, int side) {
  return side == 0 ? h->left : h->right;
}

}  // namespace

extern "C" {

void* mnCreate() { return new Handle(); }
void mnDestroy(void* handle) { delete static_cast<Handle*>(handle); }

void mnSetMaxDuty(void* handle, float v) {
  static_cast<Handle*>(handle)->kernel.setMaxDuty(v);
}
int mnBegin(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->kernel.begin());
}
void mnStep(void* handle) { static_cast<Handle*>(handle)->kernel.step(); }
uint32_t mnCycleCount(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().cycleCount;
}
int mnOutEstopped(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().estopped ? 1 : 0;
}
void mnKernelEstop(void* handle) {
  static_cast<Handle*>(handle)->kernel.estop();
}

// Drives ONE raw-duty kernel.step() directly -- bypassing MotionEngine
// entirely -- so a test can plant a genuinely nonzero MEASURED velocity
// in Output (from that tick's own position delta, since StictionMotor's
// sampleTime always advances) immediately before a nudge begins or
// services. Simulates "some other command left the wheels moving" for
// the "pulses fire only when settled" test, which a purely autonomous
// motor has no other way to reach from Python (there is no per-tick
// control point inside firePulseAndSettle() itself -- this file's own
// header comment).
void mnKickThenStep(void* handle, float ampLeft, float ampRight) {
  Handle* h = static_cast<Handle*>(handle);
  h->kernel.driveDuty(ampLeft, ampRight, 5000u);
  h->kernel.step();
}

void mnClockSetNow(void* handle, uint64_t nowUs) {
  static_cast<Handle*>(handle)->clock.nowUs = nowUs;
}
void mnClockAdvance(void* handle, uint64_t deltaUs) {
  static_cast<Handle*>(handle)->clock.nowUs += deltaUs;
}

// `side`: 0 == left, 1 == right.
void mnSetStictionParams(void* handle, int side, float breakawayDuty,
                         float stepCounts) {
  StictionMotor& m = motorFor(static_cast<Handle*>(handle), side);
  m.breakawayDuty = breakawayDuty;
  m.stepCounts = stepCounts;
}
float mnPosition(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).position();
}
int mnDutyHistoryCount(void* handle, int side) {
  return motorFor(static_cast<Handle*>(handle), side).dutyHistoryCount;
}
float mnDutyHistoryAt(void* handle, int side, int index) {
  return motorFor(static_cast<Handle*>(handle), side).dutyHistory[index];
}
void mnClearDutyHistory(void* handle, int side) {
  motorFor(static_cast<Handle*>(handle), side).clearDutyHistory();
}

// ---- MotionEngine geometry (needed by a test computing an expected
// target in Python) ------------------------------------------------------
float mnCountsPerMm(void* handle) {
  return static_cast<Handle*>(handle)->engine.countsPerMm();
}
float mnEffectiveTrackWidth(void* handle) {
  return static_cast<Handle*>(handle)->engine.effectiveTrackWidth();
}
void mnSetTrackWidth(void* handle, float mm) {
  static_cast<Handle*>(handle)->engine.setTrackWidth(mm);
}
void mnSetTravelCalib(void* handle, float mmPerDeg) {
  static_cast<Handle*>(handle)->engine.setTravelCalib(mmPerDeg);
}

// ---- arrival margins (limits().arriveDist/arriveYaw) -- a test tunes
// these to make convergence land deterministically within a small,
// countable number of pulses. ---------------------------------------
void mnSetArriveDist(void* handle, float mm) {
  static_cast<Handle*>(handle)->engine.limits().setArriveDist(mm);
}
void mnSetArriveYaw(void* handle, float deg) {
  static_cast<Handle*>(handle)->engine.limits().setArriveYaw(deg);
}

// ---- the nudge stepper itself -------------------------------------
void mnSetNudgeAmplitude(void* handle, float percent) {
  static_cast<Handle*>(handle)->engine.setNudgeAmplitude(percent);
}
void mnSetNudgeWidthTicks(void* handle, int32_t ticks) {
  static_cast<Handle*>(handle)->engine.setNudgeWidthTicks(ticks);
}
void mnSetNudgeSettle(void* handle, float ms) {
  static_cast<Handle*>(handle)->engine.setNudgeSettle(ms);
}
void mnBeginNudge(void* handle, float distanceMm, float rotationRad,
                  uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.beginNudge(distanceMm, rotationRad,
                                                  timeoutMs);
}
int mnIsNudgeActive(void* handle) {
  return static_cast<Handle*>(handle)->engine.isNudgeActive() ? 1 : 0;
}
int32_t mnNudgePulseCount(void* handle) {
  return static_cast<Handle*>(handle)->engine.nudgePulseCount();
}
int32_t mnNudgeMaxPulses(void*) {
  return diffDrive::MotionEngine::nudgeMaxPulses();
}
// service()'s own single dispatch point -- routes to serviceNudge()
// whenever nudge_ is active (service()'s own header comment,
// motion_engine.h). A test drives one "outer tick" as
// mnStep() + mnServiceNudge(), mirroring Rig::tickDrive()'s own
// kernel.step() + engine.service() pairing (shims.cpp).
int mnService(void* handle) {
  return static_cast<Handle*>(handle)->engine.service() ? 1 : 0;
}

}  // extern "C"
