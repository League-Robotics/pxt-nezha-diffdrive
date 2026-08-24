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
// convention to `cruise` above. SPRINT 006 TICKET 007: engineGoToW()
// selects its own PoseSource internally (OtosPort when connected, the
// encoder-odometry fallback otherwise -- motion-api.md S3.6) and now
// always dispatches onto MotionEngine::goToW(); its bool return is
// unconditionally true under the current implementation, kept only to
// preserve the existing "was a live pose available" contract.
void engineMoveV(float vx, float omegaRad, uint32_t durationMs);
void engineGoToR(float x, float y, float speed, float arrive,
                 uint32_t timeoutMs);
bool engineGoToW(float x, float y, float speed, float arrive,
                 uint32_t timeoutMs);

// ---- shims.cpp entry points (sprint 004 ticket 004) ---------------------
// buildSnapshot()'s own five reads, reaching live pose/OTOS/wheel-speed
// state -- every one of these already exists in shims.cpp today (this
// ticket adds ZERO new entry points there), same same-package
// forward-declaration convention as every block above.
//
// THREE HAZARDS, each with real debugging history on this project:
//
//   1. poseX()/poseY()/poseHeading() each call odomUpdate() internally
//      and therefore MUTATE odometry -- this is LOAD-BEARING, not an
//      accident to "optimize" into one cached read: between moves,
//      nothing else advances odometry, so the 50 ms telemetry tick is
//      what keeps pose current while the robot sits idle. Collapsing
//      three calls into one would silently stop that.
//   2. otosGet(0)/otosGet(1) are 0.1 mm (divide by 10 for ox/oy);
//      otosGet(2) is ALREADY centidegrees (oh) -- do not also divide it.
//   3. otosGet() reads a CACHE. The protocol fiber must NEVER trigger a
//      fresh sensor sample (this project's own OtosPort blocking-read
//      primitive, a DIFFERENT, deliberately-not-named-here entry point
//      from this ordinal-based cache accessor) -- an I2C transaction
//      interposed in the Nezha encoder's select->read window destroys
//      the sample (Phase F). See
//      tests/host/test_wire_telemetry_projection.py's own source-text
//      check for the enforcement: that blocking-read entry point's own
//      name must appear NOWHERE in this file, comments included -- a
//      one-careless-line-away, catastrophic, SILENT failure mode.
int poseX();          // [mm] MUTATES odometry -- see hazard 1 above
int poseY();          // [mm] MUTATES odometry -- see hazard 1 above
int poseHeading();    // [cdeg] MUTATES odometry -- see hazard 1 above
int otosGet(int what);  // CACHE ONLY -- see hazard 3 above; never the
                         // blocking-read entry point
int wheelSpeed(int which);  // [mm/s]; which: 0 = left, 1 = right

