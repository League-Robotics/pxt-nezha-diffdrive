// radio_transport.h -- RadioTransport: gets a formatted wire line onto
// the micro:bit radio, framed for the fleet's RADIOBRIDGE relay. Thin
// CODAL-facing leaf beneath Protocol (mirrors SerialTransport's role
// for uBit.serial -- see serial_transport.h's top comment): knows
// uBit.radio and the RadioRelay on-air fragment framing, nothing about
// pose, verb names, or command semantics.
//
// On-air framing is a port of radio-robot's
// Platform::MicroBitRadioLink (RadioRelay wire spec section 5 -- the
// fleet's own radio driver the RADIOBRIDGE relay hardware is built
// against; src/DESIGN.md §2 has the authoritative upstream repo/path
// statement): every packet is a fragment
//     [SEQ:1][FLAGS:1][LEN:1][payload:LEN]
// carried as the raw CODAL datagram payload (no MakeCode/PXT radio
// package header). FLAGS: START=0x01, MORE=0x02, END=0x04. A message
// longer than one fragment's payload capacity is split START..END; a
// single-fragment message is flagged START|END.
//
// TX (sendLine(), below) and RX (tryReceiveLine()/onDatagram(), below)
// both use this framing. RX accepts only single-fragment messages (see
// tryReceiveLine()'s own doc for the current capacity limit); no ACK
// protocol either direction -- FLAG_ACK (0x10) is never set or
// interpreted.
#pragma once

#include <cstddef>
#include <cstdint>

namespace diffDrive {

class RadioTransport {
 public:
  // Fragments `data` (len bytes) into RadioRelay-framed radio packets
  // and transmits each one via uBit.radio.datagram.send(), appending a
  // trailing 0x0A ('\n') as the final payload byte -- the same
  // one-terminator-per-line convention SerialTransport::writeLine()
  // uses. Truncates -- rather than overflows -- a `len` beyond this
  // module's internal line-buffer capacity, mirroring SerialTransport's
  // own defensive truncation.
  //
  // Lazily enables and configures the radio (uBit.radio.enable(), fixed
  // group/channel/power -- see kGroup/kChannel/kTransmitPower below --
  // matching the reference driver's own begin()) on the FIRST call,
  // never at construction and never via a separate begin() step:
  // uBit.radio.enable() has its own RAM/softdevice cost, so a
  // bench-only serial user who never calls sendLine() never pays it.
  //
  // Re-entrancy guard: TWO fibers can call this -- the TS fiber via
  // Protocol::emitLine(), and the protocol fiber via RadioSink::write()
  // (its own emitTelemetry()/emitReliability() calls) -- and
  // uBit.radio.datagram.send() can block and yield, giving the two a
  // real chance to interleave mid-format into payloadBuf_/frameBuf_.
  // Returns false, WITHOUT TOUCHING payloadBuf_/frameBuf_ at all, if a
  // call is already in progress on the other fiber; true after a
  // normal completion. The dropped caller decides for itself whether
  // that matters: Protocol::emitLine() retries once after
  // fiber_sleep(2); RadioSink::write() ignores the return value and
  // accepts the drop silently -- deliberately different from
  // SerialTransport::writeLine()'s own guard, which retries internally
  // instead of dropping (see that method's own doc comment).
  bool sendLine(const uint8_t* data, size_t len);

  // RX (radio command plane, single-fragment only): polls one queued
  // datagram, accepts frames whose flags carry START|END together (a
  // complete message in one fragment -- with the 250-byte fleet packet
  // size every relay-forwarded command line qualifies), strips the
  // trailing 0x0A, and copies the line into outBuf. Returns true when a
  // line was produced. MORE-flagged fragments are dropped (multi-
  // fragment inbound reassembly is deliberately out of scope; see
  // clasi/issues/radio-rx-command-plane-run-over-bridge.md).
  bool tryReceiveLine(uint8_t* outBuf, size_t outCap, size_t* outLen);

  // Event-driven RX internals (public only for the static MessageBus
  // trampoline): mirrors the reference driver's design -- datagram.recv()
  // is ONLY called inside the MICROBIT_RADIO_EVT_DATAGRAM handler, where
  // the queue is guaranteed non-empty. Bench-measured: polling recv() on
  // an EMPTY queue kills the program within two polls (codal's shared
  // EmptyPacket refcounting), which is exactly why the reference never
  // polls. The handler copies a complete single-fragment line into
  // rxLine_ and sets rxReady_; tryReceiveLine() just consumes the flag.
  void onDatagram();

