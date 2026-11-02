#!/usr/bin/env python3
"""
neohub_local - local, cloud-free control for a Heatmiser neoHub (legacy port 4242).

Protocol: plain TCP, each JSON command terminated with a NUL byte (\\0); the reply is
JSON, also NUL-terminated. No token, no TLS. Port 4242 must be enabled on the hub
(LEGACY_LOCAL_PORT=true) - see docs/enable-local-api.md.

Standard library only (Python 3) -> runs on any machine and inside the Home Assistant
Docker container.

Subcommands:
  info                      show the state of every zone
  zones                     list zones (name -> id)
  pair "Name" [seconds]     open pairing and wait for the thermostat (default 120s)
  rename "Old" "New"        rename a zone
  remove "Name"             delete a zone from the hub
  snapshot [--dir D]        save every zone's config (INFO + schedule) to JSON
  restore "Name" [--file F] re-push the saved settings to the thermostat
  autorestore [--dir D]     re-push ONLY zones that look reset (safe to run hourly)
  ha-json                   emit compact JSON for all zones (for Home Assistant)

Host/port: --host / --port, or the NEOHUB_HOST / NEOHUB_PORT env vars.
"""
import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime

DEFAULT_HOST = os.environ.get("NEOHUB_HOST", "192.168.1.100")  # set NEOHUB_HOST or pass --host
DEFAULT_PORT = int(os.environ.get("NEOHUB_PORT", "4242"))
DEFAULT_SNAPDIR = os.environ.get(
    "NEOHUB_SNAPDIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots"),
)


class NeoHub:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout

    def call(self, command):
        """Send a command (dict) and return the parsed reply (dict/list)."""
        payload = json.dumps(command).encode() + b"\x00"
        with socket.create_connection((self.host, self.port), self.timeout) as s:
            s.settimeout(self.timeout)
            s.sendall(payload)
            buf = b""
            while b"\x00" not in buf:
                chunk = s.recv(8192)
                if not chunk:
                    break
                buf += chunk
        buf = buf.split(b"\x00", 1)[0]
        if not buf:
            raise RuntimeError("empty reply from hub")
        return json.loads(buf.decode("utf-8", "replace"))

    # --- convenience ---
    def info(self):
        return self.call({"INFO": 0})

    def zones(self):
        return self.call({"GET_ZONES": 0})

    def comfort(self, zone):
        return self.call({"READ_COMFORT_LEVELS": zone})

    def permit_join(self, seconds, name):
        return self.call({"PERMIT_JOIN": [seconds, name]})

    def rename(self, old, new):
        return self.call({"ZONE_TITLE": [old, new]})

    def remove(self, zone):
        return self.call({"REMOVE_ZONE": zone})


def _fmt_from_mode(mode):
    return {
        "5DAY/2DAY": "5DAY/2DAY",
        "7DAY": "7DAY",
        "24HOUR": "24HOURSFIXED",
        "24HOURSFIXED": "24HOURSFIXED",
        "NONPROGRAMMABLE": "NONPROGRAMMABLE",
    }.get(mode, mode)


def snapshot_zone(hub, zone):
    """Build the snapshot object for one zone."""
    info_all = hub.info()
    dev = None
    for d in info_all.get("devices", []):
        if d.get("device") == zone:
            dev = d
            break
    if dev is None:
        raise RuntimeError("zone %r not found in INFO" % zone)
    comfort = hub.comfort(zone).get(zone, {})
    return {
        "zone": zone,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "info": dev,
        "comfort_levels": comfort,
    }


