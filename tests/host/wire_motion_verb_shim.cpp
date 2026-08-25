// wire_motion_verb_shim.cpp -- extern "C" ctypes surface for sprint 003
// ticket 004's own host tests (test_wire_motion_verbs.py): the six
// motion verbs' wire decode/dispatch, and src/wire_adapter.h's
// WireAdapter wired to a REAL kernel. Test scaffolding only: nothing
// under src/ knows this file exists, and it is compiled only into this
// test's own throwaway shared library.
//
// Sprint 003 ticket 012 extends the WaHandle surface three ways, all
// additive:
//   - `waCreate()` now wires a REAL nowMs (waNowMs(), reading this
//     handle's own FakeClock) into the WireAdapter it constructs,
//     settable via waSetNowMs() -- every host test before this ticket
//     left nowMs nullptr, so hasLiveMotionObligation() always answered
//     false; this is what makes ticket 012's own obligation-arming bug
//     fix (armed by all six motion verbs now, not just WHEELS_V --
//     wire_adapter.h's own header comment) observable from a test, via
//     the new waHasLiveMotionObligation().
//   - engineMoveV()/engineGoToR()/engineGoToW() test-double definitions,
//     mirroring shims.cpp's own ticket-012 additions field-for-field,
//     completing WHEELS_X/MOVE_X's own ticket-011 precedent for all six
//     verbs.
//   - A `FakePoseSource` member plus a settable "available" flag
//     (waSetPose()/waSetPoseSourceAvailable()) standing in for
//     shims.cpp's own gOtos/otosRef() -- lets a test drive GO_TO_W's
//     real effect (a set pose) AND its "no pose source" refusal
//     (unavailable), both through the wire, with no OTOS/I2C anywhere
//     in this link.
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
// translation production code performs. Sprint 008 ticket 003 (closing
// host-harness-double-drift.md/R-25, PY-03): setWheelsTimed() now calls
// the SAME real MotionEngine::wheelsV() engineWheelsX()/engineMoveX()
// already use below -- there is no "countsPerLength fixed at 1.0"
// shortcut left for ANY verb that reaches the kernel through `engine`.
// A test computing an expected duty for WHEELS_V must read this
// handle's own REAL waCountsPerMm(), exactly the way the WHEELS_X/
// MOVE_X real-effect tests already do (test_wire_motion_verbs.py).
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

#include "diffdrive.h"
#include "fake_pose_source.h"
#include "fake_ports.h"
#include "motion_engine.h"
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

// Forward declaration: WaHandle's constructor wires this in as the REAL
// WireAdapter's nowMs (diffDrive::WireAdapter::NowMsFn) -- defined below
// `g_activeWaHandle`, since it reads that handle's own FakeClock,
// exactly like protocol.cpp's own wireNowMs() reads its Protocol
// instance's clock_ through the same kind of singleton indirection a
// plain, non-capturing function pointer requires. This is what makes
// ticket 012's own obligation-arming fix observable from a host test --
// see this file's own header comment.
uint32_t waNowMs();

struct WaHandle {
  FakeMotor motorLeft;
  FakeMotor motorRight;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  // sprint 003 ticket 011: the same MotionEngine WHEELS_X/MOVE_X's real
  // dispatch needs, constructed over `kernel`/`clock` above exactly like
  // shims.cpp's own Rig::engine (see engineWheelsX()/engineMoveX()/
  // engineDefaultCruiseMmS() below, the test-double mirrors of the
  // production forward-declared functions wire_adapter.cpp calls for
  // these two verbs). Declared AFTER kernel/clock: member init order
  // follows declaration order, not the initializer list below -- same
  // rule shims.cpp's own Rig documents for its `engine` member.
  diffDrive::MotionEngine engine;
  // sprint 003 ticket 012: GO_TO_W's own PoseSource test double, mirror
  // of shims.cpp's own gOtos/otosRef() -- see engineGoToW() below.
  // `poseSourceAvailable` stands in for OtosPort::connected(): a test
  // that wants to exercise GO_TO_W's "no pose source" refusal sets this
  // false via waSetPoseSourceAvailable() instead of needing an actual
  // disconnected-sensor test double.
  FakePoseSource pose;
  bool poseSourceAvailable = true;
  diffDrive::WireAdapter adapter;
  RecordingSink sink;
  Wire::WireHandler handler;

