#!/usr/bin/env python3
"""
neohub_local — control local, fara cloud, pentru Heatmiser neoHub (port legacy 4242).

Protocol: TCP simplu, fiecare comanda JSON terminata cu NUL (\\0); raspunsul e JSON
terminat cu NUL. Fara token, fara TLS. Portul 4242 a fost activat pe hub
(LEGACY_LOCAL_PORT=true).

Functioneaza cu doar biblioteca standard Python 3 -> ruleaza si pe Mac, si in
containerul Docker de Home Assistant.

Subcomenzi:
  info                      afiseaza starea tuturor zonelor
  zones                     listeaza zonele (nume -> id)
  pair "Nume" [secunde]     deschide pairing si asteapta termostatul (implicit 120s)
  rename "Vechi" "Nou"      redenumeste o zona
  remove "Nume"             sterge o zona de pe hub
  snapshot [--dir D]        salveaza configul fiecarei zone (INFO + program) in JSON
  restore "Nume" [--file F] repune pe termostat setarile din ultimul snapshot
  ha-json                   emite JSON compact cu toate zonele (pentru HA command_line)

Host/port: --host / --port, sau variabilele NEOHUB_HOST / NEOHUB_PORT.
Implicit: 10.0.0.11:4242
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
        """Trimite o comanda (dict) si intoarce raspunsul (dict/list)."""
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
            raise RuntimeError("raspuns gol de la hub")
        return json.loads(buf.decode("utf-8", "replace"))

    # --- comode ---
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


# Campurile din INFO care se pierd la descarcarea bateriei si comanda care le repune.
# (valoare din INFO) -> {"INFO": cheie, "cmd": comanda, "conv": transformare}
def _fmt_from_mode(mode):
    return {
        "5DAY/2DAY": "5DAY/2DAY",
        "7DAY": "7DAY",
        "24HOUR": "24HOURSFIXED",
        "24HOURSFIXED": "24HOURSFIXED",
        "NONPROGRAMMABLE": "NONPROGRAMMABLE",
    }.get(mode, mode)


def snapshot_zone(hub, zone):
    """Construieste obiectul de snapshot pentru o zona."""
    info_all = hub.info()
    dev = None
    for d in info_all.get("devices", []):
        if d.get("device") == zone:
            dev = d
            break
    if dev is None:
        raise RuntimeError("zona %r nu a fost gasita in INFO" % zone)
    comfort = hub.comfort(zone).get(zone, {})
    return {
        "zone": zone,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "info": dev,
        "comfort_levels": comfort,
    }


def restore_zone(hub, snap, dry_run=False):
    """Repune setarile pe termostat din snapshot. Intoarce lista de (actiune, rezultat)."""
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
            out.append((label, "EROARE: %s" % e))
        time.sleep(0.4)

    # 1. Programul saptamanal (cel mai important) + formatul de program
    mode = info.get("PROGRAM_MODE")
    if mode:
        # SET_FORMAT ia doar string-ul formatului (nu array). "24HOUR" -> "24HOURSFIXED".
        do("format program (SET_FORMAT %s)" % mode,
           {"SET_FORMAT": _fmt_from_mode(mode)})
    comfort = snap.get("comfort_levels")
    if comfort:
        do("program saptamanal (SET_COMFORT_LEVELS)",
           {"SET_COMFORT_LEVELS": [comfort, zone]})

    # 2. Formatul de temperatura C/F
    tf = info.get("TEMPERATURE_FORMAT")
    if tf is not None:
        # SET_TEMP_FORMAT ia doar "C"/"F" (nu array). E setare globala pe hub.
        do("format temperatura (SET_TEMP_FORMAT)",
           {"SET_TEMP_FORMAT": "F" if tf else "C"})

    # 3. Intarziere iesire (output delay)
    od = info.get("OUTPUT_DELAY")
    if isinstance(od, int):
        do("output delay (SET_DELAY %s)" % od, {"SET_DELAY": [od, zone]})

    # 4. Setari optionale, doar daca sunt prezente si valide in snapshot
    diff = info.get("SWITCHING_DIFFERENTIAL")
    if diff not in (None, 170):
        do("diferential comutare (SET_DIFF %s)" % diff, {"SET_DIFF": [diff, zone]})
    # preheat: PREHEAT_TIME "170:170" inseamna neconfigurat -> sarim
    ph = info.get("MAX_PREHEAT")
    if ph not in (None, 170):
        do("preheat (SET_PREHEAT %s)" % ph, {"SET_PREHEAT": [ph, zone]})
    if info.get("FLOOR_LIMIT") and info.get("FLOOR_LIMIT_TEMP") not in (None, 127):
        do("limita pardoseala (SET_FLOOR)",
           {"SET_FLOOR": [info["FLOOR_LIMIT_TEMP"], zone]})

    # 5. Ce NU se poate repune automat prin API-ul legacy -> se face manual pe termostat
    sensor = info.get("SENSOR_SELECTION")
    out.append(("senzor (SENSOR_SELECTION=%s)" % sensor,
                "MANUAL: API-ul legacy nu are comanda de setare a senzorului; "
                "se alege pe termostat la configurare"))
    return out


def detect_reset(hub, snap):
    """True daca zona pare resetata la fabrica (ex: dupa moartea bateriei).
    Prudent: doar cand programul live e gol/pierdut, DESI snapshotul avea unul.
    Nu se declanseaza cand doar ai schimbat tu o setare."""
    zone = snap["zone"]
    snap_comfort = snap.get("comfort_levels") or {}
    snap_mode = (snap.get("info") or {}).get("PROGRAM_MODE")
    # Termostatul trebuie sa fie ONLINE: hub-ul nu citeste/scrie la unul offline,
    # iar un offline ar da fals-pozitiv de "reset".
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
    """Pentru fiecare zona cu snapshot: daca pare resetata, repune configul.
    De rulat periodic (ex: din HA, orar). Nu face nimic daca nu e reset."""
    acted = 0
    zones = list(hub.zones().keys())
    for z in zones:
        safe = z.replace("/", "_").replace(" ", "_")
        path = os.path.join(a.dir, "%s-latest.json" % safe)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            snap = json.load(f)
        if detect_reset(hub, snap):
            print("[auto-restore] %s pare resetat -> repun configul" % z)
            for label, res in restore_zone(hub, snap):
                print("  - %-40s %s" % (label, res))
            acted += 1
        else:
            print("[auto-restore] %s OK (fara reset)" % z)
    print("auto-restore: %d zona(e) repusa(e)" % acted)
    return 0


def cmd_info(hub, a):
    info = hub.info()
    devs = info.get("devices", [])
    if not devs:
        print("(nicio zona / niciun termostat asociat)")
        return
    for d in devs:
        print("== %s ==" % d.get("device"))
        print("  temperatura   : %s C (setat %s)" %
              (d.get("CURRENT_TEMPERATURE"), d.get("CURRENT_SET_TEMPERATURE")))
        print("  incalzeste    : %s   demand: %s" % (d.get("HEATING"), d.get("DEMAND")))
        print("  senzor        : %s" % d.get("SENSOR_SELECTION"))
        print("  baterie slaba : %s   offline: %s" %
              (d.get("LOW_BATTERY"), d.get("OFFLINE")))
        print("  mod program   : %s" % d.get("PROGRAM_MODE"))


def cmd_zones(hub, a):
    print(json.dumps(hub.zones(), indent=2, ensure_ascii=False))


def cmd_pair(hub, a):
    name = a.name
    seconds = a.seconds
    before = set(hub.zones().keys())
    res = hub.permit_join(seconds, name)
    print("Pairing deschis %ss pentru %r -> %s" % (seconds, name, json.dumps(res)))
    print("Pune ACUM termostatul in modul de pairing (meniu SETUP / conectare hub)...")
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(3)
        now = set(hub.zones().keys())
        new = now - before
        if name in now and name not in before:
            print("GATA: zona %r a aparut pe hub." % name)
            return 0
        if new:
            print("GATA: zona noua %r a aparut pe hub." % ", ".join(sorted(new)))
            return 0
        print("  ...inca astept (%ds ramase)" % int(deadline - time.time()))
    print("Fereastra s-a inchis fara asociere. Verifica ecranul termostatului si reia.")
    return 1


def cmd_rename(hub, a):
    print(json.dumps(hub.rename(a.old, a.new), ensure_ascii=False))


def cmd_remove(hub, a):
    print(json.dumps(hub.remove(a.name), ensure_ascii=False))


def cmd_snapshot(hub, a):
    os.makedirs(a.dir, exist_ok=True)
    zones = list(hub.zones().keys())
    if not zones:
        print("(nicio zona de salvat)")
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
        print("salvat %s -> %s" % (z, latest))
    return 0


def cmd_restore(hub, a):
    if a.file:
        path = a.file
    else:
        safe = a.name.replace("/", "_").replace(" ", "_")
        path = os.path.join(a.dir, "%s-latest.json" % safe)
    if not os.path.exists(path):
        print("Nu exista snapshot: %s" % path, file=sys.stderr)
        return 1
    with open(path) as f:
        snap = json.load(f)
    print("Restore %r din %s (salvat %s)" %
          (snap["zone"], path, snap.get("saved_at")))
    results = restore_zone(hub, snap, dry_run=a.dry_run)
    for label, res in results:
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
    p = argparse.ArgumentParser(description="Control local Heatmiser neoHub (port 4242).")
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
        print("EROARE: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
