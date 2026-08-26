// wire_mock_adapter.h -- Wire::Adapter test double for the wire host
// test harness. Records which methods fired and with what arguments so
// a ctypes shim can read them back; canned return values are plain
// public fields a test sets before feed()ing a line. Test scaffolding
// only: nothing under src/ knows this file exists, and it is never
// linked into anything but this test's own shared library. Mirrors
// radio-robot-lib/tests/protocol/mock_adapter.h's own shape (its own
// scope note applies here verbatim).
//
// The six motion methods Wire::Adapter declares (onWheelsV/onWheelsX/
// onMoveX/onMoveV/onGoToR/onGoToW) each get one canned Result + call
// count + last-args record, same pattern as onStop/onSet/onTlm/onRun
// above. This class is NOT src/comms/wire_adapter.h's WireAdapter (the
// production adapter, which gives all six motion verbs real effect) --
// it is a generic recording double any wire_handler.cpp test can
// canned-answer however it needs, independent of what any one concrete
// Adapter actually does.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "comms/wire_handler.h"

class WireMockAdapter : public Wire::Adapter {
 public:
  static constexpr size_t kMaxFields = 4;
  static constexpr size_t kMaxRecordedRunArgs = 16;

  // ---- canned responses, set by the test before feed() --------------------
  Wire::Identity identityToReturn;
  // A full Wire::StatusFields -- status() below copies it whole (`out =
  // statusToReturn`), so every member StatusFields declares, including
  // sprint 010 ticket 003's new `cyc`, is already settable here with no
  // per-field plumbing in this class needed. (The one place that DOES
  // still need per-field plumbing is tests/host/wire_grammar_shim.cpp's
  // extern "C" wgSetStatus(), which sets fields individually rather
  // than assigning a whole struct -- that file's own wgSetStatus is
  // where a NEW StatusFields member actually needs a new parameter.)
  Wire::StatusFields statusToReturn;
  uint32_t nowToReturn = 0;
  Wire::Result stopResult = Wire::Result::kOk;
  Wire::Result setResult = Wire::Result::kOk;
  Wire::Result tlmResult = Wire::Result::kOk;
  Wire::Result runResult = Wire::Result::kOk;
  bool runHasResult = false;
  const char* runResultText = "";  // borrowed -- must outlive its use,
                                    // same contract as every other
                                    // canned string field on this mock

  // One canned Result per motion verb -- this mock has no kernel of its
  // own to drive (see tests/host/wire_motion_verb_shim.cpp's SEPARATE
  // WireAdapter+FakeMotor handle for that); a test arms whatever Result
  // it needs and exercises decode/dispatch purely at the wire level.
  Wire::Result wheelsVResult = Wire::Result::kOk;
  Wire::Result wheelsXResult = Wire::Result::kUnknown;
  Wire::Result moveXResult = Wire::Result::kUnknown;
  Wire::Result moveVResult = Wire::Result::kUnknown;
  Wire::Result goToRResult = Wire::Result::kUnknown;
  Wire::Result goToWResult = Wire::Result::kUnknown;

  // The reliability layer's completion channel (protocol.md S8.8) --
  // Adapter-owned, polled by the handler on every ack/nack. A test
  // drives these directly to exercise the piggyback; the default
  // (0 / kNone) matches "nothing has completed yet".
  uint32_t lastDoneToReturn = 0;
  Wire::DoneReason lastDoneReasonToReturn = Wire::DoneReason::kNone;

  // A small fixed config table -- the source of truth for both a named
  // GET and a bare GET's dump. A name not in this table is the "unknown
  // field" case (onGet() returns false).
  const char* fieldNames[kMaxFields] = {"group.alpha", "group.beta",
                                         "group.gamma", "group.delta"};
  float fieldValues[kMaxFields] = {1.5f, -2.25f, 0.0f, 100.0f};
  size_t numFields = kMaxFields;

  // A single extra name/value pair a test can point at an ARBITRARY
  // field name, checked before the fixed table above. nullptr (the
  // default) means no override is armed.
  const char* overrideName = nullptr;
  float overrideValue = 0.0f;

  // ---- call counts ----------------------------------------------------
  mutable int identityCalls = 0;
  mutable int nowCalls = 0;
  mutable int statusCalls = 0;
  int estopCalls = 0;
  int stopCalls = 0;
  mutable int getCalls = 0;
  int setCalls = 0;
  int tlmCalls = 0;
  int runCalls = 0;
  int wheelsVCalls = 0;
  int wheelsXCalls = 0;
  int moveXCalls = 0;
  int moveVCalls = 0;
  int goToRCalls = 0;
  int goToWCalls = 0;

  // ---- last-call arguments ----------------------------------------------
  uint32_t lastStopId = 0;
  bool lastStopImmediate = false;
  mutable char lastGetName[64] = {};
  char lastSetName[64] = {};
  float lastSetValue = 0.0f;
  uint32_t lastSetId = 0;
  Wire::TlmMode lastTlmMode = Wire::TlmMode::kOff;

  char lastRunName[64] = {};
  size_t lastRunArgc = 0;
  char lastRunArgs[kMaxRecordedRunArgs][64] = {};

  // One record per motion verb -- every field the verb's own onXxx()
  // received, plain public floats/uint32_t a test reads back after
  // feed(). Named per-verb (lastWheelsVLeft, not a shared lastLeft)
  // since a test may want to confirm one verb's own call log is
  // untouched while dispatching a DIFFERENT verb (e.g. proving MOVE_X's
  // kUnknown answer never touches onWheelsV at all).
  float lastWheelsVLeft = 0.0f, lastWheelsVRight = 0.0f;
  uint32_t lastWheelsVDuration = 0, lastWheelsVId = 0;