  // ---- sprint 004 ticket 004: raw settable state for buildSnapshot()'s
  // five new forward-declared reads (poseX/poseY/poseHeading/otosGet/
  // wheelSpeed). Deliberately SEPARATE from `pose`/`poseSourceAvailable`
  // above: on the real robot, poseX()/poseY()/poseHeading() read
  // odometry (Rig.x/y/heading, shims.cpp) while GO_TO_W's PoseSource
  // reads OTOS (otosRef()) -- two DIFFERENT sensors. Reusing the
  // float/radian FakePoseSource for both here would conflate them AND
  // reintroduce a rad<->cdeg round-trip rounding risk the "pose
  // passthrough" and "h/oh both cdeg" scale tests exist specifically to
  // rule out (an exact integer pass-through, no conversion in the way).
  int poseXValue = 0;          // [mm], poseX()'s raw return
  int poseYValue = 0;          // [mm], poseY()'s raw return
  int poseHeadingCdeg = 0;     // [cdeg], poseHeading()'s raw return

  // otosGet()'s raw state -- `otosXRaw01mm`/`otosYRaw01mm` are 0.1 mm
  // (WireAdapter::buildSnapshot() divides by 10; NOT pre-divided here,
  // so a test setting these proves the adapter's own division, not this
  // shim's), `otosHeadingCdeg` is ALREADY centidegrees (otosGet(2)'s own
  // real contract -- see wire_adapter.cpp's own hazard-2 comment).
  // `otosConnectedValue` backs otosGet(7) independently of the other
  // three -- a disconnected OTOS can still report a stale cached pose,
  // per this ticket's own R-22 test requirement.
  int otosXRaw01mm = 0;        // [0.1 mm]
  int otosYRaw01mm = 0;        // [0.1 mm]
  int otosHeadingCdeg = 0;     // [cdeg], already-scaled
  bool otosConnectedValue = false;

  // wheelSpeed()'s raw state -- mm/s, no further scaling anywhere in the
  // adapter (the issue's own "wheel speed" scale test exists to catch a
  // stray x10 copied from the reference's own mm/s x10 telemetry
  // quantum, which this project does NOT adopt -- sprint.md Design
  // Rationale).
  int wheelSpeedLeftMms = 0;
  int wheelSpeedRightMms = 0;

  // Sprint 007 ticket 003 (closing R-11/BLK-03/API-03): mirrors
  // shims.cpp's real Rig::defaultCruiseMmS_ field-for-field, same
  // 150.0f seed -- see engineDefaultCruiseMmS()'s test-double
  // definition below, and waSetDefaultCruise()'s own comment for why
  // this is a direct field, not filtered through setKernelValue()'s
  // ">0" validation (mirrors waSetFullDutyVelocity()'s own unfiltered
  // convention -- test setup needs to be able to force this to exactly
  // 0, which the wire-level SET path deliberately cannot do).
  float defaultCruiseMmS = 150.0f;  // [mm/s]

  // A settable override for diagValue()'s otherwise kernel/engine-
  // derived ordinals (i2cf=8, lexc=9, posl=10, posr=11, dutl=12,
  // dutr=13, cyc=16, cycovr=19, wrng=25) -- lets a scale test or the
  // widest-FULL-frame byte-budget test pin an EXACT raw value (e.g.
  // i2cf=26) with no need to drive dozens of simulated I2C faults (etc.)
  // through the real kernel just to land on one. An armed ordinal wins
  // over the real kernel.output()/engine read below; an unarmed ordinal
  // (the default) still reads the real computed value, keeping this
  // shim's mirror of shims.cpp's own diagValue() switch meaningful for
  // every other already-tested boolean ordinal (0-7, 14, 15).
  static constexpr int kMaxDiagOverride = 32;
  bool diagOverrideArmed[kMaxDiagOverride] = {};
  int diagOverrideValue[kMaxDiagOverride] = {};

  explicit WaHandle(const Wire::Identity& identity)
      : kernel(motorLeft, motorRight, clock, sleeper, launcher),
        engine(kernel, clock),
        adapter(identity, &waNowMs),
        handler(adapter, sink) {}
};

