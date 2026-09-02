// emit_queue_shim.cpp -- ctypes surface for src/comms/emit_queue.h.
//
// Opaque handle plus free functions, the same shape every other shim
// here uses, because ctypes cannot call C++ methods.
#include "comms/emit_queue.h"

#include <cstring>

using Q = diffDrive::EmitQueue<8, 48>;

extern "C" {

void* eqNew() { return new Q(); }
void eqFree(void* h) { delete static_cast<Q*>(h); }

int eqEnqueue(void* h, const char* text) {
  return static_cast<Q*>(h)->enqueue(text, std::strlen(text)) ? 1 : 0;
}
int eqEnqueueLen(void* h, const char* text, int len) {
  return static_cast<Q*>(h)->enqueue(text, static_cast<size_t>(len)) ? 1 : 0;
}
int eqDequeue(void* h, char* dest, int destCap) {
  return static_cast<int>(static_cast<Q*>(h)->dequeue(
      dest, static_cast<size_t>(destCap)));
}
int eqCount(void* h) { return static_cast<Q*>(h)->count(); }
unsigned int eqDropped(void* h) { return static_cast<Q*>(h)->dropped(); }
int eqSlots(void*) { return Q::kSlots; }
int eqBytes(void*) { return Q::kBytes; }

}  // extern "C"
