# Contributing

Issues and PRs welcome, especially:

- **A verified microSD recovery image** (see [docs/enable-local-api.md](docs/enable-local-api.md))
  for a given board revision. This is the single biggest win: it turns the cloud-bypass into
  a no-tools, no-soldering procedure. Please include the U-Boot/kernel source, the first-boot
  script, and exact steps.
- **Confirmations on other board revisions / firmware versions** (update the table below).
- **More API coverage** in `neohub_local.py` (cooling, holidays, holds, repeaters).
- **Bug fixes and docs.**

## Compatibility (confirmed)

| Board | Firmware | Enable method | Notes |
|-------|----------|---------------|-------|
| NEOHUB V2 REV C (i.MX6UL) | 2218 | serial console | J1 pin 4 = hub RX; tokenless 4242 works |

Add a row when you confirm a new combination.

## Please

- Keep `neohub_local.py` dependency-free (standard library only) so it runs anywhere,
  including inside the Home Assistant container.
- Don't commit snapshots, logs, tokens, or anything with your hub's IP / personal data.