// The single process-wide "active" WaHandle the test-double shims.cpp
// free functions below operate against -- see this file's own header
// comment for why a handle parameter isn't an option (production
// signature compatibility) and why this is safe under pytest's
// single-threaded execution.
WaHandle* g_activeWaHandle = nullptr;

// sprint 003 ticket 012: the real nowMs backing g_activeWaHandle's own
// WireAdapter -- see this function's own forward-declaration comment
// above. Same "operates against the single process-wide active handle"
// contract as setWheelsTimed()/etc. below (a plain NowMsFn cannot carry
// a handle parameter any more than those can).
uint32_t waNowMs() {
  if (g_activeWaHandle == nullptr) return 0;
  return static_cast<uint32_t>(g_activeWaHandle->clock.nowMicros() /
                               1000ull);
}

}  // namespace

// ---- test-double definitions of the shims.cpp free functions
// wire_adapter.cpp forward-declares ---------------------------------------
// Must live in the SAME namespace wire_adapter.cpp forward-declares them
// in (diffDrive) -- these ARE the definitions the linker resolves
// wire_adapter.o's calls to, in this shared library.
namespace diffDrive {

void setWheelsTimed(int left, int right, uint32_t durationMs) {
  if (g_activeWaHandle == nullptr) return;
  // Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25,
  // PY-03 item 2): mirrors shims.cpp's real setWheelsTimed() EXACTLY --
  // `r.engine.wheelsV(static_cast<float>(left), static_cast<float>(right),
  // durationMs)` -- not just its velocity/twist math. The prior version
  // computed the same split by hand and called `kernel.drive()`
  // directly, which bypassed MotionEngine::wheelsV() entirely and, with
  // it, wheelsV()'s own FIRST act, cancelMove() (motion_engine.cpp,
  // motion-api.md S6: "wheels_* clears the planner") -- WHEELS_V's
  // command-supersession of an in-flight MOVE_X/GO_TO_R/GO_TO_W was
  // untested and untestable through this double. Routing through the
  // REAL engine also means this now applies the REAL countsPerMm()
  // scaling (no more implicit "countsPerLength fixed at 1.0"), the same
  // way engineWheelsX()/engineMoveX() below already do -- see this
  // file's own header comment.
  g_activeWaHandle->engine.wheelsV(static_cast<float>(left),
                                   static_cast<float>(right), durationMs);
}

void stopAll() {
  if (g_activeWaHandle == nullptr) return;
  // Sprint 005 ticket 004: mirrors shims.cpp's real stopAll() exactly --
  // `r.engine.endMove(); r.kernel.neutral();` -- not just the kernel
  // half. The pre-fix version omitted engine.endMove(), which meant a
  // still-live goal-directed move-engine move (MOVE_X/GO_TO_R/GO_TO_W)
  // stayed reported "active" (isMoveActive()) through this double after
  // a real STOP, something production has never done -- untested and
  // untestable through this double until this ticket's own completion-
  // channel logic needed to observe engineMoveActive() actually go
  // false here. (No deliverStopNow() call here, unlike production --
  // that is a CODAL-fiber cross-fiber-stop concern this host-portable
  // double has never modeled, same as every other WaHandle double
  // function in this file.)
  g_activeWaHandle->engine.endMove();
  g_activeWaHandle->kernel.neutral();
}

void estopAll() {
  if (g_activeWaHandle == nullptr) return;
  // Sprint 005 ticket 004: mirrors shims.cpp's real estopAll() exactly
  // -- `r.engine.endMove(); r.kernel.estop(); r.kernel.emergencyStopMotors();`
  // -- see stopAll()'s own comment above for why engine.endMove() is
  // the piece that was missing. kernel.emergencyStopMotors() (which
  // ALSO re-sets the estop latch, diffdrive.cpp) is added too, for the
  // same completeness -- kernel.estop() alone already covers this
  // double's own observable estop surface (Output.estopped), so this is
  // not separately exercised by name, only kept signature-faithful.
  g_activeWaHandle->engine.endMove();
  g_activeWaHandle->kernel.estop();
  g_activeWaHandle->kernel.emergencyStopMotors();
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
    // 15 (sprint 007 ticket 003): default_cruise, mirroring shims.cpp's
    // real setKernelValue() case 15 exactly (same ">0" silent-ignore
    // validation) -- see WaHandle::defaultCruiseMmS's own comment.
    case 15:
      if (v > 0.0f) g_activeWaHandle->defaultCruiseMmS = v;
      break;
    // 16 (sprint 007 ticket 005): rotational_slip, mirroring shims.cpp's
    // real setKernelValue() case 16 exactly -- a thin forward to the
    // REAL MotionEngine::setRotationalSlip(), which owns its own ">0,
    // else keep the prior value" validation (motion_engine.h).
    case 16: g_activeWaHandle->engine.setRotationalSlip(v); break;
    // 17 (sprint 007 ticket 001): stall_clear -- a write-triggered
    // ACTION wearing a config-field's clothes, mirroring shims.cpp's
    // real setKernelValue() case 17 exactly (see that file's own
    // comment). Only nonzero-vs-zero matters.
    case 17: if (v != 0.0f) k.clearStallLatch(); break;
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
    // 15 (sprint 007 ticket 003): default_cruise's GET side, mirroring
    // shims.cpp's real getConfigValue() case 15 exactly -- deliberately
    // NOT read from `c` (see case 15's own comment in setKernelValue()
    // above).
    case 15: v = g_activeWaHandle->defaultCruiseMmS; break;
    // 16 (sprint 007 ticket 005): rotational_slip's GET side, mirroring
    // shims.cpp's real getConfigValue() case 16 exactly -- a thin
    // forward to the REAL MotionEngine::rotationalSlip().
    case 16: v = g_activeWaHandle->engine.rotationalSlip(); break;
    // 17 (sprint 007 ticket 001): stall_clear's GET side -- a
    // convenience readback of Output.stallHalted, deliberately NOT
    // read from `c` (this ordinal has no stored Config field), mirror
    // of shims.cpp's real getConfigValue() case 17.
    case 17:
      v = g_activeWaHandle->kernel.output().stallHalted ? 1.0f : 0.0f;
      break;
    default: break;
  }
  // Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25,
  // PY-03 item 3): matches shims.cpp's real getConfigValue() exactly --
  // `std::lround(v * 1000.0)`, a DOUBLE-precision product (`v` promotes
  // to double against the `1000.0` double literal, same as production),
  // round-to-nearest -- not `static_cast<int>(v * 1000.0f)` (SINGLE-
  // precision, truncating), which is what this line used to read.
  return static_cast<int>(std::lround(v * 1000.0));
}

