// wire_grammar_shim.cpp -- extern "C" ctypes surface for the wire host
// test harness (ticket 002, widened by ticket 003). Test scaffolding
// only: nothing under src/ knows this file exists, and it is compiled
// only into this test's own throwaway shared library -- reused by BOTH
// test_wire_grammar.py (grammar mechanics + the nine non-motion verbs'
// golden vectors) and test_wire_reliability.py (the reliability layer),
// mirroring radio-robot-lib/tests/protocol/protocol_shim.cpp's own
// pattern of one shim, several pytest files.
//
// ctypes cannot call C++ methods directly, so this file is the thin
// translation layer: one opaque handle bundling the handler under test
// with its own private WireMockAdapter and RecordingSink, plus free
// functions Python can bind by name.
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "wire_handler.h"
#include "wire_mock_adapter.h"

namespace {

// Accumulates every Sink::write() into one buffer for the whole test to
// inspect -- callers slice it on '\n' from the Python side. std::string
// is fine here: this file is host-only test scaffolding, not the
// no-allocation library it drives (wire_handler.cpp itself never
// allocates).
//
// Ticket 003 widens this with writeLengths_: emitTelemetry(snapshot)'s
// own acceptance criteria require proving thdr/t/ack-or-nack go out as
// THREE SEPARATE Sink::write() calls, not merely that their
// concatenation looks right -- a bug that accidentally merged two of
// them into one write() would still pass a buffer-only assertion.
// Recording each call's length (in order) alongside the concatenated
// buffer lets the Python side slice the buffer back into the ORIGINAL
// per-call boundaries.
class RecordingSink : public Wire::Sink {
 public:
  void write(const char* data, size_t length) override {
    buffer_.append(data, length);
    writeLengths_.push_back(length);
  }
  const std::string& buffer() const { return buffer_; }
  void clear() {
    buffer_.clear();
    writeLengths_.clear();
  }
  size_t writeCount() const { return writeLengths_.size(); }
  size_t writeLength(size_t index) const {
    return index < writeLengths_.size() ? writeLengths_[index] : 0;
  }

 private:
  std::string buffer_;
  std::vector<size_t> writeLengths_;
};

struct Handle {
  WireMockAdapter adapter;
  RecordingSink sink;
  Wire::WireHandler handler;
  Handle() : handler(adapter, sink) {}
};

}  // namespace

extern "C" {

// ---- lifecycle -------------------------------------------------------

void* wgCreate() { return new Handle(); }
void wgDestroy(void* handle) { delete static_cast<Handle*>(handle); }

void wgFeed(void* handle, const char* data, int length) {
  static_cast<Handle*>(handle)->handler.feed(data,
                                              static_cast<size_t>(length));
}

void wgSendBanner(void* handle) {
  static_cast<Handle*>(handle)->handler.sendBanner();
}

// Ticket 003: emitTelemetry() now takes a Snapshot -- this shim builds
// one from parallel C arrays ctypes can populate directly (a
// POINTER(c_char_p)/POINTER(c_int32)/POINTER(c_int) triple plus a
// count), rather than round-tripping through a second struct ctypes
// would have to mirror byte-for-byte. `kShimMaxColumns` is this SHIM's
// own stack-array cap, independent of (and generously above)
// WireHandler's own kMaxHeaderColumns -- a test that wants to exercise
// the "wider than the header memo" fallback path can still pass more
// than 40 columns here, up to this cap.
namespace {
constexpr int kShimMaxColumns = 64;
}  // namespace

void wgEmitTelemetry(void* handle, const char* const* names,
                      const int32_t* values, const int* hexFlags,
                      int count) {
  Wire::Column cols[kShimMaxColumns];
  int n = count;
  if (n < 0) n = 0;
  if (n > kShimMaxColumns) n = kShimMaxColumns;
  for (int i = 0; i < n; ++i) {
    cols[i].name = names[i];
    cols[i].value = values[i];
    cols[i].hex = hexFlags[i] != 0;
  }
  Wire::Snapshot snapshot;
  snapshot.columns = cols;
  snapshot.count = static_cast<size_t>(n);
  static_cast<Handle*>(handle)->handler.emitTelemetry(snapshot);
}

void wgEmitReliability(void* handle) {
  static_cast<Handle*>(handle)->handler.emitReliability();
}

uint32_t wgMalformedCount(void* handle) {
  return static_cast<Handle*>(handle)->handler.malformedCount();
}

// ---- sink readback -----------------------------------------------------

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

// Ticket 003: the per-call write lengths (see RecordingSink's own
// comment) -- lets the Python side slice wgSinkRead()'s concatenated
// buffer back into the individual Sink::write() calls that produced
// it, in order.
int wgSinkWriteCount(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->sink.writeCount());
}
int wgSinkWriteLength(void* handle, int index) {
  if (index < 0) return 0;
  return static_cast<int>(
      static_cast<Handle*>(handle)->sink.writeLength(static_cast<size_t>(index)));
}

// ---- WireMockAdapter canned-response setup ------------------------------
// NOTE: every const char* passed in must outlive its use -- the mock
// stores the pointer, not a copy (mirroring Wire::Identity's own
// borrowed-pointer contract). Callers keep the Python bytes objects
// alive for the ctypes call's duration; the mock reads them again on
// every identity()/status() call after that, so the TEST must keep them
// alive for as long as the handle lives.

