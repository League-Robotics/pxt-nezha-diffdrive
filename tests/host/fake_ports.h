// fake_ports.h -- FakeMotor/FakeClock/FakeSleeper/FakeFiberLauncher: test
// doubles for DiffDrive::DifferentialDrive's four ports (src/diffdrive.h),
// used to drive the kernel synchronously from a native host build with no
// micro:bit/PXT/CODAL involvement at all.
//
// Test scaffolding only: nothing under src/ knows this file exists, and it
// is compiled only into this test tree's own throwaway shared libraries
// (see test_kernel_harness.py's compile_shared_lib()). Modeled on
// radio-robot-lib/tests/protocol/mock_adapter.h's shape -- a test double
// with plain public "canned response" fields a test sets before driving
// the code under test, plus call counters/last-argument fields a test
// reads back afterwards -- adapted to diffdrive.h's Motor/Clock/Sleeper/
// FiberLauncher ports instead of Protocol::Adapter.
//
// "No timer, no clock, deterministic, caller-driven" (matching
// FakeMotionAdapter's own spirit, radio-robot-lib/tests/protocol/
// fake_motion_adapter.h): none of these fakes do their own bookkeeping of
// elapsed time or simulated physics. A test arms exactly the value each
// port method should report, then calls DifferentialDrive::step()
// (never start()) to advance the kernel by exactly one cycle.
#pragma once

#include <cstdint>

#include "diffdrive.h"

// ---------------------------------------------------------------------
// FakeMotor -- implements DiffDrive::Motor.
//
// Honors the two sharp semantics diffdrive.md §2.1 calls out explicitly:
//
//   - sampleTime() stamps on a SUCCESSFUL collect only. A test arms the
//     position/sampleTime the NEXT tick() should report via
//     armNextSample(); tick() commits them into the values position()/
//     sampleTime() actually return only when collectSucceeds is true. A
//     failed collect (collectSucceeds == false) leaves position()/
//     sampleTime() exactly where they were, letting a test exercise
//     DifferentialDrive's i2cFaultCount_ path (refreshSample() compares
//     the stamp before/after tick() to detect a stalled collect).
//   - rebaseline() issues no bus traffic: it only increments a call
//     counter. position()/sampleTime()/velocity()/connected() all read
//     back completely unchanged immediately after a rebaseline() call --
//     that invariant is exactly what a test asserts to prove this
//     contract is honored (see
//     test_kernel_harness.py::test_rebaseline_issues_no_bus_traffic).
class FakeMotor : public DiffDrive::Motor {
 public:
  void begin() override {
    ++beginCalls;
    began = true;
  }

  void requestSample() override {
    ++requestSampleCalls;
    sampleRequested = true;
  }

  // Stages the raw duty write -- NOT yet "landed" (appliedDuty()) until
  // the next tick(), mirroring real hardware's stage/tick split.
  void setDuty(float duty) override {
    ++setDutyCalls;
    lastStagedDuty = duty;
  }

  void emergencyStop() override {
    ++emergencyStopCalls;
    emergencyStopped = true;
  }

  // "execute staged + collect": lands the most recently staged duty as
  // appliedDuty(), then -- only if collectSucceeds is armed true (the
  // default) -- commits the test-armed nextPosition/nextSampleTimeUs
  // into position()/sampleTime(). See the class comment above for why
  // a failed collect must leave those two untouched.
  void tick(uint64_t nowUs) override {
    ++tickCalls;
    lastTickNowUs = nowUs;
    appliedDutyValue_ = lastStagedDuty;
    if (collectSucceeds) {
      sampleTimeValue_ = nextSampleTimeUs;
      positionValue_ = nextPositionValue;
    }
    sampleRequested = false;
  }

  float position() const override { return positionValue_; }
  float velocity() const override { return velocityValue; }
  float appliedDuty() const override { return appliedDutyValue_; }
  bool connected() const override { return connectedValue; }
  uint64_t sampleTime() const override { return sampleTimeValue_; }
  void rebaseline() override { ++rebaselineCalls; }

  bool wedged() const override { return wedgedValue; }
  bool wedgeSuspect() const override { return wedgeSuspectValue; }

  // ---- test-armed inputs, set BEFORE calling DifferentialDrive::step()
  // ----
  bool connectedValue = true;
  bool wedgedValue = false;
  bool wedgeSuspectValue = false;
  // Motor::velocity() -- diffdrive.cpp's ONLY reader is stageDuty()'s
  // "are the wheels still coasting" check; it is NOT where
  // DifferentialDrive::Output::velocity/velocityLeft/velocityRight come
  // from (those are computed by the kernel itself, from position()/
  // sampleTime() deltas across two collects -- see refreshSample()).
  float velocityValue = 0.0f;
  bool collectSucceeds = true;    // this tick()'s collect outcome
  float nextPositionValue = 0.0f;   // [counts] armed for the next tick()
  uint64_t nextSampleTimeUs = 0;    // [us] armed for the next tick()

  // ---- call recording, read back after step() ----
  int beginCalls = 0;
  int requestSampleCalls = 0;
  int setDutyCalls = 0;
  int emergencyStopCalls = 0;
  int tickCalls = 0;
  int rebaselineCalls = 0;
  bool began = false;
  bool emergencyStopped = false;
  bool sampleRequested = false;
  float lastStagedDuty = 0.0f;
  uint64_t lastTickNowUs = 0;

 private:
  float positionValue_ = 0.0f;
  float appliedDutyValue_ = 0.0f;
  uint64_t sampleTimeValue_ = 0;
};

// ---------------------------------------------------------------------
// FakeClock -- implements DiffDrive::Clock. A bare test-settable
// microsecond counter; nothing advances it but an explicit setNow() call
// from the test.
class FakeClock : public DiffDrive::Clock {
 public:
  uint64_t nowMicros() const override { return nowUs; }

  uint64_t nowUs = 0;
};

// ---------------------------------------------------------------------
// FakeSleeper -- implements DiffDrive::Sleeper. Every call is instant
// (this is a synchronous host harness, not a real-time system) --
// DifferentialDrive::step() calls sleepMillis() twice per step for the
// encoder settle window, and a real sleep there would make every test
// pay wall-clock cost for no reason.
class FakeSleeper : public DiffDrive::Sleeper {
 public:
  void sleepMillis(uint32_t duration) override {
    ++sleepCalls;
    lastSleepMillis = duration;
  }
  void yield() override { ++yieldCalls; }

  int sleepCalls = 0;
  int yieldCalls = 0;
  uint32_t lastSleepMillis = 0;
};

// ---------------------------------------------------------------------
// FakeFiberLauncher -- implements DiffDrive::FiberLauncher as a true
// no-op, per docs/design/diffdrive.md §2: "a synchronous test harness
// can decline FiberLauncher ... call step() yourself." This harness
// drives DifferentialDrive::step() directly and never calls start(), so
// launch() is expected to never fire in ordinary use; it is a safe
// no-op (rather than aborting the process) specifically so a test CAN
// call start() deliberately -- e.g. to assert start()'s own return
// Status before begin() -- without taking the whole pytest process down.
class FakeFiberLauncher : public DiffDrive::FiberLauncher {
 public:
  void launch(void (*entry)(void*), void* context) override {
    ++launchCalls;
    lastEntry = entry;
    lastContext = context;
  }

  int launchCalls = 0;
  void (*lastEntry)(void*) = nullptr;
  void* lastContext = nullptr;
};