// Mirrors shims.cpp's real engineWheelsX()/engineMoveX()/
// engineDefaultCruiseMmS() exactly (sprint 003 ticket 011) -- these are
// what WHEELS_X's/MOVE_X's real dispatch (WireAdapter::onWheelsX()/
// onMoveX(), wire_adapter.cpp) forward-declares and calls; `engine`
// here is the SAME real MotionEngine class production code uses, wired
// to this handle's own real kernel/FakeMotor pair (this file's own
// header comment). `rotationRad` arrives already converted from the
// wire's milliradian integer -- see wire_adapter.cpp's mradToRad().
void engineWheelsX(float left, float right, float cruise,
                   uint32_t timeoutMs) {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->engine.wheelsX(left, right, cruise, timeoutMs);
}

void engineMoveX(float distance, float rotationRad, float cruise,
                 uint32_t timeoutMs) {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->engine.moveX(distance, rotationRad, cruise, timeoutMs);
}

// Sprint 007 ticket 003 (closing R-11/BLK-03/API-03,
// cruise-zero-sentinel-full-duty-lunge.md): mirrors shims.cpp's real,
// POST-FIX engineDefaultCruiseMmS() exactly -- returns the handle's own
// defaultCruiseMmS_-equivalent field, NOT a fullDutyVelocity/countsPerMm
// derivation. This double previously mirrored the OLD (pre-fix)
// derivation; left unchanged, it would have kept
// test_wheels_x_cruise_zero_uses_configured_default and its MOVE_X/
// GO_TO_R/GO_TO_W siblings silently exercising the retired contract
// while the real fix shipped elsewhere -- a fully green suite proving
// nothing about the actual behavior change. See waSetDefaultCruise()
// below for the test-setup setter.
float engineDefaultCruiseMmS() {
  if (g_activeWaHandle == nullptr) return 0.0f;
  return g_activeWaHandle->defaultCruiseMmS;
}