  // Truncation bound for sendLine()'s `len` parameter, and this
  // module's real radio-capacity ceiling. PUBLIC as of sprint 008
  // ticket 002 (WIRE-05/R-21) -- was private, moved here (not simply
  // relabeled in place) so no other private member below picks up
  // public access as a side effect. Made public so protocol.cpp's
  // Protocol::emitLine() can clip to this SAME constant by name instead
  // of re-declaring its own bare 200 literal, which had silently
  // drifted out of sync with what this constant actually means: once
  // sprint 004 ticket 005 raised SerialTransport::kMaxLineBytes to 240,
  // this constant -- and radio's real capacity -- stayed 200, and
  // emitLine()'s own separate 200 literal was numerically right but
  // disconnected from that fact, which is what let it read as merely
  // stale rather than load-bearing. Deliberately the TIGHTER of the two
  // transports' caps, not "equal" to SerialTransport's own bound (this
  // header used to claim equality -- corrected here): chosen so a line
  // emitLine() clips never depends on which transport happens to carry
  // it. The *value* is unchanged by this ticket --
  // still 200, still radio's real capacity ceiling -- this only
  // single-sources the NAME; raising radio's actual capacity is sprint
  // 010's scope (clasi/issues/radio-rx-capacity-fragmentation.md). No
  // encapsulation cost: it stays a compile-time constant, still used
  // in-class below to size payloadBuf_ -- the class still owns every
  // byte of storage it sizes.
  static constexpr size_t kMaxPayloadBytes = 200;

 private:
  void ensureRadioReady();

  // Fragments `payload[0..payloadLen)` -- which already carries its own
  // trailing '\n' as the last byte, appended by sendLine() -- into
  // on-air frames of up to one packet's payload capacity each. That
  // capacity is derived from MICROBIT_RADIO_MAX_PACKET_SIZE, whatever
  // this build's CODAL target actually resolves it to (this module
  // never hardcodes a value). Always emits at least one fragment, even
  // for a zero-length payload, so a degenerate empty line still gets a
  // valid START|END frame.
  void sendFragmented(const uint8_t* payload, size_t payloadLen);

  // RadioRelay wire spec section 5 fragment framing -- see this
  // header's top comment for the reference file this mirrors.
  static constexpr uint8_t kFlagStart = 0x01;
  static constexpr uint8_t kFlagMore = 0x02;
  static constexpr uint8_t kFlagEnd = 0x04;
  // FLAG_ACK (0x10) deliberately not declared -- TX-only, see top
  // comment: nothing in this module ever sets or interprets it.

  static constexpr int kFrameHeaderBytes = 3;  // [SEQ][FLAGS][LEN]

  // Fixed radio convention matching the fleet's RADIOBRIDGE relay:
  // group 10 (the relay's own listen group); channel 4 (vevov's
  // fleet-assigned channel; the zavaz relay matches: !CG 4 10);
  // transmit power 7 (matches the reference driver's own
  // setTransmitPower(7)). No per-robot channel-selection surface yet.
  static constexpr uint8_t kGroup = 10;
  static constexpr int kChannel = 4;
  static constexpr int kTransmitPower = 7;

  // kMaxPayloadBytes itself is declared PUBLIC, above (sprint 008
  // ticket 002) -- moved out of this section rather than merely
  // relabeled in place, so nothing below silently became public with
  // it. payloadBuf_'s bound below resolves against that earlier, public
  // declaration; C++ does not require a data member's array bound to be
  // declared textually adjacent to it, only earlier in the class.

  // Send-path scratch buffers, deliberately MEMBERS not stack locals:
  // the protocol fiber's 2 KB stack cannot afford ~450 B of line+frame
  // buffers at the bottom of the deepest call chain (bench-measured:
  // run()+formatDiag+sendLine+sendFragmented overflowed the fiber
  // stack and hard-faulted ~1 s after boot). No longer single-fiber
  // use only as of sprint 004 ticket 002: two fibers now call
  // sendLine() (see its header comment), and sending_ below is what
  // keeps only one of them touching these buffers at a time.
  uint8_t payloadBuf_[kMaxPayloadBytes + 1];
  uint8_t frameBuf_[256];

  bool radioReady_ = false;
  // Re-entrancy guard for sendLine()'s payloadBuf_/frameBuf_-touching
  // body (sprint 004 ticket 002): true from the moment a caller enters
  // that body until it returns. A second caller arriving while this is
  // already true returns false immediately, touching neither buffer;
  // only the caller that actually set this clears it, on its own way
  // out -- the dropped caller never touches it.
  bool sending_ = false;
  volatile bool rxReady_ = false;
  size_t rxLen_ = 0;
  uint8_t rxLine_[64];

 public:
  // RX diagnostics (bench): datagrams polled with nonzero length, and
  // frames accepted as complete single-fragment lines. Read by
  // Protocol::formatDiag() for the DIAG surface.
  uint32_t rxFrames_ = 0;
  uint32_t rxAccepted_ = 0;

 private:
  uint8_t txSeq_ = 0;  // rolling RadioRelay §5 sequence number
};

}  // namespace diffDrive
