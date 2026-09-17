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
//
// EXTENDED sprint 039 ticket 006 (test_creep_self_lock_stiction_sim.py):
// this file's own StictionMotor is reused, per that ticket's own
// instruction to extend rather than duplicate it, for a SECOND
// investigation unrelated to the nudge stepper above -- whether a slow
// CONTINUOUS hold (wheelsV()/moveV(), not a pulse) can self-lock below
// breakaway. The addition is two-part: (1) StictionMotor grew
// `withholdStampOnStiction` (default false, so every ticket 004 test
// keeps its original behavior byte-for-byte) so a caller can select the
// REAL port's stamp-withholding behavior instead of the always-advance
// model ticket 004 needed; (2) new exported entry points below
// (mnWheelsV/mnMoveV/mnIsDriving/mnOutVelocity*/mnOutAppliedDuty*/
// mnOutI2cFaultCount/mnSetVFloor/mnSetVMax/mnConfigureCreepPlant) drive
// MotionEngine's OTHER primitive -- the continuous Hold -- through the
// same real kernel this file already builds, rather than adding a
// third shim for a Motor double this file already owns.
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
    bool cleared = false;
    if (appliedDutyValue_ >= breakawayDuty) {
      positionValue_ += stepCounts;
      cleared = true;
    } else if (appliedDutyValue_ <= -breakawayDuty) {
      positionValue_ -= stepCounts;
      cleared = true;
    }
    // Below breakaway magnitude: pure stiction, no motion at all.
    //
    // ticket 006 addition: `withholdStampOnStiction` (default false --
    // ticket 004's own tests are unaffected) selects which of two
    // real ports' behavior this tick's sample-stamp update mirrors.
    // false (the original ticket-004 model) advances sampleTimeValue_
    // unconditionally every tick, which is right for that ticket's own
    // deterministic-pulse tests (a pulse's own dutyHistory readback
    // does not depend on stamp health) but is NOT what the real
    // NezhaMotorPort does. true mirrors
    // NezhaMotorPort::collect() (src/platform/nezha_port.cpp:391-406,
    // READ ONLY): a successful read whose raw counts are unchanged
    // from the previous accepted sample, while driven, withholds the
    // fresh sampleTime_ stamp -- "sampleTime_ HOLDS" is that function's
    // own comment. DifferentialDrive::step() turns a held stamp into
    // `sampleAdvanced{Left,Right}_ == false` (diffdrive.cpp:550-551),
    // which is the exact input K2's guard in positionError() (diffdrive
    // .cpp:955-991, READ ONLY) tests. Without this mode the shim cannot
    // reproduce the creep self-lock at all: with the stamp always
    // advancing, `advanced` is always true and K2 never suppresses
    // anything, so the I-term winds up normally regardless of physical
    // motion -- see test_creep_self_lock_stiction_sim.py's own
    // refutation run, which uses the DEFAULT (false) for exactly that
    // contrast.
    if (cleared || !withholdStampOnStiction) {
      sampleTimeValue_ += kSampleIntervalUs;
    }
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
  bool withholdStampOnStiction = false;  // ticket 006 -- see tick()'s comment

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

// ---- ticket 006: the continuous-hold primitive (wheelsV()/moveV()),
// against the same StictionMotor + real kernel above, to investigate the
// creep self-lock independently of the nudge stepper. `mnService` above
// is reused unchanged -- MotionEngine::service() already dispatches to
// the Hold branch whenever nudge_ is inactive, which it is here (this
// handle never calls beginNudge()). -------------------------------------

void mnWheelsV(void* handle, float left, float right, uint32_t durationMs) {
  static_cast<Handle*>(handle)->engine.wheelsV(left, right, durationMs);
}
void mnMoveV(void* handle, float vx, float omega, uint32_t durationMs) {
  static_cast<Handle*>(handle)->engine.moveV(vx, omega, durationMs);
}
int mnIsDriving(void* handle) {
  return static_cast<Handle*>(handle)->engine.isDriving() ? 1 : 0;
}

// side: 0 == left, 1 == right.
void mnSetWithholdStampOnStiction(void* handle, int side, int enabled) {
  motorFor(static_cast<Handle*>(handle), side).withholdStampOnStiction =
      enabled != 0;
}

float mnOutVelocityLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityLeft;
}
float mnOutVelocityRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().velocityRight;
}
float mnOutAppliedDutyLeft(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().appliedDutyLeft;
}
float mnOutAppliedDutyRight(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().appliedDutyRight;
}
uint32_t mnOutI2cFaultCount(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().i2cFaultCount;
}
int mnOutStallHalted(void* handle) {
  return static_cast<Handle*>(handle)->kernel.output().stallHalted ? 1 : 0;
}

// MotionLimits' own vFloor/vMax -- exposed so a test can prove (rather
// than merely read, in motion_engine.cpp) whether the Hold branch's
// shaper.advance() call is actually sensitive to vFloor. See
// test_creep_self_lock_stiction_sim.py's own
// test_hold_vfloor_value_has_no_effect_on_commanded_ramp.
void mnSetVFloor(void* handle, float mmPerS) {
  static_cast<Handle*>(handle)->engine.limits().setVFloor(mmPerS);
}
void mnSetVMax(void* handle, float mmPerS) {
  static_cast<Handle*>(handle)->engine.limits().setVMax(mmPerS);
}

// Bundles the DiffDrive::Config fields this investigation's PID plant
// needs into one call rather than growing eight more single-field
// exports -- every field here already has an identically-named fluent
// setter on DifferentialDrive (src/core/diffdrive.h), chained in the
// same order the historical docs/code-review/2026-09-02/raw/
// stiction_probe.cpp reference used them (kp/ki/iMax/pidMax/posErrMax),
// extended with fullDutyVelocity and maxDuty so a test does not also
// need mnSetMaxDuty(). wheelGain/wheelIntercept are left at Config's own
// defaults (1.0/0.0 -- see diffdrive.h's Config struct), which makes
// correctedCommand() return the commanded speed UNCHANGED -- exactly
// the "duty is pure feedforward" setup test_motion_engine_reductions.py
// already documents using for the same reason. kaff is included even
// though every call in this investigation passes 0 for it (isolating
// the I-term, mirroring the historical reference's own kp=0 choice) so
// a test can deliberately turn it on to check that is NOT what rescues
// a locked wheel either.
void mnConfigureCreepPlant(void* handle, float maxDuty,
                            float fullDutyVelocity, float kp, float ki,
                            float iMax, float kaff, float pidMax,
                            float posErrMax) {
  static_cast<Handle*>(handle)->kernel.setMaxDuty(maxDuty)
      .setFullDutyVelocity(fullDutyVelocity)
      .setKp(kp)
      .setKi(ki)
      .setIMax(iMax)
      .setKaff(kaff)
      .setPidMax(pidMax)
      .setPositionErrorMax(posErrMax);
}

}  // extern "C"