// Mirrors shims.cpp's real engineMoveV()/engineGoToR()/engineGoToW()
// exactly (sprint 003 ticket 012) -- what WireAdapter::onMoveV()/
// onGoToR()/onGoToW() (wire_adapter.cpp) forward-declares and calls.
// `omegaRad` arrives already converted from the wire's milliradian
// integer, same as engineMoveX()'s `rotationRad` above. `poseSource`
// stands in for shims.cpp's own gOtos/otosRef() -- see this handle's
// own `pose`/`poseSourceAvailable` fields and this file's own header
// comment.
void engineMoveV(float vx, float omegaRad, uint32_t durationMs) {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->engine.moveV(vx, omegaRad, durationMs);
}

void engineGoToR(float x, float y, float speed, float arrive,
                uint32_t timeoutMs) {
  if (g_activeWaHandle == nullptr) return;
  g_activeWaHandle->engine.goToR(x, y, speed, arrive, timeoutMs);
}

bool engineGoToW(float x, float y, float speed, float arrive,
                uint32_t timeoutMs) {
  if (g_activeWaHandle == nullptr) return false;
  if (!g_activeWaHandle->poseSourceAvailable) return false;
  g_activeWaHandle->engine.goToW(g_activeWaHandle->pose, x, y, speed, arrive,
                                 timeoutMs);
  return true;
}

// Sprint 005 ticket 004 (closing wire-motion-completion-signal.md/R-23):
// mirrors shims.cpp's real engineMoveActive() exactly -- the ONE
// genuinely new read WireAdapter::resolvePendingReason() (wire_adapter.cpp)
// needs for MOVE_X/GO_TO_R/GO_TO_W. Reads this handle's OWN real
// MotionEngine::isMoveActive(), the SAME engine engineWheelsX()/
// engineMoveX()/engineMoveV()/engineGoToR()/engineGoToW() above already
// drive -- so a test exercising the real WireAdapter's completion
// channel is exercising the exact bridge production code uses, not a
// separate notion of "active."
bool engineMoveActive() {
  if (g_activeWaHandle == nullptr) return false;
  return g_activeWaHandle->engine.isMoveActive();
}

// Mirrors the subset of shims.cpp's real diagValue() switch
// wire_adapter.cpp's status() actually reads (see that file's kDiag*
// constants) -- read straight off the SAME kernel setWheelsTimed()/
// stopAll()/estopAll() above drive, so a status() call after a WHEELS_V/
// STOP/ESTOP dispatch reflects that call's real effect. Sprint 004
// ticket 004 extends this with the FULL-column ordinals (8/9/10/11/12/
// 13/16/19/25) buildSnapshot() now also reads, each overridable via
// waSetDiagOverride() (this handle's own diagOverrideArmed/Value arrays,
// above) so a scale test can pin an exact raw value with no real fault
// injection required.
int diagValue(int what) {
  if (g_activeWaHandle == nullptr) return 0;
  if (what >= 0 && what < WaHandle::kMaxDiagOverride &&
      g_activeWaHandle->diagOverrideArmed[what]) {
    return g_activeWaHandle->diagOverrideValue[what];
  }
  const DiffDrive::DifferentialDrive::Output out =
      g_activeWaHandle->kernel.output();
  switch (what) {
    case 0: return out.ready ? 1 : 0;
    case 1: return out.estopped ? 1 : 0;
    case 2: return out.stallHalted ? 1 : 0;
    case 3: return out.leaseExpired ? 1 : 0;
    case 4: return out.connectedLeft ? 1 : 0;
    case 5: return out.connectedRight ? 1 : 0;
    // Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25,
    // PY-03 item 1): matches shims.cpp's real diagValue() exactly --
    // the SUSPECT pair, not the LATCHED wedgeLeft/wedgeRight pair
    // (diffdrive.h declares both -- genuinely different signals,
    // wedged() vs wedgeSuspect() on the Motor port). This line used to
    // read wedgeLeft/wedgeRight.
    case 6: return out.wedgeSuspectLeft ? 1 : 0;
    case 7: return out.wedgeSuspectRight ? 1 : 0;
    case 8: return static_cast<int>(out.i2cFaultCount);
    case 9: return static_cast<int>(out.leaseExpiryCount);
    case 10: return static_cast<int>(out.positionLeft);
    case 11: return static_cast<int>(out.positionRight);
    case 12: return static_cast<int>(out.appliedDutyLeft * 100.0f);
    case 13: return static_cast<int>(out.appliedDutyRight * 100.0f);
    case 14: return static_cast<int>(out.velocityLeft);
    case 15: return static_cast<int>(out.velocityRight);
    case 16: return static_cast<int>(out.cycleCount);
    case 19: return static_cast<int>(out.cycleOverrunCount);
    case 25: return static_cast<int>(g_activeWaHandle->engine.wrongWayCount());
    default: return 0;
  }
}

