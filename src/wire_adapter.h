// wire_adapter.h -- diffDrive::WireAdapter: the concrete Wire::Adapter
// (src/wire_handler.h) that closes the seam for THIS robot -- this
// project's analogue of radio-robot-lib's Protocol::DiffDriveAdapter
// (radio-robot-lib/docs/design/protocol.md S5). Sprint 003 ticket 004
// scope: WHEELS_V gets real effect (the only motion verb this robot's
// current shims.cpp/Rig surface could already execute without a
// planner). Ticket 011 (this file, now) adds WHEELS_X/MOVE_X, routed
// onto motion_engine.h's MotionEngine (tickets 006/007) via shims.cpp's
// engineWheelsX()/engineMoveX() forward declarations (wire_adapter.cpp).
// MOVE_V/GO_TO_R/GO_TO_W still answer Result::kUnknown -- an honest,
// DELIBERATE "this adapter has no route for this verb yet" result, not
// a stub left unfinished (protocol.md S9.10 item 1's own precedent: an
// adapter with no registration table answers kUnknown for exactly this
// reason, matching this class's own onRun() posture below). Ticket 012
// gives MOVE_V/GO_TO_R/GO_TO_W real effect (GO_TO_R/GO_TO_W additionally
// need ticket 010's PoseSource wiring for the world-frame form).
//
// Sprint 003 ticket 005 (the hardware transport-seam cutover) extends
// this class with a real clock (see now()'s own comment below) and the
// WHEELS_V motion-obligation tracking that clock makes possible
// (hasLiveMotionObligation()) -- no wire-visible behavior changes; both
// are for protocol.cpp's fiber loop to consume.
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
// now(): sprint 003 ticket 005 (the hardware transport-seam cutover)
// wires a REAL clock read in, supplied at COMPOSITION TIME as a plain
// function pointer (`NowMsFn` below) -- a CODAL-facing composition root
// (protocol.cpp) passes one backed by a real clock; a caller with
// nothing to offer (every existing host test) passes nothing at all and
// gets the default nullptr, so now() keeps returning the same honest 0
// it always has. This is a plain C function pointer, not a CODAL type,
// so this file's own "no pxt.h, no CODAL type" contract holds -- see
// wire_adapter.cpp's now()/hasLiveMotionObligation() for how it's used.
//
// The same clock backs this ticket's other new piece of state: with the
// kernel's own background fiber long gone (shims.cpp, sprint 002 ticket
// 001), WHEELS_V's duration-bound drive command (setWheelsTimed(),
// dispatched from onWheelsV() below) is never actually stepped unless
// something keeps calling tickDrive() while it's outstanding -- exactly
// the problem sprint 002's protocol.cpp already solved once for the old
// binary WHEELS verb (see that file's own "motion-obligation tracking"
// history). This class is the one place that sees every ACCEPTED
// WHEELS_V call, with its real duration, so it tracks the resulting
// deadline here (hasLiveMotionObligation(), private
// motionObligationDeadlineMs_) and exposes it for protocol.cpp's fiber
// loop to poll -- that loop still owns the actual tickDrive() call, a
// CODAL-fiber concern this host-portable class must never touch. With
// no clock wired (nowMs_ == nullptr, every existing host test),
// hasLiveMotionObligation() always answers false -- honest, since there
// is no way to know an elapsed-time answer without one, and no host
// test drives a tick loop that would need it to answer anything else.
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

  // Plain C function pointer, deliberately not std::function -- this
  // file must stay free of anything that could drag in CODAL or
  // heap-allocating machinery. Returns milliseconds on whatever clock
  // the composition root chose; this class only ever computes
  // DIFFERENCES against it (see hasLiveMotionObligation()), so its
  // epoch is unspecified and irrelevant.
  using NowMsFn = uint32_t (*)();

  // `identity`'s own pointer fields are borrowed (Wire::Identity's own
  // doc comment, wire_handler.h): the CALLER's identity strings must
  // outlive this adapter. Copied by value here (copies the pointers,
  // not the strings they point to). `nowMs`, if supplied, must remain
  // valid for this adapter's whole lifetime -- in practice a free
  // function or a static member function, never a capturing closure
  // (the type above cannot express one). Defaults to nullptr for every
  // caller with no real clock to offer (every existing host test).
  explicit WireAdapter(const Wire::Identity& identity,
                       NowMsFn nowMs = nullptr);

  // ---- Wire::Adapter: session ----
  void identity(Wire::Identity& out) const override;
  uint32_t now() const override;
  void status(Wire::StatusFields& out) const override;

  // Sprint 003 ticket 005: lets a composition root supply a PLACEHOLDER
  // Wire::Identity() at construction time (safe -- every field defaults
  // to "", no caller-owned storage borrowed yet) and fill in the real
  // one later, once it is actually safe to read (protocol.cpp calls
  // this from its own fiber body, not from this adapter's own
  // constructor, precisely so a CODAL identity read never happens
  // before uBit.init() has run -- see protocol.cpp's run() for why that
  // timing matters). Same borrowed-pointer contract as the constructor.
  void setIdentity(const Wire::Identity& identity);

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

  // WHEELS_X: real effect (sprint 003 ticket 011) -- forwards onto
  // motion_engine.h's MotionEngine::wheelsX(left, right, cruise,
  // timeoutMs) via shims.cpp's engineWheelsX() (same same-package
  // forward-declaration convention as setWheelsTimed() above). No unit
  // conversion needed here: WHEELS_X's wire fields are already
  // mm/mm/mm-per-s/ms, MotionEngine's own native units -- motion-api.md
  // S9.1's mrad<->rad conversion applies only to MOVE_X's `rotation`,
  // below. `cruise` < 0 is refused outright (kRange): a speed ceiling
  // has no sign. `cruise` == 0 is motion-api.md S1.1's documented "pass
  // 0 for the configured default" sentinel, resolved via shims.cpp's
  // engineDefaultCruiseMmS() (this robot's own configured full-duty
  // velocity, converted to mm/s); if that is ALSO unconfigured (a fresh
  // robot that has never had one set), the resolved cruise is still
  // <= 0 and this refuses with kRange too, rather than silently
  // commanding a zero-speed "move" nobody asked for.
  Wire::Result onWheelsX(float left, float right, float cruise,
                         uint32_t timeout, uint32_t id) override;

  // MOVE_X: real effect (sprint 003 ticket 011) -- forwards onto
  // MotionEngine::moveX(distance, rotationRad, cruise, timeoutMs) via
  // shims.cpp's engineMoveX(). `cruise`'s <0/==0 handling is identical
  // to onWheelsX() above. `rotation` is the ONE place in this codebase
  // where the wire's milliradian-integer angle becomes MotionEngine's
  // native radians (motion-api.md S9.1: "degrees at the API and
  // milliradian integers on the wire ... the conversion lives in the
  // binding, in one place") -- see wire_adapter.cpp's mradToRad() and
  // that file's own comment on why this one multiply gets a dedicated
  // test.
  Wire::Result onMoveX(float distance, float rotation, float cruise,
                       uint32_t timeout, uint32_t id) override;

  // MOVE_V/GO_TO_R/GO_TO_W (motion-api.md S9.1) still need a route this
  // adapter does not have yet (ticket 012: MOVE_V is a plain wheelsV
  // reduction already available via MotionEngine::moveV(); GO_TO_R/
  // GO_TO_W additionally need ticket 010's PoseSource wiring for the
  // world-frame form) -- every one of them answers kUnknown, the SAME
  // wire outcome onRun() below already answers for any name (protocol.md
  // S9.10 item 1's own precedent: "an Adapter with no registration
  // table ... has an empty allowlist"). This is honest, not a stub left
  // unfinished: this adapter has no route to wire these onto yet.
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

  // ---- sprint 003 ticket 005: motion-obligation tracking, NOT part of
  // Wire::Adapter's own interface -- see this file's header comment for
  // the full rationale. true iff a WHEELS_V accepted by onWheelsV() is
  // still within its commanded duration, per the clock supplied at
  // construction; always false with no clock wired (nowMs == nullptr).
  bool hasLiveMotionObligation() const;

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

  // ---- sprint 003 ticket 005: real clock + motion-obligation state ----
  NowMsFn nowMs_ = nullptr;
  bool motionObligationActive_ = false;
  uint32_t motionObligationDeadlineMs_ = 0;  // [ms], nowMs_'s own scale
};

}  // namespace diffDrive
