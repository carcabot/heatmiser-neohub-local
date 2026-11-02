# Home Assistant integration (isolated package)

This adds neoHub as sensors + automations **without touching your existing
`configuration.yaml` / `automations.yaml`**, by using a [package](https://www.home-assistant.io/docs/configuration/packages/).

## Install

1. Copy the toolkit into your config dir:

   ```
   /config/neohub/neohub_local.py
   /config/neohub/snapshots/          (created automatically)
   ```

   The HA container has Python 3 and can reach the hub on your LAN, so the script runs
   there with no extra dependencies.

2. Enable packages (once) in `configuration.yaml`:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

3. Copy [`packages/neohub.yaml`](packages/neohub.yaml) to `/config/packages/neohub.yaml`
   and set the host at the top of `neohub_local.py` or via the `NEOHUB_HOST` env — edit the
   zone names to match yours.

4. **Validate, then restart HA the safe way:**

   ```
   # inside the HA container
   python3 -m homeassistant --script check_config -c /config     # expect no errors
   ```

   Then call the **`homeassistant.restart`** service (Developer Tools → Actions), **not** a
   Docker restart. A Docker restart with a short stop timeout can SIGKILL HA mid-shutdown
   and wedge the container. (`command_line` is a new integration, so a full restart is
   needed the first time; later tweaks reload with `homeassistant.reload_all`.)

## What you get

- `sensor.neohub_raw` — polls the hub every 120 s, each zone as an attribute.
- Per-zone template sensors (example: `Living`): temperature, setpoint, heating, battery,
  connectivity. Duplicate the template block per zone and add the zone name to
  `json_attributes`.
- `shell_command.neohub_snapshot / restore / autorestore / pair`.
- Automations: daily snapshot (03:30), hourly `autorestore`, low-battery notification.

## Adding more zones

1. Add the zone name under `command_line: ... json_attributes:`.
2. Copy the `Living` template sensors and rename to the new zone.

## Pairing from HA

```yaml
action: shell_command.neohub_pair
data:
  zone: "Bucatarie"
  seconds: 150
```

Then put the neoAir into pairing mode.

## Notes

- Control (changing setpoint from HA) is intentionally **not** included: neoAir is a
  battery stat that sleeps, and the hub rejects writes while it's offline, so a setpoint
  control would fail often. Add it only if you accept it works solely when the stat is
  awake.
