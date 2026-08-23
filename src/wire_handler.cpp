// wire_handler.cpp -- see wire_handler.h for the full contract this
// file implements. Shape ported from radio-robot-lib's own
// protocol_handler.cpp feed()/tokenizeLine()/dispatch() skeleton
// (radio-robot-lib/docs/design/protocol.md S2-S3, S8) -- this is not a
// vendored copy.
#include "wire_handler.h"

#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace Wire {

namespace {

// strtoul skips leading whitespace and, absent a digits-only pre-scan,
// would accept a leading '+' as valid syntax -- neither is a well-formed
// id (protocol.md S2.2: "the digits are bare and unsigned"). A pre-pass
// that requires EVERY byte to be an ASCII digit before strtoul() ever
// runs means "#+5", "#-5", and "# 5" are all correctly rejected as
// not-an-id, rather than silently parsing a prefix.
bool parseIdDigits(const char* text, uint32_t& out) {
  if (text == nullptr || text[0] == '\0') return false;
  for (const char* p = text; *p != '\0'; ++p) {
    if (*p < '0' || *p > '9') return false;
  }
  char* endPtr = nullptr;
  errno = 0;
  unsigned long value = std::strtoul(text, &endPtr, 10);
  if (endPtr == text || *endPtr != '\0') return false;
  if (errno == ERANGE || value > UINT32_MAX) return false;
  out = static_cast<uint32_t>(value);
  return true;
}

// Resolves `token` (the line's raw last token, or nullptr if the line
// was just the verb) as a mandatory sequence id (protocol.md S2.2/S8):
// must be present and match `#[0-9]+` exactly. There is no "#0 is
// special" branch here at all -- every well-formed id, including 0, is
// handled identically by dispatch()'s own three-way sequence compare.
bool parseMandatoryId(const char* token, uint32_t& id) {
  if (token == nullptr || token[0] != '#') return false;
  return parseIdDigits(token + 1, id);
}

// The raw LAST token of `line` (verb included), independent of any
// fixed-size fields[] array's own storage cap.
//
// MUST be called BEFORE tokenizeLine() mutates any of `line`'s
// separator spaces to '\0': it walks real ' ' bytes backward from the
// end of the string. Returns nullptr if `line` has no token besides the
// verb itself (nothing after it to resolve an id from).
const char* findLastFieldToken(const char* line) {
  const char* end = line + std::strlen(line);
  const char* p = end;
  while (p > line && *(p - 1) == ' ') --p;  // skip trailing spaces
  while (p > line && *(p - 1) != ' ') --p;  // scan back through the token
  return p == line ? nullptr : p;
}

// Config values are the one place floats appear on the wire (SET). "No
// exponents, no NaN, no inf" -- nothing in this project ever needs a
// robot to accept "1e10" or "nan" as a gain.
bool isWireSpace(char c) {
  return c == ' ' || c == '\t' || c == '\n' || c == '\v' || c == '\f' ||
         c == '\r';
}

bool parseFloatField(const char* field, float& out) {
  if (field == nullptr || field[0] == '\0' || isWireSpace(field[0])) {
    return false;
  }
  for (const char* p = field; *p != '\0'; ++p) {
    // 'e'/'E' bars decimal-exponent notation ("1e10"). 'x'/'X' bars C99
    // hex float notation ("0x1p3") -- strtof accepts this syntax
    // unconditionally otherwise.
    if (*p == 'e' || *p == 'E' || *p == 'x' || *p == 'X') return false;
  }
  char* endPtr = nullptr;
  errno = 0;
  float value = std::strtof(field, &endPtr);
  if (endPtr == field || *endPtr != '\0') return false;
  if (std::isnan(value) || std::isinf(value)) return false;
  out = value;
  return true;
}

bool parseTlmMode(const char* field, TlmMode& mode) {
  struct ModeEntry {
    const char* name;
    TlmMode mode;
  };
  static constexpr ModeEntry kModes[] = {
      {"OFF", TlmMode::kOff},   {"POSE", TlmMode::kPose},
      {"FULL", TlmMode::kFull}, {"NOW", TlmMode::kNow},
      {"AUTO", TlmMode::kAuto}, {"BUFFER", TlmMode::kBuffer},
  };
  for (const auto& entry : kModes) {
    if (std::strcmp(field, entry.name) == 0) {
      mode = entry.mode;
      return true;
    }
  }
  return false;
}

// formatConfigValue() -- six fractional digits, always present, no
// exponent, using integer arithmetic because newlib-nano's printf (the
// eventual firmware target) has no %f. formatConfigValue(0.02f) ->
// "0.020000", formatConfigValue(-51.5f) -> "-51.500000".
//
// `value` is NOT wire-parsed here -- it is whatever the ADAPTER's own
// onGet() handed back (parseFloatField already rejects NaN/Inf on the
// way IN), so this function cannot assume it is finite. +-Inf is already
// handled correctly below: it compares greater than kMaxScaled and gets
// clamped before the cast. NaN does not: every comparison against a NaN
// is false, so `scaled > kMaxScaled` is false too and a NaN would sail
// past the clamp intact into `static_cast<uint32_t>(scaled)` --
// undefined behavior. There is no wire spelling for NaN, so fail safe to
// 0.0 rather than invent one.
void formatConfigValue(float value, char* out, size_t cap) {
  if (std::isnan(value)) value = 0.0f;
  constexpr uint32_t kDivisor = 1000000u;  // 10^6 -- six fixed digits
  const bool negative = value < 0.0f;
  const float magnitude = negative ? -value : value;
  constexpr float kMaxScaled = 4294967040.0f;  // largest float < UINT32_MAX
  float scaled = magnitude * static_cast<float>(kDivisor) + 0.5f;
  if (scaled > kMaxScaled) scaled = kMaxScaled;
  const uint32_t scaledInt = static_cast<uint32_t>(scaled);
  const uint32_t wholePart = scaledInt / kDivisor;
  const uint32_t fracPart = scaledInt % kDivisor;
  std::snprintf(out, cap, "%s%lu.%06lu", negative ? "-" : "",
                static_cast<unsigned long>(wholePart),
                static_cast<unsigned long>(fracPart));
}

// Copies `text` into `out` (a buffer of `outCap` bytes), STRIPPING every
// '\n'/'\r' byte rather than rejecting the call outright -- RUN's own
// returned-value formatting calls this to keep an embedded terminator
// byte from forging a second wire line. `text == nullptr` is treated
// exactly like `text == ""`. Truncates, never overflows, once `out` is
// full -- always NUL-terminates within `outCap`. Returns the number of
// bytes written (excluding the terminator).
size_t sanitizeLineText(const char* text, char* out, size_t outCap) {
  if (text == nullptr) text = "";
  size_t len = 0;
  for (const char* p = text; *p != '\0' && len + 1 < outCap; ++p) {
    if (*p == '\n' || *p == '\r') continue;  // stripped -- never reaches out
    out[len++] = *p;
  }
  out[len] = '\0';
  return len;
}

}  // namespace

