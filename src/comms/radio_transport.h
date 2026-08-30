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
// onDatagram()'s own doc for the current capacity limit and
// radioRxLineFits(), just below, for the accept/reject predicate
// itself); no ACK protocol either direction -- FLAG_ACK (0x10) is never
// set or interpreted.
#pragma once

#include <cstddef>
#include <cstdint>

namespace diffDrive {

// Pure accept/reject decision for an inbound RX fragment (sprint 010
// ticket 001, radio-rx-capacity-fragmentation.md): true iff a fragment
// whose payload declares `declaredLen` bytes (after
// RadioTransport::onDatagram() has already stripped the trailing 0x0A
// delimiter) fits WHOLE into a receive buffer of `bufferCapacity` bytes.
// False means REJECT the frame in its entirety -- the caller must drop
// it outright, exactly like an already-dropped MORE-flagged fragment,
// and must NEVER truncate it to a shorter, still-parseable prefix and
// deliver that prefix as if it were the complete line.
//
// Truncate-and-accept (the pre-fix behavior) was the actual hazard this
// function exists to close: WireHandler::feed() cannot tell a truncated
// line from a genuinely short one the host sent, so a truncated
// over-length command could silently decode and EXECUTE as a different,
// shorter, legal command. A dropped line is merely invisible; a
// truncated-and-accepted one is dangerous -- see
// radio-rx-capacity-fragmentation.md for the full defect writeup.
//
// No CODAL dependency (this header includes only <cstddef>/<cstdint>),
// so this function is host-testable directly by #include-ing this
// header -- no link against radio_transport.cpp, which requires pxt.h
// and cannot be host-compiled at all. See
// tests/host/test_radio_transport_rx_capacity.py.
inline bool radioRxLineFits(size_t declaredLen, size_t bufferCapacity) {
  return declaredLen <= bufferCapacity;
}

// Decodes a five-letter micro:bit board name into the radio channel/
// group pair it derives -- codebook and formulas live in this repo's
// radio-addressing spec (docs/radio-addressing, normative) and are
// ported here verbatim, not redesigned. `name` is
// normalized first (ASCII whitespace trimmed, `A`-`Z` mapped to
// `a`-`z`), then validated against
// `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` -- consonants (`zvgpt`) at
// positions 0/2/4, vowels (`uoiea`) at 1/3, each character's index in
// its position's alphabet is that position's base-5 digit. The digits
// are combined BIG-ENDIAN -- `name[0]` is the MOST significant digit,
// `name[4]` the least:
//
//     n = 0
//     for p in 0..4: n = n * 5 + indexInAlphabet(name[p])
//
// Getting this backwards is the documented trap: base-5 conversion
// naturally emits the least-significant digit first, and a reversed
// decoder still produces 3125 well-formed, regex-passing, distinct
// names -- just in the wrong order, with no error to see (the spec's
// own "Endianness, and why the obvious test misses it" section).
// `channel = 25 + 2*(n % 25)` (25..73, always odd,
// inclusive of 25) and `group = 1 + n/25`, incremented once more if
// that lands on 10 -- the gap microbit-radio-relay's `!C` button space
// reserves (same doc, "Why those five values are reserved").
//
// On any validation failure (null `name`, wrong length after
// trimming, a character outside the codebook) returns false and
// writes the LEGACY FALLBACK PAIR -- channel 4, group 10, the fixed
// values this file used before this function existed -- into
// *outChannel/*outGroup. Never an arbitrary or zero-initialized
// value: a caller that ignores the return value still brings the
// radio up on a sane, previously-shipped pair.
//
// Pure, header-only, no CODAL dependency (only <cstddef>/<cstdint>),
// no allocation, no heap -- same pattern radioRxLineFits() establishes
// just above, and host-testable the same way: #include this header
// directly, zero link against radio_transport.cpp (which requires
// pxt.h and cannot be host-compiled at all).
inline bool deriveRadioAddress(const char* name, uint8_t* outChannel,
                               uint8_t* outGroup) {
  *outChannel = 4;
  *outGroup = 10;
  if (name == nullptr) return false;

  auto isAsciiSpace = [](char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' ||
           c == '\f';
  };
  auto toLower = [](char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c + 32) : c;
  };

  size_t i = 0;
  while (name[i] != '\0' && isAsciiSpace(name[i])) ++i;