// ---- sprint 004 ticket 004: buildSnapshot()'s five new forward-
// declared reads -- see WaHandle's own field comments above for why
// poseX/Y/heading and otosGet() are backed by SEPARATE raw state rather
// than the existing float/radian FakePoseSource. ----

int poseX() {
  if (g_activeWaHandle == nullptr) return 0;
  return g_activeWaHandle->poseXValue;
}

int poseY() {
  if (g_activeWaHandle == nullptr) return 0;
  return g_activeWaHandle->poseYValue;
}

int poseHeading() {
  if (g_activeWaHandle == nullptr) return 0;
  return g_activeWaHandle->poseHeadingCdeg;
}

// Mirrors shims.cpp's real otosGet() ordinal contract for the four
// cases wire_adapter.cpp actually reads (0/1: 0.1 mm; 2: already cdeg;
// 7: connected) -- every other ordinal (vx/vy/omega/productId/imu
// calibration) is out of this ticket's scope and returns 0.
int otosGet(int what) {
  if (g_activeWaHandle == nullptr) return 0;
  switch (what) {
    case 0: return g_activeWaHandle->otosXRaw01mm;
    case 1: return g_activeWaHandle->otosYRaw01mm;
    case 2: return g_activeWaHandle->otosHeadingCdeg;
    case 7: return g_activeWaHandle->otosConnectedValue ? 1 : 0;
    default: return 0;
  }
}

int wheelSpeed(int which) {
  if (g_activeWaHandle == nullptr) return 0;
  return which == 0 ? g_activeWaHandle->wheelSpeedLeftMms
                     : g_activeWaHandle->wheelSpeedRightMms;
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
// Sprint 008 (wire-timeout-hardening.md): GO_TO_W's own `timeout` was
// already recorded by WireMockAdapter (wire_mock_adapter.h's
// lastGoToWTimeout) but had no exported accessor -- every one of the
// other five verbs already had one for its own timeout/duration field
// (see wvLastGoToRTimeout immediately above), so this closes that one
// gap rather than leaving GO_TO_W as the sole verb this suite cannot
// directly prove the shared clamp reached.
uint32_t wvLastGoToWTimeout(void* handle) {
  return static_cast<WvHandle*>(handle)->adapter.lastGoToWTimeout;
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

// Sprint 007 ticket 003: direct test-setup setter for
// WaHandle::defaultCruiseMmS, mirroring waSetFullDutyVelocity()'s own
// pattern exactly -- unfiltered (unlike setKernelValue()'s wire-level
// case 15 above), so a test can force this to exactly 0.0f to exercise
// the "without configured default" refusal path.
void waSetDefaultCruise(void* handle, float v) {
  static_cast<WaHandle*>(handle)->defaultCruiseMmS = v;
}

// ---- MotionEngine geometry readback (sprint 003 ticket 011): lets a
// WHEELS_X/MOVE_X test compute its own hand-computed expected duty from
// this handle's REAL countsPerMm()/effectiveTrackWidth() instead of
// hard-coding MotionEngine's default geometry constants -- same
// "read it back, don't hard-code it" pattern motion_engine_shim.cpp's
// own meCountsPerMm()/meEffectiveTrackWidth() already establish. -------

float waCountsPerMm(void* handle) {
  return static_cast<WaHandle*>(handle)->engine.countsPerMm();
}
float waEffectiveTrackWidth(void* handle) {
  return static_cast<WaHandle*>(handle)->engine.effectiveTrackWidth();
}

int waBegin(void* handle) {
  return static_cast<int>(static_cast<WaHandle*>(handle)->kernel.begin());
}
void waStep(void* handle) { static_cast<WaHandle*>(handle)->kernel.step(); }

// Sprint 005 ticket 004: waStep() above only steps the KERNEL -- unlike
// production's tickDrive() (shims.cpp), it never also calls
// engine.serviceMove(), so no existing WaHandle test could drive a
// move-engine move (MOVE_X/GO_TO_R/GO_TO_W) to a REAL completion (goal
// reached, deadline expired, or stalled) the way tickDrive()'s own
// `kernel.step(); engine.serviceMove();` pair does. Exposed as its own
// call (not folded into waStep()) so a test controls the two
// independently, matching meServiceMove()'s own sibling export in
// motion_engine_shim.cpp. Returns whether the move is STILL active
// after this call (MotionEngine::serviceMove()'s own return value).
int waServiceMove(void* handle) {
  return static_cast<WaHandle*>(handle)->engine.serviceMove() ? 1 : 0;
}

// Directly arms a FakeMotor's NEXT tick()'s committed position/sample
// time (fake_ports.h's own armed-then-committed contract) -- lets a
// test simulate "the wheel has physically reached this encoder count"
// without hand-rolling a duty-to-position physics model. Mirrors
// motion_engine_shim.cpp's own meMotorArmPosition() exactly. `side`: 0
// == left, 1 == right, same convention as every other side-taking
// export in this file (e.g. waMotorLastStagedDuty()).
void waArmMotorPosition(void* handle, int side, float positionCounts,
                        uint64_t sampleTimeUs) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  FakeMotor& motor = (side == 0 ? h->motorLeft : h->motorRight);
  motor.nextPositionValue = positionCounts;
  motor.nextSampleTimeUs = sampleTimeUs;
}

float waMotorLastStagedDuty(void* handle, int side) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  return (side == 0 ? h->motorLeft : h->motorRight).lastStagedDuty;
}