const WireHandler::VerbEntry WireHandler::kCommandTable[12] = {
    {"HELLO", &WireHandler::decodeAlwaysTrue, &WireHandler::execNoop},
    {"PING", &WireHandler::decodeAlwaysTrue, &WireHandler::execNoop},
    {"ID", &WireHandler::decodeNoFields, &WireHandler::execId},
    {"VER", &WireHandler::decodeNoFields, &WireHandler::execVer},
    {"STATUS", &WireHandler::decodeNoFields, &WireHandler::execStatus},
    {"HELP", &WireHandler::decodeNoFields, &WireHandler::execHelp},
    {"GET", &WireHandler::decodeGet, &WireHandler::execGet},
    {"SET", &WireHandler::decodeSet, &WireHandler::execSet},
    {"TLM", &WireHandler::decodeTlm, &WireHandler::execTlm},
    {"STOP", &WireHandler::decodeStop, &WireHandler::execStop},
    {"ESTOP", &WireHandler::decodeAlwaysTrue, &WireHandler::execNoop},
    {"RUN", &WireHandler::decodeRun, &WireHandler::execRun},
};

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

  // The mandatory trailing id (protocol.md S8) must be located BEFORE
  // tokenizeLine() below mutates any separator space to '\0' -- see
  // findLastFieldToken()'s own comment.
  const char* lastFieldToken = findLastFieldToken(lineBuf_);

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
  dispatch(verb, tokens + 1, count - 1, lastFieldToken);
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

// ---- dispatch / the reliability layer -----------------------------------
// protocol.md S8 in full; this is the state machine summary from
// wire_handler.h's own file header, implemented.

