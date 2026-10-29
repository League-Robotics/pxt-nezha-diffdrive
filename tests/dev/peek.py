"""Read-only look at a robot: ID, STATUS and one TLM FULL row. Never moves it."""
import argparse

from devlink import open_serial, status, tlm

ap = argparse.ArgumentParser()
ap.add_argument('robots', nargs='+')
a = ap.parse_args()

for name in a.robots:
    link = open_serial(name)
    link.send('ID')
    print(name, 'ID', [s for s in link.lines(1.0) if s.startswith('id')])
    print(name, 'STATUS', status(link))
    print(name, 'TLM', tlm(link))
    link.close()
