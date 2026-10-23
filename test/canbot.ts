// canbot.ts -- can shuffling with zetuv's gripper on the bb-obstacle mat.
// Build: uv run python tools/make_deploy.py --program canbot.ts --robot zetuv
// Host driver: tools/canplay/ (canplay.py, setup.py).
//
//   RUN setpose x y h        tell the robot its world pose (cm, deg CCW from +x)
//   RUN obs x y [x y ...]    cans to avoid; RUN obsclear empties the list
//   RUN pickat x y [h]       grip the can at a point, optionally along a fixed heading
//   RUN placeat x y [h]      put the held can down with its centre on the point
//   RUN gripcal fwd left     gripper point in the robot frame (cm)
//   RUN grip deg             servo S1: 0 open, ~60 arms meet, 180 squeeze
//   RUN canplan a b [c d ..] blind, from the start square SM-6: circle moves, then home
//   RUN cans n ...           which circles hold cans, for canplan
//   RUN discard [x]          carry the held can off the south mat edge
//   RUN tune 1|2|0           start tune, stop tune, beep
//   RUN leg x y dir          face (1) or back (-1) onto a point along a planned leg
//   RUN fetch x y h tx ty th one can move: pickat x y h, then placeat tx ty th
//   RUN face h               turn in place
//   RUN home / goto x y [h] / holding 0|1 / where
// Each long verb ends with "CB end ok|fail x y h". The firmware holds 32
// RUN names in all; past that, registrations are silently dropped.
// World frame is the playfield (cm, heading deg CCW from +x); odometry is
// anchored to it by setPose.
namespace canbot {
    const BOOT_VERSION = "00.00"        // both substituted by make_deploy
    const BOOT_ROBOT = "unknown"
    diffDrive.setupRobot()
    diffDrive.enableRadioLink()
    diffDrive.enableWifiLink()
    // Camera-measured on the bb-obstacle mat 2026-10-21: 1.055 under-turned 1.7 %.
    const CUTEBOT = diffDrive.boardKind() == 2
    if (CUTEBOT) diffDrive.setRotationalSlip(1.037)
    diffDrive.setDefaultYawRate(120)
    // Still short per 360 deg, measured by squaring on the Start line: CCW 4.4, CW 1.95.
    const TURN_CCW = CUTEBOT ? 0.0122 : 0
    const TURN_CW = CUTEBOT ? 0.0054 : 0

    // Nezha: a hobby servo on a brick port, J2 = P2/P12 (RUN grippin picks).
    let gripPin = AnalogPin.P2

    function grip(deg: number): void {
        deg = Math.max(0, Math.min(180, Math.round(deg)))
        if (!CUTEBOT) {
            pins.servoWritePin(gripPin, deg)
            diffDrive.emitLine("GRIP " + deg)
            return
        }
        const b = pins.createBuffer(6)
        b[0] = 0xFF
        b[1] = 0xF9
        b[2] = 0x40
        b[3] = 2
        b[4] = 1
        b[5] = deg
        pins.i2cWriteBuffer(0x10, b)
        diffDrive.emitLine("GRIP " + deg)
    }

    let GRIP_FWD = 18.7        // [cm] gripped can centre ahead of robot centre
    let GRIP_LEFT = -0.9       // [cm] ... and to its left (RUN gripcal sets both)
    const STAGE = 12           // [cm] straight run-in before the grasp point
    const BACKOUT = 15         // [cm] straight back-out so the held can clears neighbours before a pivot
    const OPEN = 10            // fully open: narrower settings push the can instead of passing round it
    const STOW = 75            // arms closed and narrow while travelling empty
    const CLOSE = 180
    const TRAVEL = 20          // [cm/s]
    const TURN_RATE = 120      // [deg/s]
    const APPROACH = 8         // [cm/s]
    const PARK = [24, -10]
    const START = [-52.48, -0.22, 0]   // robot centre on SM-6, facing up the number axis
    const CIRCLES = [
        [-15.76, 26.74], [-22.32, 3.72], [-25.39, -12.42], [-8.19, 3.76],
        [6.02, 18.18], [6.18, 4.05], [6.1, -10.45], [14.39, -22.3],
        [34.31, 3.63], [46.25, 23.55], [56.06, 3.82], [45.99, -15.83]]

