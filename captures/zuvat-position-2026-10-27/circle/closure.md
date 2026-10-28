**ENCODER truth (kernel wheel odometry). No camera: the encoders cannot see wheel slip, tyre scrub or a wrong trackwidth / travel_calib.**

| mode | lap | closure [mm] | heading residual [deg] | lap time [s] | i2cf growth |
|---|---|---|---|---|---|
| 0 | m0_lap1 | 46.2 | -11.54 | 11.5 | 7 |
| 0 | m0_lap2 | 56.9 | -15.81 | 11.5 | 2 |
| 0 | m0_lap3 | 58.7 | -15.44 | 11.5 | 2 |
| 0 | m0_lap4 | 55.3 | -15.57 | 11.4 | 4 |
| 0 | m0_lap5 | 68.6 | -18.53 | 11.4 | 5 |
| 1 | m1_lap1 | 66.5 | -17.54 | 11.4 | 3 |
| 1 | m1_lap2 | 15.3 | -5.74 | 11.7 | 4 |
| 1 | m1_lap3 | 39.1 | -11.27 | 11.6 | 5 |
| 2 | m2_lap1 | 48.0 | -0.44 | 9.1 | 56 |
| 2 | m2_lap2 | 1.4 | -0.52 | 9.0 | 57 |
| 2 | m2_lap3 | 1.4 | -0.45 | 9.0 | 57 |
| 2 | m2_lap4 | 2.2 | -0.34 | 9.0 | 57 |
| 2 | m2_lap5 | 1.4 | -0.59 | 9.0 | 57 |

| mode | laps | closure mean [mm] | closure worst [mm] | heading mean abs [deg] | heading worst abs [deg] | lap mean [s] | i2cf/lap | target < 11 mm |
|---|---|---|---|---|---|---|---|---|
| 0 | 5 | 57.1 | 68.6 | 15.38 | 18.53 | 11.5 | 4.0 | not met |
| 1 | 3 | 40.3 | 66.5 | 11.52 | 17.54 | 11.6 | 4.0 | not met |
| 2 | 5 | 10.9 | 48.0 | 0.47 | 0.59 | 9.0 | 56.8 | not met |
