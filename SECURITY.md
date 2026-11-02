# Security note

**The legacy local port (4242) has no authentication.** Anyone who can reach that TCP port
on your LAN can read and change your heating — pair/unpair thermostats, change schedules and
temperatures. The port is plain-text (no TLS).

Recommendations:

- Keep the hub on a trusted network. Do **not** port-forward 4242 to the internet.
- Prefer isolating IoT devices on their own VLAN/subnet and allowing only your controller
  (e.g. Home Assistant) to reach the hub.
- If you need authentication/encryption, use the **4243** TLS WebSocket API with a token
  from `/var/local/often/tokens` instead of 4242.

This project is for controlling **your own** hub on **your own** network.