  char norm[5];
  size_t len = 0;
  while (name[i] != '\0' && !isAsciiSpace(name[i])) {
    if (len < 5) norm[len] = toLower(name[i]);
    ++len;
    ++i;
  }
  if (len != 5) return false;  // too short or too long after trimming

  while (name[i] != '\0' && isAsciiSpace(name[i])) ++i;
  if (name[i] != '\0') return false;  // trailing non-whitespace: reject

  static constexpr char kConsonants[5] = {'z', 'v', 'g', 'p', 't'};
  static constexpr char kVowels[5] = {'u', 'o', 'i', 'e', 'a'};

  int n = 0;
  for (int p = 0; p < 5; ++p) {
    const char* alphabet = (p % 2 == 0) ? kConsonants : kVowels;
    int idx = -1;
    for (int a = 0; a < 5; ++a) {
      if (alphabet[a] == norm[p]) {
        idx = a;
        break;
      }
    }
    if (idx < 0) return false;  // character outside the codebook
    n = n * 5 + idx;             // big-endian: name[0] is most significant
  }

  const int channel = 25 + 2 * (n % 25);
  int group = 1 + (n / 25);
  if (group >= 10) group += 1;  // skip the gap: !C's button-space group

  *outChannel = static_cast<uint8_t>(channel);
  *outGroup = static_cast<uint8_t>(group);
  return true;
}

