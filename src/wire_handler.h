// wire_handler.h -- Wire::WireHandler: protocol v6's ASCII line-grammar
// mechanics (radio-robot-lib/docs/design/protocol.md S2, S2.1, S3.1,
// S3.2) PLUS the reliability layer (S8, S8.9 -- the canonical spec; this
// project conforms to that grammar, it does not vendor radio-robot-lib's
// C++). feed() reassembles arbitrary byte blocks into '\n'-terminated
// lines, tokenizes each line in place on runs of ' ' (no allocation, no
// std::string -- S3.2), enforces case-as-direction (S2.1: commands
// UPPERCASE, replies lowercase, verb lookup case-SENSITIVE), and
// dispatches every verb this project currently implements: the three
// unsequenced exemptions (HELLO, PING, ESTOP -- S8.3) plus the nine
// non-motion sequenced verbs (ID, VER, STATUS, HELP, GET, SET, TLM,
// STOP, RUN).
//
// ---- The reliability layer (S8), in one paragraph ----
//
// Every sequenced verb carries a MANDATORY trailing id, `#<n>`, that is
// also a strictly incrementing sequence number starting at 1. Handler
// state is EXACTLY two values -- expectedNext_ (next id expected) and
// gapOutstanding_ (a nack is currently owed, S8.5) -- deliberately no
// clock and no timer anywhere (S8.1): feed() stays a pure function of
// its input bytes plus this small state. dispatch() resolves the id
// FIRST, against expectedNext_, classifying every inbound id into
// exactly one of three cases (S8.1's table):
//   - id == expectedNext_ : decode the verb's own fields FIRST (S8.9);
//     only if decoding succeeds does the sequence advance
//     (expectedNext_ = id + 1) and `ack <id> <lastDone> <reason>` go
//     out. A decode failure at this point -- unrecognized verb, wrong
//     arity, or an unparseable field -- does NOT advance the sequence:
//     it replies `nack <expectedNext_> <lastDone> <reason>` (still
//     naming the SAME id, since it was never accepted) plus
//     `err <code> #<id>`, and sets gapOutstanding_ so a stalled stream
//     keeps re-nacking at the application's own telemetry cadence
//     (emitTelemetry(), S8.5) until a well-formed line finally supplies
//     that same id (S8.9 -- "decode failure is a NAK", the central
//     2026-08-22 change: a corrupted leg of a multi-leg routine is
//     resent, not silently skipped).
//   - id < expectedNext_ : a stale retransmit -- the host never saw our
//     ack for something we already accepted. Do NOT re-execute (a
//     resent WHEELS_V must not drive the wheels twice, once motion
//     verbs land); reply `ack <expectedNext_ - 1> <lastDone> <reason>`,
//     the already-accepted id, not the resent one. `#0` is not
//     special-cased anywhere in this file: since expectedNext_ starts
//     at (and never goes below) 1, an inbound `#0` is unconditionally
//     `< expectedNext_` and falls into this bucket with zero extra code.
//   - id > expectedNext_ : a numeric gap -- discard, do NOT execute, and
//     do not even look up the verb; reply
//     `nack <expectedNext_> <lastDone> <reason>` and set
//     gapOutstanding_. A gap stalls the stream ON PURPOSE: every
//     subsequent command, however well-formed, is nacked identically
//     until the missing id arrives.
// A merits rejection -- the verb decoded fine but the Adapter refuses it
// on its own terms (e.g. an out-of-range value) -- is a DIFFERENT case
// from a decode failure: it ACKS and ADVANCES (the line arrived intact),
// paired with `err <code> #<id>` on top of that ack. Decode failure and
// merits rejection are the two cases S8.9 keeps sharply distinct.
//
// `<lastDone>`/`<reason>` are read FRESH off Adapter::lastDone()/
// lastDoneReason() every time an ack/nack is formatted (S8.8) -- there
// is no cached copy anywhere in this class. `err <code> #<id>` orders
// code first, id last (S8.6) -- the id is always a line's LAST token,
// commands and replies alike.
//
// HELLO/ESTOP/PING (S8.3) never carry an id at all and are maximally
// forgiving of trailing content -- see dispatch()'s own comment. HELLO
// additionally resets expectedNext_/gapOutstanding_ (a (re)connecting
// host's own resync point) but does NOT touch the Adapter's
// lastDone()/lastDoneReason() -- that state is Adapter-owned and a
// handler-level reset has no business reaching into it (S8.8).
//
// Sprint 003 ticket 004 adds the six motion verbs (WHEELS_X, WHEELS_V,
// MOVE_X, MOVE_V, GO_TO_R, GO_TO_W) to Adapter and kCommandTable,
// inserted between TLM and STOP per protocol.md S6's own canonical
// ordering (WHEELS is RENAMED WHEELS_V -- there is no bare WHEELS verb
// in this table). Angles (rotation, omega) are milliradian integers on
// the wire (motion-api.md S9.1) -- decoded here with the ordinary
// signed-integer field parser, same as any other field; the
// degrees-at-the-API conversion is a LANGUAGE BINDING's job, not this
// file's. src/wire_adapter.{h,cpp} (also ticket 004) is the concrete
// Adapter behind this handler for this robot: WHEELS_V gets real effect
// there; the other five answer Result::kUnknown, a deliberate,
// documented "no planner yet" (protocol.md S9.10 item 1's own
// precedent), not a stub left unfinished.
//
// Host-portable by construction: no pxt.h, no CODAL type, anywhere in
// this file or wire_handler.cpp. See tests/host/wire_grammar_shim.cpp
// for the native host test harness (ticket 001's compile_shared_lib(),
// extended) this module is exercised through.
#pragma once

