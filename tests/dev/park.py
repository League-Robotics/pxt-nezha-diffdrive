"""Park the robot's centre at x y (cm) facing h (deg), camera-guided."""
import argparse

from devlink import Cam, open_serial, settled
from dots import Placer

ap = argparse.ArgumentParser()
ap.add_argument('x', type=float)
ap.add_argument('y', type=float)
ap.add_argument('h', type=float)
ap.add_argument('--robot', default='vevov')
ap.add_argument('--tag', type=int, default=53)
a = ap.parse_args()
cam = Cam(tag=a.tag).start()
link = open_serial(a.robot)
p = Placer(link, cam).park(settled(cam), (a.x, a.y), a.h)
print(f'parked ({p[0]:.1f},{p[1]:.1f}) hdg {p[2]:.1f}')
link.close()
cam.close()
