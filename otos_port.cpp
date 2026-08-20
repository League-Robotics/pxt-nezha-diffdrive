// otos_port.cpp -- see otos_port.h. Faithful port of radio-robot-elite
// Hardware::RealOtos onto uBit.i2c, minus the lever-arm transform.
#include "otos_port.h"

#include <cmath>

namespace diffDrive {

void OtosPort::busGap() { fiber_sleep(kBusClearanceMs); }

namespace {
// codal-microbit-v2 (V2) I2C takes uint8_t*; classic DAL (V1) takes
// char* -- same guard nezha_port.cpp uses.
int i2cWrite(uint8_t addr8, uint8_t* buf, int len) {
#if MICROBIT_CODAL
  return uBit.i2c.write(addr8, buf, len);
#else
  return uBit.i2c.write(addr8, reinterpret_cast<char*>(buf), len);
#endif
}

int i2cRead(uint8_t addr8, uint8_t* buf, int len) {
#if MICROBIT_CODAL
  return uBit.i2c.read(addr8, buf, len);
#else
  return uBit.i2c.read(addr8, reinterpret_cast<char*>(buf), len);
#endif
}
}  // namespace

bool OtosPort::writeReg8(uint8_t reg, uint8_t val) {
  busGap();
  uint8_t buf[2] = {reg, val};
  return i2cWrite(kAddr << 1, buf, 2) == MICROBIT_OK;
}

bool OtosPort::readReg8(uint8_t reg, uint8_t* val) {
  busGap();
  if (i2cWrite(kAddr << 1, &reg, 1) != MICROBIT_OK) return false;
  busGap();
  return i2cRead(kAddr << 1, val, 1) == MICROBIT_OK;
}

bool OtosPort::writeXYH(uint8_t startReg, int16_t x, int16_t y, int16_t h) {
  busGap();
  uint8_t buf[7];
  buf[0] = startReg;
  buf[1] = static_cast<uint8_t>(x & 0xFF);
  buf[2] = static_cast<uint8_t>((x >> 8) & 0xFF);
  buf[3] = static_cast<uint8_t>(y & 0xFF);
  buf[4] = static_cast<uint8_t>((y >> 8) & 0xFF);
  buf[5] = static_cast<uint8_t>(h & 0xFF);
  buf[6] = static_cast<uint8_t>((h >> 8) & 0xFF);
  return i2cWrite(kAddr << 1, buf, 7) == MICROBIT_OK;
}

void OtosPort::writePoseMm(uint8_t startReg, float xF, float yF, float hF) {
  long rx = lroundf(xF / kPosMmPerLsb);
  long ry = lroundf(yF / kPosMmPerLsb);
  long rh = lroundf(hF / kHdgRadPerLsb);
  if (rx > 32767) rx = 32767;
  if (rx < -32767) rx = -32767;
  if (ry > 32767) ry = 32767;
  if (ry < -32767) ry = -32767;
  if (rh > 32767) rh = 32767;
  if (rh < -32767) rh = -32767;
  writeXYH(startReg, static_cast<int16_t>(rx), static_cast<int16_t>(ry),
           static_cast<int16_t>(rh));
}

bool OtosPort::begin() {
  uint8_t id = 0;
  bool ok = readReg8(kRegProductId, &id);
  lastProbeId_ = id;
  initialized_ = ok && (id == kExpectedProductId);
  connected_ = initialized_;
  if (!initialized_) return false;

  writeReg8(kRegSignalProcessCfg, 0x0F);
  writeReg8(kRegReset, 0x01);
  writeReg8(kRegImuCalibration, kImuCalibSamples);

  // Zero the chip's scalar AND offset registers on every boot: the
  // chip is never power-cycled by an nRF reset, so it inherits
  // whatever an earlier session wrote (reference driver's measured
  // 42.7 mm phantom-circle failure). Scalar 0 == scale 1.000.
  writeReg8(kRegLinearScalar, 0);
  writeReg8(kRegAngularScalar, 0);
  writePoseMm(kRegOffsetXl, 0.0f, 0.0f, 0.0f);
  writePoseMm(kRegPositionXl, 0.0f, 0.0f, 0.0f);
  return true;
}

bool OtosPort::read() {
  if (!initialized_) return false;

  busGap();
  uint8_t reg = kRegPositionXl;
  uint8_t raw[12] = {0};
  int ws = i2cWrite(kAddr << 1, &reg, 1);
  busGap();
  int rs = i2cRead(kAddr << 1, raw, 12);

  connected_ = (ws == MICROBIT_OK && rs == MICROBIT_OK);
  if (!connected_) return false;

  int16_t rx = static_cast<int16_t>(raw[0] | (static_cast<uint16_t>(raw[1]) << 8));
  int16_t ry = static_cast<int16_t>(raw[2] | (static_cast<uint16_t>(raw[3]) << 8));
  int16_t rh = static_cast<int16_t>(raw[4] | (static_cast<uint16_t>(raw[5]) << 8));
  int16_t rvx = static_cast<int16_t>(raw[6] | (static_cast<uint16_t>(raw[7]) << 8));
  int16_t rvy = static_cast<int16_t>(raw[8] | (static_cast<uint16_t>(raw[9]) << 8));
  int16_t rvh = static_cast<int16_t>(raw[10] | (static_cast<uint16_t>(raw[11]) << 8));

  x_ = static_cast<float>(rx) * kPosMmPerLsb;
  y_ = static_cast<float>(ry) * kPosMmPerLsb;
  heading_ = static_cast<float>(rh) * kHdgRadPerLsb;
  vx_ = static_cast<float>(rvx) * kVelocityPerLsb;
  vy_ = static_cast<float>(rvy) * kVelocityPerLsb;
  omega_ = static_cast<float>(rvh) * kOmegaPerLsb;
  return true;
}

void OtosPort::zeroPose() {
  if (!initialized_) return;
  writePoseMm(kRegPositionXl, 0.0f, 0.0f, 0.0f);
}

void OtosPort::resetTracking() {
  if (!initialized_) return;
  writeReg8(kRegReset, 0x01);
}

void OtosPort::calibrateImu(uint8_t samples) {
  if (!initialized_) return;
  writeReg8(kRegImuCalibration, samples == 0 ? kImuCalibSamples : samples);
}

uint8_t OtosPort::imuCalibrationSamplesRemaining() {
  if (!initialized_) return 0;
  uint8_t v = 0;
  readReg8(kRegImuCalibration, &v);
  return v;
}

}  // namespace diffDrive