#include <cstddef>
#include <cstdint>

namespace Wire {

// Sink -- where finished reply lines go. Exactly one write() per
// formatted line, INCLUDING the trailing '\n'; the caller owns
// transport (serial, radio, or a test's recording buffer). Mirrors
// radio-robot-lib's own Protocol::Sink split (protocol_handler.h) so a
// later ticket wiring this onto SerialTransport/RadioTransport (sprint
// 003 ticket 005) has nothing to redesign here.
class Sink {
 public:
  virtual ~Sink() = default;
  virtual void write(const char* data, size_t length) = 0;
};

// Everything HELLO/ID/VER read off. Every pointer is borrowed: the
// adapter owns the storage (a string literal or a robot-config field)
// and must keep it alive at least until the identity() call that
// requested it returns. Mirrors radio-robot-lib's own Protocol::Identity
// (adapter.h) -- drivetrain/profile/version join name/serial now that
// ID/VER are wired up (ticket 003; ticket 002 only needed name/serial
// for HELLO's banner).
struct Identity {
  const char* name = "";
  const char* serial = "";
  const char* drivetrain = "";
  const char* profile = "";
  const char* version = "";
};

// STATUS's `k=v` payload. `tlm` is the CURRENT subscription mode's own
// lowercase wire name ("off"/"pose"/"full"/"auto"/"buffer") -- the
// handler does not re-derive it from TlmMode, so an adapter tracking its
// own mode state machine never has to reconcile it against the
// handler's opinion of what "current" means. Mirrors radio-robot-lib's
// own Protocol::StatusFields (adapter.h).
struct StatusFields {
  bool ready = false;
  bool active = false;
  bool connLeft = false;
  bool connRight = false;
  bool otos = false;
  bool wedge = false;
  uint32_t flags = 0;
  // Sprint 004 ticket 004: the I2C fault counter, closing
  // status-lost-diag-numeric-surface.md -- the retired DIAG verb's own
  // most-important numeric field (a wedged/unpowered Nezha brick shows
  // up here as a climbing count, not just a boolean "wedge" flag).
  // Sourced by WireAdapter::status() from the SAME diagValue(8) call
  // the telemetry `i2cf` column also reads, so the two can never
  // disagree (sprint.md's own Design Rationale). Decimal on the wire
  // (execStatus()'s `i2cf=%ld`), unlike `flags`' hex -- a raw fault
  // count has no bitfield meaning to pack.
  int32_t i2cf = 0;
  const char* tlm = "off";
};

// One named, already-scaled telemetry value (protocol.md S5.2: `thdr
// <col>...` then `t <v>...`). Mirrors radio-robot-lib's own
// Column shape (src/protocol/adapter.h:113-139) -- this project's own
// value type, not a vendored copy. `value` is always an
// already-scaled plain integer -- this class has no opinion on what a
// column MEANS or how it was derived, only how it prints: `hex` picks
// lowercase hex with no `0x` prefix (flags-shaped columns); everything
// else prints signed base-10.
struct Column {
  const char* name = "";
  int32_t value = 0;
  bool hex = false;
};

// One telemetry frame's worth of columns (protocol.md S5.2). `columns`
// is BORROWED: the caller (WireAdapter::buildSnapshot(), ticket 004)
// owns the backing array and must keep it alive only for the duration
// of the emitTelemetry(snapshot) call it is passed to -- WireHandler
// copies what it needs for its own header memo (see kMaxHeaderColumns/
// kMaxHeaderNameBytes below) and formats the rest immediately, keeping
// no borrowed pointer alive past that one call. Mirrors radio-robot-
// lib's own Snapshot shape (adapter.h:113-139).
struct Snapshot {
  const Column* columns = nullptr;
  size_t count = 0;
};

// Maps 1:1 onto the wire outcome (protocol.md S4; wire codes per S6.1).
// There is no kDuplicateId: the handler's own strict sequencing already
// makes a duplicate id structurally unreachable by any Adapter call
// (S2.2/S8.1's retransmit row never dispatches), so the wire's own error
// code 11 (ERR_DUPLICATE_ID) does not exist here at all -- it is
// deleted, not merely unused.
enum class Result : uint8_t {
  kOk,             // -> the ack alone; no further reply
  kUnknown,        // -> err 1 #<id>   ERR_UNKNOWN
  kBadArg,         // -> err 2 #<id>   ERR_BADARG
  kRange,          // -> err 3 #<id>   ERR_RANGE
  kFull,           // -> err 4 #<id>   ERR_FULL
  kUnimplemented,  // -> err 6 #<id>   ERR_UNIMPLEMENTED
  kNotReady,       // -> err 8 #<id>   ERR_NOT_CONFIGURED
  kBusy,           // -> err 10 #<id>  ERR_BUSY
};

// TLM subscription modes (S6.1's wire token set). The handler only
// decodes the wire token ("OFF"/"POSE"/"FULL"/"NOW"/"AUTO"/"BUFFER")
// into this enum and hands it to onTlm() -- what each mode DOES is
// entirely the adapter's business.
enum class TlmMode : uint8_t {
  kOff,
  kPose,
  kFull,
  kNow,
  kAuto,
  kBuffer,
};

// The reliability layer's completion-reason vocabulary (S8.8): the four
// reasons a motion can finish, plus kNone for "nothing has completed
// yet" -- the wire spelling "none" is what lastDone() == 0 pairs with.
// Carried here even though this ticket wires up no motion verb yet,
// because every sequenced verb's ack/nack piggybacks this pair (S8.8),
// not only the motion ones.
enum class DoneReason : uint8_t {
  kNone,     // -> "none"    -- lastDone() == 0, nothing completed yet
  kStop,     // -> "stop"    -- the stop condition was met, or stop() ended it
  kTimeout,  // -> "timeout" -- the backstop fired
  kEstop,    // -> "estop"   -- a panic stop ended it
  kAborted,  // -> "aborted" -- the caller abandoned it
};

// Adapter -- the seam behind every verb this file currently dispatches:
// identity (HELLO/ID/VER), a clock (PING), an ESTOP hook, STATUS's own
// fields, GET/SET's field table, TLM's mode hook, STOP, RUN's
// invoke-by-name, and the reliability layer's completion channel
// (lastDone()/lastDoneReason(), polled fresh on every ack/nack, S8.8).
//
// This is NOT sprint.md's own src/wire_adapter.{h,cpp} module (this file
// only declares the CONTRACT; src/wire_adapter.h's WireAdapter, ticket
// 004, is the production implementation, backed by this robot's real
// identity/config/shims.cpp surface) -- it is this file's OWN seam,
// satisfied in tests by tests/host/wire_mock_adapter.h's WireMockAdapter
// (a recording test double, never linked into production code). Ticket
// 004 widened this interface with the six motion methods (onWheelsV/
// onWheelsX/onMoveX/onMoveV/onGoToR/onGoToW) radio-robot-lib's own
// Adapter (adapter.h) already declares -- see each method's own doc
// comment below for its exact wire units.
class Adapter {
 public:
  virtual ~Adapter() = default;

