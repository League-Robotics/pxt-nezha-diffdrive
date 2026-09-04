---
status: in-progress
sprint: 029
tickets:
- 029-001
---

# Decide the kernel fork: byte-identical rule vs owning the vendored DifferentialDrive locally

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Finding: CO-07 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #15.

## Description

`src/core/diffdrive.{h,cpp}` is "byte-identical to upstream except
`cycleGapCount`" (`radio-robot-elite/src/firm/diffdrive/`; today's diff is
comments plus that counter). The motion-profile design needs four kernel
changes (K1-K4 in `kernel-reference-handling-...`), and each future kernel
fix will be another "local fix not yet ported back" comment. Either this
repo owns its fork (drop the byte-identical rule, keep a behavioural
fidelity test on the control law) or every kernel ticket ships as a
paired upstream PR.

## Remedy

Stakeholder decision, then: update `src/DESIGN.md` section 2 and the two
file headers; if paired-PR, add the upstream path and a diff check to the
build-checkpoint convention; if fork, add a fidelity test that pins the
control law's behaviour on the probe's scenarios so upstream drift is
visible.
