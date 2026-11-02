# Enabling the local API — reference

The goal is to set, in the hub's config file `/var/local/often/dcb100`:

```json
"LEGACY_LOCAL_PORT" : true,
"LEGACY_LOCAL_PORT_FORCED" : true,
```

That opens a **tokenless** plain-JSON API on TCP port **4242**. Alternatively, the hub
already holds tokens for the TLS WebSocket API on port **4243** in
`/var/local/often/tokens` — read them if you prefer that API or a HACS integration that
wants a token.

## Route A — Serial console (tested)

See [serial-console.md](serial-console.md). Short version: stop U-Boot, boot
`init=/bin/sh`, mount `mmcblk1p4` at `/var/local/often`, `sed` the two booleans to `true`,
`sync`, reboot.

## Route B — microSD recovery (experimental, UNTESTED here, no serial adapter)

The board has a microSD slot (card detect works) and a **boot-select DIP switch `SW2`
labelled `uSD / eMMC`**. On `uSD`, the i.MX6UL BootROM boots from the card instead of the
internal eMMC. This is the friendliest, solder-free route — you prepare one SD image, then
anyone can use it.

**Why it should work:** this hub is the NXP **i.MX6UL 14x14 EVK** reference design (U-Boot
and the kernel identify as such) running the Freescale **L4.1.15** BSP. A standard i.MX6UL
EVK SD image from the same BSP family should boot directly — no custom bootloader needed.

Flow:

1. Flash a small i.MX6UL EVK Linux image to a microSD (SPL + U-Boot at the i.MX raw offset,
   kernel, rootfs). A first-boot script then does step 3.
2. Set `SW2` to **uSD**, insert the card, power on.
3. The script mounts the internal **eMMC** config partition and applies the edit:
   - set `LEGACY_LOCAL_PORT` / `LEGACY_LOCAL_PORT_FORCED` to `true` in `dcb100`
   - restore `settings.oem` from `settings.default` if it was corrupted
   - `sync`, then halt
4. Power off, remove the card, set `SW2` back to **eMMC**, power on. Port 4242 is live.

**Critical cautions (why this is marked experimental):**

- When booting from SD, Linux **MMC device numbering can swap** (the SD may become
  `mmcblk0` and the eMMC `mmcblk1`, or vice-versa). The script must **identify the eMMC
  config partition by its contents** (look for `dcb100` / `settings.default`), never by a
  hard-coded `mmcblkN`, or it could write to the wrong device.
- Only mount + edit the config partition. Do **not** touch the eMMC boot/rootfs partitions.
- Verify on **your** board revision before trusting it. `NEOHUB V2 REV C` is what this repo
  was derived from; other revisions may differ.

**Contributions welcome:** if you build and verify a ready-to-flash microSD image for a
given revision, open a PR with the image recipe (U-Boot/kernel source, the first-boot
script, and exact steps). That turns the cloud-bypass into a 5-minute, no-tools procedure
for everyone.

## eMMC partition layout (observed, REV C)

```
mmcblk1p1  FAT   boot (zImage, dtb)
mmcblk1p2  ext4  rootfs
mmcblk1p3  ext4  /var/local          (settings.oem, settings.default, tokens live here/below)
mmcblk1p4  ext4  /var/local/often    (dcb100  <-- the file you edit)
```

## The commands, once you have a root shell (either route)

```sh
# find and mount the config partition by content, NOT by fixed number:
for p in /dev/mmcblk*p4 /dev/mmcblk*p3; do
  mount -o rw "$p" /mnt 2>/dev/null && [ -e /mnt/dcb100 ] && break
  umount /mnt 2>/dev/null
done
sed -i 's/"LEGACY_LOCAL_PORT" : false/"LEGACY_LOCAL_PORT" : true/; \
        s/"LEGACY_LOCAL_PORT_FORCED" : false/"LEGACY_LOCAL_PORT_FORCED" : true/' \
        /mnt/dcb100
grep LEGACY /mnt/dcb100
sync
```