// Sprint 008 ticket 003 (closes host-harness-double-drift.md/R-25,
// PY-03 item 1): drives the two INDEPENDENT FakeMotor wedge signals
// (fake_ports.h's own wedgedValue/wedgeSuspectValue) through a real
// kernel.step() cycle -- lets a test discriminate diagValue()'s
// ordinals 6/7 (which read the SUSPECT pair, this ticket's own fix)
// from the different LATCHED wedgeLeft/wedgeRight pair, something no
// WaHandle test could previously do at all. `side`: 0 == left,
// 1 == right, same convention as waMotorLastStagedDuty() above.
void waSetMotorWedged(void* handle, int side, int wedged) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  (side == 0 ? h->motorLeft : h->motorRight).wedgedValue = wedged != 0;
}
void waSetMotorWedgeSuspect(void* handle, int side, int suspect) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  (side == 0 ? h->motorLeft : h->motorRight).wedgeSuspectValue =
      suspect != 0;
}

// Sprint 008 ticket 003: the real, public MotionEngine::isMoveActive()
// -- the observable proof that setWheelsTimed()'s now-real
// engine.wheelsV() call supersedes an in-flight MOVE_X/GO_TO_R/GO_TO_W
// move via cancelMove() (motion_engine.cpp, motion-api.md S6), the same
// way engine.wheelsX() already does. cancelMove() itself is PRIVATE on
// MotionEngine (by design -- callers reach it only through a primitive
// or the move engine's own lifecycle), so this is the only external
// hook a host test has to prove it ran.
int waEngineMoveActive(void* handle) {
  return static_cast<WaHandle*>(handle)->engine.isMoveActive() ? 1 : 0;
}

// ---- sprint 003 ticket 012: the real nowMs + motion-obligation
// tracking, and GO_TO_W's FakePoseSource -------------------------------

// Sets this handle's own FakeClock, which waNowMs() (the WireAdapter's
// wired-in NowMsFn) reads -- lets a test prove hasLiveMotionObligation()
// both arms (right after an accepted motion verb) and later clears
// (once this clock has been advanced past the armed deadline).
void waSetNowMs(void* handle, uint32_t ms) {
  static_cast<WaHandle*>(handle)->clock.nowUs =
      static_cast<uint64_t>(ms) * 1000ull;
}

int waHasLiveMotionObligation(void* handle) {
  return static_cast<WaHandle*>(handle)->adapter.hasLiveMotionObligation()
             ? 1
             : 0;
}