void WireHandler::dispatch(char* verb, char** fields, size_t fieldCount,
                            const char* lastFieldToken) {
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
    // Whether PING should be MAXIMALLY FORGIVING (like ESTOP) or STRICT
    // zero-arity (like HELLO) is this file's own call, matching
    // protocol_handler.cpp's own resolution: forgiving, so a host still
    // appending an old-style `#<id>` to PING out of habit keeps working
    // unchanged, and PING (liveness) can never itself wedge on a syntax
    // nit.
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

  // ---- everything else is on the sequenced plane (protocol.md
  // S8.1/S8.9): a mandatory, well-formed #<id> is REQUIRED as the
  // line's last token, independent of whether the verb itself is even
  // recognized. ----
  uint32_t id = 0;
  if (!parseMandatoryId(lastFieldToken, id)) {
    // No trailing field at all, or one that isn't a well-formed
    // '#'[0-9]+ -- the line cannot be sequence-classified. Nothing to
    // compare against expectedNext_, so there is no reply of any kind.
    ++malformedCount_;
    return;
  }

  // The id itself is always fields[fieldCount - 1] once well-formed
  // (findLastFieldToken() found it), so the verb's own DATA fields are
  // everything before it.
  const size_t dataFieldCount = fieldCount - 1;

  if (id < expectedNext_) {
    // A stale retransmit -- the host never saw our ack for something we
    // already accepted. Do NOT re-execute (a resent command must not
    // run twice, once motion verbs exist); just re-state what we
    // already have.
    replyAck(expectedNext_ - 1);
    return;
  }
  if (id > expectedNext_) {
    // A numeric gap: something between expectedNext_ and id never
    // arrived (or arrived out of order). Discard -- do NOT execute, and
    // do not even look up the verb -- and tell the host exactly what we
    // need next.
    gapOutstanding_ = true;
    replyNack(expectedNext_);
    return;
  }

  // id == expectedNext_: find the verb and DECODE its own fields BEFORE
  // sending any reply at all (protocol.md S8.9 -- "decode failure is a
  // NAK"): this is what lets a corrupted leg of a multi-command routine
  // be resent rather than silently skipped.
  const VerbEntry* entry = nullptr;
  for (const auto& e : kCommandTable) {
    if (std::strcmp(verb, e.name) == 0) {
      entry = &e;
      break;
    }
  }
  if (entry == nullptr) {
    // Unrecognized verb (including every motion verb this ticket does
    // not yet wire up): a decode failure exactly like a known verb's
    // own bad arity or unparseable field -- the sequence does NOT
    // advance.
    handleDecodeFailure(id, resultCode(Result::kUnknown));
    return;
  }
  if (!(this->*entry->decode)(fields, dataFieldCount)) {
    handleDecodeFailure(id, resultCode(Result::kBadArg));
    return;
  }

  // Decoded fine: the line arrived intact. The sequence advances and
  // the ack is sent UNCONDITIONALLY at this point -- "did the bytes
  // arrive, in order, and did they parse" is answered here regardless
  // of whether the ADAPTER goes on to refuse the content on its own
  // merits (protocol.md S8.2).
  expectedNext_ = id + 1;
  gapOutstanding_ = false;
  replyAck(id);

  uint8_t errCode = 0;
  (this->*entry->execute)(fields, dataFieldCount, id, errCode);
  if (errCode != 0) replyErr(id, errCode);
}

void WireHandler::handleDecodeFailure(uint32_t id, uint8_t code) {
  // The sequence does NOT advance: `id` is still expectedNext_ at this
  // point (that equality is what routed dispatch() into this function
  // at all), so nacking expectedNext_ unchanged tells the host to
  // resend EXACTLY this id. gapOutstanding_ is set so a stalled stream
  // keeps re-nacking at the telemetry rate (S8.5) exactly like a
  // numeric gap would, until a well-formed line finally arrives
  // carrying this same id.
  ++malformedCount_;
  gapOutstanding_ = true;
  replyNack(expectedNext_);
  replyErr(id, code);
}

void WireHandler::replyAck(uint32_t ackedId) {
  char buf[56];
  std::snprintf(buf, sizeof(buf), "ack %lu %lu %s\n",
                static_cast<unsigned long>(ackedId),
                static_cast<unsigned long>(adapter_.lastDone()),
                doneReasonWireName(adapter_.lastDoneReason()));
  writeLine(buf);
}

