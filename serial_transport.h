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
  // buffer. Kept as a general blocking-read primitive on this class's
  // public contract; Protocol::run() itself uses tryReadLine() below
  // instead (ticket 005), since it must never block indefinitely without
  // starving telemetry's own cadence.
  size_t readLine(uint8_t* outBuf, size_t outCap);

  // Writes `len` bytes from `buf`, then a single 0x0A delimiter.
  // Callers (Protocol) never include the delimiter themselves.
  void writeLine(const uint8_t* buf, size_t len);

  // Non-blocking counterpart to readLine() (ticket 005: lets a caller
  // interleave cadence-driven work -- telemetry -- with command reads on
  // one fiber, instead of readLine()'s indefinite SYNC_SLEEP block). Never
  // sleeps: drains only whatever bytes uBit.serial already has buffered
  // (ASYNC reads), accumulating them across calls in a small internal
  // partial-line buffer.
  //
  // Returns true iff that drain completed one full line (a 0x0A delimiter
  // was seen this call or an earlier one): `outBuf`/`*outLen` are filled
  // exactly like readLine() would (same outCap-truncation behavior --
  // bytes beyond outCap are dropped, not overrun). Returns false --
  // `*outLen` left untouched -- whenever no delimiter has arrived yet,
  // including when nothing at all was available; any bytes read this call
  // are retained internally as a head start on the next call.
  bool tryReadLine(uint8_t* outBuf, size_t outCap, size_t* outLen);

 private:
  // Internal accumulation capacity is fixed at kMaxLineBytes regardless of
  // a given call's `outCap` -- outCap only bounds the final copy-out, the
  // same truncation split readLine() already has between "keep consuming
  // to stay framed" and "stop copying". The sole caller (Protocol::run())
  // always sizes outCap == kMaxLineBytes, so this never differs from
  // outCap-exact truncation in practice.
  uint8_t partial_[kMaxLineBytes] = {0};
  size_t partialLen_ = 0;
};

}  // namespace diffDrive
