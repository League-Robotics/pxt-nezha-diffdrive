// encoder_pose_source_syntax_check.cpp -- dedicated compile-only
// translation unit giving tests/host/test_cxx11_syntax_gate.py something
// to point a -fsyntax-only -std=c++11 compile at directly (sprint 006
// ticket 007).
//
// src/encoder_pose_source.h is a pure header with no natural .cpp of its
// own the way motion_engine.h rides along with motion_engine.cpp -- this
// file exists solely to be that translation unit for the gate. It is NOT
// part of the ctypes-bound behavior-test surface; see
// tests/host/motion_engine_shim.cpp for that (EncoderPoseSource is
// exposed there alongside FakePoseSource, both feeding
// MotionEngine::goToW()).
#include "encoder_pose_source.h"
