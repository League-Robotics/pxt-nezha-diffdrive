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

bool SerialTransport::tryReadLine(uint8_t* outBuf, size_t outCap,
                                  size_t* outLen) {
  // ASYNC: never blocks -- returns a buffered byte immediately, or
  // DEVICE_NO_DATA (a negative value) once the rx buffer is drained. The
  // isReadable() guard is belt-and-suspenders (uBit.serial.read(ASYNC)
  // already returns immediately either way); it just avoids a call that
  // would only ever return "no data" once the buffer is empty.
  while (uBit.serial.isReadable()) {
    const int c = uBit.serial.read(ASYNC);
    if (c < 0) break;  // drained (or a transient read error) -- stop here
    if (static_cast<uint8_t>(c) == kLineDelimiter) {
      const size_t len = partialLen_ < outCap ? partialLen_ : outCap;
      if (outBuf != nullptr && len > 0) {
        for (size_t i = 0; i < len; ++i) outBuf[i] = partial_[i];
      }
      *outLen = len;
      partialLen_ = 0;
      return true;
    }
    if (partialLen_ < sizeof(partial_)) {
      partial_[partialLen_++] = static_cast<uint8_t>(c);
    }
    // else: past kMaxLineBytes -- keep consuming so the stream stays
    // framed (mirrors readLine()'s own truncate-not-overrun behavior),
    // just stop copying into partial_.
  }
  return false;  // no complete line yet -- partial_ retained for next call
}

}  // namespace diffDrive
