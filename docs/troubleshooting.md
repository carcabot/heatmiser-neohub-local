# Troubleshooting

## LINK LED is red / the app won't connect
The hub can't reach Heatmiser's cloud. That is exactly the situation this project is for —
it does **not** need the cloud. The red LED is only the cloud indicator; local control
(port 4242) is independent and will work with the LED still red. Don't wait for it to turn
green.

## Port 4242 refuses the connection
- You haven't enabled it yet — see [enable-local-api.md](enable-local-api.md).
- Confirm on the hub: `grep LEGACY /var/local/often/dcb100` should show both
  `LEGACY_LOCAL_PORT` and `LEGACY_LOCAL_PORT_FORCED` = `true`.
- Reboot the hub once after the edit.
- Check you're using the hub's real IP and that nothing (VLAN/firewall) blocks it.

## A thermostat won't pair
- Open the window right before putting the stat into pairing: the hub accepts the
  `PERMIT_JOIN` reply (`"network allows joining"`) but the stat must send the join itself.
- **Range:** the neoAir talks to the hub over 868 MHz RF. If the hub's case is open / antenna
  disconnected, range collapses — pair with the stat next to the hub, or reassemble the hub
  first. Reassembling (antenna back in place) fixed pairing in testing.
- **Already paired elsewhere:** a stat bound to another hub won't join until it's reset
  (factory reset / re-run the connect step on the thermostat).
- It can take a second or third window. Re-open with `PERMIT_JOIN` and try again.

## INFO shows `OFFLINE: true` and temperatures look stale
Normal for battery neoAir — they sleep and report in periodically. Reads reflect the last
report; writes only land while the stat is awake.

## `settings.oem` error at boot
`ERR:/var/local/settings.oem: No match for line [...]` means the OEM file was overwritten.
Restore it: `cp /var/local/settings.default /var/local/settings.oem` (read-write mount first).

## No API token for the 4243 WebSocket API
You don't need the cloud/app: the tokens already on the hub are in
`/var/local/often/tokens`. Read them over the serial console.
