# Heatmiser neoHub — Local control without the cloud

Bring a **Heatmiser neoHub (2nd gen)** back to life when the **LINK LED is red** and the
Heatmiser cloud no longer talks to it. No cloud, no app, no API token from their portal.
You get full **local** control: pair thermostats, read live data, change settings, and
**auto-restore a neoAir's settings after its battery dies** — all over the hub's local
JSON API, and optionally inside **Home Assistant**.

> Not affiliated with Heatmiser. Use at your own risk. See [Safety](#safety--disclaimer).

## The problem

On a neoHub 2nd gen, a **red LINK LED** means the hub can't reach Heatmiser's servers.
When that happens:

- The **neoApp can't connect**, so you can't change anything remotely.
- You **can't generate an API token** (that is done from the app, which needs the cloud).
- **neoAir** battery thermostats **lose their schedule and settings when the battery dies**.

The hub still has a **local API** — it's just switched off by default and is normally
enabled from the app. This project turns it on **directly on the hub**, then gives you
tools to use it.

## What you get

- **Tokenless local API on port 4242** (the "legacy local port"), plain JSON over TCP.
- **`neohub_local.py`** — a single-file, dependency-free Python 3 CLI:
  - `pair` a thermostat (replaces the app's "add" flow)
  - `info` / `zones` — live status
  - `snapshot` / `restore` / `autorestore` — back up each zone's config and re-push it
    after a battery change
- **Home Assistant integration** as an isolated *package* (sensors + automations +
  hourly auto-restore), so it can never break your existing config.

## Does this apply to me?

- neoHub **2nd generation** (small white box, i.MX6UL inside, PCB marked `NEOHUB V2 REV C`).
- LINK LED **red**; the neoApp won't connect.
- You're OK **opening the case once** to enable the local port (USB-serial adapter, or the
  experimental microSD route).

## Step 1 — Enable the local API (port 4242)

Port 4242 is disabled by default and normally toggled from the app. With no cloud you
enable it on the hub itself. Two routes:

- **Serial console (tested, recommended).** Full walkthrough: [docs/serial-console.md](docs/serial-console.md).
- **microSD recovery (experimental, untested on your unit).** Notes: [docs/enable-local-api.md](docs/enable-local-api.md).

Both do the same thing: set `LEGACY_LOCAL_PORT` (and `LEGACY_LOCAL_PORT_FORCED`) to `true`
in the hub's config file `dcb100`, and — if you prefer the TLS WebSocket API on port 4243 —
read the existing tokens from `/var/local/often/tokens`. Details and exact commands are in
[docs/enable-local-api.md](docs/enable-local-api.md).

After this, from any machine on your LAN:

```
printf '{"INFO":0}\0' | nc <HUB_IP> 4242
```

should return JSON.

## Step 2 — Use the CLI

```bash
export NEOHUB_HOST=<HUB_IP>          # your hub's IP

python3 neohub_local.py zones                 # list zones
python3 neohub_local.py info                  # live status of every thermostat
python3 neohub_local.py pair "Living" 150     # add a thermostat (150s pairing window)
python3 neohub_local.py rename "Old" "New"
python3 neohub_local.py snapshot              # back up all zones to ./snapshots
python3 neohub_local.py restore "Living"      # re-push the saved config (after a battery change)
python3 neohub_local.py autorestore           # re-push ONLY zones that look reset (safe to run hourly)
python3 neohub_local.py ha-json               # compact JSON for Home Assistant
```

Pairing replaces the app's "add thermostat": the command opens the join window, you put
the neoAir into pairing mode (its SETUP menu), and the zone appears on the hub.

## Step 3 — Home Assistant

Copy `neohub_local.py` to `/config/neohub/` and drop
[`homeassistant/packages/neohub.yaml`](homeassistant/packages/neohub.yaml) into
`/config/packages/`. Full instructions: [homeassistant/README.md](homeassistant/README.md).
You get per-zone sensors, a daily snapshot, and hourly auto-restore.

> **Alternative:** the community HACS integration **"Heatmiser Neo"** gives full `climate`
> entities. It can use the TLS WebSocket API on port **4243** with a token from
> `/var/local/often/tokens`. Use it for rich thermostat cards; this repo's tools remain
> useful for pairing and for snapshot/restore, which that integration does not do.

## Step 4 — Auto-restore after a dead battery (the whole point)

neoAir thermostats forget their schedule/settings when the battery dies. The fix:

1. **Snapshot** every zone regularly (daily) — stores the weekly schedule + settings.
2. **After the battery is replaced**, `restore` (or the automatic `autorestore`) re-pushes:
   weekly schedule (`SET_COMFORT_LEVELS`), program format, output delay, and the optional
   per-zone settings.

What **cannot** be restored via the local API: **sensor selection** (air vs floor). Set it
once on the thermostat. See [docs/auto-restore.md](docs/auto-restore.md).

## Safety / disclaimer

- Opening the case and using the serial console may **void your warranty**. You do this at
  your own risk.
- On the serial adapter use **3.3 V logic only** — 5 V can destroy the SoC.
- The microSD route is **experimental** and not verified on every board revision.
- This project is **not affiliated with or endorsed by Heatmiser**. "Heatmiser", "neoHub"
  and "neoAir" are trademarks of their owner.

## How it works (background)

- The neoHub 2nd gen runs Linux (i.MX6UL, U-Boot + kernel 4.1, BusyBox). A labelled
  `CONSOLE` header (`J1`) exposes a 3.3 V serial console; root has no password.
- The local protocol is plain JSON over TCP on port **4242**, each message terminated with
  a NUL byte (`\0`). Commands are documented in Heatmiser's legacy "neoHub JSON commands"
  spec.
- Enabling the port is a one-time edit of the hub's `dcb100` config file; everything after
  is done over the network.

## More docs

- [docs/enable-local-api.md](docs/enable-local-api.md) - enable port 4242 (serial + microSD)
- [docs/serial-console.md](docs/serial-console.md) - serial console walkthrough (tested)
- [docs/api-commands.md](docs/api-commands.md) - the local JSON command reference
- [docs/auto-restore.md](docs/auto-restore.md) - restore after a dead battery
- [docs/troubleshooting.md](docs/troubleshooting.md) - red LED, pairing, offline writes
- [homeassistant/README.md](homeassistant/README.md) - Home Assistant package
- [tools/](tools/) - serial console helpers
- [examples/](examples/) - cron / systemd for running without Home Assistant
- [SECURITY.md](SECURITY.md) - the 4242 port is unauthenticated; read this
- [CONTRIBUTING.md](CONTRIBUTING.md) - especially the microSD image bounty