void WireHandler::replyNack(uint32_t nextId) {
  char buf[56];
  std::snprintf(buf, sizeof(buf), "nack %lu %lu %s\n",
                static_cast<unsigned long>(nextId),
                static_cast<unsigned long>(adapter_.lastDone()),
                doneReasonWireName(adapter_.lastDoneReason()));
  writeLine(buf);
}

void WireHandler::replyErr(uint32_t id, uint8_t code) {
  // Field order: code THEN #id -- the id is always the LAST token of
  // ANY line under this grammar, replies included (protocol.md S8.6).
  char buf[32];
  std::snprintf(buf, sizeof(buf), "err %u #%lu\n", static_cast<unsigned>(code),
                static_cast<unsigned long>(id));
  writeLine(buf);
}

void WireHandler::writeLine(const char* text) {
  sink_.write(text, std::strlen(text));
}

uint8_t WireHandler::resultCode(Result result) {
  switch (result) {
    case Result::kOk: return 0;  // never used as an error code
    case Result::kUnknown: return 1;
    case Result::kBadArg: return 2;
    case Result::kRange: return 3;
    case Result::kFull: return 4;
    case Result::kUnimplemented: return 6;
    case Result::kNotReady: return 8;
    case Result::kBusy: return 10;
  }
  return 1;  // unreachable with every enumerator handled above; kept so
             // a FUTURE enumerator trips -Wswitch instead of silently
             // falling through a default case
}

const char* WireHandler::doneReasonWireName(DoneReason reason) {
  switch (reason) {
    case DoneReason::kNone: return "none";
    case DoneReason::kStop: return "stop";
    case DoneReason::kTimeout: return "timeout";
    case DoneReason::kEstop: return "estop";
    case DoneReason::kAborted: return "aborted";
  }
  return "none";  // unreachable with every enumerator handled above
}

// ---- the three unsequenced verbs -----------------------------------------

