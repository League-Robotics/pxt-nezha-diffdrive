// wire_grammar_shim.cpp -- extern "C" ctypes surface for the wire
// grammar host test harness (ticket 002). Test scaffolding only:
// nothing under src/ knows this file exists, and it is compiled only
// into this test's own throwaway shared library (see
// test_wire_grammar.py, which reuses ticket 001's
// test_kernel_harness.compile_shared_lib() against this file's own
// source list instead of inventing new build plumbing).
//
// ctypes cannot call C++ methods directly, so this file is the thin
// translation layer: one opaque handle bundling the handler under test
// with its own private StubAdapter and RecordingSink, plus free
// functions Python can bind by name. Mirrors radio-robot-lib/tests/
// protocol/protocol_shim.cpp's own shape exactly.
#include <cstdint>
#include <cstring>
#include <string>

#include "wire_handler.h"

namespace {

// Accumulates every Sink::write() into one buffer for the whole test to
// inspect -- callers slice it on '\n' from the Python side. std::string
// is fine here: this file is host-only test scaffolding, not the
// no-allocation library it drives (wire_handler.cpp itself never
// allocates).
class RecordingSink : public Wire::Sink {
 public:
  void write(const char* data, size_t length) override {
    buffer_.append(data, length);
  }
  const std::string& buffer() const { return buffer_; }
  void clear() { buffer_.clear(); }

 private:
  std::string buffer_;
};

// StubAdapter -- the trivial "identity + now() + onEstop() counter"
// double this ticket's own Wire::Adapter seam needs, per the ticket's
// own Implementation Plan ("a trivial stub adapter (now()/identity
// only) -- enough for HELLO/PING"). A test sets identityName_/
// identitySerial_/nowValue_ directly before feed()ing a line, and reads
// estopCalls back afterward -- same "plain public canned-response
// fields, plus call counters" shape as radio-robot-lib's own
// MockAdapter.
class StubAdapter : public Wire::Adapter {
 public:
  void identity(Wire::Identity& out) const override {
    out.name = name;
    out.serial = serial;
  }
  uint32_t now() const override { return nowValue; }
  void onEstop() override { ++estopCalls; }

  const char* name = "testbot";
  const char* serial = "SN001";
  uint32_t nowValue = 0;
  int estopCalls = 0;
};

struct Handle {
  StubAdapter adapter;
  RecordingSink sink;
  Wire::WireHandler handler;
  Handle() : handler(adapter, sink) {}
};

}  // namespace

extern "C" {

void* wgCreate() { return new Handle(); }
void wgDestroy(void* handle) { delete static_cast<Handle*>(handle); }

void wgFeed(void* handle, const char* data, int length) {
  static_cast<Handle*>(handle)->handler.feed(data,
                                              static_cast<size_t>(length));
}

void wgSendBanner(void* handle) {
  static_cast<Handle*>(handle)->handler.sendBanner();
}

uint32_t wgMalformedCount(void* handle) {
  return static_cast<Handle*>(handle)->handler.malformedCount();
}

// ---- StubAdapter control/readback --------------------------------------

void wgSetIdentity(void* handle, const char* name, const char* serial) {
  static_cast<Handle*>(handle)->adapter.name = name;
  static_cast<Handle*>(handle)->adapter.serial = serial;
}

void wgSetNow(void* handle, uint32_t now) {
  static_cast<Handle*>(handle)->adapter.nowValue = now;
}

int wgEstopCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.estopCalls;
}

// ---- sink readback -------------------------------------------------------

int wgSinkLength(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->sink.buffer().size());
}

// Copies up to `cap` bytes of the sink's accumulated output into `out`
// (NOT nul-terminated by this call -- the wire is ASCII text with no
// embedded NUL in any reply this handler emits, so the Python side just
// slices `out[:wgSinkLength()]`). Returns the number of bytes copied.
int wgSinkRead(void* handle, char* out, int cap) {
  Handle* h = static_cast<Handle*>(handle);
  size_t n = h->sink.buffer().size();
  if (static_cast<int>(n) > cap) n = static_cast<size_t>(cap);
  std::memcpy(out, h->sink.buffer().data(), n);
  return static_cast<int>(n);
}

void wgSinkClear(void* handle) { static_cast<Handle*>(handle)->sink.clear(); }

}  // extern "C"
