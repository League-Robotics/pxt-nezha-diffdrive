**ENCODER truth (kernel wheel odometry). No camera: the encoders cannot see wheel slip, tyre scrub or a wrong trackwidth / travel_calib.**

| mode | lap | closure [mm] | heading residual [deg] | lap time [s] | i2cf growth |
|---|---|---|---|---|---|
| 0 | m0_lap1 | 26.4 | +3.05 | 17.1 | 22 |
| 0 | m0_lap2 | 3.2 | -0.22 | 17.3 | 24 |
| 0 | m0_lap3 | 5.8 | +0.10 | 17.1 | 4 |
| 0 | m0_lap4 | 8.6 | -0.57 | 17.1 | 16 |
| 0 | m0_lap5 | 5.1 | -1.88 | 17.1 | 14 |
| 1 | m1_lap1 | 3.6 | -0.65 | 14.9 | 34 |
| 1 | m1_lap2 | 2.2 | -0.46 | 15.0 | 37 |
| 1 | m1_lap3 | 1.0 | -0.41 | 15.0 | 35 |
| 1 | m1_lap4 | 0.0 | -0.50 | 15.0 | 36 |
| 1 | m1_lap5 | 2.2 | -0.29 | 15.0 | 37 |

| mode | laps | closure mean [mm] | closure worst [mm] | heading mean abs [deg] | heading worst abs [deg] | lap mean [s] | i2cf/lap | target < 11 mm |
|---|---|---|---|---|---|---|---|---|
| 0 | 5 | 9.8 | 26.4 | 1.16 | 3.05 | 17.1 | 16.0 | not met |
| 1 | 5 | 1.8 | 3.6 | 0.46 | 0.65 | 15.0 | 35.8 | met |
