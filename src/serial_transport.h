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

// Shared buffer size for one wire line's content, excluding the trailing
// 0x0A this module owns and strips/appends. Sprint 003 ticket 005
// (the hardware transport-seam cutover) raised this from 200 to 240 to
// match Wire::WireHandler::kMaxLineBytes (wire_handler.h) exactly --
// protocol.md's own "max line: 240 bytes including the terminator" is
// WireHandler's ceiling, but a legal 201-239-byte v6 line (a verbose
// RUN with several arguments, say) would have been silently truncated
// by THIS buffer before WireHandler ever saw it, one layer below the
// tested "discard the whole overlong line, never truncate into a
// still-parseable prefix" guarantee WireHandler itself implements. Not
// a hard protocol limit of this module's own; just kept equal to the
// one layer above it so this transport is never the tighter cap.
constexpr size_t kMaxLineBytes = 240;

// RX/TX serial ring capacity used by begin() (sprint 004 ticket 006,
// code review R-19/WIRE-03). v5 sized these at a flat 128 B, tuned for
// a ~27-byte binary WHEELS frame -- that sizing driver is gone under
// v6, where a single line can legally be kMaxLineBytes (240 B). The
// protocol fiber only drains the ring once per ~24 ms motion-tick
// window (shims.cpp's self-pacing tick), so a near-max-length line plus
// anything else arriving in the same window (a keepalive ack, a
// reliability-layer resend) can exceed one line's worth of bytes before
// the next drain -- 128 B overflows on exactly that pattern, silently
// (codal's ring drops the overflow with no signal). Sized to 2x
// kMaxLineBytes so the ring can absorb a max-length line AND a second,
// smaller one in the same window.
constexpr size_t kRingBytes = 2 * kMaxLineBytes;

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
  // One-time setup: grows codal's default ~20-byte serial rings to
  // kRingBytes (ticket 006; previously a flat 128 B tuned for v5's
  // binary frames -- see kRingBytes' own comment) so a full line
  // arriving as one burst, or two lines arriving in the same
  // motion-tick window, can't overflow them between protocol-fiber
  // polls. Call before the first read.
  void begin();


  // Writes `len` bytes from `buf`, then a single 0x0A delimiter.
  // Callers (Protocol) never include the delimiter themselves.
  //
  // Two-writer guard (sprint 004 ticket 006, code review R-19/R-20 aka
  // WIRE-03/WIRE-04): two fibers call this today -- the TS fiber via
  // Protocol::emitLine(), and the protocol fiber via the serial
  // WireHandler's own replies/keepalives (Protocol::SerialSink::write())
  // -- and this predates ticket 006 itself; the review is what caught
  // it, unfixed, already present. Each call issues two back-to-back
  // uBit.serial.send(..., SYNC_SLEEP) calls that block and yield the
  // caller, exactly the window the other caller could interleave bytes
  // into. Unlike RadioTransport::sendLine()'s guard (ticket 002), where
  // a second caller drops immediately and only Protocol::emitLine()
  // retries once, BOTH callers here get a bounded retry: a caller that
  // finds the guard already held sleeps 2 ms and checks again, up to a
  // small fixed attempt cap, because serial has no caller whose loss is
  // "fine" the way telemetry's self-healing seq gap makes radio's drop
  // acceptable (see sprint.md's Design Rationale). If the retry cap is
  // exhausted, or either uBit.serial.send() call itself reports a
  // failure, the attempt is counted in a drop counter (read via
  // diagValue(26)/probe(26), shims.cpp) and this function returns
  // having given up silently -- callers do not check a return value or
  // retry themselves; the bounded retry and the drop accounting are
  // both fully internal to this call, unlike RadioTransport's
  // caller-driven retry-once.
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

  // Count of writeLine() calls dropped since boot (ticket 006): either
  // the two-writer guard's retry cap was exhausted before this call got
  // a turn, or one of writeLine()'s own uBit.serial.send() calls itself
  // reported a failure. Exposed to the wire protocol's numeric DIAG
  // surface via diagValue(26) (shims.cpp) / probe(26) (bench) -- a
  // bench operator watches this stay at 0 during a normal run the same
  // way the existing counters (i2cFaultCount, cycleOverrunCount, etc.)
  // are already read.
  uint32_t dropCount() const { return dropCount_; }

 private:
  // Internal accumulation capacity is fixed at kMaxLineBytes regardless of
  // a given call's `outCap` -- outCap only bounds the final copy-out, the
  // same truncation split readLine() already has between "keep consuming
  // to stay framed" and "stop copying". The sole caller (Protocol::run())
  // always sizes outCap == kMaxLineBytes, so this never differs from
  // outCap-exact truncation in practice.
  uint8_t partial_[kMaxLineBytes] = {0};
  size_t partialLen_ = 0;

  // Two-writer guard for writeLine() (ticket 006): true from the moment
  // a caller enters the guarded body until it returns. A second caller
  // arriving while this is already true does NOT drop immediately the
  // way RadioTransport::sending_ does -- it sleeps and retries, bounded
  // (see writeLine()'s own doc comment and serial_transport.cpp's
  // kMaxSendAttempts). Only the caller that actually set this clears
  // it, on its own way out.
  bool sending_ = false;

  // Backing counter for dropCount() above.
  uint32_t dropCount_ = 0;
};

}  // namespace diffDrive