namespace {

// The `ConfigField` enum entries (main.ts) mapped onto
// setKernelValue()/getConfigValue()'s existing field ordinals
// (shims.cpp) -- one wire NAME per field, replacing the old binary
// CONFIG/SET_FIELD/GET_CONFIG verbs' bare ordinal one-for-one (sprint.md
// Migration Concerns: "GET/SET address the same DifferentialDrive::
// Config/Rig fields that exist today, under new wire names, with
// nothing to convert"). Declaration order matches ConfigField's own
// declaration order so a bare GET's dump reads in the same order a
// human reading main.ts would expect. 15 entries through sprint 006;
// 17 as of sprint 007 ticket 003 (`default_cruise` joins `stall_clear`);
// 18 as of sprint 007 ticket 005, which fills in `rotational_slip`
// (ordinal 16) between them.
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
    {"default_cruise", 15},    // ConfigField.DefaultCruise (sprint 007
                               // ticket 003, closing R-11/BLK-03/API-03
                               // -- see shims.cpp's engineDefaultCruiseMmS()/
                               // Rig::defaultCruiseMmS_ for the field this
                               // ordinal actually reaches).
    {"rotational_slip", 16},   // ConfigField.RotationalSlip (sprint 007
                               // ticket 005, closing R-14/API-06 -- see
                               // motion_engine.h's setRotationalSlip()/
                               // rotationalSlip_ for the validation and
                               // the load-bearing derivation comment on
                               // the 0.952 default).
    {"stall_clear", 17},       // ConfigField.StallClear (sprint 007
                               // ticket 001) -- a write-triggered action
                               // wearing a config-field's clothes; see
                               // shims.cpp's setKernelValue()/
                               // getConfigValue() case 17 and
                               // clearStall()'s own comment.
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

// Sprint 004 ticket 004 additions -- otosGet(7)'s connected/disconnected
// boolean (R-22/WIRE-06's fix for status()'s own out.otos, below) and
// diagValue()'s numeric FULL-column ordinals (sprint.md Phase B / the
// issue's own column table; shims.cpp's diagValue() switch is the
// authority for these numbers).
constexpr int kOtosConnected = 7;      // otosGet(int), NOT diagValue()
constexpr int kDiagI2cFault = 8;       // -> STATUS `i2cf=` and the `i2cf` column
constexpr int kDiagLeaseExpiryCount = 9;   // -> `lexc`
constexpr int kDiagPositionLeft = 10;      // -> `posl`
constexpr int kDiagPositionRight = 11;     // -> `posr`
constexpr int kDiagAppliedDutyLeft = 12;   // -> `dutl`
constexpr int kDiagAppliedDutyRight = 13;  // -> `dutr`
constexpr int kDiagCycleCount = 16;        // -> `cyc`
constexpr int kDiagCycleOverrunCount = 19; // -> `cycovr`
constexpr int kDiagWrongWayCount = 25;     // -> `wrng`

// LOCAL flags layout's own free function, extracted (unchanged bit
// layout) so STATUS's `flags=` and the telemetry `flags` column read
// the SAME computation instead of two independently-editable copies
// (sprint.md's own Design Rationale; status-lost-diag-numeric-surface.md).
// Called from both status() and buildSnapshot() below.
uint32_t computeFlags() {
  uint32_t flags = 0;
  if (diagValue(kDiagReady) != 0) flags |= kFlagReady;
  if (diagValue(kDiagEstopped) != 0) flags |= kFlagEstopped;
  if (diagValue(kDiagStallHalted) != 0) flags |= kFlagStallHalted;
  if (diagValue(kDiagLeaseExpired) != 0) flags |= kFlagLeaseExpired;
  if (diagValue(kDiagConnLeft) != 0) flags |= kFlagConnLeft;
  if (diagValue(kDiagConnRight) != 0) flags |= kFlagConnRight;
  if (diagValue(kDiagWedgeLeft) != 0) flags |= kFlagWedgeLeft;
  if (diagValue(kDiagWedgeRight) != 0) flags |= kFlagWedgeRight;
  return flags;
}

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

// Sprint 004 ticket 004 closes the numeric half of the gap the comment
// below used to describe (status-lost-diag-numeric-surface.md):
// `i2cf=<n>` now rides STATUS via the SAME diagValue(kDiagI2cFault) call
// the telemetry `i2cf` column reads, so the two can never disagree.
// FULL's other seven numeric columns (posl/posr/dutl/dutr/lexc/wrng/
// cycovr) still have no STATUS-level equivalent -- they are telemetry,
// not status, per the issue's own resolution of that split (see
// buildSnapshot() below); only `i2cf` was judged genuinely status-shaped
// (SUC-005). R-22/WIRE-06 (code review 2026-08-23) also fixed here:
// `out.otos` used to hardcode false with a comment claiming no OTOS was
// wire-reachable -- false even at the time it was written, since
// otosGet(7) already existed and engineGoToW() already gated on it.
void WireAdapter::status(Wire::StatusFields& out) const {
  out.ready = diagValue(kDiagReady) != 0;
  const bool estopped = diagValue(kDiagEstopped) != 0;
  const bool stallHalted = diagValue(kDiagStallHalted) != 0;
  const bool leaseExpired = diagValue(kDiagLeaseExpired) != 0;

  out.connLeft = diagValue(kDiagConnLeft) != 0;
  out.connRight = diagValue(kDiagConnRight) != 0;
  // R-22/WIRE-06 fix: otosGet(7) is the SAME connected/disconnected
  // boolean engineGoToW() (shims.cpp) already gates its own dispatch on
  // -- STATUS can no longer claim "no OTOS" while a GO_TO_W move is
  // actively using one. otosGet() reads a cache; this is not a
  // fresh-sample blocking read (see this file's own forward-declaration
  // block for why that distinction is load-bearing).
  out.otos = otosGet(kOtosConnected) != 0;
  out.wedge = diagValue(kDiagWedgeLeft) != 0 || diagValue(kDiagWedgeRight) != 0;
  // "active" here means "a motion command is currently in effect" -- the
  // closest reading of this robot's WHEELS_V-only, planner-free command
  // surface can produce (mirrors DiffDriveAdapter::status()'s own
  // reasoning).
  out.active = out.ready && !estopped && !leaseExpired && !stallHalted &&
               (diagValue(kDiagVelocityLeft) != 0 ||
                diagValue(kDiagVelocityRight) != 0);

  out.flags = computeFlags();
  out.i2cf = diagValue(kDiagI2cFault);

  out.tlm = tlmModeWireName(mode_);
}

Wire::Result WireAdapter::onWheelsV(float left, float right,
                                    uint32_t duration, uint32_t id) {
  (void)id;
  if (duration > kWheelsVDurationCeiling) return Wire::Result::kRange;
  // WIRE-08 (code review 2026-08-23): refuse BEFORE the cast below runs
  // at all -- see kWireBoundaryCastCeiling's own doc comment
  // (wire_adapter.h) for why an unclamped static_cast<int> here is
  // platform-dependent UB for a wire-legal but absurd value, and why
  // this bound is what keeps the cast well-defined (and therefore
  // identical) on both the C++20 host and the C++11 target.
  if (left < -kWireBoundaryCastCeiling || left > kWireBoundaryCastCeiling ||
      right < -kWireBoundaryCastCeiling || right > kWireBoundaryCastCeiling) {
    return Wire::Result::kRange;
  }
  // left/right arrive as exact integral values (decoded from the wire's
  // signed-integer fields, wire_handler.cpp) -- a plain narrowing cast
  // is exact, no rounding needed, now that the range check above rules
  // out the one region where "exact" stops being true.
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
  // Sprint 006 ticket 007: engineGoToW() now falls back to encoder
  // odometry when no OTOS is connected (motion-api.md S3.6) rather than
  // refusing, so this call always dispatches in the current
  // implementation -- see this method's own doc comment (wire_adapter.h)
  // for why the `!engineGoToW(...)` check below is nonetheless kept.
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
  // WIRE-08 (code review 2026-08-23): `value` arrives with no ceiling
  // of its own (parseFloatField, wire_handler.cpp, accepts any finite
  // float) -- setKernelValue()'s own x1000 scaling convention can turn
  // an absurd-but-legal field value into a product that overflows
  // `long`'s 32-bit range before std::lround() ever runs (e.g. `SET
  // pid_kp 3000000` -> 3e9), which is unspecified on the target, not
  // merely imprecise. Refuse BEFORE the round -- see
  // kWireBoundaryCastCeiling's own doc comment (wire_adapter.h).
  const float scaled = value * 1000.0f;
  if (scaled < -kWireBoundaryCastCeiling || scaled > kWireBoundaryCastCeiling) {
    return Wire::Result::kRange;
  }
  setKernelValue(entry->ordinal, static_cast<int>(std::lround(scaled)));
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

bool WireAdapter::telemetryEnabled() const {
  return mode_ != Wire::TlmMode::kOff;
}

const Wire::Snapshot& WireAdapter::buildSnapshot() {
  // protocol.md S6.2: seq wraps 0..127 -- THIS method's responsibility,
  // not WireHandler's (the handler only prints whatever value it is
  // given). Advanced BEFORE building the frame, so the very first frame
  // this adapter ever emits reports seq 1, not 0.
  seq_ = static_cast<uint8_t>((seq_ + 1) & 0x7F);

  // Read every source exactly ONCE per call -- poseX()/poseY()/
  // poseHeading() each mutate odometry (this file's own
  // forward-declaration block), so calling any of them twice per tick
  // would double-advance it for no reason.
  const int32_t x = static_cast<int32_t>(poseX());
  const int32_t y = static_cast<int32_t>(poseY());
  const int32_t h = static_cast<int32_t>(poseHeading());
  // otosGet(0)/(1) are 0.1 mm -- divide by 10 for ox/oy (plain integer
  // division, truncating toward zero: the issue's own "OTOS 0.1mm->mm"
  // scale test pins -5678 -> -567, not the round-half -568 a
  // std::lround-style conversion would give). otosGet(2) is ALREADY
  // centidegrees -- do NOT also divide it.
  const int32_t ox = otosGet(0) / 10;
  const int32_t oy = otosGet(1) / 10;
  const int32_t oh = static_cast<int32_t>(otosGet(2));
  const int32_t vl = static_cast<int32_t>(wheelSpeed(0));
  const int32_t vr = static_cast<int32_t>(wheelSpeed(1));
  const int32_t i2cf = static_cast<int32_t>(diagValue(kDiagI2cFault));
  const uint32_t flags = computeFlags();

  size_t i = 0;
  columns_[i++] = {"seq", static_cast<int32_t>(seq_), false};
  columns_[i++] = {"now", static_cast<int32_t>(now()), false};
  columns_[i++] = {"flags", static_cast<int32_t>(flags), true};
  columns_[i++] = {"x", x, false};
  columns_[i++] = {"y", y, false};
  columns_[i++] = {"h", h, false};
  columns_[i++] = {"ox", ox, false};
  columns_[i++] = {"oy", oy, false};
  columns_[i++] = {"oh", oh, false};
  columns_[i++] = {"vl", vl, false};
  columns_[i++] = {"vr", vr, false};
  columns_[i++] = {"i2cf", i2cf, false};

  // FULL adds these 8; every other non-off mode (currently just kPose;
  // kAuto/kBuffer have no distinct column-set behavior implemented on
  // this adapter -- see this file's own buildSnapshot() doc comment,
  // wire_adapter.h) gets POSE's 12 above and stops here.
  if (mode_ == Wire::TlmMode::kFull) {
    columns_[i++] = {"cyc", static_cast<int32_t>(diagValue(kDiagCycleCount)),
                     false};
    columns_[i++] = {"posl",
                     static_cast<int32_t>(diagValue(kDiagPositionLeft)),
                     false};
    columns_[i++] = {"posr",
                     static_cast<int32_t>(diagValue(kDiagPositionRight)),
                     false};
    columns_[i++] = {"dutl",
                     static_cast<int32_t>(diagValue(kDiagAppliedDutyLeft)),
                     false};
    columns_[i++] = {"dutr",
                     static_cast<int32_t>(diagValue(kDiagAppliedDutyRight)),
                     false};
    columns_[i++] = {"lexc",
                     static_cast<int32_t>(diagValue(kDiagLeaseExpiryCount)),
                     false};
    columns_[i++] = {"wrng",
                     static_cast<int32_t>(diagValue(kDiagWrongWayCount)),
                     false};
    columns_[i++] = {"cycovr",
                     static_cast<int32_t>(diagValue(kDiagCycleOverrunCount)),
                     false};
  }

  snapshot_.columns = columns_;
  snapshot_.count = i;
  return snapshot_;
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
