// radio_transport.h -- RadioTransport: gets a formatted wire line onto
// the micro:bit radio, framed for the fleet's RADIOBRIDGE relay. This is
// a second thin CODAL-facing leaf beneath Protocol, playing the same
// role SerialTransport plays for uBit.serial (see serial_transport.h's
// own top comment): it knows uBit.radio and the RadioRelay on-air
// fragment framing, and NOTHING about pose, COBS, CRC, verb names, or
// command semantics.
//
// On-air framing provenance: this module's fragment format is a
// TX-only port of radio-robot-elite's Platform::MicroBitRadioLink
// (src/firm/platform/microbit/microbit_radio_link.{h,cpp}) -- the
// fleet's own robot-side radio driver, which the RADIOBRIDGE relay
// hardware is built against -- specifically its RadioRelay wire spec
// section 5: every on-air packet is a fragment
//     [SEQ:1][FLAGS:1][LEN:1][payload:LEN]
// carried as the raw CODAL datagram payload (no MakeCode/PXT radio
// package header). FLAGS: START=0x01, MORE=0x02, END=0x04 (the
// reference's ACK=0x10 is not declared here -- see below). A message
// longer than one fragment's payload capacity is split START..END; a
// single-fragment message is flagged START|END.
//
// TX-only, by sprint.md's own explicit scope (Design Rationale: "the
// reference's full bidirectional implementation... rejected as more
// code and complexity than this sprint's telemetry-only scope needs" --
// a sender never needs its own reassembly buffer or ISR listener to
// speak this framing correctly): no MICROBIT_RADIO_EVT_DATAGRAM
// listener is ever registered, no reassembly buffer exists, and the
// reference's FLAG_ACK (0x10) is never set or interpreted -- there is
// nothing here that could receive an ACK to begin with.
//
// Not copied wholesale from the reference: this file only implements
// the minimal send-side subset (begin/enable + fragment + transmit)
// the reference's much larger bidirectional class provides.
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
  // uses. Safe for binary content for the same reason protocol.h
  // documents for the serial transport: COBS here is keyed on 0x0A, so
  // a binary line's own bytes never contain a literal 0x0A. Truncates
  // -- rather than overflows -- a `len` beyond this module's internal
  // line-buffer capacity, mirroring SerialTransport's own defensive
  // truncation.
  //
  // Lazily enables and configures the radio (uBit.radio.enable(), fixed
  // group 10, channel 0, transmit power 7 -- matching the reference
  // driver's own begin()) on the FIRST call, never at construction and
  // never via a separate begin() step: uBit.radio.enable() has its own
  // RAM/softdevice cost (sprint.md), so a bench-only serial user who
  // never calls sendLine() never pays it.
  //
  // Re-entrancy guard (sprint 004 ticket 002): as of this sprint, TWO
  // fibers can call this -- the TS fiber via Protocol::emitLine(), and
  // the protocol fiber via RadioSink::write() (its own
  // emitTelemetry()/emitReliability() calls) -- and
  // uBit.radio.datagram.send() can block and yield, giving the two a
  // real chance to interleave mid-format into payloadBuf_/frameBuf_.
  // Returns false, WITHOUT TOUCHING payloadBuf_/frameBuf_ at all, if a
  // call is already in progress on the other fiber; true after a
  // normal completion. The dropped caller decides for itself whether
  // that matters: Protocol::emitLine() retries once after
  // fiber_sleep(2); RadioSink::write() ignores the return value and
  // accepts the drop silently (see sprint.md's Design Rationale for
  // why the two callers get different policies).
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
  // this build's CODAL target actually resolves it to (CODAL's own
  // default is 32 bytes -- sprint.md Open Question 1; this module does
  // not assume a raised value). Always emits at least one fragment,
  // even for a zero-length payload, so a degenerate empty line still
  // gets a valid START|END frame.
  void sendFragmented(const uint8_t* payload, size_t payloadLen);

  // RadioRelay wire spec section 5 fragment framing -- see this
  // header's top comment for the reference file this mirrors.
  static constexpr uint8_t kFlagStart = 0x01;
  static constexpr uint8_t kFlagMore = 0x02;
  static constexpr uint8_t kFlagEnd = 0x04;
  // FLAG_ACK (0x10) deliberately not declared -- TX-only, see top
  // comment: nothing in this module ever sets or interprets it.

  static constexpr int kFrameHeaderBytes = 3;  // [SEQ][FLAGS][LEN]

  // Fixed radio convention matching the fleet's RADIOBRIDGE relay
  // (sprint.md Design Rationale): group is the relay's own listen
  // group, channel is this build's single default frequency band (no
  // per-robot channel-selection surface this sprint -- Open Question
  // 2), transmit power matches the reference driver's own
  // setTransmitPower(7).
  static constexpr uint8_t kGroup = 10;
  // Channel 4: vevov's fleet-assigned radio channel (stakeholder,
  // 2026-08-19). The zavaz relay is configured to match (!CG 4 10).
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
