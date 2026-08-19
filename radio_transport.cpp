// radio_transport.cpp -- see radio_transport.h. Talks to uBit.radio
// directly, the same way serial_transport.cpp talks to uBit.serial and
// nezha_port.cpp talks to uBit.i2c: one small CODAL-facing leaf, no
// shaping/porting layers of its own.
//
// sendFragmented() below is a provenance-documented, TX-only port of
// radio-robot-elite's Platform::MicroBitRadioLink::sendFragmented()
// (src/firm/platform/microbit/microbit_radio_link.cpp) -- the fleet's
// own reference driver the RADIOBRIDGE relay hardware is built
// against. Trimmed to exactly what a sender needs: no reassembly
// buffer, no RX ISR registration, no ACK interpretation -- see
// radio_transport.h's top comment for the full citation and rationale.
#include "radio_transport.h"

#include <cstring>

#include "pxt.h"

using namespace pxt;

namespace diffDrive {

namespace {
constexpr uint8_t kLineDelimiter = 0x0A;
}  // namespace

void RadioTransport::ensureRadioReady() {
  if (radioReady_) return;
  radioReady_ = true;
  // Call order mirrors the reference driver's own begin()
  // (microbit_radio_link.cpp): enable, then frequency band, then
  // group, then transmit power. CODAL does not default to band 0 --
  // it must be set explicitly, or a robot and the relay could sit on
  // different frequencies and never hear each other.
  uBit.radio.enable();
  uBit.radio.setFrequencyBand(kChannel);
  uBit.radio.setGroup(kGroup);
  uBit.radio.setTransmitPower(kTransmitPower);
}

void RadioTransport::sendFragmented(const uint8_t* payload,
                                    size_t payloadLen) {
  // MICROBIT_RADIO_MAX_PACKET_SIZE is whatever this build's CODAL
  // target actually compiles with -- see this file's header comment
  // and sprint.md Open Question 1. Computed locally (not as a
  // class-level constant) so this translation unit has no static
  // initialization-order dependency on the macro.
  constexpr int kMaxFrame = MICROBIT_RADIO_MAX_PACKET_SIZE;
  constexpr int kMtu = kMaxFrame - kFrameHeaderBytes;
  static_assert(kMtu > 0,
               "MICROBIT_RADIO_MAX_PACKET_SIZE too small to hold the "
               "[SEQ][FLAGS][LEN] fragment header plus any payload");

  size_t off = 0;
  bool first = true;
  uint8_t frame[kFrameHeaderBytes + kMtu];

  do {
    size_t chunk = payloadLen - off;
    if (chunk > static_cast<size_t>(kMtu)) chunk = static_cast<size_t>(kMtu);

    uint8_t flags = 0;
    if (first) flags |= kFlagStart;
    if (off + chunk < payloadLen) {
      flags |= kFlagMore;
    } else {
      flags |= kFlagEnd;
    }

    frame[0] = txSeq_++;
    frame[1] = flags;
    frame[2] = static_cast<uint8_t>(chunk);
    if (chunk > 0) {
      memcpy(frame + kFrameHeaderBytes, payload + off, chunk);
    }
    uBit.radio.datagram.send(frame,
                             static_cast<int>(kFrameHeaderBytes + chunk));

    off += chunk;
    first = false;
  } while (off < payloadLen);
}

void RadioTransport::sendLine(const uint8_t* data, size_t len) {
  ensureRadioReady();

  // `data`/`len` plus one trailing '\n' delimiter -- the ONE
  // terminator every outbound line uses here, exactly as
  // SerialTransport::writeLine() appends for the serial side (see this
  // module's header for why that's safe for binary content). Truncates
  // rather than overflows on an over-length caller, mirroring
  // SerialTransport's own defensive truncation.
  uint8_t payload[kMaxPayloadBytes + 1];
  size_t n = (len < sizeof(payload) - 1) ? len : sizeof(payload) - 1;
  if (n > 0) {
    memcpy(payload, data, n);
  }
  payload[n] = kLineDelimiter;
  sendFragmented(payload, n + 1);
}

}  // namespace diffDrive
