// cutebot_port.cpp -- see cutebot_port.h. Host-compilable in its
// entirety; no pxt.h anywhere in this file (see cutebot_port.h's own
// header comment for where the target-only half of a Cutebot board
// lives instead).
#include "cutebot_port.h"

#include "vfp_guard.h"

#include <cmath>

namespace diffDrive {

namespace {
float clampf(float value, float lo, float hi) {
  return value < lo ? lo : (value > hi ? hi : value);
}
}  // namespace

// ---- CutebotDevice: the shared 0x10 slave ---------------------------

bool CutebotDevice::writeV2Frame(uint8_t cmd, const uint8_t* params,
                                 uint8_t paramLen) {
  uint8_t frame[8] = {0xFF, 0xF9, cmd, paramLen, 0, 0, 0, 0};
  for (uint8_t i = 0; i < paramLen; ++i) frame[4 + i] = params[i];
  const int status = bus_.write(kAddress << 1, frame,
                                static_cast<int>(4 + paramLen));
  // Every v2 i2cCommandSend() in the ELECFREAKS extension is followed
  // by a 1 ms busy-wait (SOURCE READING -- the design doc's own
  // S1.2). Routed through the guarded sleep per this repo's own
  // fiber-yield-safety rule -- never a spin, never a raw
  // fiber_sleep(). On the host this resolves to a linked no-op (see
  // tests/host/cutebot_port_shim.cpp).
  vfpSafeSleep(1);
  return status == 0;
}

bool CutebotDevice::writeWheelFrame(uint8_t wheelSel, uint8_t absL,
                                    uint8_t absR, uint8_t dirbits) {
  const uint8_t params[4] = {wheelSel, absL, absR, dirbits};
  return writeV2Frame(kCmdWheel, params, 4);
}

void CutebotDevice::shipFrame() {
  const uint8_t dirbits =
      static_cast<uint8_t>((stagedValue_[0] < 0 ? 0x01 : 0x00) |
                           (stagedValue_[1] < 0 ? 0x02 : 0x00));
  const uint8_t absL = static_cast<uint8_t>(
      stagedValue_[0] < 0 ? -stagedValue_[0] : stagedValue_[0]);
  const uint8_t absR = static_cast<uint8_t>(
      stagedValue_[1] < 0 ? -stagedValue_[1] : stagedValue_[1]);
  writeWheelFrame(kWheelBoth, absL, absR, dirbits);
}

void CutebotDevice::stageDuty(int side, int8_t wireValue) {
  stagedValue_[side] = wireValue;
  staged_[side] = true;
  if (staged_[0] && staged_[1]) {
    shipFrame();
    staged_[0] = false;
    staged_[1] = false;
  }
}

bool CutebotDevice::writeSingleWheelZero(int side) {
  const uint8_t wheelSel =
      static_cast<uint8_t>(side == 0 ? kWheelLeft : kWheelRight);
  return writeWheelFrame(wheelSel, 0, 0, 0);
}

bool CutebotDevice::selectDegrees(int side) {
  const uint8_t sel = (side == 0) ? kSelDegreesLeft : kSelDegreesRight;
  const uint8_t params[1] = {sel};
  return writeV2Frame(kCmdEncoder, params, 1);
}

bool CutebotDevice::readSelectedDegrees(int32_t* degreesOut) {
  uint8_t data[4] = {0, 0, 0, 0};
  if (bus_.read(kAddress << 1, data, 4) != 0) return false;
  *degreesOut = static_cast<int32_t>(
      static_cast<uint32_t>(data[0]) |
      (static_cast<uint32_t>(data[1]) << 8) |
      (static_cast<uint32_t>(data[2]) << 16) |
      (static_cast<uint32_t>(data[3]) << 24));
  return true;
}

bool CutebotDevice::hardwareClearEncoder(int side) {
  const uint8_t params[1] = {static_cast<uint8_t>(side)};
  return writeV2Frame(kCmdClear, params, 1);
}

bool CutebotDevice::ensureProbed() {
  if (probed_) return true;
  // v1-style fixed 7-byte revision probe (SOURCE READING, the
  // extension's top-level readHardVersion(), the design doc's own
  // S1.1) -- NOT a v2 frame, so it does not go through
  // writeV2Frame()/the 1 ms wait, which is specific to v2.ts's
  // i2cCommandSend(). UNVERIFIED whether a real board needs a settle
  // here too; nothing in the source reading says so.
  static const uint8_t kProbe[7] = {0x99, 0x15, 0x01, 0x00, 0x00, 0x00, 0x88};
  if (bus_.write(kAddress << 1, kProbe, 7) != 0) return false;
  uint8_t reply = 0;
  if (bus_.read(kAddress << 1, &reply, 1) != 0) return false;
  isV2_ = (reply != 1);
  probed_ = true;
  return true;
}

// ---- CutebotMotorPort ------------------------------------------------

void CutebotMotorPort::begin() {
  device_.ensureProbed();
  // Seed encOffset_ from a single sample -- NezhaMotorPort's
  // median-of-3 boot seed guards a MEASURED Nezha quirk (the 0x46
  // register sitting frozen at 0 until its first select+read); nothing
  // in the Cutebot source reading suggests the same, so this starts
  // with the plainest possible seed and earns anything fancier on the
  // bench (see this file's header "minimal shaping" note).
  if (!device_.selectDegrees(side_)) {
    connected_ = false;
    return;
  }
  int32_t rawDegrees = 0;
  if (device_.readSelectedDegrees(&rawDegrees)) {
    const int32_t raw = rawDegrees * 10;
    encOffset_ = raw;
    lastRaw_ = raw;
    connected_ = true;
  } else {
    connected_ = false;
  }
}

void CutebotMotorPort::requestSample() {
  device_.selectDegrees(side_);  // return value ignored -- collect()'s
                                 // own read failure is what connected()
                                 // and the held sampleTime() contract
                                 // key off, matching NezhaMotorPort's
                                 // own requestSample()
}

void CutebotMotorPort::collect(uint64_t now) {  // [us]
  int32_t rawDegrees = 0;
  if (device_.readSelectedDegrees(&rawDegrees)) {
    connected_ = true;
    const int32_t raw = rawDegrees * 10;
    lastRaw_ = raw;
    const float pos = static_cast<float>(raw - encOffset_) *
                       static_cast<float>(fwdSign_);
    if (hasLastTick_) {
      const float dt = static_cast<float>(now - sampleTime_) / 1e6f;  // [s]
      if (dt > 0.0f) velocity_ = (pos - lastPosition_) / dt;
    }
    lastPosition_ = pos;
    sampleTime_ = now;  // stamped at collect SUCCESS only
    hasLastTick_ = true;
  } else {
    connected_ = false;  // sampleTime_ HOLDS -- age grows honestly
  }
}

void CutebotMotorPort::setDuty(float duty) {
  stagedDuty_ = clampf(duty, -1.0f, 1.0f);
}

void CutebotMotorPort::tick(uint64_t now) {  // [us]
  lastTick_ = now;
  collect(now);

  // Minimal shaping (see this file's header): clamp, round to a
  // percent, ship -- no dedupe, no slew, no reversal dwell. Every
  // cycle stages, regardless of whether the value changed; the "one
  // frame per cycle" guarantee comes from CutebotDevice's own
  // both-sides-staged gate, not from skipping unchanged writes.
  const int pct = static_cast<int>(std::lround(stagedDuty_ * 100.0f));
  lastApplied_ = pct;  // caller-space -- matches appliedDuty()'s own
                       // convention, the same as NezhaMotorPort's
                       // lastWritten_ (recorded BEFORE fwdSign_)
  const int wireValue = pct * static_cast<int>(fwdSign_);
  device_.stageDuty(side_, static_cast<int8_t>(wireValue));
}

void CutebotMotorPort::emergencyStop() {
  // The one call that must not depend on a healthy tick(): zero the
  // stage AND write zero through an immediate, unstaged single-wheel
  // frame now -- see CutebotDevice::writeSingleWheelZero()'s own
  // comment for why this does not disturb the other side's staging.
  stagedDuty_ = 0.0f;
  lastApplied_ = 0;
  device_.writeSingleWheelZero(side_);
}

float CutebotMotorPort::position() const { return lastPosition_; }
float CutebotMotorPort::velocity() const { return velocity_; }

float CutebotMotorPort::appliedDuty() const {
  return static_cast<float>(lastApplied_) / 100.0f;
}

void CutebotMotorPort::rebaseline() {
  // Software-only re-anchor, exactly like NezhaMotorPort::rebaseline():
  // position() reads 0 from here, no bus traffic, the device's own
  // hardware counter is untouched. cmd 0x50 (CutebotDevice::
  // hardwareClearEncoder()) is a REAL hardware zero and is deliberately
  // never called by this method.
  encOffset_ = lastRaw_;
  lastPosition_ = 0.0f;
}

WiringResult CutebotMotorPort::configureWiring(uint8_t port, int8_t sign) {
  if (port != wiredPort()) {
    // The Cutebot's wheels are fixed to the one 0x10 slave -- there is
    // no second port to move to. See this file's own WiringResult
    // comment for why kUnimplemented, not kBadArg/kRange.
    return WiringResult::kUnimplemented;
  }
  if (sign != 1 && sign != -1) {
    // Out-of-range sign: ignored, no-change-free -- matches
    // NezhaMotorPort::configureWiring()'s own precedent for an
    // out-of-range field ("Out-of-range ignored, no-change free",
    // nezha_port.h).
    return WiringResult::kOk;
  }
  if (sign == fwdSign_) return WiringResult::kOk;  // no-op, already this

  // Zero this wheel first, while it can still be addressed under its
  // CURRENT sign -- same reasoning as NezhaMotorPort::configureWiring()
  // (nezha_port.cpp): a rewire that skipped this could orphan a
  // running wheel that nothing is able to command any more once the
  // sign (and therefore the caller's notion of "forward") changes.
  emergencyStop();

  fwdSign_ = sign;

  // The encoder state describes the OLD sign; drop it and let begin()
  // re-anchor -- same reset shape as NezhaMotorPort::configureWiring().
  stagedDuty_ = 0.0f;
  lastApplied_ = 0;
  lastPosition_ = 0.0f;
  velocity_ = 0.0f;
  sampleTime_ = 0;
  lastTick_ = 0;
  hasLastTick_ = false;
  connected_ = false;

  begin();
  return WiringResult::kOk;
}

// ---- board-generic diag hook -----------------------------------------

int cutebotBoardDiagValue(const CutebotMotorPort& left,
                          const CutebotMotorPort& right, int ordinal) {
  switch (ordinal) {
    case 35: return static_cast<int>(left.wiredPort());
    case 36: return static_cast<int>(left.wiredSign());
    case 37: return static_cast<int>(right.wiredPort());
    case 38: return static_cast<int>(right.wiredSign());
    default: return 0;
  }
}

}  // namespace diffDrive
