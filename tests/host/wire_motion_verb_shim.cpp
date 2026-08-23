// wire_motion_verb_shim.cpp -- extern "C" ctypes surface for sprint 003
// ticket 004's own host tests (test_wire_motion_verbs.py): the six
// motion verbs' wire decode/dispatch, and src/wire_adapter.h's
// WireAdapter wired to a REAL kernel. Test scaffolding only: nothing
// under src/ knows this file exists, and it is compiled only into this
// test's own throwaway shared library.
//
// Two handles, two different jobs, mirroring wire_grammar_shim.cpp's own
// one-shim-several-concerns shape:
//
//   - WvHandle (wvXxx functions): WireHandler + WireMockAdapter, exactly
//     like wire_grammar_shim.cpp's own Handle -- exercises decode arity/
//     malformed-input/dispatch for all six motion verbs at the wire
//     level, independent of what any one concrete Adapter does with
//     them.
//   - WaHandle (waXxx functions): WireHandler + the REAL
//     diffDrive::WireAdapter (src/wire_adapter.h), wired to a REAL
//     DiffDrive::DifferentialDrive kernel over FakeMotor -- this is what
//     proves WHEELS_V's real effect (ticket 004's own acceptance
//     criterion) and WireAdapter's own GET/SET field-name table and
//     STOP/ESTOP wiring, end to end, with no micro:bit involved.
//
// WaHandle supplies its OWN definitions of the shims.cpp free functions
// wire_adapter.cpp forward-declares (setWheelsTimed/stopAll/estopAll/
// setKernelValue/getConfigValue/diagValue) -- a FakeMotor-backed kernel
// standing in for the real Rig/NezhaMotorPort composition, the same
// "same-package forward declaration, different definition per build"
// pattern protocol.cpp/shims.cpp already use in production. Those
// functions take NO handle parameter (matching the real production
// signatures exactly -- wire_adapter.cpp must stay signature-compatible
// with shims.cpp's real definitions), so they operate against a single
// process-wide "active" WaHandle pointer, armed by waCreate()/cleared by
// waDestroy(). This is safe under pytest's default single-threaded,
// one-test-at-a-time execution (no xdist parallelism in this repo's test
// config) -- never call two WaHandle instances' waFeed()/waStep()
// concurrently from separate threads.
//
// The test-double setWheelsTimed()/getConfigValue()/setKernelValue()/
// diagValue() bodies below intentionally mirror shims.cpp's real
// implementations field-for-field (same math, same field ordinals) so a
// test exercising WireAdapter through this shim is exercising the exact
// translation production code performs -- with countsPerLength fixed at
// 1.0 (mm/s IS counts/s in this test double) so assertions read directly
// in mm/s without needing to know a real robot's calibration.
#include <cstdint>
#include <cstring>
#include <string>

#include "diffdrive.h"
#include "fake_ports.h"
#include "wire_adapter.h"
#include "wire_handler.h"
#include "wire_mock_adapter.h"

namespace {

// Accumulates every Sink::write() into one buffer for the whole test to
// inspect -- callers slice it on '\n' from the Python side. Identical to
// wire_grammar_shim.cpp's own RecordingSink; duplicated rather than
// shared because the two shims compile into separate shared libraries
// (ctypes cannot span a symbol across two independently-loaded .so
// files without extra plumbing this test scaffolding doesn't need).
class RecordingSink : public Wire::Sink {
 public:
  void write(const char* data, size_t length) override {
    buffer_.append(data, length);
  }
  const std::string& buffer() const { return buffer_; }
  void clear() { buffer_.clear(); }

 private:
  std::string buffer_;
};

// ---- WvHandle: WireHandler + WireMockAdapter ----------------------------

struct WvHandle {
  WireMockAdapter adapter;
  RecordingSink sink;
  Wire::WireHandler handler;
  WvHandle() : handler(adapter, sink) {}
};

// ---- WaHandle: WireHandler + the REAL WireAdapter + a REAL kernel over
// FakeMotor -----------------------------------------------------------

struct WaHandle {
  FakeMotor motorLeft;
  FakeMotor motorRight;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::WireAdapter adapter;
  RecordingSink sink;
  Wire::WireHandler handler;

