// wire_adapter.cpp -- see wire_adapter.h for the class contract and the
// documented scope decisions (why five motion verbs answer kUnknown, why
// now()/onRun() are inert on this adapter, the borrowed-Identity
// contract).
#include "wire_adapter.h"

#include <cmath>
#include <cstring>

namespace diffDrive {

// ---- shims.cpp entry points (sprint 003 ticket 004) --------------------
// shims.cpp has no header of its own (see its own file comment) and
// main.ts's `//% shim=diffDrive::...` mechanism is the TS-facing binding,
// not a C++ one -- these are plain same-namespace C++ forward
// declarations, exactly like protocol.cpp's own block reaching the same
// file. Must stay signature-compatible with shims.cpp's real
// definitions; every one of these already existed before this ticket --
// this file adds no new entry point to shims.cpp, keeping ticket
// 006/007's motion_engine extraction free to replace every one of these
// call sites later without this file's own public interface changing.
void stopAll();
void estopAll();
void setWheelsTimed(int left, int right, uint32_t durationMs);
void setKernelValue(int field, int value);
int getConfigValue(int field);
int diagValue(int what);

// ---- shims.cpp entry points (sprint 003 ticket 011) --------------------
// WHEELS_X/MOVE_X's own route onto motion_engine.h's MotionEngine.
// wire_adapter.cpp has no reference of its own to the Rig-owned `engine`
// singleton -- sprint.md's Design Rationale keeps that composition
// inside shims.cpp, reached from here only through forward-declared free
// functions, same convention as the six declarations above -- so these
// three thin, wire-shaped forwards are the seam. `rotationRad` arrives
// at engineMoveX() ALREADY converted from the wire's milliradian
// integer -- see mradToRad() below, this file's ONE such conversion
// (motion-api.md S9.1). `cruise` <= 0 passed to engineWheelsX()/
// engineMoveX() is MotionEngine's own existing "nothing to command"
// no-op (motion_engine.h); the wire's "0 means the configured default"
// substitution (motion-api.md S1.1) is resolved by onWheelsX()/onMoveX()
// below, via engineDefaultCruiseMmS(), BEFORE either of these is ever
// called -- neither one ever sees the sentinel itself.
void engineWheelsX(float left, float right, float cruise,
                   uint32_t timeoutMs);
void engineMoveX(float distance, float rotationRad, float cruise,
                 uint32_t timeoutMs);
float engineDefaultCruiseMmS();

// ---- shims.cpp entry points (sprint 003 ticket 012) --------------------
// MOVE_V/GO_TO_R/GO_TO_W's own route onto motion_engine.h's MotionEngine,
// completing the six-verb motion surface -- same forward-declaration
// convention as engineWheelsX()/engineMoveX()/engineDefaultCruiseMmS()
// above. `omegaRad` arrives at engineMoveV() ALREADY converted from the
// wire's milliradian integer, same seam as engineMoveX()'s `rotationRad`
// (mradToRad() below). `speed`'s <0/==0 handling for engineGoToR()/
// engineGoToW() is resolved by onGoToR()/onGoToW() below, via
// engineDefaultCruiseMmS(), BEFORE either is ever called -- identical
// convention to `cruise` above. engineGoToW() additionally reports back,
// via its bool return, whether a live PoseSource was actually available
// to dispatch onto MotionEngine::goToW() -- false means "no OTOS
// fitted/connected" (motion-api.md S3.6, ticket 010's own out-of-scope
// encoder-odometry fallback), not a decode or dispatch failure of its
// own; onGoToW() below turns that into an honest refusal rather than
// ever calling MotionEngine::goToW() with a bogus pose.
void engineMoveV(float vx, float omegaRad, uint32_t durationMs);
void engineGoToR(float x, float y, float speed, float arrive,
                 uint32_t timeoutMs);
bool engineGoToW(float x, float y, float speed, float arrive,
                 uint32_t timeoutMs);

namespace {

// The 15 `ConfigField` enum entries (main.ts) mapped onto
// setKernelValue()/getConfigValue()'s existing field ordinals
// (shims.cpp) -- one wire NAME per field, replacing the old binary
// CONFIG/SET_FIELD/GET_CONFIG verbs' bare ordinal one-for-one (sprint.md
// Migration Concerns: "GET/SET address the same DifferentialDrive::
// Config/Rig fields that exist today, under new wire names, with
// nothing to convert"). Declaration order matches ConfigField's own
// declaration order so a bare GET's dump reads in the same order a
// human reading main.ts would expect.
struct FieldEntry {
  const char* name;  // wire key
  int ordinal;        // shims.cpp's setKernelValue()/getConfigValue() field
};

constexpr FieldEntry kFields[] = {
    {"max_duty", 0},           // ConfigField.MaxDuty
    {"full_duty_velocity", 1}, // ConfigField.FullDutyVelocity
    {"pid_kp", 2},             // ConfigField.Kp
    {"pid_ki", 3},             // ConfigField.Ki
    {"pid_i_max", 4},          // ConfigField.IMax
    {"accel_kaff", 5},         // ConfigField.Kaff
    {"pid_max", 6},            // ConfigField.PidMax
    {"twist_hold_gain", 7},    // ConfigField.TwistHoldGain
    {"speed_floor", 8},        // ConfigField.SpeedFloor
    {"pos_err_max", 9},        // ConfigField.PosErrMax
    {"stall_speed", 10},       // ConfigField.StallSpeed
    {"stall_demand", 11},      // ConfigField.StallDemand
    {"stall_window", 12},      // ConfigField.StallWindow
    {"lambda_enabled", 13},    // ConfigField.LambdaEnabled
    {"crawl_pulse", 14},       // ConfigField.CrawlPulse
};
constexpr size_t kFieldCount = sizeof(kFields) / sizeof(kFields[0]);

const FieldEntry* findField(const char* name) {
  for (const auto& entry : kFields) {
    if (std::strcmp(name, entry.name) == 0) return &entry;
  }
  return nullptr;
}

// LOCAL flags layout, mirroring radio-robot-lib's own DiffDriveAdapter
// posture (diffdrive_adapter.cpp's computeFlags()): these bit numbers
// are NOT any externally-numbered scheme -- they exist only so STATUS's
// `flags=<hex>` packs the same handful of diagValue() booleans a bench
// operator already reads off the DIAG verb into one word.
constexpr uint32_t kFlagReady = 1u << 0;
constexpr uint32_t kFlagEstopped = 1u << 1;
constexpr uint32_t kFlagStallHalted = 1u << 2;
constexpr uint32_t kFlagLeaseExpired = 1u << 3;
constexpr uint32_t kFlagConnLeft = 1u << 4;
constexpr uint32_t kFlagConnRight = 1u << 5;
constexpr uint32_t kFlagWedgeLeft = 1u << 6;
constexpr uint32_t kFlagWedgeRight = 1u << 7;

// diagValue()'s own field-ordinal contract (shims.cpp) this file reads
// from -- named here so status() below reads as prose, not magic
// numbers. Only the subset status() actually needs; shims.cpp's DIAG
// verb reads many more (protocol.cpp's formatDiag()).
constexpr int kDiagReady = 0;
constexpr int kDiagEstopped = 1;
constexpr int kDiagStallHalted = 2;
constexpr int kDiagLeaseExpired = 3;
constexpr int kDiagConnLeft = 4;
constexpr int kDiagConnRight = 5;
constexpr int kDiagWedgeLeft = 6;
constexpr int kDiagWedgeRight = 7;
constexpr int kDiagVelocityLeft = 14;
constexpr int kDiagVelocityRight = 15;

const char* tlmModeWireName(Wire::TlmMode mode) {
  switch (mode) {
    case Wire::TlmMode::kOff: return "off";
    case Wire::TlmMode::kPose: return "pose";
    case Wire::TlmMode::kFull: return "full";
    case Wire::TlmMode::kAuto: return "auto";
    case Wire::TlmMode::kBuffer: return "buffer";
    // kNow is a one-shot request in the CURRENT mode's own shape
    // (protocol.md S6.1) -- never stored into mode_ (see onTlm() below),
    // kept here only so this switch stays exhaustive against a future
    // TlmMode enumerator.
    case Wire::TlmMode::kNow: return "pose";
  }
  return "off";  // unreachable with every enumerator handled above
}

// motion-api.md S9.1: "Angles are degrees at the API and milliradian
// integers on the wire ... The conversion lives in the binding, in one
// place." This is that one place: MOVE_X's wire `rotation` field and
// MOVE_V's wire `omega` field (sprint 003 ticket 012) both arrive here
// as a milliradian INTEGER, already decoded into this float by
// wire_handler.cpp; MotionEngine::moveX()/moveV() (motion_engine.h) both
// want RADIANS (or radians-per-second, for `omega`), their own native
// unit, with no wire-unit awareness of their own. 1 mrad == 0.001 rad,
// exact for any value either field can carry -- see
// test_wire_motion_verbs.py's own dedicated round-trip tests (both
// signs, both fields): an off-by-1000 here is invisible in a green
// build (everything still compiles and dispatches) and catastrophic on
// the robot (a 90 deg turn either barely twitches or spins wildly past
// a full revolution, depending on which way the factor is missed).
float mradToRad(float milliradians) { return milliradians * 0.001f; }

}  // namespace

WireAdapter::WireAdapter(const Wire::Identity& identity, NowMsFn nowMs)
    : identity_(identity), nowMs_(nowMs) {}

void WireAdapter::identity(Wire::Identity& out) const { out = identity_; }

void WireAdapter::setIdentity(const Wire::Identity& identity) {
  identity_ = identity;
}

uint32_t WireAdapter::now() const {
  // See this file's own header comment: nowMs_ is supplied at
  // composition time by a CODAL-facing caller (protocol.cpp); every
  // host test leaves it nullptr, so this stays the same honest 0
  // default it always was -- PING's own liveness contract only needs a
  // reply to exist, not a wall-clock-accurate value.
  return nowMs_ != nullptr ? nowMs_() : 0;
}

void WireAdapter::status(Wire::StatusFields& out) const {
  out.ready = diagValue(kDiagReady) != 0;
  const bool estopped = diagValue(kDiagEstopped) != 0;
  const bool stallHalted = diagValue(kDiagStallHalted) != 0;
  const bool leaseExpired = diagValue(kDiagLeaseExpired) != 0;
  const bool wedgeLeft = diagValue(kDiagWedgeLeft) != 0;
  const bool wedgeRight = diagValue(kDiagWedgeRight) != 0;

  out.connLeft = diagValue(kDiagConnLeft) != 0;
  out.connRight = diagValue(kDiagConnRight) != 0;
  // No OTOS in this project's wire-reachable surface yet (poseX/Y/
  // heading are cached-OTOS-fused odometry, not a boolean presence
  // flag) -- documented default, the same "no OTOS in this library"
  // choice DiffDriveAdapter makes for the identical reason.
  out.otos = false;
  out.wedge = wedgeLeft || wedgeRight;
  // "active" here means "a motion command is currently in effect" -- the
  // closest reading of this robot's WHEELS_V-only, planner-free command
  // surface can produce (mirrors DiffDriveAdapter::status()'s own
  // reasoning).
  out.active = out.ready && !estopped && !leaseExpired && !stallHalted &&
               (diagValue(kDiagVelocityLeft) != 0 ||
                diagValue(kDiagVelocityRight) != 0);

  uint32_t flags = 0;
  if (out.ready) flags |= kFlagReady;
  if (estopped) flags |= kFlagEstopped;
  if (stallHalted) flags |= kFlagStallHalted;
  if (leaseExpired) flags |= kFlagLeaseExpired;
  if (out.connLeft) flags |= kFlagConnLeft;
  if (out.connRight) flags |= kFlagConnRight;
  if (wedgeLeft) flags |= kFlagWedgeLeft;
  if (wedgeRight) flags |= kFlagWedgeRight;
  out.flags = flags;

  out.tlm = tlmModeWireName(mode_);
}

Wire::Result WireAdapter::onWheelsV(float left, float right,
                                    uint32_t duration, uint32_t id) {
  (void)id;
  if (duration > kWheelsVDurationCeiling) return Wire::Result::kRange;
  // left/right arrive as exact integral values (decoded from the wire's
  // signed-integer fields, wire_handler.cpp) -- a plain narrowing cast
  // is exact, no rounding needed.
  setWheelsTimed(static_cast<int>(left), static_cast<int>(right), duration);
  // sprint 003 ticket 005: record the resulting deadline so
  // hasLiveMotionObligation() can tell protocol.cpp's fiber loop to keep
  // ticking the kernel until it elapses -- see this file's header
  // comment. A no-op (never "active") with no clock wired.
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + duration;
  }
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onWheelsX(float left, float right, float cruise,
                                    uint32_t timeout, uint32_t id) {
  (void)id;
  // A speed ceiling has no sign -- refuse outright rather than take its
  // magnitude, or fall into wheelsX()'s own non-positive-cruise no-op
  // (motion_engine.h), which would silently accept this as "nothing to
  // command."
  if (cruise < 0.0f) return Wire::Result::kRange;
  // motion-api.md S1.1: "An X-form's commanded value is a displacement
  // ... so cruise is its own argument. Pass 0 for the configured
  // default." engineDefaultCruiseMmS() itself resolves to 0 if this
  // robot has never had one configured either -- refused below, not
  // silently accepted as a zero-speed command.
  const float resolvedCruise =
      cruise == 0.0f ? engineDefaultCruiseMmS() : cruise;
  if (resolvedCruise <= 0.0f) return Wire::Result::kRange;
  engineWheelsX(left, right, resolvedCruise, timeout);
  // sprint 003 ticket 012: arm the SAME motion-obligation tracking
  // onWheelsV() above always has -- see wire_adapter.h's own header
  // comment for the bug this fixes (ticket 011 dispatched real effect
  // here without arming it, so protocol.cpp's fiber never ticked the
  // kernel for this verb on hardware). `timeout` is a backstop, not
  // this move's real duration, so this is a conservative deadline: the
  // fiber may keep ticking a little past actual completion, which is
  // harmless.
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + timeout;
  }
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onMoveX(float distance, float rotation,
                                  float cruise, uint32_t timeout,
                                  uint32_t id) {
  (void)id;
  // Same cruise <0/==0 handling as onWheelsX() above.
  if (cruise < 0.0f) return Wire::Result::kRange;
  const float resolvedCruise =
      cruise == 0.0f ? engineDefaultCruiseMmS() : cruise;
  if (resolvedCruise <= 0.0f) return Wire::Result::kRange;
  // The wire's ONE milliradian->radian conversion seam (motion-api.md
  // S9.1) -- see mradToRad()'s own comment above.
  engineMoveX(distance, mradToRad(rotation), resolvedCruise, timeout);
  // sprint 003 ticket 012: see onWheelsX()'s identical comment above.
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + timeout;
  }
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onMoveV(float v_x, float omega, uint32_t duration,
                                  uint32_t id) {
  (void)id;
  // Shares WHEELS_V's own ceiling and "duration is the lease" rationale
  // -- see kWheelsVDurationCeiling's own doc comment (wire_adapter.h).
  if (duration > kWheelsVDurationCeiling) return Wire::Result::kRange;
  // The wire's OTHER milliradian->radian conversion seam (motion-api.md
  // S9.1) -- `omega` is angle-shaped exactly like MOVE_X's `rotation`;
  // see mradToRad()'s own comment above.
  engineMoveV(v_x, mradToRad(omega), duration);
  // sprint 003 ticket 012: see onWheelsX()'s identical comment above --
  // here `duration` IS the lease already, same as onWheelsV().
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + duration;
  }
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onGoToR(float x, float y, float speed, float arrive,
                                  uint32_t timeout, uint32_t id) {
  (void)id;
  // `speed`'s <0/==0 handling mirrors onWheelsX()/onMoveX() above -- see
  // this method's own doc comment (wire_adapter.h) for why (`speed`
  // plays `cruise`'s role for the underlying moveX() call).
  if (speed < 0.0f) return Wire::Result::kRange;
  const float resolvedSpeed =
      speed == 0.0f ? engineDefaultCruiseMmS() : speed;
  if (resolvedSpeed <= 0.0f) return Wire::Result::kRange;
  engineGoToR(x, y, resolvedSpeed, arrive, timeout);
  // sprint 003 ticket 012: see onWheelsX()'s identical comment above.
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + timeout;
  }
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onGoToW(float x, float y, float speed, float arrive,
                                  uint32_t timeout, uint32_t id) {
  (void)id;
  // Same speed <0/==0 handling as onGoToR() above.
  if (speed < 0.0f) return Wire::Result::kRange;
  const float resolvedSpeed =
      speed == 0.0f ? engineDefaultCruiseMmS() : speed;
  if (resolvedSpeed <= 0.0f) return Wire::Result::kRange;
  // motion-api.md S3.6 / ticket 010's own Description: the
  // encoder-odometry fallback is explicitly out of scope and not built,
  // so "no OTOS fitted, or fitted but never begun/connected" is a real
  // reachable state on this fleet, not theoretical -- see this method's
  // own doc comment (wire_adapter.h) for why kUnimplemented is the
  // refusal this class answers rather than driving toward a
  // garbage/zeroed pose.
  if (!engineGoToW(x, y, resolvedSpeed, arrive, timeout)) {
    return Wire::Result::kUnimplemented;
  }
  // sprint 003 ticket 012: see onWheelsX()'s identical comment above --
  // only armed on the path that actually dispatched a move.
  if (nowMs_ != nullptr) {
    motionObligationActive_ = true;
    motionObligationDeadlineMs_ = nowMs_() + timeout;
  }
  return Wire::Result::kOk;
}

void WireAdapter::onEstop() {
  // ESTOP -> estopAll() -> kernel.estop() + emergencyStopMotors(): the
  // handler itself never inspects this method's return (void, per
  // wire_handler.h's own Adapter::onEstop() contract) -- it replies
  // `estop` unconditionally after calling this.
  estopAll();
  // sprint 003 ticket 005: clear any live WHEELS_V obligation too -- an
  // e-stop must revert protocol.cpp's fiber loop to its idle poll
  // immediately, not keep ticking until a now-meaningless deadline
  // elapses (same rationale sprint 002's original obligation-clearing
  // handleEstop() documented).
  motionObligationActive_ = false;
}

Wire::Result WireAdapter::onStop(bool /*immediate*/, uint32_t /*id*/) {
  // STOP [now] -> stopAll() -> kernel.neutral(): stopAll() has no
  // refusal path of its own (matches kernel.neutral()'s own unconditional
  // acceptance), so this always acks kOk. `immediate` (STOP's optional
  // `now` token) has no effect here -- this project's stopAll() has
  // always been immediate regardless, same posture DiffDriveAdapter
  // documents for its own onStop() override (protocol.md S5.1: "both are
  // immediate at the kernel level").
  stopAll();
  // sprint 003 ticket 005: see onEstop()'s identical comment above.
  motionObligationActive_ = false;
  return Wire::Result::kOk;
}

bool WireAdapter::hasLiveMotionObligation() const {
  if (!motionObligationActive_ || nowMs_ == nullptr) return false;
  const uint32_t nowMs = nowMs_();
  // Wraparound-safe elapsed check (signed-difference idiom), same one
  // sprint 002's original obligation tracking used in protocol.cpp.
  return static_cast<int32_t>(nowMs - motionObligationDeadlineMs_) < 0;
}

bool WireAdapter::onGet(const char* name, float& out) const {
  const FieldEntry* entry = findField(name);
  if (entry == nullptr) return false;
  out = static_cast<float>(getConfigValue(entry->ordinal)) * 0.001f;
  return true;
}

Wire::Result WireAdapter::onSet(const char* name, float value, uint32_t id) {
  (void)id;
  const FieldEntry* entry = findField(name);
  if (entry == nullptr) return Wire::Result::kUnknown;
  setKernelValue(entry->ordinal,
                static_cast<int>(std::lround(value * 1000.0f)));
  return Wire::Result::kOk;
}

size_t WireAdapter::fieldCount() const { return kFieldCount; }

const char* WireAdapter::fieldName(size_t index) const {
  return index < kFieldCount ? kFields[index].name : "";
}

Wire::Result WireAdapter::onTlm(Wire::TlmMode mode) {
  // TLM NOW is a one-shot request in the CURRENT subscription's shape,
  // not a new subscription (protocol.md S6.1: "does not change mode") --
  // so it is deliberately never stored into mode_. Everything else
  // becomes the persisted mode.
  if (mode != Wire::TlmMode::kNow) mode_ = mode;
  return Wire::Result::kOk;
}

Wire::Result WireAdapter::onRun(const char* /*name*/,
                                const char* const* /*argv*/,
                                size_t /*argc*/, char* /*result*/,
                                size_t /*resultCapacity*/, bool& hasResult) {
  // No registration table -- see wire_adapter.h's own doc comment on
  // this override. Every RUN is ERR_UNKNOWN, the same wire outcome as
  // any name a real registration table would not recognize.
  hasResult = false;
  return Wire::Result::kUnknown;
}

}  // namespace diffDrive
