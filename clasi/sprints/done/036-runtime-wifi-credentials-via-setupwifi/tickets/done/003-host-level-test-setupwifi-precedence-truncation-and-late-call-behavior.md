---
id: '003'
title: 'Host-level test: setupWifi() precedence, truncation, and late-call behavior'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-level test: setupWifi() precedence, truncation, and late-call behavior

## Description

**Correction to the sprint-level test strategy before you start**: the
roadmap and issue both suggest "a host-level test for the
truncation/copy behavior, pattern per `tests/host/test_wifi_link.py`"
(compiling real C++ into a shared lib via `compile_shared_lib`). That
pattern does NOT apply here. `test_wifi_link.py` compiles
`src/comms/wifi_link.cpp`, which this sprint does not modify at all —
the new logic (`setupWifi()`, `wifiCredsExplicit_`,
`wifiCredsTruncated_`, the `serviceWifi()` branch) lives entirely in
`src/comms/protocol.cpp`/`protocol.h`, and **`tests/host/` cannot
compile `protocol.cpp` at all — it includes `pxt.h`, directly and
transitively** (confirmed by the existing
`tests/host/test_protocol_stack_canary_source_pin.py` and
`tests/host/test_dispatched_job_motion_source_pin.py`, both of which
say so explicitly and use SOURCE-TEXT PINNING instead of compiling).

Follow that established alternative: a **source-pin test**, in the
exact shape of `tests/host/test_dispatched_job_motion_source_pin.py`
(read it first — it is the closest precedent: same file, same
"wiring, not pure logic" situation). Copy its `_strip_comments()`
helper (or import it if the codebase has since consolidated it — check
`test_bus_guard_source_pin.py`, referenced in that file's own comment,
for whether a shared helper now exists before duplicating it again).

### What to pin

Read the actual `Protocol::setupWifi()` and `serviceWifi()` bodies
ticket 001 lands, then write regex/text assertions (not a full
parser) that the following SHAPES are present in `protocol.cpp`:

1. **Late-call guard exists and gates the store.** A conditional on
   `wifiBegun_` appears in `setupWifi()`'s body, structurally before
   any write to `wifiSsid_`, `wifiPassword_`, `wifiCredsExplicit_`, or
   `wifiCredsTruncated_` — i.e., the guard is not present but
   ineffective (e.g., present only as a comment, or checked after the
   writes already happened).
2. **Precedence branches on `wifiCredsExplicit_`, not a truthiness
   check on the stored SSID.** `serviceWifi()`'s config-building code
   contains an `if (wifiCredsExplicit_)` (or equivalent boolean read of
   that exact member) rather than a ternary/condition keyed off
   `wifiSsid_[0]` — this is the specific bug class ticket 001 exists to
   avoid regressing back into.
3. **Truncation is computed before the copy, from both fields.** Both
   `wifiSsid_` and `wifiPassword_` have a length check against their
   `sizeof` (or the literal 32/63) prior to the `snprintf` that fills
   them, and `wifiCredsTruncated_` is assigned from that check.
4. **`enableWifi()` (or the direct `wifiEnabled_ = true` it performs)
   is reached unconditionally in the non-late-call path** — i.e., not
   gated behind a truthiness check on the ssid argument, since
   `setupWifi("")` must still enable (see SUC-002).
5. **`wifiDbgBuf_` is sized 384, and `emitWifiDebug()`'s format string
   contains both `credsrc=` and `trunc=`.**

Also add one narrow **compiled** case if practical: extract nothing
from `protocol.cpp` itself, but if the truncation-length computation
(`strlen(ssid) >= sizeof(wifiSsid_)` etc.) is simple enough to restate
as a tiny standalone helper function with no `pxt.h`/CODAL dependency
in your source pin test module itself (pure host Python re-deriving
the same boundary math against the sizes `33`/`64`), do so as a sanity
cross-check on the constants — this is optional polish, not a
substitute for the source-pin assertions above, which are what
actually verify the shipped code.

## Acceptance Criteria

- [x] New file `tests/host/test_setupwifi_precedence_source_pin.py`
      (or similar name) exists, following
      `test_dispatched_job_motion_source_pin.py`'s structure: a module
      docstring explaining what this IS and IS NOT proving (a "What
      this is NOT" paragraph naming the `pxt.h` compile blocker, same
      as its precedent), `_strip_comments()`, then one test function
      per pinned shape above.
- [x] The test fails if `protocol.cpp` is edited to reintroduce the
      ternary-only precedence bug (verify by temporarily reverting the
      `serviceWifi()` branch to the old ternary locally and confirming
      the new test catches it, then restore the fix — do not leave the
      revert in the tree).
- [x] The test fails if the late-call guard is removed or checked
      after the writes.
- [x] The test fails if `wifiDbgBuf_` shrinks back to 320 or the
      `credsrc=`/`trunc=` fields are removed from the format string.
- [x] `tests/tools/test_make_deploy_wifi.py` still passes untouched —
      this ticket does not touch `tools/make_deploy.py`.

## Testing

- **Existing tests to run**:
  `tests/host/test_dispatched_job_motion_source_pin.py`,
  `tests/host/test_protocol_stack_canary_source_pin.py` (confirm the
  pattern still works as expected and nothing in this ticket's new
  file collides with either), `tests/tools/test_make_deploy_wifi.py`.
- **New tests to write**: the source-pin file described above.
- **Verification command**: `uv run pytest tests/host/test_setupwifi_precedence_source_pin.py
  tests/host/test_dispatched_job_motion_source_pin.py
  tests/tools/test_make_deploy_wifi.py`. The full suite runs once,
  inside `close_sprint`.
