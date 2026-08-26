---
status: pending
sprint: ''
tickets: []
---

# Changing the radio group mid-run is unverified

Sprint 021 ticket 005 shipped the `set radio group` block. Its
supported path — called from `on start`, before the radio has come up —
is sound: `RadioTransport::setGroup()` stores into `group_`, and
`ensureRadioReady()` reads that field (not a constant) when it later
brings the radio up, so the radio comes up already on the requested
group. That is the student-facing path and it is what the curriculum
uses.

The other path was never tested. When `radioReady_ == true` — a prior
`sendLine()`/`tryReceiveLine()` already brought the radio up —
`setGroup()` re-applies via `uBit.radio.setGroup(group_)`. **Whether
that actually changes what the already-armed radio receives on has not
been observed either way.**

## The source observation that raised the question

This is a reading of the vendored `MicroBitRadio.cpp`, not a
measurement.

`MicroBitRadio::setFrequencyBand()` performs an explicit restart, and
says why inline:

> We need to restart the radio for the frequency change to take effect

followed by an `NVIC_DisableIRQ` / `TASKS_DISABLE` / wait / write /
`TASKS_RXEN` cycle.

`MicroBitRadio::setGroup()` has no equivalent. It records
`this->group`, writes `NRF_RADIO->PREFIX0 = group`, and returns:

```cpp
int MicroBitRadio::setGroup(uint8_t group)
{
    if (ble_running())
        return DEVICE_NOT_SUPPORTED;
    this->group = group;
    NRF_RADIO->PREFIX0 = (uint32_t)group;
    return DEVICE_OK;
}
```

Whether the nRF52 RX state machine latches the address filter at
`RXEN` (making a restart necessary) or re-reads `PREFIX0` per packet
(making it unnecessary) is the open question. Both are plausible from
the datasheet; neither has been checked on this hardware.

Note the asymmetry cuts differently for TX and RX: `send()` configures
the radio per call, so transmission would pick up a new `PREFIX0`
immediately regardless. Only reception is in question.

## Why it is still open

The check needs untethered radio — USB reaches only the bench stand —
so it needs vevov on the zavaz relay (channel 4; never retune getez's
channel 3). Ticket 005 was closed without it at the stakeholder's
direction after the session had already run long.

## What a real test looks like

A script existed for this and was never run. The shape was right:

1. Baseline: open the group-10 link, confirm a round trip.
2. Send a group change to 11 over that live link — this is the
   already-armed branch, the whole point.
3. Same group-10 link: confirm it now goes unanswered.
4. Separate link with the relay retuned to group 11: confirm it answers.
   **This leg is what distinguishes the two outcomes.** Without it, a
   robot that has gone deaf on every group is indistinguishable from
   one that moved correctly.
5. Restore to 10 over the group-11 link; confirm 10 answers again.

Step 4 also needs its own control: a relay retune that silently failed
produces exactly the same reading as a robot that went deaf. Confirm
the relay is really on group 11 before concluding anything about the
robot.

Whatever runs, **the result must name its capture file** — see
`.claude/rules/measurement-citations.md`. This issue exists partly
because a previous attempt wrote a confident bench result for a test
that was never run.

## Cost of leaving it

Low. Nothing in the curriculum re-sets the group mid-run; the block is
documented for `on start`. The risk is a student calling it after the
radio is live and getting a silent no-op, or worse a radio that stops
receiving until power-cycled. The header comment on `setGroup()` says
plainly that this is unverified, so nobody is misled in the meantime.