def restore_zone(hub, snap, dry_run=False):
    """Re-push settings to the thermostat from a snapshot. Returns (action, result) pairs."""
    zone = snap["zone"]
    info = snap["info"]
    out = []

    def do(label, command):
        if dry_run:
            out.append((label, "DRY-RUN: " + json.dumps(command)))
            return
        try:
            res = hub.call(command)
            out.append((label, json.dumps(res)))
        except Exception as e:
            out.append((label, "ERROR: %s" % e))
        time.sleep(0.4)

    # 1. Weekly schedule (the important one) + program format
    mode = info.get("PROGRAM_MODE")
    if mode:
        # SET_FORMAT takes a bare format string (not an array). "24HOUR" -> "24HOURSFIXED".
        do("program format (SET_FORMAT %s)" % mode,
           {"SET_FORMAT": _fmt_from_mode(mode)})
    comfort = snap.get("comfort_levels")
    if comfort:
        do("weekly schedule (SET_COMFORT_LEVELS)",
           {"SET_COMFORT_LEVELS": [comfort, zone]})

    # 2. Temperature format C/F
    tf = info.get("TEMPERATURE_FORMAT")
    if tf is not None:
        # SET_TEMP_FORMAT takes a bare "C"/"F" (not an array). Hub-wide setting.
        do("temperature format (SET_TEMP_FORMAT)",
           {"SET_TEMP_FORMAT": "F" if tf else "C"})

    # 3. Output delay
    od = info.get("OUTPUT_DELAY")
    if isinstance(od, int):
        do("output delay (SET_DELAY %s)" % od, {"SET_DELAY": [od, zone]})

    # 4. Optional settings, only if present and valid in the snapshot
    diff = info.get("SWITCHING_DIFFERENTIAL")
    if diff not in (None, 170):
        do("switching differential (SET_DIFF %s)" % diff, {"SET_DIFF": [diff, zone]})
    # preheat: PREHEAT_TIME "170:170" means unset -> skip
    ph = info.get("MAX_PREHEAT")
    if ph not in (None, 170):
        do("preheat (SET_PREHEAT %s)" % ph, {"SET_PREHEAT": [ph, zone]})
    if info.get("FLOOR_LIMIT") and info.get("FLOOR_LIMIT_TEMP") not in (None, 127):
        do("floor limit (SET_FLOOR)",
           {"SET_FLOOR": [info["FLOOR_LIMIT_TEMP"], zone]})

    # 5. Cannot be restored via the legacy API -> set manually on the thermostat
    sensor = info.get("SENSOR_SELECTION")
    out.append(("sensor (SENSOR_SELECTION=%s)" % sensor,
                "MANUAL: the legacy API has no command to set the sensor; "
                "choose it on the thermostat during setup"))
    return out


def detect_reset(hub, snap):
    """True if the zone looks factory-reset (e.g. after a dead battery).
    Conservative: only when the live schedule is empty/lost DESPITE the snapshot having one.
    Does not trigger just because you changed a setting."""
    zone = snap["zone"]
    snap_comfort = snap.get("comfort_levels") or {}
    snap_mode = (snap.get("info") or {}).get("PROGRAM_MODE")
    # The thermostat must be ONLINE: the hub won't read/write an offline one, and an
    # offline stat would be a false "reset" positive.
    live_dev = None
    for d in hub.info().get("devices", []):
        if d.get("device") == zone:
            live_dev = d
            break
    if live_dev is None or live_dev.get("OFFLINE"):
        return False
    try:
        live_comfort = hub.comfort(zone).get(zone, {})
    except Exception:
        return False
    live_mode = live_dev.get("PROGRAM_MODE")
    lost_schedule = bool(snap_comfort) and not live_comfort
    lost_mode = (snap_mode not in (None, "NONPROGRAMMABLE")
                 and live_mode in (None, "NONPROGRAMMABLE"))
    return lost_schedule or lost_mode


def _hub_from_args(a):
    return NeoHub(a.host, a.port)


def cmd_autorestore(hub, a):
    """For each zone with a snapshot: if it looks reset, re-push its config.
    Safe to run periodically (e.g. hourly from HA). Does nothing if not reset."""
    acted = 0
    for z in list(hub.zones().keys()):
        safe = z.replace("/", "_").replace(" ", "_")
        path = os.path.join(a.dir, "%s-latest.json" % safe)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            snap = json.load(f)
        if detect_reset(hub, snap):
            print("[auto-restore] %s looks reset -> re-pushing config" % z)
            for label, res in restore_zone(hub, snap):
                print("  - %-40s %s" % (label, res))
            acted += 1
        else:
            print("[auto-restore] %s OK (no reset)" % z)
    print("auto-restore: %d zone(s) restored" % acted)
    return 0


def cmd_info(hub, a):
    info = hub.info()
    devs = info.get("devices", [])
    if not devs:
        print("(no zones / no thermostats paired)")
        return
    for d in devs:
        print("== %s ==" % d.get("device"))
        print("  temperature : %s C (set %s)" %
              (d.get("CURRENT_TEMPERATURE"), d.get("CURRENT_SET_TEMPERATURE")))
        print("  heating     : %s   demand: %s" % (d.get("HEATING"), d.get("DEMAND")))
        print("  sensor      : %s" % d.get("SENSOR_SELECTION"))
        print("  low battery : %s   offline: %s" %
              (d.get("LOW_BATTERY"), d.get("OFFLINE")))
        print("  program     : %s" % d.get("PROGRAM_MODE"))


def cmd_zones(hub, a):
    print(json.dumps(hub.zones(), indent=2, ensure_ascii=False))