  // ---- session ----
  virtual void identity(Identity& out) const = 0;
  virtual uint32_t now() const = 0;  // [ms], for PING's `pong <now>`
  virtual void status(StatusFields& out) const = 0;

  // ---- motion: the six verbs (motion-api.md S9.1, sprint 003 ticket
  // 004). Angles (rotation, omega) arrive already decoded from the
  // wire's milliradian integers into float milliradians -- degrees-at-
  // the-API is a LANGUAGE BINDING's conversion, not this seam's. ----
  virtual Result onWheelsV(float left, float right,  // [mm/s] [mm/s]
                           uint32_t duration,          // [ms]
                           uint32_t id) = 0;
  virtual Result onWheelsX(float left, float right,  // [mm] [mm]
                           float cruise,               // [mm/s]
                           uint32_t timeout,            // [ms]
                           uint32_t id) = 0;
  virtual Result onMoveX(float distance, float rotation,  // [mm] [mrad]
                        float cruise, uint32_t timeout,    // [mm/s] [ms]
                        uint32_t id) = 0;
  virtual Result onMoveV(float v_x, float omega,        // [mm/s] [mrad/s]
                        uint32_t duration, uint32_t id) = 0;  // [ms]
  virtual Result onGoToR(float x, float y, float speed,   // [mm] [mm] [mm/s]
                        float arrive, uint32_t timeout,    // [mm] [ms]
                        uint32_t id) = 0;
  virtual Result onGoToW(float x, float y, float speed,
                        float arrive, uint32_t timeout,
                        uint32_t id) = 0;