// Chooses the radio group ensureRadioReady() actually brings the
// radio up on: `storedGroup` if a prior explicit setGroup() call
// happened (`groupOverridden` true -- e.g. the student-facing
// `on start` block ran before radio bring-up), otherwise
// `derivedGroup` (deriveRadioAddress()'s output). An explicit override
// always wins over the derived default -- this is the mechanism that
// keeps the student-facing "set radio group" block working unchanged.
// Pure/header-only so this selection contract -- not just the
// derivation above -- is host-testable, even though RadioTransport
// itself is not (see this header's top comment).
inline uint8_t selectRadioGroup(bool groupOverridden, uint8_t storedGroup,
                                uint8_t derivedGroup) {
  return groupOverridden ? storedGroup : derivedGroup;
}

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
  // Lazily enables and configures the radio (uBit.radio.enable(),
  // group/channel/power -- see group_/deriveRadioAddress()/
  // kTransmitPower above/below; group is student-settable via
  // setGroup(), channel is derived from the board's own name and power
  // is fixed -- matching the reference driver's own begin()) on the
  // FIRST call, never at construction and never via a separate begin()
  // step:
  // uBit.radio.enable() has its own RAM/softdevice cost, so a
  // bench-only serial user who never calls sendLine() never pays it.
  //
  // Re-entrancy guard: TWO fibers can call this -- the TS fiber via
  // Protocol::emitLine(), and the protocol fiber via RadioSink::write()
  // (replies and emitTelemetry()'s frames) -- and
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

  // Set the radio group this robot listens/transmits on -- the ONE
  // write path the blocks layer gains into this class's configuration;
  // transmit power stays a fixed constexpr value, below, and channel
  // is derived (see deriveRadioAddress(), above) rather than settable
  // at all. Always stores `group` into group_ unconditionally, and
  // also sets groupOverridden_ = true -- an explicit setGroup() call,
  // from any caller, permanently opts this board OUT of the
  // derived-group default for the rest of its run.
  //
  // Supported path: called from `on start`, before the radio has come
  // up (radioReady_ == false). Nothing else happens here in that case --
  // ensureRadioReady() reads group_ (via selectRadioGroup(), above,
  // now that groupOverridden_ is true) the first time it actually
  // runs, and brings the radio up already on the requested group. This
  // is the student-facing path the block targets.
  //
  // If the radio has ALREADY come up (radioReady_ == true, e.g. a prior
  // sendLine()/tryReceiveLine() already lazily called
  // ensureRadioReady()), this re-applies the group immediately via
  // uBit.radio.setGroup(group_) so the call does not silently no-op.
  // Whether that re-apply actually changes what the already-armed radio
  // receives on is UNVERIFIED on this hardware -- no test of this path
  // has been run. As a source observation only (not a measurement): the
  // vendored MicroBitRadio.cpp's setFrequencyBand() performs an explicit
  // TASKS_DISABLE/TASKS_RXEN restart with the comment "We need to
  // restart the radio for the frequency change to take effect", while
  // its setGroup() only writes NRF_RADIO->PREFIX0 and returns, with no
  // such restart. What that difference means for reception on
  // already-armed hardware has not been observed either way.
  void setGroup(uint8_t group);

  // Event-driven RX internals (public only for the static MessageBus
  // trampoline): mirrors the reference driver's design -- datagram.recv()
  // is ONLY called inside the MICROBIT_RADIO_EVT_DATAGRAM handler, where
  // the queue is guaranteed non-empty. Bench-measured: polling recv() on
  // an EMPTY queue kills the program within two polls (codal's shared
  // EmptyPacket refcounting), which is exactly why the reference never
  // polls. The handler copies a complete single-fragment line into
  // rxLine_ and sets rxReady_; tryReceiveLine() just consumes the flag.
  // A single-fragment datagram whose declared LEN (after stripping the
  // trailing 0x0A) exceeds rxLine_'s capacity is REJECTED whole --
  // rxOversizeDropped_ counts it, rxReady_ is left untouched, and no
  // prefix is copied -- see radioRxLineFits()'s own doc comment, above,
  // for why this must never truncate-and-accept instead.
  void onDatagram();

  // Truncation bound for sendLine()'s `len` parameter, and this
  // module's real radio-capacity ceiling. PUBLIC as of sprint 008
  // ticket 002 (WIRE-05/R-21) -- was private, moved here (not simply
  // relabeled in place) so no other private member below picks up
  // public access as a side effect. Made public so protocol.cpp's
  // Protocol::emitLine() can clip to this SAME constant by name instead
  // of re-declaring its own bare literal, which had silently drifted
  // out of sync with what this constant actually means: once sprint
  // 004 ticket 005 raised SerialTransport::kMaxLineBytes to 240, this
  // constant -- and radio's real capacity -- stayed at its old, smaller
  // value, and emitLine()'s own separate literal was numerically right
  // but disconnected from that fact, which is what let it read as
  // merely stale rather than load-bearing.
  //
  // RAISED to 240 by sprint 010 ticket 002
  // (radio-rx-capacity-fragmentation.md): this constant now EQUALS
  // SerialTransport::kMaxLineBytes (serial_transport.h) and
  // Wire::WireHandler::kMaxLineBytes (wire_handler.h) -- and this
  // class's own private RX-capacity constant just below (kMaxLineBytes,
  // sprint 010 ticket 001) -- all four are the SAME number, 240. Sprint
  // 008's version of this comment described the relationship as
  // deliberately the smaller of the two transports' bounds, not equal
  // to SerialTransport's own; that was true at the old value and is no
  // longer true now. tests/host/test_wire_constants_drift.py pins this
  // four-way equality by reading all the relevant headers as text, so a
  // future edit to any one of the four numbers fails a test instead of
  // silently reintroducing an inequality. The widened value still fits
  // one physical radio fragment: the MTU (kMtu = MICROBIT_RADIO_MAX_
  // PACKET_SIZE(250, pxt.json) - kFrameHeaderBytes(3) = 247, see
  // sendFragmented() in radio_transport.cpp) has 6 bytes of margin above
  // the 241-byte payload+delimiter this constant now allows, so
  // sendFragmented()'s multi-fragment loop still runs its
  // single-iteration path for every real payload. No encapsulation
  // cost: it stays a compile-time constant, still used in-class below
  // to size payloadBuf_ -- the class still owns every byte of storage
  // it sizes.
  static constexpr size_t kMaxPayloadBytes = 240;

 private:
  // Brings the radio up on ITS OWN derived channel/group -- see
  // deriveRadioAddress()/selectRadioGroup(), above, and this method's
  // definition (radio_transport.cpp) for the exact call order, which
  // is load-bearing (that file's own comment on the enable/band/group/
  // power sequence explains why).
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

  // Fixed transmit power: 7 (matches the reference driver's own
  // setTransmitPower(7)). No settable surface, student-facing or
  // per-robot. Channel is NOT a fixed constant here any more -- the
  // old hand-maintained `static constexpr int kChannel = 4` (deploy-
  // time text-substituted by tools/make_deploy.py, now retired) is
  // gone. ensureRadioReady() (radio_transport.cpp) now derives the
  // channel it brings the radio up on -- along with group_'s default,
  // immediately below -- from the board's own microbit_friendly_name()
  // via deriveRadioAddress(), above (this repo's radio-addressing
  // spec, normative). There is still no student-facing surface to
  // override the channel, and none is planned.
  static constexpr int kTransmitPower = 7;

  // Radio group this robot listens/transmits on -- MUTABLE, unlike
  // kTransmitPower just above. No longer defaults to a hardcoded 10:
  // this field only matters once groupOverridden_ (below) is true --
  // i.e. setGroup() has been called at least once, explicitly. Until
  // then, ensureRadioReady() ignores this stored value entirely in
  // favor of the group deriveRadioAddress() computes from the board's
  // own name; see
  // selectRadioGroup(), above, for the exact selection logic and
  // setGroup()'s own doc comment for the override contract. 0 here is
  // simply "not yet meaningful", not a radio group any board actually
  // runs on (0 is one of the five reserved values -- MakeCode's own
  // unconfigured-radio default -- deriveRadioAddress() never emits it,
  // and neither does a real setGroup() call from student code, which
  // always passes a group the block picked).
  uint8_t group_ = 0;

  // True once setGroup() has been called at least once (an explicit
  // override, e.g. from the `on start` block); false for a board that
  // was never told a group -- the common case, and the one that gets
  // the derived default. Set to true only inside setGroup()
  // (radio_transport.cpp); never reset once true, since an override is
  // permanent for the life of the running program.
  bool groupOverridden_ = false;

  // kMaxPayloadBytes itself is declared PUBLIC, above (sprint 008
  // ticket 002) -- moved out of this section rather than merely
  // relabeled in place, so nothing below silently became public with
  // it. payloadBuf_'s bound below resolves against that earlier, public
  // declaration; C++ does not require a data member's array bound to be
  // declared textually adjacent to it, only earlier in the class.

  // Send-path scratch buffers, deliberately MEMBERS not stack locals:
  // the protocol fiber's 2 KB stack cannot afford ~450 B of line+frame
  // buffers at the bottom of the deepest call chain (bench-measured:
  // run()+the (since-retired) DIAG-surface formatter+sendLine+
  // sendFragmented overflowed the fiber stack and hard-faulted ~1 s
  // after boot). No longer single-fiber
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

  // RX line-buffer capacity, in bytes: the wire grammar's own 240-byte
  // line ceiling (Wire::WireHandler::kMaxLineBytes, wire_handler.h),
  // duplicated here as radio_transport.h's OWN independent constant
  // rather than included by name -- src/DESIGN.md §1's layering table
  // places Transports below the Wire grammar, so this header must not
  // #include "wire_handler.h" (the same layering reason
  // SerialTransport::kMaxLineBytes, serial_transport.h, already exists
  // as ITS OWN independent 240 rather than including wire_handler.h
  // either). MUST stay == both of those (see ticket 002's drift test).
  // Sized off the wire grammar's line cap, NOT off the physical
  // single-fragment MTU (~247 B: MICROBIT_RADIO_MAX_PACKET_SIZE (250,
  // pxt.json) - kFrameHeaderBytes (3), see sendFragmented()'s kMtu in
  // radio_transport.cpp) -- the MTU is comfortably larger, so this
  // buffer's job is to carry one whole v6 line, not to reach radio's
  // own physical ceiling. Was a bare `64` with no name of its own
  // before sprint 010 ticket 001 (radio-rx-capacity-fragmentation.md);
  // naming it lets radioRxLineFits() (above) and this ticket's own host
  // test pin the real capacity by value instead of by an anonymous
  // array bound.
  static constexpr size_t kMaxLineBytes = 240;
  uint8_t rxLine_[kMaxLineBytes];

 public:
  // RX diagnostics (bench): datagrams polled with nonzero length, and
  // frames accepted as complete single-fragment lines. Bench-only
  // counters; the cleartext DIAG verb that used to read them
  // (Protocol::formatDiag()) was retired, and nothing in the current
  // tree consumes these.
  uint32_t rxFrames_ = 0;
  uint32_t rxAccepted_ = 0;
  // Count of single-fragment datagrams REJECTED because their declared
  // LEN exceeded rxLine_'s capacity (sprint 010 ticket 001,
  // radio-rx-capacity-fragmentation.md) -- dropped whole, never
  // truncated-and-accepted; see radioRxLineFits()'s own doc comment for
  // why. Same bench-diagnostics convention as rxFrames_/rxAccepted_
  // above.
  uint32_t rxOversizeDropped_ = 0;

 private:
  uint8_t txSeq_ = 0;  // rolling RadioRelay §5 sequence number
};

}  // namespace diffDrive