    // Cans the robot must not hit: world positions (cm).
    let obsX: number[] = []
    let obsY: number[] = []
    let occKnown = false
    function addObs(x: number, y: number): void {
        obsX.push(x)
        obsY.push(y)
    }
    function removeObs(x: number, y: number): void {
        for (let i = obsX.length - 1; i >= 0; i--)
            if (Math.abs(obsX[i] - x) < 5 && Math.abs(obsY[i] - y) < 5) {
                obsX.removeAt(i)
                obsY.removeAt(i)
            }
    }
    function spotX(n: number): number { return n == 0 ? PARK[0] : CIRCLES[n - 1][0] }
    function spotY(n: number): number { return n == 0 ? PARK[1] : CIRCLES[n - 1][1] }

    let ox = START[0]
    let oy = START[1]
    let oh = START[2]

    function rad(d: number): number { return d * Math.PI / 180 }
    function wrap(d: number): number {
        while (d > 180) d -= 360
        while (d <= -180) d += 360
        return d
    }

    export function setPose(x: number, y: number, h: number): void {
        diffDrive.resetPose()
        ox = x
        oy = y
        oh = h
    }
    function wx(): number {
        return ox + Math.cos(rad(oh)) * diffDrive.poseX() - Math.sin(rad(oh)) * diffDrive.poseY()
    }
    function wy(): number {
        return oy + Math.sin(rad(oh)) * diffDrive.poseX() + Math.cos(rad(oh)) * diffDrive.poseY()
    }
    function wh(): number { return wrap(oh + diffDrive.heading()) }

    function report(tag: string): void {
        diffDrive.emitLine("CB " + tag + " " + diffDrive.roundTo(wx(), 1) + " " + diffDrive.roundTo(wy(), 1)
            + " " + diffDrive.roundTo(wh(), 1))
    }

    // Robot centre must stay on the mat, inside this box.
    const XMIN = -53.5
    const XMAX = 50
    const YMIN = -16
    const YMAX = 25
    let failed = false

    function fail(why: string): void {
        if (!failed) report("abort " + why)
        failed = true
        diffDrive.stop()
    }
    // Planned points keep this margin inside the fence.
    function inset(x: number, y: number): number {
        return Math.max(0, 3 - Math.min(Math.min(x - XMIN, XMAX - x), Math.min(y - YMIN, YMAX - y)))
    }
    function outside(x: number, y: number): number {
        return Math.max(Math.max(0, Math.max(XMIN - x, x - XMAX)), Math.max(YMIN - y, y - YMAX))
    }

    function step(distance: number, yaw: number): void {
        if (failed) return
        const h = rad(wh())
        const ex = wx() + distance * Math.cos(h)
        const ey = wy() + distance * Math.sin(h)
        if (outside(ex, ey) > Math.max(0.5, outside(wx(), wy()))
            || canOut(ex, ey, wh()) > Math.max(0.5, canOut(wx(), wy(), wh()))) {
            fail("off mat")
            return
        }
        const before = outside(wx(), wy())
        diffDrive.clearStallLatch()
        if (distance == 0 && yaw != 0) {
            // pivots fall short by a direction-dependent fraction (line-measured)
            const k = yaw > 0 ? TURN_CCW : TURN_CW
            diffDrive.move(0, yaw * (1 + k))
            oh -= yaw * k
        } else {
            diffDrive.move(distance, yaw)
        }
        if (outside(wx(), wy()) > Math.max(2, before + 1)) fail("left mat")
    }

    // Mat edges (cm) less a can radius: a held can must stay inside.
    const CAN_XMIN = -58
    const CAN_XMAX = 56
    const CAN_YMIN = -22
    const CAN_YMAX = 31
    let holding = false

