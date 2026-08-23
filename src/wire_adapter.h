// wire_adapter.h -- diffDrive::WireAdapter: the concrete Wire::Adapter
// (src/wire_handler.h) that closes the seam for THIS robot -- this
// project's analogue of radio-robot-lib's Protocol::DiffDriveAdapter
// (radio-robot-lib/docs/design/protocol.md S5). Sprint 003 ticket 004
// scope: WHEELS_V gets real effect (the only motion verb this robot's
// current shims.cpp/Rig surface can already execute without a planner);
// WHEELS_X/MOVE_X/MOVE_V/GO_TO_R/GO_TO_W all answer Result::kUnknown --
// an honest, DELIBERATE "this adapter has no planner yet" result, not a
// stub left unfinished (protocol.md S9.10 item 1's own precedent: an
// adapter with no registration table answers kUnknown for exactly this
// reason, matching this class's own onRun() posture below). Tickets
// 011/012 give WHEELS_X/MOVE_X and MOVE_V/GO_TO_R/GO_TO_W real effect
// once motion_engine (ticket 006/007) exists to route them onto.
//
// STOP/ESTOP/GET/SET call straight through to shims.cpp's EXISTING
// hardware-facing primitives (stopAll/estopAll/setKernelValue/
// getConfigValue/diagValue) via the same same-package C++
// forward-declaration convention protocol.cpp already uses to reach
// shims.cpp (that file has no header of its own -- see wire_adapter.cpp's
// own forward-declaration block, which must stay signature-compatible
// with shims.cpp's real definitions, exactly like protocol.cpp's). This
// class therefore holds NO reference to a kernel, motion engine, or Rig
// of its own: every piece of real state lives behind a forward-declared
// free function, exactly like every OTHER caller of those functions
// (protocol.cpp's own binary verb handlers). It adds no NEW entry point
// to shims.cpp -- every function it calls already existed before this
// ticket.
//
// Host-portable by construction: no pxt.h, no CODAL type, anywhere in
// this file or wire_adapter.cpp -- see tests/host/wire_motion_verb_shim.cpp
// for how the host test harness supplies its OWN definitions of the
// forward-declared shims.cpp functions (a FakeMotor-backed kernel
// standing in for the real Rig/NezhaMotorPort composition), so this
// class links and is exercised end to end with no micro:bit involved.
//
// identity() is wired for real via a caller-supplied Wire::Identity at
// construction (borrowed pointers, same contract as Wire::Identity's own
// doc comment in wire_handler.h) -- DiffDriveAdapter's own pattern --
// rather than reading microbit_friendly_name()/microbit_serial_number()
// directly, which are CODAL globals this class must never touch.
//
// now() has no forward-declared clock read to call: shims.cpp has never
// needed one (PING is this project's only consumer of Wire::Adapter::
// now(), and its own liveness contract only needs a reply to exist, not
// a wall-clock-accurate value) -- returns 0 until a later ticket adds
// one, the same "honest, functionally inert default" posture lastDone()/
// lastDoneReason() below already take deliberately, for the identical
// reason (no planner/clock hook exists yet to make the value live).
#pragma once

#include <cstddef>
#include <cstdint>

#include "wire_handler.h"

namespace diffDrive {

class WireAdapter : public Wire::Adapter {
 public:
  // WHEELS_V's documented ceiling (motion-api.md S1, protocol.md S5
  // point 1): "duration [ms] required, ceiling 5000 -- a dead host
  // cannot mean a runaway." wire_handler.h's own Adapter contract holds
  // no bounds table of its own (protocol.md S7's "the library stores
  // none" spirit, extended to bounds); this is that enforcement, on
  // this adapter.
  static constexpr uint32_t kWheelsVDurationCeiling = 5000;  // [ms]

  // `identity`'s own pointer fields are borrowed (Wire::Identity's own
  // doc comment, wire_handler.h): the CALLER's identity strings must
  // outlive this adapter. Copied by value here (copies the pointers,
  // not the strings they point to).
  explicit WireAdapter(const Wire::Identity& identity);