  // ---- safety ----
  virtual void onEstop() = 0;
  // `immediate` is STOP's own optional `now` token (a deceleration
  // CHOICE, not a different verb) -- an adapter with no ramp of its own
  // is free to treat both identically.
  virtual Result onStop(bool immediate, uint32_t id) = 0;

  // ---- configuration -- pure delegation, no storage in this file
  // (protocol.md S7: which names are valid is entirely the adapter's
  // business) ----
  virtual bool onGet(const char* name, float& out) const = 0;
  virtual Result onSet(const char* name, float value, uint32_t id) = 0;
  virtual size_t fieldCount() const = 0;  // for a bare GET
  virtual const char* fieldName(size_t index) const = 0;

  // ---- telemetry ----
  virtual Result onTlm(TlmMode mode) = 0;

  // ---- the reliability layer's completion channel (S8.8) -- POLLED
  // fresh by this class every time it formats an ack/nack line; no
  // callback, no clock, no cached copy anywhere in WireHandler. An
  // adapter with no completion event of its own returns 0/kNone
  // forever, which is wire-correct even though it is functionally inert
  // on that adapter. ----
  virtual uint32_t lastDone() const = 0;
  virtual DoneReason lastDoneReason() const = 0;

  // ---- invocation by name (protocol.md's RUN section) -- this class
  // holds no function table, does no name resolution, and does no type
  // conversion; it only parses "RUN <name> [arg...] #id" into a name and
  // the RAW, unconverted argument tokens that followed it, and hands
  // them here unchanged. See the .cpp's execRun() for the full contract
  // (borrowed pointers, sanitization of the returned text, synchronous
  // invocation). ----
  virtual Result onRun(const char* name, const char* const* argv, size_t argc,
                       char* result, size_t resultCapacity,
                       bool& hasResult) = 0;
};

class WireHandler {
 public:
  // Wire line ceiling, protocol.md S2: "Max line: 240 bytes including
  // the terminator." The handler sizes its buffer off this one
  // constant so the number is spelled exactly once.
  static constexpr size_t kMaxLineBytes = 240;

  WireHandler(Adapter& adapter, Sink& sink);

