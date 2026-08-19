---
status: pending
sprint: '001'
---

# Test on the micro:bit named "zetuv", located via mbdeploy

## Description

When testing this extension on hardware, use the micro:bit named
**zetuv** as the test device.

Use the **mbdeploy** tool to discover which serial port or UID zetuv
is currently using — do not hard-code a port path or guess from
`/dev` listings. mbdeploy resolves the device by name, so testing
works regardless of which port the board enumerates on.

This applies to any hardware-in-the-loop testing, including the
square-drive test program described in
[[test-system-drive-square]].
