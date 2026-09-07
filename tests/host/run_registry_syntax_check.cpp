// run_registry_syntax_check.cpp -- compile-only translation unit so the
// c++11 syntax gate has something to point -fsyntax-only at.
//
// src/comms/run_registry.h's TABLE is a pure header template; the .cpp
// beside it holds only the firmware's shared instance. This file exists
// solely to be that translation unit for the header. It is NOT part of
// the ctypes-bound behaviour surface -- see run_registry_shim.cpp.
#include "comms/run_registry.h"

// Force the template to actually instantiate: a header that only parses
// is not the same as one that compiles, and the gate is worth nothing
// if the body is never seen by the compiler.
namespace {
diffDrive::RunRegistry<32, 24> g_probe;
}