def cmd_pair(hub, a):
    name = a.name
    seconds = a.seconds
    before = set(hub.zones().keys())
    res = hub.permit_join(seconds, name)
    print("Pairing open for %ss for %r -> %s" % (seconds, name, json.dumps(res)))
    print("Put the thermostat into pairing mode NOW (SETUP menu / connect to hub)...")
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(3)
        now = set(hub.zones().keys())
        new = now - before
        if name in now and name not in before:
            print("DONE: zone %r appeared on the hub." % name)
            return 0
        if new:
            print("DONE: new zone %r appeared on the hub." % ", ".join(sorted(new)))
            return 0
        print("  ...still waiting (%ds left)" % int(deadline - time.time()))
    print("Window closed without pairing. Check the thermostat display and retry.")
    return 1


def cmd_rename(hub, a):
    print(json.dumps(hub.rename(a.old, a.new), ensure_ascii=False))


def cmd_remove(hub, a):
    print(json.dumps(hub.remove(a.name), ensure_ascii=False))


def cmd_snapshot(hub, a):
    os.makedirs(a.dir, exist_ok=True)
    zones = list(hub.zones().keys())
    if not zones:
        print("(no zones to save)")
        return 1
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    for z in zones:
        snap = snapshot_zone(hub, z)
        safe = z.replace("/", "_").replace(" ", "_")
        hist = os.path.join(a.dir, "%s-%s.json" % (safe, ts))
        latest = os.path.join(a.dir, "%s-latest.json" % safe)
        for path in (hist, latest):
            with open(path, "w") as f:
                json.dump(snap, f, indent=2, ensure_ascii=False)
        print("saved %s -> %s" % (z, latest))
    return 0


def cmd_restore(hub, a):
    if a.file:
        path = a.file
    else:
        safe = a.name.replace("/", "_").replace(" ", "_")
        path = os.path.join(a.dir, "%s-latest.json" % safe)
    if not os.path.exists(path):
        print("No snapshot found: %s" % path, file=sys.stderr)
        return 1
    with open(path) as f:
        snap = json.load(f)
    print("Restoring %r from %s (saved %s)" %
          (snap["zone"], path, snap.get("saved_at")))
    for label, res in restore_zone(hub, snap, dry_run=a.dry_run):
        print("  - %-40s %s" % (label, res))
    return 0


def cmd_ha_json(hub, a):
    info = hub.info()
    out = {}
    for d in info.get("devices", []):
        z = d.get("device")

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        out[z] = {
            "current_temperature": num(d.get("CURRENT_TEMPERATURE")),
            "target_temperature": num(d.get("CURRENT_SET_TEMPERATURE")),
            "heating": bool(d.get("HEATING")),
            "demand": bool(d.get("DEMAND")),
            "away": bool(d.get("AWAY")),
            "standby": bool(d.get("STANDBY")),
            "low_battery": bool(d.get("LOW_BATTERY")),
            "offline": bool(d.get("OFFLINE")),
            "hold": bool(d.get("TEMP_HOLD")),
            "program_mode": d.get("PROGRAM_MODE"),
            "sensor": d.get("SENSOR_SELECTION"),
        }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Local control for a Heatmiser neoHub (port 4242).")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info").set_defaults(fn=cmd_info)
    sub.add_parser("zones").set_defaults(fn=cmd_zones)

    sp = sub.add_parser("pair")
    sp.add_argument("name")
    sp.add_argument("seconds", nargs="?", type=int, default=120)
    sp.set_defaults(fn=cmd_pair)

    sp = sub.add_parser("rename")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.set_defaults(fn=cmd_rename)

    sp = sub.add_parser("remove")
    sp.add_argument("name")
    sp.set_defaults(fn=cmd_remove)

    sp = sub.add_parser("snapshot")
    sp.add_argument("--dir", default=DEFAULT_SNAPDIR)
    sp.set_defaults(fn=cmd_snapshot)

    sp = sub.add_parser("restore")
    sp.add_argument("name")
    sp.add_argument("--file", default=None)
    sp.add_argument("--dir", default=DEFAULT_SNAPDIR)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_restore)

    sp = sub.add_parser("autorestore")
    sp.add_argument("--dir", default=DEFAULT_SNAPDIR)
    sp.set_defaults(fn=cmd_autorestore)

    sub.add_parser("ha-json").set_defaults(fn=cmd_ha_json)

    a = p.parse_args(argv)
    hub = _hub_from_args(a)
    try:
        return a.fn(hub, a) or 0
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
