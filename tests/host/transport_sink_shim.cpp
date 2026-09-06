// transport_sink_shim.cpp -- extern "C" ctypes surface for
// src/comms/transport_sink.h: `wireLineContentLength()` (the pure
// terminator decision) and a real `TransportSink` driven through the
// `Wire::Sink&` interface the wire stack actually calls it through,
// over a recording fake transport.
//
// #includes transport_sink.h directly. Neither it nor the
// wire_handler.h it needs for `Wire::Sink` has any CODAL dependency,
// which is exactly what makes this seam reachable from a desktop host
// build -- unlike protocol.cpp (where the three per-transport sinks
// used to live) and unlike serial_transport.cpp/radio_transport.cpp,
// all of which require pxt.h and cannot be host-compiled at all
// (src/DESIGN.md S1's layering table).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cstddef>
#include <cstring>

#include "comms/transport_sink.h"

namespace {

// Recorder's own buffer bound -- a namespace-scope constant rather than
// a static member so nothing here can odr-use an undefined one.
constexpr size_t kRecorderCapacity = 512;

// Stands in for SerialTransport/RadioTransport/WifiLink: records the
// bytes a sink hands it, exactly as they arrive. A real transport
// appends its own single delimiter after these; `Recorder::onWire()`
// below reproduces that, so a test can assert on what actually reaches
// the wire, not just on a length.
struct Recorder {
  unsigned char content[kRecorderCapacity];
  size_t contentLen = 0;
  size_t writeCount = 0;

  void writeLine(const unsigned char* data, size_t len) {
    ++writeCount;
    contentLen = len < kRecorderCapacity ? len : kRecorderCapacity;
    if (contentLen > 0) std::memcpy(content, data, contentLen);
  }
};

void recorderWrite(Recorder& recorder, const uint8_t* data, size_t len) {
  recorder.writeLine(reinterpret_cast<const unsigned char*>(data), len);
}

struct Handle {
  Recorder recorder;
  diffDrive::TransportSink<Recorder> sink{recorder, &recorderWrite};
};

}  // namespace

extern "C" {

// The pure decision on its own, with no sink and no transport in the
// link -- the same plain-function shape radio_transport_rx_capacity_
// shim.cpp uses for radioRxLineFits().
size_t transportSinkContentLength(const char* data, size_t length) {
  return diffDrive::wireLineContentLength(data, length);
}

void* transportSinkCreate() { return new Handle(); }

void transportSinkDestroy(void* handle) {
  delete static_cast<Handle*>(handle);
}

// Writes one line through the Wire::Sink INTERFACE, not through
// TransportSink's own type -- the wire stack only ever holds a
// `Wire::Sink&` (WireHandler's own member), so this is the call path
// that actually ships.
void transportSinkWrite(void* handle, const char* data, size_t length) {
  Handle* h = static_cast<Handle*>(handle);
  Wire::Sink& sink = h->sink;
  sink.write(data, length);
}

size_t transportSinkLastContentLength(void* handle) {
  return static_cast<Handle*>(handle)->recorder.contentLen;
}

size_t transportSinkWriteCount(void* handle) {
  return static_cast<Handle*>(handle)->recorder.writeCount;
}

// Copies out what the transport was handed, plus the single delimiter a
// real transport appends -- i.e. the bytes that would be on the wire.
// Returns how many bytes were written into `out`.
size_t transportSinkOnWire(void* handle, char* out, size_t cap) {
  Handle* h = static_cast<Handle*>(handle);
  if (out == nullptr || cap == 0) return 0;
  const size_t len = h->recorder.contentLen;
  const size_t copied = len < (cap - 1) ? len : (cap - 1);
  if (copied > 0) std::memcpy(out, h->recorder.content, copied);
  out[copied] = '\n';
  return copied + 1;
}

}  // extern "C"
