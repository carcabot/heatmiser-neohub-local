# Local API command reference (port 4242)

Plain JSON over TCP. **Every command must be terminated with a NUL byte (`\0`).** The
response is JSON, also NUL-terminated. No token, no TLS.

Quick test:

```bash
printf '{"INFO":0}\0' | nc <HUB_IP> 4242
```

`<device(s)>` is a zone name (`"Living"`), a list (`["Living","Bucatarie"]`), or a group name.

## Read

| Command | Returns |
|---|---|
| `{"INFO":0}` | full live state of every zone (temp, setpoint, battery, offline, program mode, sensor, …) |
| `{"GET_ZONES":0}` | map of zone name → id |
| `{"GET_SYSTEM":0}` | hub-wide settings (firmware, format, legacy port state, …) |
| `{"FIRMWARE":0}` | firmware version |
| `{"READ_COMFORT_LEVELS":"Living"}` | the weekly schedule for a zone |

## Pairing / zones

| Command | Effect |
|---|---|
| `{"PERMIT_JOIN":[<seconds>,"<name>"]}` | open the join window AND create the zone; put the neoAir into pairing mode within the window |
| `{"PERMIT_JOIN":["repeater",<seconds>]}` | join a zigbee repeater (different form) |
| `{"ZONE_TITLE":["<old>","<new>"]}` | rename a zone |
| `{"REMOVE_ZONE":"<name>"}` | delete a zone |

## Write (the settings that get lost on a dead battery)

| Command | Sets |
|---|---|
| `{"SET_COMFORT_LEVELS":[<levels>,<device(s)>]}` | weekly schedule (object from `READ_COMFORT_LEVELS`) |
| `{"SET_FORMAT":"5DAY/2DAY"}` | program format: `"NONPROGRAMMABLE"`, `"7DAY"`, `"5DAY/2DAY"`, `"24HOURSFIXED"` (string, not array) |
| `{"SET_TEMP_FORMAT":"C"}` | `"C"` or `"F"` (string, hub-wide) |
| `{"SET_DELAY":[<minutes>,<device(s)>]}` | output delay |
| `{"SET_DIFF":[<diff>,<device(s)>]}` | switching differential |
| `{"SET_PREHEAT":[<temp>,<device(s)>]}` | max preheat |
| `{"SET_FLOOR":[<temp>,<device(s)>]}` | floor limit temperature |
| `{"SET_FROST":[<temp>,<device(s)>]}` | frost/standby temperature |
| `{"SET_TEMP":[<temp>,<device(s)>]}` | current target (schedule overrides at next event) |

**Cannot be set via this API:** `SENSOR_SELECTION` (air/floor). Choose it on the thermostat.

## Gotchas

- Writes to an **offline** (sleeping) battery stat are rejected (`"...should be a valid device"`).
  They succeed only while the stat is awake — e.g. right after a battery change when it
  reconnects.
- `SET_FORMAT` and `SET_TEMP_FORMAT` take a **bare string**, not an array (unlike the others).
- The full legacy spec is "neoHub JSON commands" from Heatmiser (not redistributed here).
