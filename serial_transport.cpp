// serial_transport.cpp -- see serial_transport.h. Talks to uBit.serial
// directly (the microbit's default USB-CDC serial link), the same way
// nezha_port.cpp talks to uBit.i2c directly: one small CODAL-facing
// leaf, no shaping/porting layers of its own.
#include "serial_transport.h"

#include "pxt.h"

using namespace pxt;

namespace diffDrive {

namespace {
constexpr uint8_t kLineDelimiter = 0x0A;
}  // namespace

size_t SerialTransport::readLine(uint8_t* outBuf, size_t outCap) {
  size_t len = 0;
  while (true) {
    // SYNC_SLEEP: blocks this fiber until a byte is available, cheaply
    // yielding to the scheduler rather than spinning -- the caller
    // (Protocol::run(), its own fiber) is fine to block here for as
    // long as no host is talking; this is exactly the natural back-off
    // between checks.
    const int c = uBit.serial.read(SYNC_SLEEP);
    if (c < 0) continue;  // transient read error -- keep waiting
    if (static_cast<uint8_t>(c) == kLineDelimiter) break;
    if (len < outCap) {
      outBuf[len++] = static_cast<uint8_t>(c);
    }
    // else: past outCap -- keep consuming bytes up to the next 0x0A so
    // the stream stays framed, but stop copying (truncate).
  }
  return len;
}

void SerialTransport::writeLine(const uint8_t* buf, size_t len) {
  if (len > 0) {
    uBit.serial.send(const_cast<uint8_t*>(buf), static_cast<int>(len),
                     SYNC_SLEEP);
  }
  uint8_t delimiter = kLineDelimiter;
  uBit.serial.send(&delimiter, 1, SYNC_SLEEP);
}

}  // namespace diffDrive
