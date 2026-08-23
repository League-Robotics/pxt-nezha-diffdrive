// wire_adapter.h -- diffDrive::WireAdapter: the concrete Wire::Adapter
// (src/wire_handler.h) that closes the seam for THIS robot -- this
// project's analogue of radio-robot-lib's Protocol::DiffDriveAdapter
// (radio-robot-lib/docs/design/protocol.md S5), except this project's
// own motion issue requires ALL SIX motion verbs to have real effect,
// unlike DiffDriveAdapter's own deliberate "WHEELS_V real, five
// kUnknown" posture. Sprint 003 ticket 004: WHEELS_V. Ticket 011:
// WHEELS_X/MOVE_X, routed onto motion_engine.h's MotionEngine (tickets
// 006/007) via shims.cpp's engineWheelsX()/engineMoveX() forward
// declarations (wire_adapter.cpp). Ticket 012 (this file, now):
// MOVE_V/GO_TO_R/GO_TO_W, completing the six-verb motion surface --
// MOVE_V is a plain wheelsV reduction (engineMoveV()); GO_TO_R forwards
// onto MotionEngine::goToR() (engineGoToR()); GO_TO_W additionally needs
// a live PoseSource (ticket 010) -- engineGoToW() bridges to shims.cpp's
// own OTOS lazy singleton (gOtos/otosRef()) and reports back whether one
// was actually available (see onGoToW()'s own doc comment below for what
// this class answers when it is not). Every one of the six motion verbs
// now has real effect on this class -- the DiffDriveAdapter-style "no
// planner" kUnknown no longer applies to any of them (onRun() below is
// the only remaining honest kUnknown on this class, for an unrelated
// reason -- see its own doc comment).
//
// Sprint 003 ticket 005 (the hardware transport-seam cutover) extends
// this class with a real clock (see now()'s own comment below) and
// motion-obligation tracking (hasLiveMotionObligation()) that clock
// makes possible -- no wire-visible behavior changes; both are for
// protocol.cpp's fiber loop to consume. Ticket 004 armed this ONLY from
// onWheelsV(); ticket 012 arms it from every one of the six motion
// handlers below -- see hasLiveMotionObligation()'s own comment for a
// real bug ticket 011 left behind, and how this ticket fixes it.
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
// nothing to offer (every host test before ticket 012's own waNowMs())
// passes nothing at all and gets the default nullptr, so now() keeps
// returning the same honest 0 it always has. This is a plain C function
// pointer, not a CODAL type, so this file's own "no pxt.h, no CODAL
// type" contract holds -- see wire_adapter.cpp's
// now()/hasLiveMotionObligation() for how it's used.
//
// The same clock backs this ticket's other new piece of state: with the
// kernel's own background fiber long gone (shims.cpp, sprint 002 ticket
// 001), NONE of the six motion verbs' accepted commands are ever
// actually stepped unless something keeps calling tickDrive() while one
// is outstanding -- exactly the problem sprint 002's protocol.cpp
// already solved once for the old binary WHEELS verb (see that file's
// own "motion-obligation tracking" history). This class is the one
// place that sees every ACCEPTED motion verb, with its own duration or
// timeout, so it tracks the resulting deadline here
// (hasLiveMotionObligation(), private motionObligationDeadlineMs_) and
// exposes it for protocol.cpp's fiber loop to poll -- that loop still
// owns the actual tickDrive() call, a CODAL-fiber concern this
// host-portable class must never touch. With no clock wired (nowMs_ ==
// nullptr, every host test before ticket 012), hasLiveMotionObligation()
// always answers false -- honest, since there is no way to know an
// elapsed-time answer without one.
//
// Ticket 004/005 armed this ONLY from onWheelsV() -- correct as far as
// it went (WHEELS_V's own `duration` IS the kernel's own lease,
// motion-api.md S3.2). Ticket 011 then added WHEELS_X/MOVE_X's real
// dispatch WITHOUT also arming this flag from either handler -- a real
// bug, found while implementing this ticket: with the flag armed only
// by WHEELS_V, protocol.cpp's fiber loop (see that file's own run())
// never calls tickDrive() for any other motion verb, so on hardware a
// WHEELS_X/MOVE_X/MOVE_V/GO_TO_R/GO_TO_W accepted by this class is
// committed to the kernel and then never serviced by anything except
// the starvation watchdog's ~100-150 ms port-level stop (shims.cpp's
// own "Move-completion stop delivery" comment) -- the move aborts
// almost immediately instead of actually running. Ticket 012 fixes this
// entirely INSIDE this class (no protocol.cpp change needed): every one
// of onWheelsX()/onMoveX()/onMoveV()/onGoToR()/onGoToW() now arms the
// SAME obligation the way onWheelsV() always has, using its own
// `timeout` (the X-forms/GO_TO-forms) or `duration` (the V-forms) as
// the deadline. For the X-forms/GO_TO-forms this is a conservative
// overestimate of how long the move actually needs (their `timeout` is
// a backstop, not the move's real duration) -- protocol.cpp's fiber may
// keep ticking a little past actual completion, which is harmless
// (serviceMove() is a cheap no-op once the move-engine is idle again),
// not a correctness problem.
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
  // this adapter. Shared by MOVE_V (sprint 003 ticket 012) -- the
  // identical "duration IS the lease" V-form rationale applies
  // (motion-api.md S3.4: "duration is required and is the lease,
  // exactly as in wheels_v").
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

  // MOVE_V: real effect (sprint 003 ticket 012) -- the plain wheelsV
  // reduction (motion-api.md S2: move_v(v_x, omega) == wheels_v(v_x -
  // omega*b/2, v_x + omega*b/2)), forwarded onto motion_engine.h's
  // MotionEngine::moveV() via shims.cpp's engineMoveV() (same
  // forward-declaration convention as engineWheelsX()/engineMoveX()
  // above). `omega` is the wire's OTHER milliradian-integer angle field
  // (motion-api.md S9.1: degrees at the API, milliradians on the wire,
  // for any angle or angular RATE) -- converted via the SAME
  // mradToRad() seam MOVE_X's `rotation` uses (wire_adapter.cpp).
  // `duration` shares WHEELS_V's own ceiling (kWheelsVDurationCeiling)
  // and identical "duration IS the lease, a dead host cannot mean a
  // runaway" rationale -- move_v is a V-form exactly like wheels_v
  // (motion-api.md S3.4).
  Wire::Result onMoveV(float v_x, float omega, uint32_t duration,
                       uint32_t id) override;

  // GO_TO_R: real effect (sprint 003 ticket 012) -- forwards onto
  // MotionEngine::goToR() via shims.cpp's engineGoToR(). `speed` plays
  // the same role for go_to_r's underlying moveX() call that `cruise`
  // plays for onWheelsX()/onMoveX() above (motion_engine.h: "speed is
  // the resulting moveX() call's cruise") -- identical <0/==0 handling:
  // refused outright (kRange) if negative, substituted with
  // engineDefaultCruiseMmS() if zero, refused (kRange) if that
  // substitution is ALSO unconfigured. `arrive`/`timeout` pass straight
  // through unmodified -- MotionEngine::goToR() itself ignores `arrive`
  // (a single-shot reduction, not the supervisory re-solving loop
  // motion-api.md S3.5 describes; sprint.md's own Design Rationale) and
  // uses `timeout` as moveX()'s own real backstop, same as MOVE_X.
  Wire::Result onGoToR(float x, float y, float speed, float arrive,
                       uint32_t timeout, uint32_t id) override;

  // GO_TO_W: real effect (sprint 003 ticket 012) -- the world-frame
  // counterpart, forwarded onto MotionEngine::goToW() via shims.cpp's
  // engineGoToW(). Same `speed` <0/==0 handling as onGoToR() above.
  // GO_TO_W additionally needs a live PoseSource (motion_engine.h,
  // ticket 010) -- engineGoToW() bridges to shims.cpp's own OTOS lazy
  // singleton and reports back (via its bool return) whether one was
  // actually available. motion-api.md S3.6 describes an
  // encoder-odometry fallback for a robot with no OTOS fitted at all;
  // ticket 010's own Description states that fallback is explicitly out
  // of scope and not built, so "no OTOS fitted, or fitted but never
  // begun/connected" is a REAL reachable state on this fleet, not a
  // theoretical one. DECISION (this ticket's own acceptance criteria
  // require one, made explicitly): this method answers
  // Wire::Result::kUnimplemented in that case -- protocol.md S6.1's own
  // documented meaning for that code, "recognized, not wired on this
  // build," is exactly this situation (GO_TO_W is a real, decoded verb;
  // THIS robot/build simply has no OTOS wired in to service it) --
  // rather than kRange (nothing about the ARGUMENTS is out of range) or
  // kNotReady (protocol.md's own "refused pre-ready" is a robot-wide
  // startup gate, not a per-verb missing-hardware condition). Refusing
  // this way is what keeps this method from silently driving toward a
  // garbage/zeroed pose when no sensor backs it.
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

  // ---- sprint 003 ticket 005 (armed by every one of the six motion
  // verbs as of ticket 012 -- see this file's header comment for the
  // full rationale, including the bug ticket 011 left and ticket 012
  // fixed): NOT part of Wire::Adapter's own interface. True iff the
  // most recently ACCEPTED motion verb's own duration/timeout window,
  // per the clock supplied at construction, has not yet elapsed; always
  // false with no clock wired (nowMs == nullptr).
  bool hasLiveMotionObligation() const;

  // No motion queue and no completion event on this adapter yet.
  // DECISION (sprint 003 ticket 012, explicitly revisited per that
  // ticket's own acceptance criteria): even though MOVE_X/GO_TO_R/
  // GO_TO_W's underlying MotionEngine move DOES have a genuine
  // completion event internally (isMoveActive() going false, tracked
  // move-engine state) unlike WHEELS_V's plain lease-expiry, NONE of it
  // is threaded back through this project's thin, wire-shaped bridge
  // functions (engineWheelsX()/engineMoveX()/engineMoveV()/
  // engineGoToR()/engineGoToW(), all void or availability-only in their
  // return value) -- and this class deliberately holds no reference of
  // its own to MotionEngine (sprint.md's own Design Rationale: `engine`
  // stays a shims.cpp-owned singleton, reached only through
  // forward-declared free functions, so wire_adapter.cpp and shims.cpp
  // stay decoupled from each other). Building a real completion channel
  // would mean either breaking that boundary or giving every bridge
  // function a stateful "how did the LAST call end" return value no
  // wire host has asked for yet -- out of this ticket's scope. Both
  // methods therefore keep reporting the inert default for every one of
  // the six verbs, matching DiffDriveAdapter's own posture for the
  // identical reason (protocol.md S8.8.1) -- a deliberate, documented
  // choice, not an oversight, and a natural candidate to revisit once a
  // real use case needs `lastDone()`/`lastDoneReason()` to mean
  // something.
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

  // ---- sprint 003 ticket 005: real clock + motion-obligation state
  // (armed by every one of the six motion verbs as of ticket 012) ----
  NowMsFn nowMs_ = nullptr;
  bool motionObligationActive_ = false;
  uint32_t motionObligationDeadlineMs_ = 0;  // [ms], nowMs_'s own scale
};

}  // namespace diffDrive