    function canOut(x: number, y: number, hdeg: number): number {
        if (!holding) return 0
        const h = rad(hdeg)
        const cx = x + GRIP_FWD * Math.cos(h) - GRIP_LEFT * Math.sin(h)
        const cy = y + GRIP_FWD * Math.sin(h) + GRIP_LEFT * Math.cos(h)
        return Math.max(Math.max(0, Math.max(CAN_XMIN - cx, cx - CAN_XMAX)), Math.max(CAN_YMIN - cy, cy - CAN_YMAX))
    }

    const HIT = 7.5            // [cm] gripper centre to a standing can's centre

    function gripperHits(hdeg: number, n0: number): boolean {
        for (let n = 0; n < obsX.length; n++)
            if (n != n0 && gripperHitsOnly(hdeg, n)) return true
        return false
    }

    function sweepOK(delta: number): boolean {
        const allowed = Math.max(0.5, canOut(wx(), wy(), wh()))
        // a can already touching the gripper is not an obstacle for this turn
        let touching = -1
        for (let n = 0; n < obsX.length; n++)
            if (gripperHitsOnly(wh(), n)) touching = n
        const steps = Math.ceil(Math.abs(delta) / 5)
        for (let k = 1; k <= steps; k++) {
            const hk = wh() + delta * k / steps
            if (canOut(wx(), wy(), hk) > allowed) return false
            if (gripperHits(hk, touching)) return false
        }
        return true
    }

    function gripperHitsOnly(hdeg: number, n: number): boolean {
        const h = rad(hdeg)
        const gx = wx() + GRIP_FWD * Math.cos(h)
        const gy = wy() + GRIP_FWD * Math.sin(h)
        return Math.sqrt((gx - obsX[n]) * (gx - obsX[n]) + (gy - obsY[n]) * (gy - obsY[n])) < HIT
    }

    export function turnTo(h: number): void {
        for (let i = 0; i < 6 && !failed; i++) {
            let err = wrap(h - wh())
            if (Math.abs(err) < 1.5) break
            if (!sweepOK(err)) {
                const other = err > 0 ? err - 360 : err + 360
                if (sweepOK(other)) {
                    err = other
                } else {
                    report("boxed in")
                    const bx = wx() - 8 * Math.cos(rad(wh()))
                    const by = wy() - 8 * Math.sin(rad(wh()))
                    step(outside(bx, by) + inset(bx, by) > 0 ? 8 : -8, 0)
                    continue
                }
            }
            step(0, err)
            if (Math.abs(err) > 6 && Math.abs(wrap(h - wh())) > Math.abs(err) - 2) {
                report("stuck turn " + Math.round(err))
                const bx = wx() - 3 * Math.cos(rad(wh()))
                const by = wy() - 3 * Math.sin(rad(wh()))
                step(outside(bx, by) + inset(bx, by) > 0 ? 3 : -3, 0)
                diffDrive.setDefaultYawRate(150)
            }
        }
        diffDrive.setDefaultYawRate(TURN_RATE)
        if (!failed && Math.abs(wrap(h - wh())) > 10) fail("turn")
    }

    export function driveTo(x: number, y: number): void {
        for (let i = 0; i < 3 && !failed; i++) {
            const dx = x - wx()
            const dy = y - wy()
            const d = Math.sqrt(dx * dx + dy * dy)
            if (d < 1) return
            if (d < 4) {
                const h = rad(wh())
                step(dx * Math.cos(h) + dy * Math.sin(h), 0)
                return
            }
            const b = Math.atan2(dy, dx) * 180 / Math.PI
            // facing the point or backing onto it: the smaller turn, unless that
            // would push a held can off the mat
            let face = Math.abs(wrap(b - wh())) > 90 ? b + 180 : b
            if (canOut(x, y, face) > Math.max(0.5, canOut(wx(), wy(), wh()))) face = face + 180
            turnTo(face)
            // a stuck turn's unstick step moves the robot: measure again
            const h = rad(wh())
            step((x - wx()) * Math.cos(h) + (y - wy()) * Math.sin(h), 0)
        }
    }

    // Bring the gripper centre onto (px, py), arriving straight along the
    // line from where the robot is now.
    function dist(x: number, y: number): number {
        return Math.sqrt((x - wx()) * (x - wx()) + (y - wy()) * (y - wy()))
    }

