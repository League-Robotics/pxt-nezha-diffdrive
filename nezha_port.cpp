// nezha_port.cpp -- see nezha_port.h. Ported from the firmware's
// nezha_motor.cpp; the shaping-stage ORDER is load-bearing.
#include "nezha_port.h"

#include <cmath>

namespace diffDrive {

namespace {
float clampf(float value, float lo, float hi) {
  return value < lo ? lo : (value > hi ? hi : value);
}
}  // namespace

// ---- bus primitives -------------------------------------------------

bool NezhaMotorPort::writeFrame(uint8_t arg, uint8_t reg, uint8_t val) {
  uint8_t frame[8] = {0xFF, 0xF9, port_, arg, reg, val, 0xF5, 0x00};
  // codal-microbit-v2 (V2) I2C takes uint8_t*; classic DAL (V1) takes char*.
#if MICROBIT_CODAL
  int status = uBit.i2c.write(kAddress << 1, frame, 8);
#else
  int status = uBit.i2c.write(kAddress << 1,
                              reinterpret_cast<char*>(frame), 8);
#endif
  return status == MICROBIT_OK;
}

bool NezhaMotorPort::readEncoderRaw(int32_t* raw) {
  uint8_t data[4] = {0, 0, 0, 0};
#if MICROBIT_CODAL
  int status = uBit.i2c.read(kAddress << 1, data, 4);
#else
  int status = uBit.i2c.read(kAddress << 1,
                             reinterpret_cast<char*>(data), 4);
#endif
  if (status != MICROBIT_OK) return false;
  *raw = static_cast<int32_t>(
      static_cast<uint32_t>(data[0]) |
      (static_cast<uint32_t>(data[1]) << 8) |
      (static_cast<uint32_t>(data[2]) << 16) |
      (static_cast<uint32_t>(data[3]) << 24));
  return true;
}

// ---- lifecycle ------------------------------------------------------

void NezhaMotorPort::begin() {
  // The 0x46 register sits frozen at 0 until its first select+read.
  // Median-of-3 atomic reads -> software offset, so position() starts
  // at zero without ever device-resetting the counter.
  int32_t samples[3] = {0, 0, 0};
  int good = 0;
  for (int i = 0; i < 3; ++i) {
    if (!writeFrame(0x00, kRegEncoder, 0x00)) continue;
    fiber_sleep(4);  // [ms] select -> read settle
    int32_t raw = 0;
    if (readEncoderRaw(&raw)) samples[good++] = raw;
  }
  if (good > 0) {
    // median of what we got
    for (int i = 0; i < good; ++i)
      for (int j = i + 1; j < good; ++j)
        if (samples[j] < samples[i]) {
          int32_t t = samples[i]; samples[i] = samples[j]; samples[j] = t;
        }
    encOffset_ = samples[good / 2];
    lastGoodRaw_ = encOffset_;
    connected_ = true;
  }
  primed_ = true;
}

// ---- command staging + shaping --------------------------------------

void NezhaMotorPort::setDuty(float duty) {
  stagedDuty_ = clampf(duty, -1.0f, 1.0f);
}

void NezhaMotorPort::emergencyStop() {
  // The one call that must not depend on a healthy tick(): zero the
  // stage AND write zero through the never-shaped stop path now.
  stagedDuty_ = 0.0f;
  writeShapedDuty(0.0f, static_cast<uint32_t>(lastTickUs_ / 1000));
}

void NezhaMotorPort::writeShapedDuty(float duty, uint32_t nowMs) {
  // 1. Exact zero short-circuits ALL shaping. Stop is stop. The zero
  //    entry TIME is recorded and the last nonzero SIGN is kept: a
  //    reversal that passes through a brief commanded zero (a move
  //    ending, then the next move starting opposite -- every square
  //    corner) is still a reversal, and the brick still needs its full
  //    zero dwell. The old code cleared the sign history here, which
  //    shipped corner reversals ~20-30 ms after the zero -- inside the
  //    (20, 50] ms window the wedgelab campaign measured as 12/12
  //    latching (radio-robot-elite docs/knowledge/2026-07-04-encoder-
  //    wedge.md). Bench signature this fixes: intermittent tour-corner
  //    encoder freezes -> leg overshoot / heading corruption.
  if (duty == 0.0f) {
    if (!atZero_) {
      atZero_ = true;
      zeroSinceMs_ = nowMs;
    }
    dwelling_ = false;  // an explicit stop supersedes a pending dwell
    writeRawDuty(0.0f, lastTickUs_, /*stopping=*/true);
    return;
  }
  // 2. Deadband BOOST: a genuine sub-deadband command is raised to the
  //    floor, never zeroed (zero has its own meaning above).
  if (std::fabs(duty) < outputDeadband_) {
    duty = duty < 0.0f ? -outputDeadband_ : outputDeadband_;
  }
  const int sign = duty > 0.0f ? 1 : -1;
  // 3. Reversal dwell: on ANY sign change versus the last NONZERO
  //    command -- direct flip or through an intervening zero -- hold
  //    commanded zero until a full reversalDwell_ of zero time has
  //    elapsed, crediting time already spent at commanded zero.
  if (lastNonzeroSign_ != 0 && sign != lastNonzeroSign_) {
    if (!dwelling_) {
      dwelling_ = true;
      dwellStart_ = atZero_ ? zeroSinceMs_ : nowMs;
    }
    if (static_cast<float>(nowMs - dwellStart_) < reversalDwell_) {
      writeRawDuty(0.0f, lastTickUs_, /*stopping=*/true);
      return;  // still holding; the new duty ships on a later tick
    }
    dwelling_ = false;
  }
  atZero_ = false;
  lastNonzeroSign_ = sign;
  writeRawDuty(duty, lastTickUs_, /*stopping=*/false);
}

void NezhaMotorPort::writeRawDuty(float duty, uint64_t nowUs,
                                  bool stopping) {
  duty = clampf(duty, -1.0f, 1.0f);

  // Sigma-delta quantizer to integer percent. The carry preserves
  // sub-percent resolution; it is DISCARDED on a commanded zero so a
  // stopped wheel cannot creep from accumulated remainder.
  int pct;
  if (stopping) {
    dutyCarry_ = 0.0f;
    pct = 0;
  } else {
    float wanted = clampf(duty * 100.0f + dutyCarry_, -100.0f, 100.0f);
    pct = static_cast<int>(std::lround(wanted));
    dutyCarry_ = clampf(wanted - static_cast<float>(pct), -1.0f, 1.0f);
  }

  // stopNotTaken: a commanded zero re-writes while the wheel still
  // reads motion, regardless of the dedupe cache -- the brick latches
  // its last speed and one lost zero write is permanent.
  const bool stopNotTaken =
      pct == 0 && std::fabs(velocity_) > kStopConfirmVelocity;
  if (pct == lastWrittenPct_ && !stopNotTaken) return;

  // Min-write throttle -- stop writes always bypass it.
  if (!stopping && writeThrottle_ > 0.0f &&
      static_cast<float>(nowUs - lastWriteTimeUs_) < writeThrottle_) {
    return;
  }

  // Slew -- skipped for a stop and for the very first write (the
  // kNeverWritten sentinel through a clamp once produced a
  // wrong-direction first command, a wedge trigger).
  if (!stopping && lastWrittenPct_ != kNeverWritten) {
    const int step = pct - lastWrittenPct_;
    const int maxStep = static_cast<int>(slewRate_);
    if (step > maxStep) pct = lastWrittenPct_ + maxStep;
    else if (step < -maxStep) pct = lastWrittenPct_ - maxStep;
  }

  const int signed_pct = pct * fwdSign_;
  const uint8_t direction = signed_pct >= 0 ? kDirCw : kDirCcw;
  const uint8_t magnitude =
      static_cast<uint8_t>(signed_pct >= 0 ? signed_pct : -signed_pct);
  if (writeFrame(direction, kRegMotorRun, magnitude)) {
    // Commit only on ACK: a NAK'd write retries next tick instead of
    // latching "already written".
    lastWrittenPct_ = static_cast<int8_t>(pct);
    lastWriteTimeUs_ = nowUs;
  } else {
    connected_ = false;
  }
}

// ---- split-phase encoder -------------------------------------------

void NezhaMotorPort::requestSample() {
  // Select 0x46. The kernel spends the settle in sleepMillis(4); this
  // port is the brick's only client, so ordering holds structurally.
  writeFrame(0x00, kRegEncoder, 0x00);
}

void NezhaMotorPort::collect(uint64_t nowUs) {
  int32_t raw = 0;
  if (readEncoderRaw(&raw)) {
    lastGoodRaw_ = raw;
    connected_ = true;
    const float pos =
        static_cast<float>(raw - encOffset_) * static_cast<float>(fwdSign_);
    if (hasLastTick_) {
      const float dt =
          static_cast<float>(nowUs - sampleTimeUs_) / 1e6f;  // [s]
      if (dt > 0.0f) velocity_ = (pos - lastPosition_) / dt;
    }
    lastPosition_ = pos;
    sampleTimeUs_ = nowUs;  // stamped at collect SUCCESS only
    hasLastTick_ = true;
  } else {
    connected_ = false;  // sampleTimeUs_ HOLDS -- age grows honestly
  }
}

void NezhaMotorPort::tick(uint64_t nowUs) {
  lastTickUs_ = nowUs;
  collect(nowUs);
  writeShapedDuty(stagedDuty_, static_cast<uint32_t>(nowUs / 1000));

  // Wedge detector: consecutive IDENTICAL position reads, raw and
  // unconditional; the suspect flavor additionally requires drive.
  if (lastPosition_ == lastWedgeCheckPosition_ && connected_) {
    ++identicalReads_;
    if (std::fabs(appliedDuty()) > kMotionThreshold) {
      ++identicalReadsDriven_;
      if (identicalReadsDriven_ > maxDrivenStreak_)
        maxDrivenStreak_ = identicalReadsDriven_;
    } else {
      identicalReadsDriven_ = 0;
    }
  } else {
    identicalReads_ = 0;
    identicalReadsDriven_ = 0;
  }
  lastWedgeCheckPosition_ = lastPosition_;
  wedgeLatched_ = identicalReads_ >= kWedgeThreshold;
  wedgeSuspect_ = identicalReadsDriven_ >= kWedgeThreshold;
}

// ---- readbacks ------------------------------------------------------

float NezhaMotorPort::position() const { return lastPosition_; }
float NezhaMotorPort::velocity() const { return velocity_; }

float NezhaMotorPort::appliedDuty() const {
  if (lastWrittenPct_ == kNeverWritten) return 0.0f;
  return static_cast<float>(lastWrittenPct_) / 100.0f;
}

void NezhaMotorPort::rebaseline() {
  // Software-only re-anchor: position() reads 0 from here, no bus
  // traffic, the device counter is untouched.
  encOffset_ = lastGoodRaw_;
  lastPosition_ = 0.0f;
}

void NezhaMotorPort::configureShaping(float outputDeadband,
                                      float reversalDwell, float slewRate,
                                      float writeThrottle) {
  outputDeadband_ = outputDeadband;
  reversalDwell_ = reversalDwell;
  slewRate_ = slewRate;
  writeThrottle_ = writeThrottle;
}

}  // namespace diffDrive
