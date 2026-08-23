// wire_handler.h -- Wire::WireHandler: protocol v6's ASCII line-grammar
// mechanics ONLY (radio-robot-lib/docs/design/protocol.md S2, S2.1,
// S3.1, S3.2 -- the canonical spec; this project conforms to that
// grammar, it does not vendor radio-robot-lib's C++). feed() reassembles
// arbitrary byte blocks into '\n'-terminated lines, tokenizes each line
// in place on runs of ' ' (no allocation, no std::string -- S3.2),
// enforces case-as-direction (S2.1: commands UPPERCASE, replies
// lowercase, verb lookup case-SENSITIVE), and dispatches the three
// verbs that never need the mandatory-#id/ack/nack reliability layer:
// HELLO, PING, ESTOP (S8.3's unsequenced exemption set).
//
// Deliberately out of scope for this file (sprint 003 ticket 003 adds
// it): the reliability layer itself -- expectedNext_/gapOutstanding_,
// id parsing, ack/nack, decode-failure-is-NAK. Every OTHER verb (ID,
// VER, STATUS, GET, SET, TLM, the six motion verbs, STOP, RUN, ...) is
// sequenced under the full protocol and cannot be wired up correctly
// without that layer; until it lands, an otherwise-well-formed
// uppercase verb this file does not recognize is simply counted
// malformed with no reply -- there is no id yet to nack against.
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

// The two strings HELLO's banner needs. Borrowed pointers, not owned:
// valid only for the duration of the identity() call that filled them
// in -- matches radio-robot-lib's own Protocol::Identity convention
// (adapter.h).
struct Identity {
  const char* name;
  const char* serial;
};

// Adapter -- the minimal seam this ticket's three verbs need: identity
// for HELLO's banner, a clock for PING's `pong <now>`, and an ESTOP
// hook. This is NOT the full protocol.md S4 Adapter contract, and it is
// NOT sprint.md's own src/wire_adapter.{h,cpp} module (a later ticket's
// deliverable) -- it is kept intentionally small here, with only the
// three methods HELLO/PING/ESTOP need, so this ticket's own tests can
// exercise it with a trivial stub (tests/host/wire_grammar_shim.cpp)
// instead of a six-motion-verb mock this ticket has no use for yet.
// Expect this interface to be widened (or replaced by wire_adapter.h
// entirely) once sequenced verbs are wired up.
class Adapter {
 public:
  virtual ~Adapter() = default;
  virtual void identity(Identity& out) const = 0;
  virtual uint32_t now() const = 0;  // [ms], for PING's `pong <now>`
  virtual void onEstop() = 0;
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

  // Lines dropped as an unrecognized/not-yet-wired uppercase verb,
  // wrong HELLO arity, or an overlong line (discarded to the next
  // '\n'). A lowercase-led inbound verb -- another robot's reply
  // overheard on a shared channel, protocol.md S2.1 -- is dropped
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

  void dispatch(char* verb, char** fields, size_t fieldCount);
  void handleHello();
  void handlePing();
  void handleEstop();
  void writeLine(const char* text);

  // Field-token storage cap for one line. None of this ticket's three
  // verbs takes a data field, but the cap must still be generous enough
  // that tokenizeLine()'s own returned count (used only for HELLO's
  // strict-zero-arity check here) reflects a realistic line rather than
  // clipping early.
  static constexpr size_t kMaxFieldTokens = 20;

  Adapter& adapter_;
  Sink& sink_;

  char lineBuf_[kMaxLineBytes] = {};
  size_t lineLen_ = 0;
  bool overflowing_ = false;
  uint32_t malformedCount_ = 0;
};

}  // namespace Wire
