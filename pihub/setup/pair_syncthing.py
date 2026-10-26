#!/usr/bin/env python3
"""Pair this PC's Syncthing with the Pi and set up the folders PiHub syncs.

Run once on each PC after Syncthing is installed and running:
    python3 pair_syncthing.py            (Linux)
    py pair_syncthing.py                 (Windows)

What it does:
  * this PC: adds the Pi as a device (paused; PiHub wakes it every 4 days) and
    shares each folder below as Send Only
  * the Pi (over ssh): adds this PC and the same folders as Receive Only into
    /srv/nas/devices/<device>/..., with Staggered versioning so a deletion on
    the PC never destroys the Pi's copy
  * writes this PC's Syncthing API key into the pihub-client config
"""
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "client"))
from pihub_client import config_path, load_config  # noqa: E402

PI_SSH = os.environ.get("PI_SSH", "som@piscreen.local")
PI_ADDR = os.environ.get("PI_ADDR", "tcp://192.168.1.13:22000")
ST = "http://127.0.0.1:8384"


def folders(device):
    home = os.path.expanduser("~")
    music = os.path.join(home, "Music", "OmaOpus")
    out = []
    for name in ("Documents", "Desktop", "Pictures", "Videos"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            out.append((device + "-" + name.lower(), "%s %s" % (device, name), p, "/srv/nas/devices/%s/%s" % (device, name)))
    if os.path.isdir(music):
        out.append(("music-omaopus", "OmaOpus music", music, "/srv/nas/music/omaopus"))
    return out


def st_config_file():
    cands = [os.path.expanduser("~/.local/state/syncthing/config.xml"), os.path.expanduser("~/.config/syncthing/config.xml")]
    if os.name == "nt":
        cands.insert(0, os.path.join(os.environ.get("LOCALAPPDATA", ""), "Syncthing", "config.xml"))
    for c in cands:
        if os.path.isfile(c):
            return c
    raise SystemExit("Couldn't find Syncthing's config.xml. Start Syncthing once, then run this again.")


def st(method, path, key, body=None):
    req = urllib.request.Request(ST + path, method=method, headers={"X-API-Key": key, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else {}


PI_SIDE = r'''
import json, re, sys, urllib.request
a = json.loads(sys.stdin.read())
key = re.search(r"<apikey>([^<]+)</apikey>", open("/home/som/.local/state/syncthing/config.xml").read()).group(1)
def st(m, p, b=None):
    r = urllib.request.Request("http://127.0.0.1:8384" + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                               headers={"X-API-Key": key, "Content-Type": "application/json"})
    return urllib.request.urlopen(r, timeout=15).read()
me = json.loads(st("GET", "/rest/system/status"))["myID"]
st("PUT", "/rest/config/devices/" + a["pc_id"], {"deviceID": a["pc_id"], "name": a["device"], "addresses": ["dynamic"]})
for fid, label, pi_path in a["folders"]:
    st("PUT", "/rest/config/folders/" + fid, {
        "id": fid, "label": label, "path": pi_path, "type": "receiveonly",
        "devices": [{"deviceID": me}, {"deviceID": a["pc_id"]}],
        "versioning": {"type": "staggered", "params": {"maxAge": "2592000", "cleanInterval": "3600"}},
        "rescanIntervalS": 3600, "fsWatcherEnabled": False})
print(me)
'''


def main():
    cfg = load_config()
    device = cfg["device"]
    key = re.search(r"<apikey>([^<]+)</apikey>", open(st_config_file(), encoding="utf-8").read()).group(1)
    my_id = st("GET", "/rest/system/status", key)["myID"]
    fl = folders(device)
    print("This PC (%s) is %s" % (device, my_id))
    print("Folders to sync:", ", ".join(f[2] for f in fl))

    payload = json.dumps({"pc_id": my_id, "device": device, "folders": [(f[0], f[1], f[3]) for f in fl]})
    # ssh joins its arguments into one remote shell command, so quote the script as a single word.
    r = subprocess.run(["ssh", PI_SSH, "python3 -c " + shlex.quote(PI_SIDE)], input=payload.encode(), capture_output=True)
    if r.returncode != 0:
        raise SystemExit("Pi side failed:\n" + r.stderr.decode())
    pi_id = r.stdout.decode().strip().splitlines()[-1]
    print("Pi is", pi_id)

    st("PUT", "/rest/config/devices/" + pi_id, key,
       {"deviceID": pi_id, "name": "pi (picloud)", "addresses": [PI_ADDR, "dynamic"], "paused": True})
    for fid, label, path, _ in fl:
        st("PUT", "/rest/config/folders/" + fid, key, {
            "id": fid, "label": label, "path": path, "type": "sendonly",
            "devices": [{"deviceID": my_id}, {"deviceID": pi_id}],
            "rescanIntervalS": 3600, "fsWatcherEnabled": True})

    cfg_file = config_path()
    raw = json.load(open(cfg_file, encoding="utf-8"))
    raw.setdefault("syncthing", {}).update({"url": ST, "api_key": key, "pi_device_id": pi_id})
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
    print("Done. The Pi is paused until PiHub's next round; press 'Sync now' on the dashboard to test.")


if __name__ == "__main__":
    main()