void wgSetIdentity(void* handle, const char* name, const char* serial,
                    const char* drivetrain, const char* profile,
                    const char* version) {
  Wire::Identity& id = static_cast<Handle*>(handle)->adapter.identityToReturn;
  id.name = name;
  id.serial = serial;
  id.drivetrain = drivetrain;
  id.profile = profile;
  id.version = version;
}

void wgSetNow(void* handle, uint32_t now) {
  static_cast<Handle*>(handle)->adapter.nowToReturn = now;
}

void wgSetStatus(void* handle, int ready, int active, int connL, int connR,
                  int otos, int wedge, uint32_t flags, int32_t i2cf,
                  const char* tlm) {
  Wire::StatusFields& s = static_cast<Handle*>(handle)->adapter.statusToReturn;
  s.ready = ready != 0;
  s.active = active != 0;
  s.connLeft = connL != 0;
  s.connRight = connR != 0;
  s.otos = otos != 0;
  s.wedge = wedge != 0;
  s.flags = flags;
  s.i2cf = i2cf;  // sprint 004 ticket 004
  s.tlm = tlm;
}

// `name` must outlive its use, same borrowed-pointer contract as
// wgSetIdentity above.
void wgSetGetOverride(void* handle, const char* name, float value) {
  WireMockAdapter& a = static_cast<Handle*>(handle)->adapter;
  a.overrideName = name;
  a.overrideValue = value;
}

// `result` is Wire::Result's DECLARATION-ORDER ordinal
// (wire_handler.h), NOT a wire error code -- see test_wire_grammar.py's
// RESULT_* constants, which mirror that same order.
void wgSetStopResult(void* handle, int result) {
  static_cast<Handle*>(handle)->adapter.stopResult =
      static_cast<Wire::Result>(result);
}
void wgSetSetResult(void* handle, int result) {
  static_cast<Handle*>(handle)->adapter.setResult =
      static_cast<Wire::Result>(result);
}
void wgSetTlmResult(void* handle, int result) {
  static_cast<Handle*>(handle)->adapter.tlmResult =
      static_cast<Wire::Result>(result);
}
void wgSetRunResult(void* handle, int result) {
  static_cast<Handle*>(handle)->adapter.runResult =
      static_cast<Wire::Result>(result);
}
void wgSetRunHasResult(void* handle, int hasResult) {
  static_cast<Handle*>(handle)->adapter.runHasResult = hasResult != 0;
}
// `text` must outlive its use -- same borrowed-pointer contract as
// wgSetGetOverride above.
void wgSetRunResultText(void* handle, const char* text) {
  static_cast<Handle*>(handle)->adapter.runResultText = text;
}

// `reason` is Wire::DoneReason's DECLARATION-ORDER ordinal -- see
// test_wire_grammar.py's DONE_* constants.
void wgSetLastDone(void* handle, uint32_t lastDone) {
  static_cast<Handle*>(handle)->adapter.lastDoneToReturn = lastDone;
}
void wgSetLastDoneReason(void* handle, int reason) {
  static_cast<Handle*>(handle)->adapter.lastDoneReasonToReturn =
      static_cast<Wire::DoneReason>(reason);
}

// ---- WireMockAdapter call-log readback -----------------------------------

int wgEstopCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.estopCalls;
}

int wgStopCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.stopCalls;
}
uint32_t wgLastStopId(void* handle) {
  return static_cast<Handle*>(handle)->adapter.lastStopId;
}
int wgLastStopImmediate(void* handle) {
  return static_cast<Handle*>(handle)->adapter.lastStopImmediate ? 1 : 0;
}

int wgGetCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.getCalls;
}

int wgSetCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.setCalls;
}
float wgLastSetValue(void* handle) {
  return static_cast<Handle*>(handle)->adapter.lastSetValue;
}
uint32_t wgLastSetId(void* handle) {
  return static_cast<Handle*>(handle)->adapter.lastSetId;
}
int wgLastSetNameMatches(void* handle, const char* name) {
  return std::strcmp(static_cast<Handle*>(handle)->adapter.lastSetName,
                      name) == 0
             ? 1
             : 0;
}

int wgTlmCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.tlmCalls;
}
int wgLastTlmMode(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->adapter.lastTlmMode);
}

int wgRunCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.runCalls;
}
int wgLastRunNameMatches(void* handle, const char* name) {
  return std::strcmp(static_cast<Handle*>(handle)->adapter.lastRunName,
                      name) == 0
             ? 1
             : 0;
}
int wgLastRunArgc(void* handle) {
  return static_cast<int>(static_cast<Handle*>(handle)->adapter.lastRunArgc);
}
// Returns 1 if argv[index] from the last onRun() call equals `value`, 0
// if it does not match OR index is out of the recorded range -- so a
// test cannot mistake "out of range" for "matched an empty string".
int wgLastRunArgMatches(void* handle, int index, const char* value) {
  WireMockAdapter& a = static_cast<Handle*>(handle)->adapter;
  if (index < 0 || static_cast<size_t>(index) >= a.lastRunArgc) return 0;
  if (static_cast<size_t>(index) >= WireMockAdapter::kMaxRecordedRunArgs) {
    return 0;
  }
  return std::strcmp(a.lastRunArgs[index], value) == 0 ? 1 : 0;
}

int wgIdentityCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.identityCalls;
}
int wgNowCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.nowCalls;
}
int wgStatusCalls(void* handle) {
  return static_cast<Handle*>(handle)->adapter.statusCalls;
}

}  // extern "C"