// Sprint 005 ticket 004: the real WireAdapter::lastDone()/lastDoneReason()
// -- lets a test poll the completion channel directly, without needing
// to route through a SUBSEQUENT sequenced verb's own ack/nack (the
// production reading path, exercised separately by this ticket's
// ack/nack-based tests). Wire::DoneReason's DECLARATION-ORDER ordinal,
// as int -- same int-not-enum-class convention every other ctypes-
// facing result in this file already uses (e.g. waOnTlm()'s own int
// param/return).
uint32_t waLastDone(void* handle) {
  return static_cast<WaHandle*>(handle)->adapter.lastDone();
}
int waLastDoneReason(void* handle) {
  return static_cast<int>(
      static_cast<WaHandle*>(handle)->adapter.lastDoneReason());
}

// GO_TO_W's own PoseSource test double (FakePoseSource, tests/host/
// fake_pose_source.h) -- see this file's own header comment and
// engineGoToW()'s doc comment above.
void waSetPose(void* handle, float x, float y, float heading) {
  static_cast<WaHandle*>(handle)->pose.setPose(x, y, heading);
}

void waSetPoseSourceAvailable(void* handle, int available) {
  static_cast<WaHandle*>(handle)->poseSourceAvailable = available != 0;
}

// ---- sprint 004 ticket 004: buildSnapshot()'s own raw settable state
// -- RAW shim units in every case (0.1 mm for OTOS, mm/s for wheel
// speed, mm/cdeg for pose), never pre-scaled, so a test exercising the
// real WireAdapter::buildSnapshot() is exercising the adapter's OWN
// scale factors, not this shim's. ----

void waSetPoseRaw(void* handle, int x_mm, int y_mm, int heading_cdeg) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  h->poseXValue = x_mm;
  h->poseYValue = y_mm;
  h->poseHeadingCdeg = heading_cdeg;
}

void waSetOtosRaw(void* handle, int x_01mm, int y_01mm, int heading_cdeg) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  h->otosXRaw01mm = x_01mm;
  h->otosYRaw01mm = y_01mm;
  h->otosHeadingCdeg = heading_cdeg;
}

void waSetOtosConnected(void* handle, int connected) {
  static_cast<WaHandle*>(handle)->otosConnectedValue = connected != 0;
}

void waSetWheelSpeed(void* handle, int left_mms, int right_mms) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  h->wheelSpeedLeftMms = left_mms;
  h->wheelSpeedRightMms = right_mms;
}

// `what` is a diagValue() ordinal (see this file's own diagValue()
// comment) -- arms an override that wins over the real kernel/engine
// read until this handle is destroyed. Silently ignored if `what` is
// out of the override array's bounds.
void waSetDiagOverride(void* handle, int what, int value) {
  WaHandle* h = static_cast<WaHandle*>(handle);
  if (what < 0 || what >= WaHandle::kMaxDiagOverride) return;
  h->diagOverrideArmed[what] = true;
  h->diagOverrideValue[what] = value;
}

// ---- sprint 004 ticket 004: telemetry projection readback -----------

const Wire::Snapshot* waBuildSnapshot(void* handle) {
  return &static_cast<WaHandle*>(handle)->adapter.buildSnapshot();
}

int waSnapshotCount(const Wire::Snapshot* snapshot) {
  return static_cast<int>(snapshot->count);
}

const char* waSnapshotColumnName(const Wire::Snapshot* snapshot, int index) {
  return snapshot->columns[index].name;
}

int32_t waSnapshotColumnValue(const Wire::Snapshot* snapshot, int index) {
  return snapshot->columns[index].value;
}

int waSnapshotColumnHex(const Wire::Snapshot* snapshot, int index) {
  return snapshot->columns[index].hex ? 1 : 0;
}

void waEmitTelemetry(void* handle, const Wire::Snapshot* snapshot) {
  static_cast<WaHandle*>(handle)->handler.emitTelemetry(*snapshot);
}

// Returns Wire::Result's DECLARATION-ORDER ordinal, as int -- same
// int-not-enum-class convention every other ctypes-facing result in
// this file already uses (e.g. wvSetWheelsVResult's own int param).
int waOnTlm(void* handle, int mode) {
  return static_cast<int>(static_cast<WaHandle*>(handle)->adapter.onTlm(
      static_cast<Wire::TlmMode>(mode)));
}

int waHasLiveTelemetry(void* handle) {
  return static_cast<WaHandle*>(handle)->adapter.telemetryEnabled() ? 1 : 0;
}

}  // extern "C"