  // Feed an arbitrary block from the port -- may contain zero, one, or
  // several complete lines, and may end mid-line. Partial lines are
  // buffered across calls; complete lines are parsed and dispatched
  // immediately, in the order they complete. Must survive (protocol.md
  // S2, S3.1):
  //   - several complete lines in one block;
  //   - a block ending mid-line (the remainder is buffered to the next
  //     feed() call);
  //   - a block that is only a line fragment;
  //   - a lone '\r' immediately before '\n' (stripped as a terminal
  //     artifact; '\r' appears nowhere else on the wire);
  //   - a blank or all-whitespace line (ignored SILENTLY -- a terminal
  //     artifact, not an error; does NOT count malformed);
  //   - a line longer than the 240-byte maximum: discarded to the next
  //     '\n' and counted malformed -- NEVER truncated into a
  //     still-parseable prefix that would be a command the host never
  //     sent;
  //   - embedded NULs, arbitrary binary garbage, or a multi-KB blast
  //     with no newline at all (bounded by the fixed line buffer and
  //     the overflow rule above; never overflows, never allocates).
  //
  // A characterization note on embedded NULs, carried over from
  // radio-robot-lib's own protocol.md S9.4: every wire-touching
  // comparison here (verb lookup, tokenizing) runs on a NUL-terminated
  // C string, per the no-allocation, no-std::string constraint (S3.2).
  // A NUL byte anywhere inside a line therefore acts as an early
  // terminator for THIS line only -- e.g. "PING\0extra\n" dispatches
  // exactly like a bare "PING\n", silently discarding "extra" with no
  // malformed-count increment -- rather than being rejected outright.
  // This is a known, pinned characterization (see
  // test_embedded_nul_immediately_after_verb_matches_bare_verb in
  // tests/host/test_wire_grammar.py), not a bug: a real fix would mean
  // abandoning C-string comparisons throughout the parser, in tension
  // with the no-std::string firmware constraint this file is written
  // to. The one place this class does NOT just let the C-string view
  // win silently: a line whose first non-space byte IS the embedded
  // NUL (e.g. "\0PING\n") would otherwise leave the tokenizer's own
  // internal token array uninitialized (a real memory-safety hazard,
  // not just a surprising parse) -- wire_handler.cpp's onLineComplete()
  // guards this explicitly and counts it malformed instead.
  void feed(const char* data, size_t length);

  // HELLO's reply, byte-identical to the unsolicited boot banner a
  // caller would send at connect time (protocol.md S4/S6):
  // "device NEZHA2 robot <name> <serial>\n".
  void sendBanner();

  // The telemetry frame (protocol.md S5.2): emits, in order, as THREE
  // separate Sink::write() calls (never concatenated into one) --
  //   1. `thdr <col>...\n`, but only when a fresh header is DUE (see
  //      below);
  //   2. `t <v>...\n`, always, one value per column in `snapshot`, in
  //      the same order as the most recently emitted header;
  //   3. emitReliability()'s own ack/nack keepalive (see its own doc
  //      comment) -- so a telemetry subscriber never has to poll a
  //      second entry point to also learn whether its last command
  //      landed.
  // A fresh header is DUE when: this is the very first call ever made
  // on this instance; the column set changed since the last header
  // (count, any column's name, OR any column's hex-ness -- a memo that
  // compared only names/count would miss a hex-ness-only flip); or
  // kHeaderRefreshFrames calls have elapsed since the last header,
  // whichever comes first. That last case is what keeps a late-
  // attaching listener over a lossy broadcast radio from being
  // permanently locked out of decoding (sprint.md SUC-004) -- it has
  // nothing to do with the column set changing at all.
  //
  // `snapshot`'s backing array is borrowed only for the duration of
  // this call; this class copies what it needs of it (the header memo)
  // and touches nothing else afterward.
  void emitTelemetry(const Snapshot& snapshot);

  // The reliability layer's own periodic emission (protocol.md S8.5):
  // "nack <expectedNext_> <lastDone> <reason>" if gapOutstanding_ is
  // set, "ack <expectedNext_ - 1> <lastDone> <reason>" otherwise, with
  // <lastDone>/<reason> read FRESH off the Adapter, same as every other
  // ack/nack this class formats. The application drives this call on
  // whatever cadence it already has -- this class adds NO timer and NO
  // clock of its own to make it happen (S8.1's own constraint). This is
  // what lets a lost ack/nack self-heal: as long as this is called
  // regularly, a stalled gap keeps producing fresh nacks, and a quiet
  // host still eventually learns its last command landed.
  //
  // Callable completely independent of any Snapshot -- carries what
  // used to be emitTelemetry()'s entire body, verbatim, now split out
  // so this keepalive survives `TLM OFF` (no Snapshot to project, but
  // the reliability layer must keep going regardless).
  // emitTelemetry(snapshot) above calls this internally as its own
  // third step; a caller with nothing to project (or no subscriber at
  // all) is free to call this alone.
  void emitReliability();

