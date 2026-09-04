# No units in identifier names

A method, field, parameter or variable is named for **what it is**, never
for the unit it happens to be measured in. The unit goes in a trailing
comment on the declaration, in square brackets.

```cpp
float velocity = 0.0f;          // [counts/s]
float stopDistance = 0.0f;      // [mm] per wheel
float acceleration() const;     // [mm/s^2]
void advance(float target, float remain, float dt);  // [mm/s] [mm] [s]
```

Not `lastVMmS()`, not `stopDistanceMm`, not `accelMmS2_`, not `dtS`.

## Why

- A unit in the name is a comment that cannot be trusted: the moment
  the quantity is rescaled (counts → mm, deg → rad, the x1000 wire
  convention) the name is a lie and nothing flags it. A `// [mm]`
  comment sits on the declaration where the change is made.
- Names are read far more often than declared. `remain <= v * dt` is
  readable; `remainMm <= vCmdMmS * dtS` is not, and it teaches students
  that arithmetic needs Hungarian suffixes to be safe.
- It is the convention the vendored kernel (`src/core/diffdrive.h`)
  already follows on every field, and the one the rest of `src/` drifted
  away from (`aAccelMmS2_`, `defaultCruiseMmS_`, `engineDefaultCruiseMmS()`).
  New code follows the kernel; existing names are renamed when their
  file is next touched, not left as precedent.

## Where the unit goes instead

- Declaration: trailing `// [unit]` comment, one per field or parameter,
  in declaration order for a parameter list.
- A boundary that *converts* units is a named function whose name says
  the conversion, not a variable whose name says the unit:
  `omegaFloorAsWheelSpeed(b)`, `mradToRad()`, `countsPerMm()`.
- Wire field names and JSON config keys follow their own file's
  convention (`pivot_overrun_mm` exists in `radio-robot-lib`); this rule
  is about code identifiers.

Stakeholder direction, 2026-09-03, on the motion-profile design doc.