    // Bring the gripper centre onto (px, py) along a straight run-in. The
    // run-in comes from the robot's side if it fits on the mat, otherwise
    // from the nearest direction that does.
    // Re-zero heading and x on the Start-box line (west edge at LINE_X,
    // running along y): drive straight across it slowly and note how far
    // the robot had gone when each outer sensor first saw dark.
    const LINE_X = -36.94
    const LINE_X2 = -35.07     // east edge
    const SENSOR_FWD = 5.5     // [cm] sensor bar ahead of robot centre
    const SENSOR_HALF = 3.0    // [cm] outer channel offset either side
    const DARK = 100
    const CREEP = 6            // [cm/s]

    // Every circle may hold a can. A travel leg keeps the robot's path and
    // the reach ahead of it CLEAR cm from each, detouring past one if needed.
    const CLEAR = 10.5
    const REACH = 20

    function blocker(x1: number, y1: number, sx: number, sy: number): number {
        const x0 = wx()
        const y0 = wy()
        const L = Math.sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0))
        if (L < 1) return -1
        const ux = (x1 - x0) / L
        const uy = (y1 - y0) / L
        let best = -1
        let bestT = 9999
        for (let i = 0; i < obsX.length; i++) {
            const cx = obsX[i]
            const cy = obsY[i]
            if (Math.abs(cx - sx) < 3 && Math.abs(cy - sy) < 3) continue
            const t = (cx - x0) * ux + (cy - y0) * uy
            const d = Math.abs((cx - x0) * uy - (cy - y0) * ux)
            if (Math.sqrt((cx - x0) * (cx - x0) + (cy - y0) * (cy - y0)) < CLEAR) continue
            if (t < 0 || t > L + REACH || d >= CLEAR) continue
            if (t < bestT) {
                best = i
                bestT = t
            }
        }
        return best
    }

    // Drive to (x, y), going round circles in the way. (sx, sy) is the
    // target spot, which the gripper is meant to reach.
    export function travelTo(x: number, y: number, sx: number = 999, sy: number = 999): void {
        for (let k = 0; k < 3 && !failed; k++) {
            const b = blocker(x, y, sx, sy)
            if (b < 0) break
            const cx = obsX[b]
            const cy = obsY[b]
            const L = Math.sqrt((x - wx()) * (x - wx()) + (y - wy()) * (y - wy()))
            const ux = (x - wx()) / L
            const uy = (y - wy()) / L
            const side = (cx - wx()) * uy - (cy - wy()) * ux > 0 ? -1 : 1
            let wpx = cx + side * uy * (CLEAR + 3)
            let wpy = cy - side * ux * (CLEAR + 3)
            if (outside(wpx, wpy) + inset(wpx, wpy) > 0) {
                wpx = cx - side * uy * (CLEAR + 3)
                wpy = cy + side * ux * (CLEAR + 3)
            }
            wpx = Math.max(XMIN + 3, Math.min(XMAX - 3, wpx))
            wpy = Math.max(YMIN + 3, Math.min(YMAX - 3, wpy))
            report("detour " + b)
            driveTo(wpx, wpy)
        }
        driveTo(x, y)
    }

    // Cross the line at y = 14, clear of circles 2 and 3, arms closed.
    export function resquare(): void {
        if (!holding) {
            grip(STOW)
            squareY()
        }
        travelTo(-50, 14)
        squareUp()
    }

    export function squareUp(): void {
        squareLine(0, (LINE_X + LINE_X2) / 2, DARK)
    }

    // Cross a straight line that runs square to heading h (0/90/180/-90),
    // centred at `centre` along h. Fixes heading and that one coordinate.
    // Fix y on the south border line: only its inner edge (y = SOUTH_EDGE)
    // is on the paper, so read the entry crossings only. Never with a can.
    const SOUTH_EDGE = -25.18   // the faint line trips the sensor at its centre (camera-checked)
    export function squareY(): void {
        if (holding) return
        grip(STOW)
        travelTo(-45, -4)
        squareLine(-90, -SOUTH_EDGE, 60, true)
        step(-8, 0)
    }

    export function squareLine(h: number, centre: number, dark: number, edge: boolean = false): void {
        turnTo(h)
        if (failed) return
        const x0 = wx()
        const y0 = wy()
        const cross = [-1, -1, -1, -1]   // left in, right in, left out, right out
        let s = 0
        let ps = 0
        let pgl = 0
        let pgr = 0
        let peak = 0
        function at(pg: number, g: number): number {
            return g == pg ? s : ps + (s - ps) * (dark - pg) / (g - pg)
        }
        const t0 = control.millis()
        diffDrive.clearStallLatch()
        diffDrive.setWheelSpeeds(CREEP, CREEP)
        while (diffDrive.driveTick()) {
            s = Math.sqrt((wx() - x0) * (wx() - x0) + (wy() - y0) * (wy() - y0))
            const gl = diffDrive.lineSensorGrey(0)
            const gr = diffDrive.lineSensorGrey(3)
            peak = Math.max(peak, Math.max(gl, gr))
            const l = gl > dark
            const r = gr > dark
            if (cross[0] < 0 && l) cross[0] = at(pgl, gl)
            if (cross[1] < 0 && r) cross[1] = at(pgr, gr)
            if (cross[0] >= 0 && cross[2] < 0 && !l) cross[2] = at(pgl, gl)
            if (cross[1] >= 0 && cross[3] < 0 && !r) cross[3] = at(pgr, gr)
            ps = s
            pgl = gl
            pgr = gr
            if (edge && cross[0] >= 0 && cross[1] >= 0) break
            if (cross[2] >= 0 && cross[3] >= 0) break
            if (s > 35 || control.millis() - t0 > 14000 || (!edge && outside(wx(), wy()) > 0.5)) break
            diffDrive.setWheelSpeeds(CREEP, CREEP)
        }
        diffDrive.stop()
        if (edge) {
            cross[2] = cross[0]
            cross[3] = cross[1]
        }
        if (cross[2] < 0 || cross[3] < 0) {
            report("no line peak " + peak)
            fail("no line")
            return
        }
        const th = Math.atan(((cross[0] - cross[1]) + (cross[2] - cross[3])) / 2 / (2 * SENSOR_HALF))
        const midR = (cross[1] + cross[3]) / 2
        const u = centre - SENSOR_FWD * Math.cos(th) - SENSOR_HALF * Math.sin(th) + (s - midR) * Math.cos(th)
        diffDrive.emitLine("CB square " + diffDrive.roundTo(cross[0], 3) + " " + diffDrive.roundTo(cross[1], 3) + " "
            + diffDrive.roundTo(cross[2], 3) + " " + diffDrive.roundTo(cross[3], 3) + " peak " + peak
            + " odo " + diffDrive.roundTo(wx(), 1) + " " + diffDrive.roundTo(wy(), 1) + " " + diffDrive.roundTo(wh(), 1))
        const hr = rad(h)
        // replace the along-h coordinate, keep the across one from odometry
        const across = -wx() * Math.sin(hr) + wy() * Math.cos(hr)
        setPose(u * Math.cos(hr) - across * Math.sin(hr), u * Math.sin(hr) + across * Math.cos(hr), h + th * 180 / Math.PI)
        report("squared")
    }

    // Drive the gripper point (GRIP_FWD, GRIP_LEFT in the robot frame)
    // straight onto (tx, ty). A point ahead of the axle can be given any
    // velocity: v and w follow from inverting its kinematics.
    const TRACK = 9.1          // [cm]
    const POINT_TOL = 0.3      // [cm]

    function gx(): number { return wx() + GRIP_FWD * Math.cos(rad(wh())) - GRIP_LEFT * Math.sin(rad(wh())) }
    function gy(): number { return wy() + GRIP_FWD * Math.sin(rad(wh())) + GRIP_LEFT * Math.cos(rad(wh())) }

    export function pointTo(tx: number, ty: number, vmax: number): void {
        if (failed) return
        let best = 9999
        let stalls = 0
        const t0 = control.millis()
        diffDrive.clearStallLatch()
        diffDrive.setWheelSpeeds(0, 0)
        while (true) {
            if (!diffDrive.driveTick()) {
                if (++stalls > 5) break
                diffDrive.clearStallLatch()
            }
            const c = Math.cos(rad(wh()))
            const sn = Math.sin(rad(wh()))
            const ex = tx - gx()
            const ey = ty - gy()
            const d = Math.sqrt(ex * ex + ey * ey)
            if (d < POINT_TOL || d > best + 1 || control.millis() - t0 > 20000) break
            if (outside(wx(), wy()) > 1) {
                fail("left mat")
                break
            }
            best = Math.min(best, d)
            const sp = Math.min(vmax, Math.max(3, 1.5 * d))
            const pdx = ex / d * sp
            const pdy = ey / d * sp
            const v = ((GRIP_FWD * c - GRIP_LEFT * sn) * pdx + (GRIP_FWD * sn + GRIP_LEFT * c) * pdy) / GRIP_FWD
            const w = (-sn * pdx + c * pdy) / GRIP_FWD
            let l = v - w * TRACK / 2
            let r = v + w * TRACK / 2
            const m = Math.max(Math.abs(l), Math.abs(r))
            if (m > 0 && m < 3) {
                l = l * 3 / m
                r = r * 3 / m
            }
            diffDrive.setWheelSpeeds(l, r)
        }
        diffDrive.stop()
        report("point err " + diffDrive.roundTo(Math.sqrt((tx - gx()) * (tx - gx()) + (ty - gy()) * (ty - gy())), 2))
    }

    // Straight back after a grip or release, as far as the fence allows.
    function backOut(): void {
        const h = rad(wh())
        let d = BACKOUT
        while (d > 3 && outside(wx() - d * Math.cos(h), wy() - d * Math.sin(h)) > 0) d -= 2
        step(-d, 0)
    }

    // Pivots catch on the mat edge behind the start square: drive out first.
    function leaveStart(): void {
        if (wx() < -46 && Math.abs(wh()) < 30) step(-44 - wx(), 0)
    }

    // fixed: approach heading forced to `base` (999 = choose).
    function approach(px: number, py: number, fixed: number = 999): void {
        diffDrive.setDefaultSpeed(TRAVEL)
        leaveStart()
        let base = dist(px, py) > 3 ? Math.atan2(py - wy(), px - wx()) * 180 / Math.PI : wh()
        let offs = [0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180]
        if (fixed != 999) {
            base = fixed
            offs = [0]
        }
        let tx = 0, ty = 0, sx = 0, sy = 0, a = 0
        let found = false
        // a fixed heading may shorten the run-in to fit on the mat
        const stages = fixed != 999 ? [STAGE, 8, 5, 2] : [STAGE]
        for (const off of offs) {
            for (const st of stages) {
                a = base + off
                const c = Math.cos(rad(a))
                const s = Math.sin(rad(a))
                tx = px - GRIP_FWD * c + GRIP_LEFT * s
                ty = py - GRIP_FWD * s - GRIP_LEFT * c
                sx = tx - st * c
                sy = ty - st * s
                const m = fixed != 999 ? 0 : inset(tx, ty) + inset(sx, sy)
                if (outside(tx, ty) + outside(sx, sy) + m == 0) {
                    found = true
                    break
                }
            }
            if (found) break
        }
        if (!found) {
            fail("no approach")
            return
        }
        if (dist(sx, sy) > 4) travelTo(sx, sy, px, py)
        turnTo(a)
        if (failed) return
        if (!holding) {
            grip(OPEN)
            basic.pause(400)
        }
        pointTo(px, py, APPROACH)
        diffDrive.setDefaultSpeed(TRAVEL)
    }

    function spot(n: number): number[] {
        if (n >= 1 && n <= CIRCLES.length) return CIRCLES[n - 1]
        return PARK
    }

    export function pick(n: number): void {
        const p = spot(n)
        pickAt(p[0], p[1])
        report("picked " + n)
    }

    export function pickAt(x: number, y: number, fixed: number = 999): void {
        grip(STOW)
        approach(x, y, fixed)
        if (failed) return
        grip(CLOSE)
        holding = true
        removeObs(x, y)
        basic.pause(CUTEBOT ? 400 : 1000)   // a hobby servo closes slower than the Cutebot's
        backOut()
    }

    export function place(n: number): void {
        const p = spot(n)
        placeAt(p[0], p[1])
        report("placed " + n)
    }

    export function placeAt(x: number, y: number, fixed: number = 999): void {
        approach(x, y, fixed)
        if (failed) return
        grip(OPEN)
        holding = false
        addObs(x, y)
        basic.pause(800)          // arms fully open before backing out, or they drag the can
        diffDrive.setDefaultSpeed(APPROACH)
        backOut()
        diffDrive.setDefaultSpeed(TRAVEL)
        grip(STOW)
    }

    export function moveCan(from: number, to: number): void {
        pick(from)
        resquare()
        place(to)
    }

    export function swap(a: number, b: number): void {
        moveCan(a, 0)
        moveCan(b, a)
        moveCan(0, b)
    }

    // Carry the held can off the mat's south edge at x and let it go there.
    export function discard(x: number): void {
        driveTo(x, -2)
        turnTo(-90)
        if (failed) return
        holding = false
        diffDrive.setDefaultSpeed(APPROACH)
        driveTo(x, YMIN + 2)
        grip(OPEN)
        basic.pause(500)
        backOut()
        diffDrive.setDefaultSpeed(TRAVEL)
    }

    // One planned leg: face (dir 1) or face away from (dir -1) the point, then
    // drive straight onto it. The host has checked the leg is clear.
    export function leg(x: number, y: number, dir: number): void {
        const b = Math.atan2(y - wy(), x - wx()) * 180 / Math.PI
        if (Math.sqrt((x - wx()) * (x - wx()) + (y - wy()) * (y - wy())) < 1) return
        turnTo(dir < 0 ? b + 180 : b)
        const h = rad(wh())
        step((x - wx()) * Math.cos(h) + (y - wy()) * Math.sin(h), 0)
    }

    export function home(): void {
        travelTo(START[0], START[1])
        turnTo(START[2])
        report("home")
    }

    function a(i: number): number { return diffDrive.runArg(i) }
    // No motion until the robot has been told where it is.
    let poseKnown = false
    function start(): void {
        failed = !poseKnown
        if (failed) report("abort no pose")
    }

    function done(): void {
        diffDrive.stop()
        report(failed ? "end fail" : "end ok")
    }


    diffDrive.onRun("setpose", (arg: number) => {
        if (diffDrive.runArgCount() < 3) {
            poseKnown = false
            report("abort pose needs x y h")
            return
        }
        setPose(a(0), a(1), a(2))
        poseKnown = true
        report("pose")
    })
    diffDrive.runSignature("setpose", "(x:number=-52.48, y:number=-0.22, h:number=0)")
    diffDrive.onRun("holding", (arg: number) => { holding = a(0) != 0; report("holding " + a(0)) })
    diffDrive.runSignature("holding", "(yes:number=1)")
    control.inBackground(() => basic.showString(BOOT_ROBOT + " " + BOOT_VERSION))
    diffDrive.onRun("grip", (arg: number) => grip(a(0)))
    diffDrive.onRun("grippin", (arg: number) => {
        gripPin = arg == 12 ? AnalogPin.P12 : AnalogPin.P2
        report("pose")
    })
    diffDrive.runSignature("grip", "(deg:number=180)")
    // RUN cans n n n: which spots hold cans (otherwise canplan infers it)
    diffDrive.onRun("cans", (arg: number) => {
        obsX = []
        obsY = []
        for (let i = 0; i < diffDrive.runArgCount(); i++) addObs(spotX(a(i)), spotY(a(i)))
        occKnown = true
        report("cans " + diffDrive.runArgCount())
    })
    // RUN obs x y [x y ...]: add cans at world points; RUN obsclear empties the list
    diffDrive.onRun("obs", (arg: number) => {
        for (let i = 0; i + 1 < diffDrive.runArgCount(); i += 2) addObs(a(i), a(i + 1))
        occKnown = true
        report("obs " + obsX.length)
    })
    diffDrive.onRun("obsclear", (arg: number) => {
        obsX = []
        obsY = []
        report("obs 0")
    })
    diffDrive.runSignature("cans", "(a:number, b:number, c:number, d:number)")
    diffDrive.onRun("gripcal", (arg: number) => {
        GRIP_FWD = a(0)
        GRIP_LEFT = a(1)
        report("pose")
    })
    diffDrive.runSignature("gripcal", "(fwd:number=18.7, left:number=-0.9)")
    diffDrive.onRun("where", (arg: number) => report("pose"))
    // RUN tune 1: start of a session, 2: end of it, 0: a beep between steps
    diffDrive.onRun("tune", (arg: number) => {
        if (arg == 1) diffDrive.playStartTune()
        else if (arg == 2) diffDrive.playStopTune()
        else diffDrive.beep()
        report("pose")
    })
    diffDrive.runSignature("where", "()")
    diffDrive.addRunProgram("goto", () => { start(); driveTo(a(0), a(1)); if (diffDrive.runArgCount() > 2) turnTo(a(2)); report("at"); done() })
    diffDrive.runSignature("goto", "(x:number, y:number, h:number)")
    diffDrive.addRunProgram("pickat", () => { start(); pickAt(a(0), a(1), diffDrive.runArgCount() > 2 ? a(2) : 999); report("picked"); done() })
    diffDrive.runSignature("pickat", "(x:number, y:number, heading:number)")
    diffDrive.addRunProgram("discard", () => { start(); discard(diffDrive.runArgCount() > 0 ? a(0) : wx()); report("discarded"); done() })
    diffDrive.runSignature("discard", "(x:number)")
    diffDrive.addRunProgram("placeat", () => { start(); placeAt(a(0), a(1), diffDrive.runArgCount() > 2 ? a(2) : 999); report("placed"); done() })
    diffDrive.runSignature("placeat", "(x:number, y:number)")
    // Pairs of from/to spots, run in order, then home. Spot 0 is the park spot.
    function plan(): void {
        setPose(START[0], START[1], START[2])
        poseKnown = true
        if (!occKnown) {
            obsX = []
            obsY = []
            const made: boolean[] = [false, false, false, false, false, false, false, false, false, false, false, false, false]
            for (let i = 0; i + 1 < diffDrive.runArgCount(); i += 2) {
                if (!made[a(i)]) addObs(spotX(a(i)), spotY(a(i)))
                made[a(i + 1)] = true
            }
        }
        resquare()
        for (let i = 0; i + 1 < diffDrive.runArgCount() && !failed; i += 2) {
            moveCan(a(i), a(i + 1))
            resquare()
        }
        home()
    }
    diffDrive.addRunProgram("canplan", () => { poseKnown = true; start(); plan(); done() })
    diffDrive.runSignature("canplan", "(from:number, to:number, from2:number, to2:number, from3:number, to3:number)")
    diffDrive.addRunProgram("home", () => { start(); home(); done() })
    diffDrive.addRunProgram("leg", () => { start(); leg(a(0), a(1), a(2)); done() })
    // One whole can move: pick at (x, y) along heading h, carry it round the
    // obstacles, put it down at (tx, ty) along heading th, back out.
    diffDrive.addRunProgram("fetch", () => {
        start()
        pickAt(a(0), a(1), a(2))
        if (!failed) placeAt(a(3), a(4), a(5))
        report("fetched")
        done()
    })
    diffDrive.runSignature("fetch", "(x:number, y:number, h:number, tx:number, ty:number, th:number)")
    diffDrive.addRunProgram("face", () => { start(); turnTo(a(0)); done() })
    diffDrive.runSignature("face", "(h:number)")
    diffDrive.runSignature("leg", "(x:number, y:number, dir:number=1)")
    diffDrive.runSignature("home", "()")
}