  // Lines dropped as: an unrecognized verb or one this file does not
  // (yet) implement, wrong arity, an unparseable field, a sequenced
  // verb whose mandatory id was missing or malformed, or an overlong
  // line (discarded to the next '\n'). This INCLUDES a decode failure on
  // an in-order sequenced id (protocol.md S8.9) -- unlike a numeric gap
  // (id > expectedNext_) or a stale retransmit (id < expectedNext_),
  // NEITHER of which is ever counted here, since neither one's content
  // is ever even inspected. A lowercase-led inbound verb -- another
  // robot's reply overheard on a shared channel, S2.1 -- is dropped
  // silently and does NOT increment this, and neither does a
  // blank/all-whitespace line.
  uint32_t malformedCount() const { return malformedCount_; }

 private:
  void appendByte(char c);
  void onLineComplete();

  // Splits `line` (already NUL-terminated) into tokens in place on runs
  // of ' ', collapsing separators and ignoring leading/trailing
  // whitespace (protocol.md S2/S3.2). Returns the TRUE total token
  // count (verb included), which may exceed `maxTokens` -- only the
  // first `maxTokens` pointers are stored.
  static size_t tokenizeLine(char* line, char** tokens, size_t maxTokens);

  // Resolves the mandatory trailing id against expectedNext_ (protocol.md
  // S8.1), decodes the verb's own fields BEFORE sending any reply at all
  // for the in-order case (S8.9), and dispatches. `lastFieldToken` is
  // the line's raw last token (verb included), found by a backward scan
  // done BEFORE tokenizeLine() mutates the line -- see the .cpp's
  // findLastFieldToken() for why. nullptr means the line was just the
  // verb, with nothing after it to resolve an id from.
  void dispatch(char* verb, char** fields, size_t fieldCount,
                const char* lastFieldToken);

  // A DECODE FAILURE on an in-order id (protocol.md S8.9): the sequence
  // does NOT advance -- `id` is still expectedNext_ (that equality is
  // what routed dispatch() into this function at all), so nacking
  // expectedNext_ unchanged tells the host to resend EXACTLY this id.
  void handleDecodeFailure(uint32_t id, uint8_t code);
  void replyAck(uint32_t ackedId);   // "ack <ackedId> <lastDone> <reason>\n"
  void replyNack(uint32_t nextId);   // "nack <nextId> <lastDone> <reason>\n"
  void replyErr(uint32_t id, uint8_t code);  // "err <code> #<id>\n" (S8.6)
  void writeLine(const char* text);  // one Sink::write() per line
  static uint8_t resultCode(Result result);
  static const char* doneReasonWireName(DoneReason reason);

  void handleHello();
  void handlePing();
  void handleEstop();

  // Every DECODE function is pure: no adapter call, no sink write, no
  // mutation of handler state. It answers exactly one question -- "does
  // this line's own content parse?" -- so dispatch() can decide
  // ack-vs-nack BEFORE anything with a wire or Adapter side effect runs
  // (protocol.md S8.9). Returns false (a DECODE FAILURE) for wrong arity
  // or an unparseable field; true otherwise. `fields`/`fieldCount` here
  // EXCLUDE the id (already resolved and stripped by dispatch()).
  using DecodeFn = bool (WireHandler::*)(char** fields, size_t fieldCount);

  // Every EXECUTE function runs ONLY after dispatch() has already
  // decided the line decodes AND has already sent the `ack` for it -- so
  // an execute function is free to write informational reply lines
  // (id/ver/status/help/get/ret) directly to the sink; nothing it does
  // can race the ack that must precede those lines on the wire. It
  // reports any ADAPTER-level (merits) rejection through `errCode` (0 ==
  // kOk == no err line; nonzero == the wire code dispatch() will emit as
  // `err <errCode> #<id>` right after whatever this function itself
  // already wrote).
  using ExecuteFn = void (WireHandler::*)(char** fields, size_t fieldCount,
                                          uint32_t id, uint8_t& errCode);

  struct VerbEntry {
    const char* name;
    DecodeFn decode;
    ExecuteFn execute;
  };

  // HELLO/PING/ESTOP's own rows are trivial stand-ins (decodeAlwaysTrue/
  // execNoop) NEVER actually invoked through this table -- dispatch()
  // intercepts all three by verb identity before any id is even looked
  // at (protocol.md S8.3). They are still present here purely so HELP's
  // generated listing (execHelp()) walks ONE table for every verb name
  // this file knows about and cannot drift from the dispatcher. Ticket
  // 004 inserted the six motion verbs between TLM and STOP, matching
  // protocol.md S6's own canonical ordering.
  static const VerbEntry kCommandTable[18];

