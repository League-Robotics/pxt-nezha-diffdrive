**ENCODER truth (kernel wheel odometry). No camera: the encoders cannot see wheel slip, tyre scrub or a wrong trackwidth / travel_calib.**

| mode | lap | closure [mm] | heading residual [deg] | lap time [s] | i2cf growth |
|---|---|---|---|---|---|
| 1 | m1_lap1 | 6.1 | +2.43 | 15.5 | 62 |
| 1 | m1_lap2 | 3.2 | -0.38 | 15.0 | 39 |
| 1 | m1_lap3 | 5.4 | -0.53 | 15.0 | 36 |
| 1 | m1_lap4 | 2.8 | -0.46 | 15.0 | 39 |
| 1 | m1_lap5 | 2.2 | -0.38 | 15.0 | 41 |
| 0 | m0_lap1 | 13.9 | +1.99 | 17.1 | 9 |
| 0 | m0_lap2 | 14.4 | +1.44 | 17.2 | 38 |
| 0 | m0_lap3 | 7.0 | -0.03 | 17.2 | 29 |

| mode | laps | closure mean [mm] | closure worst [mm] | heading mean abs [deg] | heading worst abs [deg] | lap mean [s] | i2cf/lap | target < 11 mm |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 3.9 | 6.1 | 0.84 | 2.43 | 15.1 | 43.4 | met |
| 0 | 3 | 11.8 | 14.4 | 1.15 | 1.99 | 17.2 | 25.3 | not met |
