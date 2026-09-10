---
id: 009
title: 'WifiLink: redact the passphrase from lastCommand() and DBG:wifi'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: dbg-wifi-prints-the-passphrase-in-cleartext.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WifiLink: redact the passphrase from lastCommand() and DBG:wifi

## Description

MEASURED gopiv 2026-09-09, `captures/wifi-join-codes-20260909/` (the
`cmd=` field is redacted in that capture's `notes.md`; it was **not**
redacted on the wire — see
`clasi/issues/dbg-wifi-prints-the-passphrase-in-cleartext.md`, filed
because of what this capture showed). `Protocol::emitWifiDebug()`
(`src/comms/protocol.cpp:396`) reports `WifiLink::lastCommand()`
verbatim. `WifiLink::startCommand()` (`src/comms/wifi_link.cpp:296-305`)
copies its `command` argument into `lastCommand_` unconditionally via
`copyBounded()`. The one call site that composes a command containing a
secret is `serviceJoin()`'s explicit join step
(`src/comms/wifi_link.cpp` around line 588-593):
`snprintf(cmd, ..., "AT+CWJAP=\"%s\",\"%s\"", config_.ssid,
config_.password); startCommand(cmd, "OK", kJoinTimeout);` — so the
passphrase lands in `lastCommand_`, and `emitLine()` fans that out to
serial, the radio link, AND the WiFi link itself
(`Protocol::emitWifiDebug()`'s own doc comment), i.e. every fleet robot
built through `tools/make_deploy.py::_inject_wifi_secrets()` has been
broadcasting its own passphrase on `DBG:wifi`. This is sequenced to run
**before ticket 002** (before any credential-store or wire work adds a
second place a password could leak) because Sprint 038's Goals already
state a **HARD CONSTRAINT — no passphrase ever leaves the board**, and
every later ticket's acceptance criteria assume that constraint already
holds. It does not; this ticket closes the gap in already-shipped code
before the sprint extends it further.

**Fix at the source, not the sink**: `WifiLink` must never let the
passphrase reach the buffer `lastCommand()` returns. Extend
`startCommand()` with an optional trace-override parameter (a redacted
string to record in `lastCommand_` in place of `command` itself),
defaulting to `nullptr`/unused so every other call site is
byte-for-byte unchanged. At the `AT+CWJAP=` call site, build the real
command for the UART exactly as today, and separately build a redacted
trace string — SSID kept (`config_.ssid` is not a secret and is
diagnostically valuable per the issue's own "Proposed resolution" step
1), passphrase replaced with a fixed marker, e.g.
`AT+CWJAP="<ssid>",***` — and pass that as the override. Do **not**
change `Protocol::emitWifiDebug()`: once the source is redacted, no
change is needed there, only a comment explaining why the field is
safe to print verbatim (per the issue's "Affected code" list).

**Audit every other `startCommand()` call site for the same shape**
(per the issue's "Proposed resolution" step 2) — grep confirms sites at
`wifi_link.cpp` lines 542 (`kConfigureSteps`, static strings, no
secret), 564 (`AT+CWJAP?` query, SSID only, no password), 593 (the
`AT+CWJAP=` join — the one fixed here), 613, 629, 643-649, 666-671,
693-697, 711, 887-896 (`AT+CIPSEND=...` framing, TCP payload
metadata, no credential). `AT+CWJAP=` is the only one that carries a
secret today. Add a host test that pins this fact so a future call
site introducing a new secret-carrying command is caught, not just the
one fixed here.

No units in the new parameter/field names
(`.claude/rules/no-units-in-identifiers.md` — not applicable to this
change's naming, but keep the convention in mind for anything new
introduced).

## Acceptance Criteria

- [x] `WifiLink::lastCommand()` never returns a string containing the
      passphrase, in any state (`kJoin`, `kBackoff`, after a
      `+CWJAP:<code>` failure, after a successful join) — the SSID
      still appears in the traced form.
- [x] The real `AT+CWJAP="<ssid>","<password>"` command sent to the
      UART is byte-for-byte unchanged — this ticket redacts the trace,
      not the wire command the module actually receives.
- [x] Host test (`tests/host/test_wifi_link.py` or equivalent): drive a
      join with a scripted password, assert the exact passphrase
      string appears nowhere in `lastCommand()`'s return value at any
      point in the join sequence, and that the SSID still does.
- [x] Host test: audit assertion enumerating every `startCommand()`
      call site (or equivalent structural check) confirming only the
      `AT+CWJAP=` join step uses the trace-override parameter — pins
      the "only one call site carries a secret" finding so a future
      addition is caught if it doesn't redact.
- [x] `Protocol::emitWifiDebug()`'s existing `DBG:wifi` host tests
      (from ticket 001) still pass unmodified — this ticket does not
      change `Protocol`, only `WifiLink`.
- [x] No passphrase appears in any commit, log line, comment, or
      captured test artifact this ticket produces
      (`.claude/rules/measurement-citations.md` /
      `.claude/rules/mcp-required.md`-adjacent hygiene already required
      sprint-wide).
- [x] Ticket description/commit notes that `nezha-robot-template`'s
      `scripts/redact-wifi-trace.sh` becomes dead weight once the
      extension pin containing this fix is adopted there — no change to
      that script from this ticket (it lives in a different repo); this
      is a forward-pointer for a follow-up, per the issue's step 4.

## Implementation Notes

Implemented exactly per the plan: `WifiLink::startCommand()` grows an
optional `const char* traceOverride = nullptr` parameter (default
preserves every other call site byte-for-byte); `serviceJoin()`'s
`AT+CWJAP=` step builds a second, redacted string
(`AT+CWJAP="<ssid>",***`) alongside the real command and passes it as
the override. `Protocol::emitWifiDebug()` is unchanged code, plus a
comment explaining why `cmd=` is safe to print verbatim now that the
source is redacted. A structural host test
(`test_only_the_cwjap_join_call_site_passes_a_trace_override`) audits
every `startCommand()` call site in `wifi_link.cpp` and pins that
exactly one — the join step — carries the trace-override argument.

**Forward-pointer** (per the issue's step 4, and this ticket's own
last acceptance criterion): once the extension pin containing this fix
lands in `League-Robotics/nezha-robot-template` (via
`tools/publish_extension.py`), that consumer repo's
`scripts/redact-wifi-trace.sh` — a host-side workaround that redacts
the `cmd=` field in captured logs/notes because the wire itself was not
safe — becomes dead weight: the wire is redacted at the source now, so
there is nothing left for that script to redact. No change to that
script from this ticket (it lives in a different repo); a follow-up
ticket there should remove it once the pin is adopted.

## Implementation Plan

**Approach**: Minimal, additive change to `WifiLink::startCommand()`
and its one caller with a secret. No change to the public `Config`/
`begin()` shape, no change to `Protocol`.

**Files to modify**:
- `src/comms/wifi_link.h` — `startCommand()`'s declaration grows an
  optional trace-override parameter (default `nullptr`); doc comment
  on `lastCommand()`'s contract updated to state it is always
  redaction-safe.
- `src/comms/wifi_link.cpp` — `startCommand()`'s body: when the
  override is non-null, copy it into `lastCommand_` instead of
  `command`. `serviceJoin()`'s `AT+CWJAP=` step: build the redacted
  trace string alongside the real command and pass it through.

**Testing plan**: Extend `tests/host/test_wifi_link.py` with a scripted
join (any outcome — success, `+CWJAP:2`, timeout) asserting the
passphrase string is absent from `lastCommand()` throughout, and the
SSID is present. Add the call-site audit test described above.

**Documentation updates**: None required beyond this ticket's own
commit message citing the capture artifact
(`captures/wifi-join-codes-20260909/notes.md`) that motivated it.
