// radio_transport_rx_capacity_shim.cpp -- extern "C" ctypes surface for
// src/comms/radio_transport.h's radioRxLineFits() (sprint 010 ticket 001,
// radio-rx-capacity-fragmentation.md). radioRxLineFits() is one pure,
// free function (no class, no state) -- smaller in scope than the
// handle-plus-free-functions shims this directory otherwise uses
// (kernel_shim.cpp, motion_engine_shim.cpp), the same plain-function
// shape heading_wrap_shim.cpp already uses for wrapRadians().
//
// #includes radio_transport.h directly -- NOT radio_transport.cpp,
// which requires pxt.h (uBit.radio, PacketBuffer) and cannot be
// host-compiled at all (src/DESIGN.md §1's layering table). The header
// itself has no CODAL dependency (only <cstddef>/<cstdint>), which is
// exactly what makes radioRxLineFits() reachable from a desktop host
// build with zero link against the CODAL-bound translation unit.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "comms/radio_transport.h"

extern "C" {

// Returns 1 (fits, accept) or 0 (does not fit, reject) -- ctypes has no
// native C++ bool ABI guarantee across platforms, so this shim surfaces
// radioRxLineFits()'s bool result as a plain int, the same convention
// encoder_glitch_armor_shim.cpp uses for its Decision enum.
int radioTransportRxLineFits(size_t declaredLen, size_t bufferCapacity) {
  return diffDrive::radioRxLineFits(declaredLen, bufferCapacity) ? 1 : 0;
}

// radioRxClassify() plus its RadioRxCounters, the RX path's OTHER
// host-portable half: which disposition each inbound line gets, and
// which counter moves for it. Same reasoning as radioRxLineFits()
// above -- onDatagram() itself needs pxt.h, but the decision it makes
// does not.
//
// The counters live in a heap-allocated struct behind an opaque handle
// (the shape run_bridge_shim.cpp uses) so a test can run a whole
// sequence of arrivals against one accumulating set, which is the only
// way the "frames - accepted == the two drop counts" relationship is
// observable at all.
void* radioRxCountersNew() { return new diffDrive::RadioRxCounters(); }
void radioRxCountersFree(void* h) {
  delete static_cast<diffDrive::RadioRxCounters*>(h);
}

// Returns the RadioRxDisposition enumerator as an int -- see the
// radioRxDispositionCode* accessors below for the values, exported
// rather than duplicated on the Python side.
int radioRxClassify(void* h, size_t declaredLen, size_t bufferCapacity,
                    int slotBusy) {
  return static_cast<int>(diffDrive::radioRxClassify(
      declaredLen, bufferCapacity, slotBusy != 0,
      *static_cast<diffDrive::RadioRxCounters*>(h)));
}

unsigned int radioRxFrames(void* h) {
  return static_cast<diffDrive::RadioRxCounters*>(h)->frames;
}
unsigned int radioRxAccepted(void* h) {
  return static_cast<diffDrive::RadioRxCounters*>(h)->accepted;
}
unsigned int radioRxOversizeDropped(void* h) {
  return static_cast<diffDrive::RadioRxCounters*>(h)->oversizeDropped;
}
unsigned int radioRxOverrunDropped(void* h) {
  return static_cast<diffDrive::RadioRxCounters*>(h)->overrunDropped;
}

int radioRxDispositionCodeAccept() {
  return static_cast<int>(diffDrive::RadioRxDisposition::kAccept);
}
int radioRxDispositionCodeOversize() {
  return static_cast<int>(diffDrive::RadioRxDisposition::kOversize);
}
int radioRxDispositionCodeOverrun() {
  return static_cast<int>(diffDrive::RadioRxDisposition::kOverrun);
}

}  // extern "C"
