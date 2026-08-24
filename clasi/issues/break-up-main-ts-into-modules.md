---
status: pending
sprint: '012'
---

# Break main.ts into modules

`main.ts` is 1034 lines and holds the entire public block API plus the
simulator. It needs splitting into modules — at minimum a config module
and a motion-commands module.

## What is actually in there

Reading the file, it is already several distinct subsystems wearing one
filename:

| lines | subsystem | notes |
|---|---|---|
| ~49–104 | **config state** | `defaultSpeed`, `defaultYawRate`, track width, wheel calibration |
| ~73–245 | **RUN dispatch** | `onRun` / `onRunCommand` / `runArg` / `runArgText` / `runArgCount` |
| ~106–138 | **direct drive** | `setWheelSpeeds`, `driveTwist`, `driveTick` |
| ~247–385 | **motion commands** | `move`, `goTo`, `startMove`, `startGoTo`, `isMoving`, `moveProgress`, `stopMove`, `whileMoving`, `whileGoingTo` |
| ~387–434 | **local pose** | `poseX`, `poseY`, `heading`, `resetPose` |
| ~436–524 | **world / OTOS** | tracking, seeding, `readWorld`, `worldX/Y/Heading`, calibration, sensor offset |
| ~526–650 | **goToWorld** | the world-frame planner, its own tuning constants |
| ~652–728 | **stop + config setters** | e-stop, `setDefaultSpeed`, `setTrackWidth`, `setConfigValue` |
| ~730–950 | **the simulator** | `sim*` state and its tick model — over 200 lines |
| ~951–1000 | **shim surface** | OTOS + taper shims, no blocks |

The simulator alone is a fifth of the file and has nothing to do with
the block API that students see.

## Suggested split

- `config.ts` — defaults, track width, calibration, `ConfigField`,
  `setConfigValue`
- `motion.ts` — `move` / `goTo` / `start*` / `while*` / progress / stop
- `pose.ts` — local odometry pose
- `world.ts` — OTOS world tracking, seeding, and `goToWorld`
- `run.ts` — the RUN command dispatch and argument accessors
- `sim.ts` — the simulator, which nothing on hardware needs
- `shims.ts` — the `//%` shim declarations

## Constraints that matter for this refactor

These are load-bearing and easy to break:

1. **Namespace `let` initialisers run AFTER a test file's top-level
   code.** Splitting across files multiplies the number of places this
   can bite. `runParts` / `runNames` / `runHandlers` / `runAnyHandlers`
   / `runWired` are deliberately declared with **no initialiser** and
   created on first use by `ensureRunState()` — that is a fix for a
   silent boot death (panic 980, no serial output). Any new module must
   keep that pattern for anything a test file touches at load.
2. **PXT file ORDER in `pxt.json` is the compile order.** A split that
   reorders declarations can change initialisation order.
3. **`//%` annotations must sit immediately above their signature**, and
   the block API's `group=` values determine the toolbox layout students
   see — moving functions between files must not silently regroup them.
4. Writing `radio` followed by a full stop, even in a comment, makes PXT
   demand a `radio` package this project does not use.

## Do it with the layout change

There is a parallel issue to move sources into `src/` and `test/`. These
should land together or in a deliberate order, because both rewrite the
`files` list in `pxt.json`, and a build is the only way to verify either.
A build has already been shown to work with sources under `src/`.
