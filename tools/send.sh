#!/bin/sh
# Send text to the serial console, via the FIFO created by console.py.
#   ./send.sh 'printenv'        # with newline
#   ./send.sh -n ' '            # raw, no newline (e.g. a keypress to stop autoboot)
FIFO="$(dirname "$0")/tx"
if [ "$1" = "-n" ]; then shift; printf '%s' "$*" > "$FIFO"
else printf '%s\n' "$*" > "$FIFO"; fi
