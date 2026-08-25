// encoder_glitch_armor_shim.cpp -- extern "C" ctypes surface for
// src/encoder_glitch_armor.h. EncoderGlitchArmor is small but stateful
// (the two-strike gate needs to remember the last accepted/rejected raw
// counts across calls), so this shim follows the
// handle-plus-free-functions shape (tests/host/DESIGN.md S2) rather than
// heading_wrap_shim.cpp's plain-function shape -- the same convention
// kernel_shim.cpp/motion_engine_shim.cpp use ("egaXxx", mirroring their
// "kdXxx"/"meXxx" prefixes).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cstdint>

#include "core/encoder_glitch_armor.h"

extern "C" {

// ---- lifecycle -------------------------------------------------------

void* egaCreate() { return new diffDrive::EncoderGlitchArmor(); }
void egaDestroy(void* handle) {
  delete static_cast<diffDrive::EncoderGlitchArmor*>(handle);
}

// ---- NezhaMotorPort::begin()'s own priming calls, mirrored exactly ---

void egaSeedLastGoodRaw(void* handle, int32_t raw) {
  static_cast<diffDrive::EncoderGlitchArmor*>(handle)->seedLastGoodRaw(raw);
}
void egaMarkPrimed(void* handle) {
  static_cast<diffDrive::EncoderGlitchArmor*>(handle)->markPrimed();
}

// ---- the decision under test ------------------------------------------

// Returns the Decision enum's underlying int value:
// 0 = kAccept, 1 = kAcceptAsRebaseline, 2 = kRejectPending (matches
// declaration order in encoder_glitch_armor.h).
int egaEvaluate(void* handle, int32_t raw) {
  return static_cast<int>(
      static_cast<diffDrive::EncoderGlitchArmor*>(handle)->evaluate(raw));
}

int32_t egaLastGoodRaw(void* handle) {
  return static_cast<diffDrive::EncoderGlitchArmor*>(handle)->lastGoodRaw();
}

}  // extern "C"
