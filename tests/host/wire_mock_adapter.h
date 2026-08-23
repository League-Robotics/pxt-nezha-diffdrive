// wire_mock_adapter.h -- Wire::Adapter test double for the wire host
// test harness (sprint 003 ticket 003). Records which methods fired and
// with what arguments so a ctypes shim can read them back; canned
// return values are plain public fields a test sets before feed()ing a
// line. Test scaffolding only: nothing under src/ knows this file
// exists, and it is never linked into anything but this test's own
// shared library. Mirrors radio-robot-lib/tests/protocol/mock_adapter.h's
// own shape (its own scope note applies here verbatim) -- scoped down to
// the nine non-motion sequenced verbs plus HELLO/PING/ESTOP this
// project's wire_handler.cpp dispatches as of this ticket; ticket 004
// widens this file the same way it widens Wire::Adapter itself.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "wire_handler.h"

class WireMockAdapter : public Wire::Adapter {
 public:
  static constexpr size_t kMaxFields = 4;
  static constexpr size_t kMaxRecordedRunArgs = 16;

  // ---- canned responses, set by the test before feed() --------------------
  Wire::Identity identityToReturn;
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