  explicit WaHandle(const Wire::Identity& identity)
      : kernel(motorLeft, motorRight, clock, sleeper, launcher),
        adapter(identity),
        handler(adapter, sink) {}
};

// The single process-wide "active" WaHandle the test-double shims.cpp
// free functions below operate against -- see this file's own header
// comment for why a handle parameter isn't an option (production
// signature compatibility) and why this is safe under pytest's
// single-threaded execution.
WaHandle* g_activeWaHandle = nullptr;

}  // namespace

// ---- test-double definitions of the shims.cpp free functions
// wire_adapter.cpp forward-declares ---------------------------------------
// Must live in the SAME namespace wire_adapter.cpp forward-declares them
// in (diffDrive) -- these ARE the definitions the linker resolves
// wire_adapter.o's calls to, in this shared library.
namespace diffDrive {

void setWheelsTimed(int left, int right, uint32_t durationMs) {
  if (g_activeWaHandle == nullptr) return;
  // Mirrors shims.cpp's real setWheelsTimed() exactly (velocity =
  // (left+right)/2, twist = (right-left)/2, half-differential,
  // CCW-positive) with countsPerLength fixed at 1.0 -- see this file's
  // own header comment.
  const float velocity = 0.5f * static_cast<float>(left + right);
  const float twist = 0.5f * static_cast<float>(right - left);
  g_activeWaHandle->kernel.drive(velocity, twist, durationMs);
}

void stopAll() {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->kernel.neutral();
}

void estopAll() {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->kernel.estop();
}

// Mirrors shims.cpp's real setKernelValue() switch exactly (same field
// ordinals, same x1000 scaling convention) -- see wire_adapter.cpp's own
// kFields table for the wire-name mapping this ticket adds on top.
void setKernelValue(int field, int value) {
  if (g_activeWaHandle == nullptr) return;
  DiffDrive::DifferentialDrive& k = g_activeWaHandle->kernel;
  const float v = static_cast<float>(value) * 0.001f;
  switch (field) {
    case 0: k.setMaxDuty(v); break;
    case 1: k.setFullDutyVelocity(v); break;
    case 2: k.setKp(v); break;
    case 3: k.setKi(v); break;
    case 4: k.setIMax(v); break;
    case 5: k.setKaff(v); break;
    case 6: k.setPidMax(v); break;
    case 7: k.setTwistHoldGain(v); break;
    case 8: k.setSpeedFloor(v); break;
    case 9: k.setPositionErrorMax(v); break;
    case 10:
      k.setStall(v, k.config().stallDemand, k.config().stallWindow);
      break;
    case 11:
      k.setStall(k.config().stallSpeed, v, k.config().stallWindow);
      break;
    case 12:
      k.setStall(k.config().stallSpeed, k.config().stallDemand, v);
      break;
    case 13: k.setLambdaEnabled(v != 0.0f); break;
    case 14: k.setCrawlPulse(v); break;
    default: break;
  }
}

// Mirrors shims.cpp's real getConfigValue() switch exactly, for the
// fields this ticket's field-name table actually reaches.
int getConfigValue(int field) {
  if (g_activeWaHandle == nullptr) return 0;
  const DiffDrive::DifferentialDrive::Config c =
      g_activeWaHandle->kernel.config();
  float v = 0.0f;
  switch (field) {
    case 0: v = c.maxDuty; break;
    case 1: v = c.fullDutyVelocity; break;
    case 2: v = c.kp; break;
    case 3: v = c.ki; break;
    case 4: v = c.iMax; break;
    case 5: v = c.kaff; break;
    case 6: v = c.pidMax; break;
    case 7: v = c.twistHoldGain; break;
    case 8: v = c.vMin; break;
    case 9: v = c.posErrMax; break;
    case 10: v = c.stallSpeed; break;
    case 11: v = c.stallDemand; break;
    case 12: v = c.stallWindow; break;
    case 13: v = c.lambdaEnabled ? 1.0f : 0.0f; break;
    case 14: v = c.crawlPulse; break;
    default: break;
  }
  return static_cast<int>(v * 1000.0f);
}

// Mirrors the subset of shims.cpp's real diagValue() switch
// wire_adapter.cpp's status() actually reads (see that file's kDiag*
// constants) -- read straight off the SAME kernel setWheelsTimed()/
// stopAll()/estopAll() above drive, so a status() call after a WHEELS_V/
// STOP/ESTOP dispatch reflects that call's real effect.
int diagValue(int what) {
  if (g_activeWaHandle == nullptr) return 0;
  const DiffDrive::DifferentialDrive::Output out =
      g_activeWaHandle->kernel.output();
  switch (what) {
    case 0: return out.ready ? 1 : 0;
    case 1: return out.estopped ? 1 : 0;
    case 2: return out.stallHalted ? 1 : 0;
    case 3: return out.leaseExpired ? 1 : 0;
    case 4: return out.connectedLeft ? 1 : 0;
    case 5: return out.connectedRight ? 1 : 0;
    case 6: return out.wedgeLeft ? 1 : 0;
    case 7: return out.wedgeRight ? 1 : 0;
    case 14: return static_cast<int>(out.velocityLeft);
    case 15: return static_cast<int>(out.velocityRight);
    default: return 0;
  }
}

}  // namespace diffDrive

