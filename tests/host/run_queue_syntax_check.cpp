// run_queue_syntax_check.cpp -- compile-only translation unit so the
// c++11 syntax gate has something to point -fsyntax-only at.
//
// src/comms/run_queue.h is a pure header with no natural .cpp of its
// own; this file exists solely to be that translation unit. It is NOT
// part of the ctypes-bound behaviour surface -- see run_queue_shim.cpp
// for that.
#include "comms/run_queue.h"

// Force the template to actually instantiate: a header that only parses
// is not the same as one that compiles, and the gate is worth nothing
// if the body is never seen by the compiler.
namespace {
diffDrive::RunQueue<8, 48> g_probe;
}
