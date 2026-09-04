---
status: done
sprint: 029
tickets:
- 029-005
---

# Strip units from identifier names across project-owned src/ (stakeholder direction, this round)

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Finding: CH-04 ([review](../../../docs/code-review/2026-09-02/review.md) section 5). Triage #24. Rule:
`.claude/rules/no-units-in-identifiers.md`.

## Description

The house style is the kernel's: a bare name and a trailing `// [unit]`
comment. Project-owned `src/` drifted into unit suffixes -- about 520
occurrences: `nowMs`/`nowMs_`/`wireNowMs` (78), `aDecelMmS2_` family (57),
`distanceMm`/`rotationRad`/`yawRad`/`omegaRad`/`angleRad` (69),
`timeoutMs`/`durationMs`/`deadlineUs`/`startMs`/`lastTickMs` (70), the
shaping fields (63), `cruiseMmS`/`speedMmS`/`twistMmS`/`remainMm` (42),
the `*Counts` locals (28), the sim `*Mm`/`*Rad`/`*Ms` state (42). The
vendored kernel and conversion-named functions (`mradToRad`,
`countsPerMm`, `writePoseMm`) are excluded.

## Remedy

- `src/motion/` renames ride with the motion-profile sprint's engine
  rewrite (`one-velocity-shaper-...`); this issue covers `shims.cpp`,
  `comms/`, `blocks/`, `platform/`.
- Every rename lands with its `// [unit]` comment, or the unit is lost
  rather than moved.
- A source-pin test that fails on a new `MmS`/`Ms`/`Us`/`Mm`/`Rad`/`Deg`/
  `Counts`/`Pct` suffix outside `src/core/` and outside a small allow-list
  of conversion functions.

## Acceptance

- The pin test is green with an empty allow-list except the conversions.
