// wire_handler.cpp -- see wire_handler.h for the full contract this
// file implements. Shape ported from radio-robot-lib's own
// protocol_handler.cpp feed()/tokenizeLine()/dispatch() skeleton
// (radio-robot-lib/docs/design/protocol.md S2-S3, S8.3), rewritten
// fresh for this project's own (currently three-verb) catalog -- this
// is not a vendored copy.
#include "wire_handler.h"

#include <cstdio>
#include <cstring>

namespace Wire {

WireHandler::WireHandler(Adapter& adapter, Sink& sink)
    : adapter_(adapter), sink_(sink) {}

// ---- feed() / line reassembly ------------------------------------------

void WireHandler::feed(const char* data, size_t length) {
  for (size_t i = 0; i < length; ++i) appendByte(data[i]);
}

void WireHandler::appendByte(char c) {
  if (c == '\n') {
    onLineComplete();
    return;
  }
  if (overflowing_) return;  // discard content until the next '\n'
  if (lineLen_ >= kMaxLineBytes - 1) {
    // Storing this byte would make the line's content alone reach
    // kMaxLineBytes - 1, i.e. the line (content + '\n') would exceed
    // the wire's 240-byte cap. Discard to the next '\n' rather than
    // truncate: a truncated prefix that still parses as a legal verb
    // with legal arity would be a command the host never sent.
    overflowing_ = true;
    lineLen_ = 0;
    return;
  }
  lineBuf_[lineLen_++] = c;
}

void WireHandler::onLineComplete() {
  if (overflowing_) {
    overflowing_ = false;
    lineLen_ = 0;
    ++malformedCount_;
    return;
  }
  // A lone '\r' immediately before '\n' is a terminal artifact and is
  // stripped; '\r' appears nowhere else on the wire (protocol.md S2).
  if (lineLen_ > 0 && lineBuf_[lineLen_ - 1] == '\r') --lineLen_;
  lineBuf_[lineLen_] = '\0';

  // A blank or all-whitespace line is ignored SILENTLY (protocol.md S2)
  // -- a terminal artifact, not an error; it does NOT count malformed.
  // Cheap pre-check before the real tokenizer runs.
  bool anyNonSpace = false;
  for (size_t i = 0; i < lineLen_; ++i) {
    if (lineBuf_[i] != ' ') {
      anyNonSpace = true;
      break;
    }
  }
  if (!anyNonSpace) {
    lineLen_ = 0;
    return;
  }

  char* tokens[kMaxFieldTokens];
  size_t count = tokenizeLine(lineBuf_, tokens, kMaxFieldTokens);
  // anyNonSpace being true normally guarantees at least the verb token
  // was found -- EXCEPT for one C-string edge case anyNonSpace's own
  // byte-by-byte scan does not share with tokenizeLine()'s scan: an
  // embedded NUL is "not a space" (anyNonSpace treats it as content),
  // but it terminates tokenizeLine()'s NUL-terminated-string view
  // immediately, same as the real end of the buffer. A line whose
  // first non-space byte is an embedded NUL (e.g. "\0PING\n") is
  // exactly this case: anyNonSpace correctly sees non-space content at
  // that byte, but tokenizeLine()'s forward scan sees only an empty
  // string there and returns 0 tokens, leaving `tokens[0]`
  // uninitialized. Guard it explicitly rather than dereferencing that:
  // this is corrupted content, not the grammar's own narrowly-defined
  // blank-line/lowercase-reply exceptions, so it is malformed, not
  // silently dropped.
  if (count == 0) {
    ++malformedCount_;
    lineLen_ = 0;
    return;
  }
  char* verb = tokens[0];
  dispatch(verb, tokens + 1, count - 1);
  lineLen_ = 0;
}

// ---- tokenizing (protocol.md S2, S3.2) ----------------------------------

size_t WireHandler::tokenizeLine(char* line, char** tokens,
                                  size_t maxTokens) {
  size_t count = 0;
  char* p = line;
  while (true) {
    while (*p == ' ') ++p;  // skip a run of separator spaces (sp ::= ' '+)
    if (*p == '\0') break;  // end of line -- no more tokens
    if (count < maxTokens) tokens[count] = p;
    ++count;
    while (*p != '\0' && *p != ' ') ++p;  // scan to next separator or end
    if (*p == '\0') break;
    *p = '\0';  // terminate this token
    ++p;        // step past the separator byte just nulled
  }
  return count;
}

// ---- dispatch ------------------------------------------------------------

void WireHandler::dispatch(char* verb, char** fields, size_t fieldCount) {
  (void)fields;  // no verb this ticket wires up decodes a data field

  // Case is direction (protocol.md S2.1): commands are UPPERCASE,
  // replies are lowercase, and verb lookup is case-sensitive. A verb
  // starting with a lowercase letter can never be a command this file
  // recognizes -- it is another robot's reply, overheard on a shared
  // channel, and is dropped SILENTLY, not counted malformed.
  if (verb[0] >= 'a' && verb[0] <= 'z') return;

  // ESTOP and PING are outside the sequence entirely and maximally
  // forgiving of trailing content (protocol.md S8.3): ANY line whose
  // verb token is exactly "ESTOP"/"PING" executes/answers, regardless
  // of arity or what follows -- "ESTOP", "ESTOP 1 2 3", "ESTOP #5" all
  // behave identically.
  if (std::strcmp(verb, "ESTOP") == 0) {
    handleEstop();
    return;
  }
  if (std::strcmp(verb, "PING") == 0) {
    handlePing();
    return;
  }
  if (std::strcmp(verb, "HELLO") == 0) {
    // HELLO's own arity is strict zero-fields (protocol.md S8.3): a
    // HELLO with a trailing field is wrong arity, same as any other
    // extra field, and (being outside the sequence entirely) has no
    // ack/nack to anchor an err against -- silently malformed, exactly
    // like an unrecognized verb.
    if (fieldCount != 0) {
      ++malformedCount_;
      return;
    }
    handleHello();
    return;
  }

  // Every other verb (ID, VER, STATUS, GET, SET, TLM, the six motion
  // verbs, STOP, RUN, ...) is sequenced under the full protocol and
  // needs the mandatory-#id/ack/nack reliability layer that sprint 003
  // ticket 003 adds -- this file does not parse an id at all yet. An
  // otherwise well-formed uppercase verb this table does not (yet)
  // recognize is counted malformed with no reply -- the same outcome an
  // unrecognized verb gets once the reliability layer lands
  // (protocol.md S8.9), minus the nack this file has no sequence state
  // to frame.
  ++malformedCount_;
}

void WireHandler::writeLine(const char* text) {
  sink_.write(text, std::strlen(text));
}

// ---- the three unsequenced verbs -----------------------------------------

void WireHandler::handleHello() {
  // This ticket does not implement the reliability layer's session
  // reset (protocol.md S8.3's "HELLO resets the sequence") -- that
  // state (expectedNext_/gapOutstanding_) does not exist in this class
  // yet (sprint 003 ticket 003 adds it). HELLO here only proves
  // dispatch: it replies the identical banner sendBanner() would emit
  // unsolicited.
  sendBanner();
}

void WireHandler::handlePing() {
  // Unsequenced and maximally forgiving (see dispatch()'s own comment
  // at the PING branch): ANY line whose verb is PING replies `pong`,
  // regardless of what -- if anything -- follows it.
  char buf[32];
  std::snprintf(buf, sizeof(buf), "pong %lu\n",
                static_cast<unsigned long>(adapter_.now()));
  writeLine(buf);
}

void WireHandler::handleEstop() {
  // ESTOP is outside the sequence entirely (protocol.md S8.3) --
  // execute BEFORE replying so a panic stop never queues behind an
  // outbound reply.
  adapter_.onEstop();
  writeLine("estop\n");
}

// ---- unsolicited emissions ------------------------------------------------

void WireHandler::sendBanner() {
  Identity identity;
  adapter_.identity(identity);
  char buf[96];
  std::snprintf(buf, sizeof(buf), "device NEZHA2 robot %s %s\n", identity.name,
                identity.serial);
  writeLine(buf);
}

}  // namespace Wire