  // Field-token storage cap for one line, verb-exclusive (id excluded --
  // it is resolved separately, see dispatch()'s own comment). Every
  // fixed-arity verb this file wires up has at most 5 data fields
  // (GO_TO_R/GO_TO_W's x/y/speed/arrive/timeout) -- comfortably inside
  // this cap. RUN is the one exception: its arity is open-ended, so this
  // cap doubles as RUN's own hard ceiling on how many raw DATA tokens it
  // will trust fields[] to hold pointers for at all -- decodeRun()
  // checks its own fieldCount against this constant BEFORE indexing
  // fields[].
  static constexpr size_t kMaxFieldTokens = 20;

  // RUN's own ceiling on how many ARGUMENTS (excluding the function
  // name) it will forward to onRun() -- a firmware resource limit (the
  // fixed argv[] array execRun() builds on the stack), not a claim about
  // any real function's arity.
  static constexpr size_t kMaxRunArgs = 16;

  // RUN's stringified return value -- an ARRAY SIZE (content bytes plus
  // the NUL terminator), sized so the WHOLE reply line -- "ret " + this
  // text + " #<id>" at id's maximum width (a 10-digit uint32_t) + '\n'
  // -- can never exceed kMaxLineBytes even before execRun()'s own
  // sanitize pass, which can only shrink the text further, never grow
  // it.
  static constexpr size_t kMaxRunResultBytes =
      kMaxLineBytes - 4 /* "ret " */ - 12 /* " #4294967295" */;

  // ---- per-verb decode/execute pairs -- see DecodeFn/ExecuteFn's own
  // comments above for the shared contract. ----
  bool decodeNoFields(char** fields, size_t fieldCount);
  void execId(char** fields, size_t fieldCount, uint32_t id, uint8_t& errCode);
  void execVer(char** fields, size_t fieldCount, uint32_t id,
              uint8_t& errCode);
  void execStatus(char** fields, size_t fieldCount, uint32_t id,
                  uint8_t& errCode);
  void execHelp(char** fields, size_t fieldCount, uint32_t id,
               uint8_t& errCode);

  bool decodeGet(char** fields, size_t fieldCount);
  void execGet(char** fields, size_t fieldCount, uint32_t id,
              uint8_t& errCode);

  bool decodeSet(char** fields, size_t fieldCount);
  void execSet(char** fields, size_t fieldCount, uint32_t id,
              uint8_t& errCode);

  bool decodeTlm(char** fields, size_t fieldCount);
  void execTlm(char** fields, size_t fieldCount, uint32_t id,
              uint8_t& errCode);

  // ---- motion: WHEELS_X / WHEELS_V / MOVE_X / MOVE_V / GO_TO_R /
  // GO_TO_W (motion-api.md S9.1's wire mapping, sprint 003 ticket 004).
  // Every decode function here is a plain arity + signed/unsigned-
  // integer-field-parseability check, same DecodeFn contract as every
  // other verb; every exec function re-parses the same fields (decode
  // already proved they succeed) and forwards them to the Adapter as
  // floats, the same "wire integer -> float for arithmetic convenience"
  // pattern WHEELS_V's own left/right fields already used before
  // motion-api.md's other five verbs existed on this wire. ----
  bool decodeWheelsX(char** fields, size_t fieldCount);
  void execWheelsX(char** fields, size_t fieldCount, uint32_t id,
                   uint8_t& errCode);

  bool decodeWheelsV(char** fields, size_t fieldCount);
  void execWheelsV(char** fields, size_t fieldCount, uint32_t id,
                   uint8_t& errCode);

  bool decodeMoveX(char** fields, size_t fieldCount);
  void execMoveX(char** fields, size_t fieldCount, uint32_t id,
                uint8_t& errCode);

  bool decodeMoveV(char** fields, size_t fieldCount);
  void execMoveV(char** fields, size_t fieldCount, uint32_t id,
                uint8_t& errCode);

  bool decodeGoToR(char** fields, size_t fieldCount);
  void execGoToR(char** fields, size_t fieldCount, uint32_t id,
                uint8_t& errCode);

  // Identical field shape to GO_TO_R (motion-api.md S9.1) -- decodeGoToW
  // simply delegates to decodeGoToR; execGoToW is its own function only
  // because it must call onGoToW(), not onGoToR().
  bool decodeGoToW(char** fields, size_t fieldCount);
  void execGoToW(char** fields, size_t fieldCount, uint32_t id,
                uint8_t& errCode);

