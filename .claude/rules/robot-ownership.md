# Which robot this project may touch

As of 2026-09-02 (stakeholder ruling): **this project's bench robot is
gopiv**, on the mbdeploy farm (nolanet; node meili on 2026-09-02, but
boards move between nodes -- `mbdeploy list --remote` is the authority).

- **tigez belongs to another agent.** Do not flash it, drive it, open
  its serial port, or use it as a substitute, even when it is plugged
  into this machine's USB. A board being physically present here is
  not permission.
- zetuv belongs to nezha-upy (ruling of 2026-08-19); tovez was assigned
  to a different agent (2026-08-25). Same rule.
- If gopiv is unreachable (silent, SWD `No ACK`, absent from
  `mbdeploy list --remote`), the hardware criterion is **BLOCKED**:
  finish the host-side work, record what was measured, and report.
  Never route the work to another board.
- Check ownership before the first flash of a session, not after. A
  ticket that names a board does not override this file; if they
  disagree, this file wins and the ticket is stale.

Reflection: `clasi/reflections/2026-09-02-used-tigez-instead-of-gopiv.md`.
