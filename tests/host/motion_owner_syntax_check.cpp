// motion_owner_syntax_check.cpp -- dedicated compile-only translation
// unit giving tests/host/test_cxx11_syntax_gate.py something to point a
// -fsyntax-only -std=c++11 compile at directly.
//
// src/core/motion_owner.h is a pure header with no natural .cpp of its
// own the way motion_engine.h rides along with motion_engine.cpp --
// this file exists solely to be that translation unit for the gate. It
// is NOT part of the ctypes-bound behavior-test surface; see
// motion_owner_shim.cpp for that.
#include "core/motion_owner.h"