extern "C" {

// ============================================================================
// WvHandle: WireHandler + WireMockAdapter -- decode/dispatch tests
// ============================================================================

void* wvCreate() { return new WvHandle(); }
void wvDestroy(void* handle) { delete static_cast<WvHandle*>(handle); }

void wvFeed(void* handle, const char* data, int length) {
  static_cast<WvHandle*>(handle)->handler.feed(data,
                                                static_cast<size_t>(length));
}

uint32_t wvMalformedCount(void* handle) {
  return static_cast<WvHandle*>(handle)->handler.malformedCount();
}

int wvSinkLength(void* handle) {
  return static_cast<int>(static_cast<WvHandle*>(handle)->sink.buffer().size());
}
int wvSinkRead(void* handle, char* out, int cap) {
  WvHandle* h = static_cast<WvHandle*>(handle);
  size_t n = h->sink.buffer().size();
  if (static_cast<int>(n) > cap) n = static_cast<size_t>(cap);
  std::memcpy(out, h->sink.buffer().data(), n);
  return static_cast<int>(n);
}
void wvSinkClear(void* handle) { static_cast<WvHandle*>(handle)->sink.clear(); }

// ---- canned Result setters (Wire::Result's DECLARATION-ORDER ordinal) ----

void wvSetWheelsVResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.wheelsVResult =
      static_cast<Wire::Result>(result);
}
void wvSetWheelsXResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.wheelsXResult =
      static_cast<Wire::Result>(result);
}
void wvSetMoveXResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.moveXResult =
      static_cast<Wire::Result>(result);
}
void wvSetMoveVResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.moveVResult =
      static_cast<Wire::Result>(result);
}
void wvSetGoToRResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.goToRResult =
      static_cast<Wire::Result>(result);
}
void wvSetGoToWResult(void* handle, int result) {
  static_cast<WvHandle*>(handle)->adapter.goToWResult =
      static_cast<Wire::Result>(result);
}

// ---- call-count / last-args readback --------------------------------------

int wvWheelsVCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.wheelsVCalls;
}
float wvLastWheelsVLeft(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsVLeft;
}
float wvLastWheelsVRight(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsVRight;
}
uint32_t wvLastWheelsVDuration(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsVDuration;
}
uint32_t wvLastWheelsVId(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsVId;
}

int wvWheelsXCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.wheelsXCalls;
}
float wvLastWheelsXLeft(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsXLeft;
}
float wvLastWheelsXRight(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsXRight;
}
float wvLastWheelsXCruise(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsXCruise;
}
uint32_t wvLastWheelsXTimeout(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastWheelsXTimeout;
}

int wvMoveXCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.moveXCalls;
}
float wvLastMoveXDistance(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveXDistance;
}
float wvLastMoveXRotation(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveXRotation;
}
float wvLastMoveXCruise(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveXCruise;
}
uint32_t wvLastMoveXTimeout(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveXTimeout;
}

int wvMoveVCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.moveVCalls;
}
float wvLastMoveVVx(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveVVx;
}
float wvLastMoveVOmega(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveVOmega;
}
uint32_t wvLastMoveVDuration(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastMoveVDuration;
}

int wvGoToRCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.goToRCalls;
}
float wvLastGoToRX(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToRX;
}
float wvLastGoToRY(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToRY;
}
float wvLastGoToRSpeed(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToRSpeed;
}
float wvLastGoToRArrive(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToRArrive;
}
uint32_t wvLastGoToRTimeout(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToRTimeout;
}

int wvGoToWCalls(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.goToWCalls;
}
float wvLastGoToWX(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToWX;
}
float wvLastGoToWY(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToWY;
}

// ============================================================================
// WaHandle: WireHandler + the REAL WireAdapter + a REAL kernel over
// FakeMotor -- WHEELS_V's real effect, GET/SET's field table, STOP/ESTOP.
// ============================================================================

void* waCreate(const char* name, const char* serial, const char* drivetrain,
              const char* profile, const char* version) {
  // `identity`'s pointer fields are borrowed (Wire::Identity's own doc
  // comment) -- the CALLER (the Python test) must keep name/serial/
  // drivetrain/profile/version alive for the handle's whole lifetime,
  // same contract as wire_grammar_shim.cpp's wgSetIdentity.
  Wire::Identity identity;
  identity.name = name;
  identity.serial = serial;
  identity.drivetrain = drivetrain;
  identity.profile = profile;
  identity.version = version;
  WaHandle* h = new WaHandle(identity);
  g_activeWaHandle = h;
  return h;
}

void waDestroy(void* handle) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  if (g_activeWaHandle == h) g_activeWaHandle = nullptr;
  delete h;
}

void waFeed(void* handle, const char* data, int length) {
  static_cast<WaHandle*>(handle)->handler.feed(data,
                                               static_cast<size_t>(length));
}

uint32_t waMalformedCount(void* handle) {
  return static_cast<WaHandle*>(handle)->handler.malformedCount();
}

int waSinkLength(void* handle) {
  return static_cast<int>(static_cast<WaHandle*>(handle)->sink.buffer().size());
}
int waSinkRead(void* handle, char* out, int cap) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  size_t n = h->sink.buffer().size();
  if (static_cast<int>(n) > cap) n = static_cast<size_t>(cap);
  std::memcpy(out, h->sink.buffer().data(), n);
  return static_cast<int>(n);
}
void waSinkClear(void* handle) { static_cast<WaHandle*>(handle)->sink.clear(); }

// ---- kernel calibration + stepping (test setup, not part of the wire
// surface) -------------------------------------------------------------

void waSetMaxDuty(void* handle, float v) {
  static_cast<WaHandle*>(handle)->kernel.setMaxDuty(v);
}
void waSetFullDutyVelocity(void* handle, float v) {
  static_cast<WaHandle*>(handle)->kernel.setFullDutyVelocity(v);
}
int waBegin(void* handle) {
  return static_cast<int>(static_cast<WaHandle*>(handle)->kernel.begin());
}
void waStep(void* handle) { static_cast<WaHandle*>(handle)->kernel.step(); }

float waMotorLastStagedDuty(void* handle, int side) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  return (side == 0 ? h->motorLeft : h->motorRight).lastStagedDuty;
}

}  // extern "C"
