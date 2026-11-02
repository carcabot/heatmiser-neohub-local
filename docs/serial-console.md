# Serial console method (tested)

This is how you get a root shell on the neoHub 2nd gen and enable the local API. It is the
reliable route. Budget ~30 minutes.

## You need

- A **3.3 V USB-to-serial adapter** (e.g. CP2102, CH340, FT232 — set the jumper to **3.3 V**).
- 3 jumper wires.
- A serial terminal at **115200 8N1** (`screen`, `minicom`, PuTTY, or the Python logger below).

## The console header (J1)

On `NEOHUB V2 REV C` the 4-pin header near the top is labelled **`CONSOLE`**, with **`GND`**
marked on the silkscreen. Only GND is labelled; the other three are TX, RX and 3.3 V in an
unknown order. You find RX/TX by probing — it's harmless.

Pinout that worked on REV C (pin 1 = the GND end):

| J1 pin | Function (REV C) | Connect to adapter |
|--------|------------------|--------------------|
| 1 (GND)| GND              | GND                |
| 2      | TX (hub → you)   | RXD                |
| 3      | 3.3 V            | leave unconnected  |
| 4      | RX (you → hub)   | TXD                |

> If your revision differs: connect GND, then move the adapter's **RXD** across pins 2/3/4
> with the hub powered — the pin that spits out boot text is the hub's **TX**. The hub's
> **RX** is one of the remaining pins (the one that is *not* ~3.3 V to GND). Don't drive a
> 3.3 V pin with TXD.

**Never connect the 3.3 V pin to the adapter's power.** The hub is powered by its own
mini-USB.

## Open a console

`screen /dev/ttyUSB0 115200` (Linux) or `screen /dev/cu.usbserial-XXXX 115200` (macOS), or
use a tiny bidirectional logger — see `tools/` in this repo if provided.

## Get a root shell (no password)

Power the hub. You'll see U-Boot:

```
U-Boot 2015.04 ...
Hit any key to stop autoboot:  3
```

Press a key within 3 seconds to stop at the `=>` prompt, then boot straight to a shell:

```
=> setenv mmcroot '/dev/mmcblk1p2 rootwait rw init=/bin/sh'
=> run loadimage; run mmcboot
```

(This is **not saved**; the next power-cycle boots normally.) You land at `sh-4.3#` as root.

> There is also a getty on the serial console after a normal boot, and `/etc/shadow` has an
> empty root password — so you can just log in on the console too. The `init=/bin/sh` route
> is used because it gives you the filesystem read-write before the hub app starts.

## Enable the local port + read tokens

```sh
# mount the data partitions (p3=/var/local, p4=/var/local/often)
mount -o remount,rw / ; mount -t proc proc /proc
mount /dev/mmcblk1p3 /var/local
mkdir -p /var/local/often
mount /dev/mmcblk1p4 /var/local/often

# turn the legacy local port ON (tokenless API on 4242)
sed -i 's/"LEGACY_LOCAL_PORT" : false/"LEGACY_LOCAL_PORT" : true/; \
        s/"LEGACY_LOCAL_PORT_FORCED" : false/"LEGACY_LOCAL_PORT_FORCED" : true/' \
        /var/local/often/dcb100
grep LEGACY /var/local/often/dcb100          # confirm both true

# (optional) tokens for the TLS WebSocket API on port 4243
cat /var/local/often/tokens

sync
```

Power-cycle the hub (normal boot). From the LAN:

```
printf '{"INFO":0}\0' | nc <HUB_IP> 4242      # should return JSON
```

You're done with the serial adapter — everything else is over the network.

## If settings.oem got corrupted

If the boot log shows `ERR:/var/local/settings.oem: No match for line [...]`, the OEM
settings file was overwritten with junk. Restore the factory default:

```sh
mount -o remount,rw /var/local
cp /var/local/settings.default /var/local/settings.oem
sync
```
