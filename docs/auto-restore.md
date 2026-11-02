# Auto-restore after a dead battery

neoAir thermostats hold their own weekly schedule and settings. When the battery dies and is
replaced, they can come back reset to defaults. The hub keeps talking to them over RF, so we
re-push what was lost.

## How

1. **Snapshot** (run daily). For every zone it stores, under `snapshots/<Zone>-latest.json`:
   - the full live `INFO` object, and
   - the weekly schedule (`READ_COMFORT_LEVELS`).

   ```bash
   python3 neohub_local.py snapshot
   ```

2. **Restore** (after a battery change, or automatically). Re-pushes:
   - weekly schedule — `SET_COMFORT_LEVELS` (the big one)
   - program format (5DAY/2DAY, 7DAY, …) — `SET_FORMAT`
   - temperature format C/F — `SET_TEMP_FORMAT`
   - output delay — `SET_DELAY`
   - optional, if present in the snapshot: switching differential, preheat, floor limit

   ```bash
   python3 neohub_local.py restore "Living"
   ```

3. **autorestore** (safe to run hourly) only acts on a zone that is **online** and looks
   **reset** (its schedule came back empty, or the program mode was lost) — so it heals a
   battery-replaced thermostat without ever reverting a change you made on purpose, and it
   never writes to a sleeping/offline stat.

   ```bash
   python3 neohub_local.py autorestore
   ```

## What cannot be auto-restored

- **Sensor selection** (built-in air vs floor vs both): the legacy API has no command to set
  it. Choose it once on the thermostat after pairing. The tools report this explicitly.

## Notes on battery thermostats

- neoAir stats sleep to save battery and report in periodically, so `INFO` often shows
  `OFFLINE: true`. Writes (SET_*) only succeed while the stat is awake/online — which is the
  case right after a battery change when it reconnects.
