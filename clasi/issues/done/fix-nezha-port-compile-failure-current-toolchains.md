---
status: done
tickets:
- NONE
---

# Fix nezha_port.cpp compile failure on current toolchains

## Description

`nezha_port.cpp` fails to compile (`char*` → `uint8_t*` conversion
error) under the current pxt-microbit toolchain (codal-microbit-v2,
arm-gcc 7.3.1) — confirmed both in a local scratch `pxt` build and via
`pxt build --cloudbuild` during sprint 001.

This is **pre-existing on master**, not introduced by sprint 001:
programmer agents confirmed the identical failure with all sprint-001
files removed from `pxt.json`. The file is untouched by the sprint.

Likely a toolchain-strictness drift since the extension was originally
published (v1.0.0 presumably built under an earlier toolchain). Until
fixed, a full local/cloud rebuild of the extension does not produce a
hex; the MakeCode web editor may use different toolchain settings.

Related observation from the same builds: the legacy classic-microbit
(nRF51, arm-gcc 5.4) build variant lacks `std::snprintf`, which the
sprint-001 protocol code uses. This extension realistically targets
micro:bit v2 only (I2C Nezha driver); consider explicitly dropping the
classic target rather than chasing C99 stdio there.
