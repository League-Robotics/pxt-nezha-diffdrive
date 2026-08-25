// radio_transport_rx_capacity_shim.cpp -- extern "C" ctypes surface for
// src/radio_transport.h's radioRxLineFits() (sprint 010 ticket 001,
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

}  // extern "C"