  // ---- Wire::Adapter: session ----
  void identity(Wire::Identity& out) const override;
  uint32_t now() const override;
  void status(Wire::StatusFields& out) const override;

  // ---- Wire::Adapter: motion ----

  // WHEELS_V: real effect -- maps onto shims.cpp's existing
  // setWheelsTimed(left, right, durationMs), which already computes
  // velocity=(left+right)/2 and twist=(right-left)/2 (half-differential,
  // CCW-positive), scaled by the Rig's own countsPerLength, and drives
  // the kernel with `duration` as the lease (protocol.md S5). This class
  // only enforces the wire's own duration ceiling before forwarding --
  // setWheelsTimed() returns void, so there is no adapter-observable
  // refusal path from the kernel side (kernel.drive()'s own Status is
  // already discarded by that existing function, unchanged by this
  // ticket).
  Wire::Result onWheelsV(float left, float right, uint32_t duration,
                         uint32_t id) override;

  // The other five motion verbs (motion-api.md S9.1) all need a planner
  // this robot does not have yet (ticket 006/007's motion_engine
  // extraction) -- every one of them answers kUnknown, the SAME wire
  // outcome onRun() below already answers for any name (protocol.md
  // S9.10 item 1's own precedent: "an Adapter with no registration
  // table ... has an empty allowlist"). This is honest, not a stub left
  // unfinished: this adapter has no planner to wire these onto yet.
  Wire::Result onWheelsX(float left, float right, float cruise,
                         uint32_t timeout, uint32_t id) override;
  Wire::Result onMoveX(float distance, float rotation, float cruise,
                       uint32_t timeout, uint32_t id) override;
  Wire::Result onMoveV(float v_x, float omega, uint32_t duration,
                       uint32_t id) override;
  Wire::Result onGoToR(float x, float y, float speed, float arrive,
                       uint32_t timeout, uint32_t id) override;
  Wire::Result onGoToW(float x, float y, float speed, float arrive,
                       uint32_t timeout, uint32_t id) override;

  // ---- Wire::Adapter: safety ----
  void onEstop() override;                            // -> estopAll()
  Wire::Result onStop(bool immediate, uint32_t id) override;  // -> stopAll()

  // ---- Wire::Adapter: configuration -- a small field-name table
  // replacing the old binary CONFIG/SET_FIELD/GET_CONFIG verbs'
  // ConfigField ordinal one-for-one (sprint.md Migration Concerns: "the
  // old multi-pair CONFIG batch verb is not reintroduced"). See
  // wire_adapter.cpp's kFields table for the full name<->ordinal
  // mapping onto shims.cpp's existing setKernelValue()/getConfigValue()
  // field numbers. ----
  bool onGet(const char* name, float& out) const override;
  Wire::Result onSet(const char* name, float value, uint32_t id) override;
  size_t fieldCount() const override;
  const char* fieldName(size_t index) const override;

  // ---- Wire::Adapter: telemetry ----
  Wire::Result onTlm(Wire::TlmMode mode) override;

  // No motion queue and no completion event on this adapter yet (ticket
  // 006/007 introduce a planner) -- WHEELS_V has no stop condition of
  // its own; it just holds a velocity for `duration` and lets the lease
  // expire, which is not a "completion" this adapter can observe. Both
  // always report the inert default, matching DiffDriveAdapter's own
  // posture for the identical reason (protocol.md S8.8.1).
  uint32_t lastDone() const override { return 0; }
  Wire::DoneReason lastDoneReason() const override {
    return Wire::DoneReason::kNone;
  }

  // No registration table -- this project's actual by-name test trigger
  // is protocol.cpp's own MessageBus RUN bridge (runSlots_/handleRun()),
  // a CODAL-specific mechanism this host-portable class must never
  // touch. Every RUN is ERR_UNKNOWN here, the same wire outcome any name
  // a real registration table would not recognize (protocol.md S6.3).
  Wire::Result onRun(const char* name, const char* const* argv, size_t argc,
                     char* result, size_t resultCapacity,
                     bool& hasResult) override;

 private:
  Wire::Identity identity_;
  Wire::TlmMode mode_ = Wire::TlmMode::kOff;
};

}  // namespace diffDrive