void WireHandler::handleHello() {
  // HELLO resets the reliability layer's own sequencing state
  // (protocol.md S8.3) -- the session-start resync a (re)connecting
  // host performs. It does NOT touch the Adapter's own
  // lastDone()/lastDoneReason() (S8.8): that state is Adapter-owned, and
  // a handler-level reset has no business reaching into it. An Adapter
  // that wants a HELLO to also clear ITS OWN notion of "last completed
  // motion" is free to do so from wherever it observes HELLO itself.
  expectedNext_ = 1;
  gapOutstanding_ = false;
  sendBanner();  // protocol.md S4: HELLO's reply is byte-identical to
                 // the unsolicited boot banner
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

// ---- trivial stand-ins for HELLO/PING/ESTOP's table rows -----------------
// Never actually invoked through kCommandTable (all three are
// intercepted by verb identity in dispatch() before the table lookup
// ever runs) -- present purely so HELP's generated listing walks one
// table for every verb name.

bool WireHandler::decodeAlwaysTrue(char** fields, size_t fieldCount) {
  (void)fields;
  (void)fieldCount;
  return true;
}

void WireHandler::execNoop(char** fields, size_t fieldCount, uint32_t id,
                            uint8_t& errCode) {
  (void)fields;
  (void)fieldCount;
  (void)id;
  errCode = 0;
}

// ---- session verbs ---------------------------------------------------------
// ID/VER/STATUS/HELP all take zero DATA fields (id already stripped by
// dispatch()) -- any remaining field at all is wrong arity, a decode
// failure.

bool WireHandler::decodeNoFields(char** fields, size_t fieldCount) {
  (void)fields;
  return fieldCount == 0;
}

void WireHandler::execId(char** fields, size_t fieldCount, uint32_t id,
                          uint8_t& errCode) {
  (void)fields;
  (void)fieldCount;
  (void)id;
  errCode = 0;
  Identity identity;
  adapter_.identity(identity);
  char buf[96];
  std::snprintf(buf, sizeof(buf), "id %s %s %s\n", identity.drivetrain,
                identity.profile, identity.version);
  writeLine(buf);
}

void WireHandler::execVer(char** fields, size_t fieldCount, uint32_t id,
                           uint8_t& errCode) {
  (void)fields;
  (void)fieldCount;
  (void)id;
  errCode = 0;
  Identity identity;
  adapter_.identity(identity);
  char buf[64];
  std::snprintf(buf, sizeof(buf), "ver %s\n", identity.version);
  writeLine(buf);
}

void WireHandler::execStatus(char** fields, size_t fieldCount, uint32_t id,
                              uint8_t& errCode) {
  (void)fields;
  (void)fieldCount;
  (void)id;
  errCode = 0;
  StatusFields status;
  adapter_.status(status);
  char buf[176];
  std::snprintf(buf, sizeof(buf),
                "status ready=%d active=%d connL=%d connR=%d otos=%d "
                "wedge=%d flags=%x tlm=%s next=%lu\n",
                status.ready ? 1 : 0, status.active ? 1 : 0,
                status.connLeft ? 1 : 0, status.connRight ? 1 : 0,
                status.otos ? 1 : 0, status.wedge ? 1 : 0,
                static_cast<unsigned int>(status.flags), status.tlm,
                static_cast<unsigned long>(expectedNext_));
  writeLine(buf);
}

void WireHandler::execHelp(char** fields, size_t fieldCount, uint32_t id,
                            uint8_t& errCode) {
  (void)fields;
  (void)fieldCount;
  (void)id;
  errCode = 0;
  // Generated by walking kCommandTable at runtime, so it cannot drift
  // from the dispatcher -- the SAME table dispatch() looks verbs up in.
  char buf[kMaxLineBytes];
  size_t pos = 0;
  auto append = [&](const char* text) {
    while (*text != '\0' && pos < sizeof(buf) - 1) buf[pos++] = *text++;
  };
  append("help");
  for (const auto& entry : kCommandTable) {
    append(" ");
    append(entry.name);
  }
  append("\n");
  buf[pos] = '\0';
  writeLine(buf);
}

// ---- configuration: pure delegation, no storage here (protocol.md S7) ----

bool WireHandler::decodeGet(char** fields, size_t fieldCount) {
  (void)fields;
  return fieldCount <= 1;
}

void WireHandler::execGet(char** fields, size_t fieldCount, uint32_t id,
                           uint8_t& errCode) {
  (void)id;
  errCode = 0;  // GET never produces an err -- an unknown name is just a
                // silent no-`get`-line answer (protocol.md S7, S8.2).

  char buf[kMaxLineBytes];
  char formatted[32];
  if (fieldCount == 0) {
    // Bare GET: dump every field the adapter declares, one line each.
    size_t total = adapter_.fieldCount();
    for (size_t i = 0; i < total; ++i) {
      const char* name = adapter_.fieldName(i);
      float value = 0.0f;
      if (!adapter_.onGet(name, value)) continue;
      formatConfigValue(value, formatted, sizeof(formatted));
      std::snprintf(buf, sizeof(buf), "get %s %s\n", name, formatted);
      writeLine(buf);
    }
    return;
  }

  const char* name = fields[0];
  float value = 0.0f;
  // Unknown name: no `get` line, but the command is still acked (it
  // arrived fine and was answered with an empty result) -- not an
  // error, and not counted malformed.
  if (!adapter_.onGet(name, value)) return;
  formatConfigValue(value, formatted, sizeof(formatted));
  std::snprintf(buf, sizeof(buf), "get %s %s\n", name, formatted);
  writeLine(buf);
}

bool WireHandler::decodeSet(char** fields, size_t fieldCount) {
  if (fieldCount != 2) return false;
  float discard = 0.0f;
  return parseFloatField(fields[1], discard);
}

void WireHandler::execSet(char** fields, size_t fieldCount, uint32_t id,
                           uint8_t& errCode) {
  (void)fieldCount;
  float value = 0.0f;
  parseFloatField(fields[1], value);  // decodeSet() already proved this
                                       // succeeds
  Result result = adapter_.onSet(fields[0], value, id);
  errCode = resultCode(result);
}

// ---- telemetry -------------------------------------------------------------

bool WireHandler::decodeTlm(char** fields, size_t fieldCount) {
  if (fieldCount != 1) return false;
  TlmMode discard;
  return parseTlmMode(fields[0], discard);
}

void WireHandler::execTlm(char** fields, size_t fieldCount, uint32_t id,
                           uint8_t& errCode) {
  (void)fieldCount;
  (void)id;
  errCode = 0;  // the adapter's own Result never surfaces on the wire
                // for TLM.
  TlmMode mode;
  parseTlmMode(fields[0], mode);  // decodeTlm() already proved this succeeds
  (void)adapter_.onTlm(mode);
}

// ---- STOP: `STOP [now] #<id>` ---------------------------------------------

bool WireHandler::decodeStop(char** fields, size_t fieldCount) {
  if (fieldCount == 0) return true;
  return fieldCount == 1 && std::strcmp(fields[0], "now") == 0;
}

void WireHandler::execStop(char** fields, size_t fieldCount, uint32_t id,
                            uint8_t& errCode) {
  const bool immediate = fieldCount == 1;  // decodeStop() already proved
                                            // this is exactly "now"
  (void)fields;
  Result result = adapter_.onStop(immediate, id);
  errCode = resultCode(result);
}

// ---- RUN: parse-and-delegate only, per wire_handler.h's own onRun() doc --
//
// This handler holds no function table, does no name resolution, and
// does no type conversion -- it extracts the function-name token and
// the raw argument tokens that follow it, and hands them to the adapter
// unchanged. decodeRun()'s own DECODE FAILURES are purely structural: no
// function name at all, or more raw tokens than this line's fixed-size
// arrays can safely hold pointers for. An UNKNOWN function name, or a
// wrong arity the ADAPTER itself detects, is NOT a decode failure --
// RUN's own grammar was satisfied (a name plus some argument tokens), so
// those are merits rejections the adapter reports through its own
// Result (protocol.md S8.9).

bool WireHandler::decodeRun(char** fields, size_t fieldCount) {
  (void)fields;
  if (fieldCount == 0) return false;  // no function name at all -- this
                                       // covers "RUN #7" (the id
                                       // consumes the only field), which
                                       // S8.9 lists explicitly among its
                                       // own decode-failure examples --
                                       // it NACKs, not acks.
  if (fieldCount > kMaxFieldTokens - 1) return false;  // storage overflow
  const size_t argc = fieldCount - 1;
  return argc <= kMaxRunArgs;
}

void WireHandler::execRun(char** fields, size_t fieldCount, uint32_t id,
                           uint8_t& errCode) {
  const char* name = fields[0];
  const size_t argc = fieldCount - 1;  // fields[1 .. fieldCount-1]

  const char* argv[kMaxRunArgs];
  for (size_t i = 0; i < argc; ++i) argv[i] = fields[1 + i];

  char result[kMaxRunResultBytes] = {};
  bool hasResult = false;
  Result outcome =
      adapter_.onRun(name, argv, argc, result, sizeof(result), hasResult);

  errCode = resultCode(outcome);
  if (outcome != Result::kOk) return;
  if (!hasResult) return;  // a void-returning function: the ack already
                            // sent is the whole story.

  // Sanitize the ADAPTER's own returned text before it reaches the
  // sink -- the same '\n'/'\r'-stripping rule sendDebug()-style text
  // would get. kMaxRunResultBytes already guarantees the sanitized text
  // plus "ret "/" #<id>"/'\n' fits kMaxLineBytes, and sanitizing can
  // only shrink it further, never risk overflow.
  char sanitized[kMaxRunResultBytes];
  sanitizeLineText(result, sanitized, sizeof(sanitized));

  // +1: kMaxLineBytes already counts the WIRE content up to and
  // including '\n', but snprintf() also needs room for its own NUL
  // terminator -- a content string that legitimately reaches the full
  // 240 bytes needs a 241-byte buffer, or snprintf silently truncates
  // the last byte (here, the trailing '\n' itself) to make room for the
  // NUL it always writes.
  char buf[kMaxLineBytes + 1];
  std::snprintf(buf, sizeof(buf), "ret %s #%lu\n", sanitized,
                static_cast<unsigned long>(id));
  writeLine(buf);
}

// ---- unsolicited emissions -------------------------------------------------

void WireHandler::sendBanner() {
  Identity identity;
  adapter_.identity(identity);
  char buf[96];
  std::snprintf(buf, sizeof(buf), "device NEZHA2 robot %s %s\n", identity.name,
                identity.serial);
  writeLine(buf);
}

void WireHandler::emitTelemetry() {
  // The reliability layer's own periodic emission (protocol.md S8.5) --
  // rides the caller's own cadence, no timer of this class's own. A
  // stalled stream (gapOutstanding_) keeps re-nacking for free at this
  // rate; otherwise this simply re-states the highest id already
  // accepted, so a host that goes quiet after its last command still
  // eventually learns it landed. Both branches poll the Adapter's
  // lastDone()/lastDoneReason() fresh, right now -- there is no cached
  // copy of either on this class.
  if (gapOutstanding_) {
    replyNack(expectedNext_);
  } else {
    replyAck(expectedNext_ - 1);
  }
}

}  // namespace Wire