  bool decodeStop(char** fields, size_t fieldCount);
  void execStop(char** fields, size_t fieldCount, uint32_t id,
               uint8_t& errCode);

  bool decodeRun(char** fields, size_t fieldCount);
  void execRun(char** fields, size_t fieldCount, uint32_t id,
              uint8_t& errCode);

  // Trivial stand-ins for HELLO/PING/ESTOP's own kCommandTable rows --
  // see kCommandTable's own comment for why these exist but are never
  // actually invoked.
  bool decodeAlwaysTrue(char** fields, size_t fieldCount);
  void execNoop(char** fields, size_t fieldCount, uint32_t id,
               uint8_t& errCode);

  // ---- telemetry header memo (protocol.md S5.2, sprint.md Phase B) --
  // headerChanged() decides whether emitTelemetry() owes a fresh
  // `thdr`; rememberHeader() then copies the just-emitted header's own
  // shape into headerNames_/headerHex_/headerCount_ so the NEXT call
  // has something to compare against. Deliberately a COPY, not a
  // borrowed pointer into the caller's own Snapshot -- the caller is
  // free to mutate or destroy its own Column array the instant
  // emitTelemetry() returns; this memo must not care. ----
  bool headerChanged(const Snapshot& snapshot) const;
  void rememberHeader(const Snapshot& snapshot);
  void emitHeader(const Snapshot& snapshot);  // "thdr <col>...\n"
  void emitFrame(const Snapshot& snapshot);   // "t <v>...\n"

  Adapter& adapter_;
  Sink& sink_;

  char lineBuf_[kMaxLineBytes] = {};
  size_t lineLen_ = 0;
  bool overflowing_ = false;
  uint32_t malformedCount_ = 0;

  // ---- the reliability layer's own state (protocol.md S8.1) -- exactly
  // these two fields, and deliberately NO clock/timer. `lastDone_` is
  // NOT here: it lives on the Adapter (S8.8), polled fresh on every
  // ack/nack, never cached on this class. ----
  uint32_t expectedNext_ = 1;    // next sequence id expected from the host
  bool gapOutstanding_ = false;  // a nack is currently owed (S8.5)

  // ---- telemetry header memo state (protocol.md S5.2) -- a COPY of
  // the most recently emitted header's shape, sized generously above
  // any realistic column set (sprint.md's own widest set, POSE+FULL,
  // is 20 columns; column names in this project are all <=6 chars) so
  // headerChanged()'s per-column comparison never has to worry about
  // storage running out for a real caller. A Snapshot wider than
  // kMaxHeaderColumns is treated as always-changed by headerChanged()
  // (a safe fallback -- see its own .cpp comment), never a buffer
  // overrun. ----
  static constexpr size_t kMaxHeaderColumns = 40;
  static constexpr size_t kMaxHeaderNameBytes = 16;
  char headerNames_[kMaxHeaderColumns][kMaxHeaderNameBytes] = {};
  bool headerHex_[kMaxHeaderColumns] = {};
  size_t headerCount_ = 0;
  bool everEmittedHeader_ = false;  // false until the very first thdr

  // The 20-frame (~1 Hz at this project's 50 ms emission cadence)
  // forced header refresh (sprint.md SUC-004) -- counts calls to
  // emitTelemetry(snapshot) since the last thdr was emitted (for ANY
  // reason: a real change, the very first call, or this same
  // staleness trigger), reset to 1 every time one goes out since the
  // call that emits it counts as the first frame of the next streak.
  static constexpr uint32_t kHeaderRefreshFrames = 20;
  uint32_t framesSinceHeader_ = 0;

  // Telemetry's own member-owned scratch buffer (never a stack local
  // in emitHeader()/emitFrame() -- see this file's own kMaxLineBytes
  // comment and sprint.md's Phase B formatting constraints: the
  // protocol fiber is 2 KB, and radio_transport.h:128 records a
  // measured hard-fault from exactly this mistake elsewhere in this
  // project). Sized identically to lineBuf_ (the wire's own 240-byte
  // line ceiling) rather than reused: lineBuf_ is RX-only reassembly
  // state (fed byte-by-byte from feed()), and aliasing an unrelated TX
  // formatting buffer onto it would be a correctness landmine for a
  // future edit, not a real memory saving.
  char emitBuf_[kMaxLineBytes] = {};
};

}  // namespace Wire
