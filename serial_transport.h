// serial_transport.h -- SerialTransport: owns the raw USB-serial byte
// stream and 0x0A line delimiting for the Protocol v5 wire link. This
// is the "thin CODAL-facing port" layer (mirrors how nezha_port.{h,cpp}
// is the thin I2C-facing port beneath the DiffDrive kernel): it knows
// uBit.serial and the 0x0A byte, and NOTHING about COBS, CRC, verb
// names, or command semantics -- see protocol.h for that layer.
//
// Byte buffers, not ManagedString: a binary verb's line content may
// legally contain an embedded 0x00 byte (COBS here is keyed on 0x0A,
// not 0x00 -- see protocol.h), so this module and everything layered
// on it carry explicit (buffer, length) pairs end to end rather than
// NUL-terminated strings.
#pragma once

#include <cstddef>
#include <cstdint>

namespace diffDrive {

// Suggested shared buffer size for one wire line's content, excluding
// the trailing 0x0A this module owns and strips/appends. Sized with
// headroom over this project's own (deliberately small, locally-defined
// -- see sprint.md Design Rationale) binary payloads; not a hard
// protocol limit, just what callers should size their line buffers to.
constexpr size_t kMaxLineBytes = 200;

class SerialTransport {
 public:
  // Blocks the calling fiber -- cooperatively (SYNC_SLEEP: the fiber
  // sleeps and yields to the scheduler, it never spins) -- until a
  // complete line has arrived on uBit.serial, then copies its content
  // (the bytes strictly between the previous delimiter and this one,
  // NOT including the 0x0A itself) into `outBuf` and returns the
  // length copied. A line longer than `outCap` is truncated to
  // `outCap` bytes -- the remainder up to and including the next 0x0A
  // is read and discarded -- rather than overrunning the caller's
  // buffer.
  size_t readLine(uint8_t* outBuf, size_t outCap);

  // Writes `len` bytes from `buf`, then a single 0x0A delimiter.
  // Callers (Protocol) never include the delimiter themselves.
  void writeLine(const uint8_t* buf, size_t len);
};

}  // namespace diffDrive