  float lastWheelsXLeft = 0.0f, lastWheelsXRight = 0.0f,
        lastWheelsXCruise = 0.0f;
  uint32_t lastWheelsXTimeout = 0, lastWheelsXId = 0;

  float lastMoveXDistance = 0.0f, lastMoveXRotation = 0.0f,
        lastMoveXCruise = 0.0f;
  uint32_t lastMoveXTimeout = 0, lastMoveXId = 0;

  float lastMoveVVx = 0.0f, lastMoveVOmega = 0.0f;
  uint32_t lastMoveVDuration = 0, lastMoveVId = 0;

  float lastGoToRX = 0.0f, lastGoToRY = 0.0f, lastGoToRSpeed = 0.0f,
        lastGoToRArrive = 0.0f;
  uint32_t lastGoToRTimeout = 0, lastGoToRId = 0;

  float lastGoToWX = 0.0f, lastGoToWY = 0.0f, lastGoToWSpeed = 0.0f,
        lastGoToWArrive = 0.0f;
  uint32_t lastGoToWTimeout = 0, lastGoToWId = 0;

  // ---- Wire::Adapter ------------------------------------------------------

  void identity(Wire::Identity& out) const override {
    ++identityCalls;
    out = identityToReturn;
  }
  uint32_t now() const override {
    ++nowCalls;
    return nowToReturn;
  }
  void status(Wire::StatusFields& out) const override {
    ++statusCalls;
    out = statusToReturn;
  }

  Wire::Result onWheelsV(float left, float right, uint32_t duration,
                         uint32_t id) override {
    ++wheelsVCalls;
    lastWheelsVLeft = left;
    lastWheelsVRight = right;
    lastWheelsVDuration = duration;
    lastWheelsVId = id;
    return wheelsVResult;
  }
  Wire::Result onWheelsX(float left, float right, float cruise,
                         uint32_t timeout, uint32_t id) override {
    ++wheelsXCalls;
    lastWheelsXLeft = left;
    lastWheelsXRight = right;
    lastWheelsXCruise = cruise;
    lastWheelsXTimeout = timeout;
    lastWheelsXId = id;
    return wheelsXResult;
  }
  Wire::Result onMoveX(float distance, float rotation, float cruise,
                       uint32_t timeout, uint32_t id) override {
    ++moveXCalls;
    lastMoveXDistance = distance;
    lastMoveXRotation = rotation;
    lastMoveXCruise = cruise;
    lastMoveXTimeout = timeout;
    lastMoveXId = id;
    return moveXResult;
  }
  Wire::Result onMoveV(float v_x, float omega, uint32_t duration,
                       uint32_t id) override {
    ++moveVCalls;
    lastMoveVVx = v_x;
    lastMoveVOmega = omega;
    lastMoveVDuration = duration;
    lastMoveVId = id;
    return moveVResult;
  }
  Wire::Result onGoToR(float x, float y, float speed, float arrive,
                       uint32_t timeout, uint32_t id) override {
    ++goToRCalls;
    lastGoToRX = x;
    lastGoToRY = y;
    lastGoToRSpeed = speed;
    lastGoToRArrive = arrive;
    lastGoToRTimeout = timeout;
    lastGoToRId = id;
    return goToRResult;
  }
  Wire::Result onGoToW(float x, float y, float speed, float arrive,
                       uint32_t timeout, uint32_t id) override {
    ++goToWCalls;
    lastGoToWX = x;
    lastGoToWY = y;
    lastGoToWSpeed = speed;
    lastGoToWArrive = arrive;
    lastGoToWTimeout = timeout;
    lastGoToWId = id;
    return goToWResult;
  }

  void onEstop() override { ++estopCalls; }
  Wire::Result onStop(bool immediate, uint32_t id) override {
    ++stopCalls;
    lastStopId = id;
    lastStopImmediate = immediate;
    return stopResult;
  }
  bool onGet(const char* name, float& out) const override {
    ++getCalls;
    std::snprintf(lastGetName, sizeof(lastGetName), "%s", name);
    if (overrideName != nullptr && std::strcmp(name, overrideName) == 0) {
      out = overrideValue;
      return true;
    }
    for (size_t i = 0; i < numFields; ++i) {
      if (std::strcmp(name, fieldNames[i]) == 0) {
        out = fieldValues[i];
        return true;
      }
    }
    return false;
  }
  Wire::Result onSet(const char* name, float value, uint32_t id) override {
    ++setCalls;
    std::snprintf(lastSetName, sizeof(lastSetName), "%s", name);
    lastSetValue = value;
    lastSetId = id;
    return setResult;
  }
  size_t fieldCount() const override { return numFields; }
  const char* fieldName(size_t index) const override {
    return index < numFields ? fieldNames[index] : "";
  }
  Wire::Result onTlm(Wire::TlmMode mode) override {
    ++tlmCalls;
    lastTlmMode = mode;
    return tlmResult;
  }
  uint32_t lastDone() const override { return lastDoneToReturn; }
  Wire::DoneReason lastDoneReason() const override {
    return lastDoneReasonToReturn;
  }
  Wire::Result onRun(const char* name, const char* const* argv, size_t argc,
                     char* result, size_t resultCapacity,
                     bool& hasResult) override {
    ++runCalls;
    std::snprintf(lastRunName, sizeof(lastRunName), "%s", name);
    lastRunArgc = argc;
    for (size_t i = 0; i < argc && i < kMaxRecordedRunArgs; ++i) {
      std::snprintf(lastRunArgs[i], sizeof(lastRunArgs[i]), "%s", argv[i]);
    }
    hasResult = runHasResult;
    if (runHasResult) {
      std::snprintf(result, resultCapacity, "%s", runResultText);
    }
    return runResult;
  }
};
