# tools/

Helpers for the serial-console route ([../docs/serial-console.md](../docs/serial-console.md)).

- `console.py` — bidirectional serial console (115200 8N1). Logs everything to a timestamped
  file and sends whatever you write into the `tx` FIFO. Needs `pyserial`
  (`pip install pyserial`).
- `send.sh` — write a line (or a raw keystroke) into that FIFO.

```bash
pip install pyserial
python3 tools/console.py /dev/ttyUSB0 115200      # leave running in one terminal
# in another terminal:
tools/send.sh -n ' '          # tap to stop U-Boot autoboot during the 3s countdown
tools/send.sh "printenv"
```
