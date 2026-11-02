#!/usr/bin/env python3
"""Bidirectional serial console for the neoHub (115200 8N1).
Everything from the console is written to a timestamped .log; whatever you write into the
'tx' FIFO is sent over serial. Handy for stopping U-Boot autoboot and issuing commands.

Usage: python3 console.py [/dev/ttyUSB0] [115200]
Send a command:  ./send.sh 'printenv'
Standard library + pyserial (pip install pyserial).
"""
import serial, sys, os, time, datetime, select
port = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEOHUB_SERIAL", "/dev/ttyUSB0")
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
here = os.path.dirname(os.path.abspath(__file__))
log = os.path.join(here, "console-%s.log" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
fifo = os.path.join(here, "tx")
if not os.path.exists(fifo):
    os.mkfifo(fifo)
s = serial.Serial(port, baud, timeout=0.2)
fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
print("port=%s baud=%s log=%s fifo=%s" % (port, baud, log, fifo), flush=True)
with open(log, "ab") as f:
    while True:
        d = s.read(4096)
        if d:
            f.write(d); f.flush()
            sys.stdout.buffer.write(d); sys.stdout.flush()
        r, _, _ = select.select([fd], [], [], 0)
        if r:
            try:
                c = os.read(fd, 4096)
            except BlockingIOError:
                c = b""
            if c:
                for ch in c:
                    s.write(bytes([ch])); time.sleep(0.003)
                s.flush()
