// transport_sink_syntax_check.cpp -- compile-only translation unit so
// the c++11 syntax gate has something to point -fsyntax-only at.
//
// src/comms/transport_sink.h is a pure header with no natural .cpp of
// its own; this file exists solely to be that translation unit. It is
// NOT part of the ctypes-bound behaviour surface -- see
// transport_sink_shim.cpp for that.
#include "comms/transport_sink.h"

// Force the template to actually instantiate against a transport shaped
// like the real ones: a header that only parses is not the same as one
// that compiles, and the gate is worth nothing if TransportSink::write()
// is never seen by the compiler.
namespace {
struct ProbeTransport {
  void writeLine(const uint8_t*, size_t) {}
};

void probeWrite(ProbeTransport& transport, const uint8_t* data, size_t len) {
  transport.writeLine(data, len);
}

ProbeTransport g_transport;
diffDrive::TransportSink<ProbeTransport> g_sink{g_transport, &probeWrite};
}  // namespace
