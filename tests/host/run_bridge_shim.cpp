// run_bridge_shim.cpp -- ctypes surface for src/comms/run_bridge.h.
//
// Opaque handle plus free functions, the same shape run_queue_shim.cpp
// and every other shim here uses, because ctypes cannot call C++
// methods. The clock is a plain argument on rbOffer(), which is the
// whole reason RunBridge takes `now` rather than owning a clock: a test
// can step time exactly onto the dedupe window's edges.
#include "comms/run_bridge.h"

#include <cstring>

using B = diffDrive::RunBridge;

extern "C" {

void* rbNew() { return new B(); }
void rbFree(void* h) { delete static_cast<B*>(h); }

// Returns the Offer enumerator as an int -- see rbOfferCode* below for
// the values, exported rather than duplicated on the Python side.
int rbOffer(void* h, const char* data, int len, unsigned int now) {
  return static_cast<int>(static_cast<B*>(h)->offer(
      reinterpret_cast<const unsigned char*>(data),
      static_cast<size_t>(len), static_cast<uint32_t>(now)));
}

// Convenience for the common "NUL-terminated payload" case.
int rbOfferText(void* h, const char* text, unsigned int now) {
  return rbOffer(h, text, static_cast<int>(std::strlen(text)), now);
}

int rbDispatchOne(void* h) {
  return static_cast<B*>(h)->dispatchOne() ? 1 : 0;
}
const char* rbCurrentText(void* h) { return static_cast<B*>(h)->currentText(); }
unsigned int rbDropCount(void* h) { return static_cast<B*>(h)->dropCount(); }
int rbQueued(void* h) { return static_cast<B*>(h)->queued(); }
int rbIsBypassName(const char* text) { return B::isBypassName(text) ? 1 : 0; }

int rbSlots() { return B::kSlots; }
int rbTextBytes() { return static_cast<int>(B::kTextBytes); }
int rbDedupe() { return static_cast<int>(B::kDedupe); }  // [ms]

int rbOfferCodeMalformed() { return static_cast<int>(B::Offer::kMalformed); }
int rbOfferCodeSuppressed() { return static_cast<int>(B::Offer::kSuppressed); }
int rbOfferCodeBypass() { return static_cast<int>(B::Offer::kBypass); }
int rbOfferCodeQueued() { return static_cast<int>(B::Offer::kQueued); }
int rbOfferCodeDropped() { return static_cast<int>(B::Offer::kDropped); }

}  // extern "C"
