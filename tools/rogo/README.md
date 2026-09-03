# rogo

`nc` for a robot. Finds the robot's own DNS-SD announcement
(`<name> robot link` on `_robotlink._tcp`, from the firmware's WiFi
transport), connects to its TCP server, and pipes stdin/stdout to the
v6 wire. Standard library only.

Install, from this checkout or straight from git:

```bash
pipx install /path/to/pxt-nezha-diffdrive/tools/rogo
pipx install "git+https://github.com/League-Robotics/pxt-nezha-diffdrive.git#subdirectory=tools/rogo"
```

Upgrade after a change with `pipx reinstall rogo` (or `pipx upgrade`
for the git install). Use:

```bash
rogo tovez                      # interactive: type verbs, see replies
rogo tovez PING STATUS          # send these lines, print replies, exit
echo 'TLM POSE #1' | rogo tovez --wait 5
rogo --browse                   # who is announcing on _robotlink._tcp
rogo --discover tovez           # print "<ip> <port>" and exit
rogo 192.168.1.213              # skip discovery (port 7654)
```

`rogo.py`'s docstring is the full reference; `docs/robot-connections.md`
in the repo (also on the Robot Garage wiki) covers the wire rules.
