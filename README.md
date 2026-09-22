# bgp-flap-watch

Watch a BIRD 2 routing table for prefixes that keep coming and going.

It polls `birdc show route` every few seconds, diffs the prefix set against the last poll, and
logs a warning when a prefix changes state `--threshold` times inside `--window` seconds. BGP
session state changes from `birdc show protocols` are logged too, so you can see whether a
flap lines up with a session reset.

No dependencies beyond Python 3.10 and `birdc` on the path.

## Usage

```
./flap_watch.py --protocol upstream1 --interval 10 --window 300 --threshold 4
```

```
2024-03-02 11:20:13,402 WARNING session upstream2: up -> start Active Socket: Connection refused
2024-03-02 11:22:41,118 WARNING flap: 192.0.2.0/24 changed 4 times in 300s
```

| option | default | |
|---|---|---|
| `--protocol` | all | only routes learned from this session |
| `--table` | master4 | table to watch; use `master6` for IPv6 |
| `--socket` | BIRD default | control socket path, e.g. `/run/bird/bird.ctl` |
| `--interval` | 15 | seconds between polls |
| `--window` | 600 | flap window in seconds |
| `--threshold` | 4 | changes inside the window that count as a flap |

Run it as a user that can talk to the BIRD socket (usually the `bird` group).

## Running as a service

```ini
[Unit]
Description=BGP flap watch
After=bird.service

[Service]
ExecStart=/usr/local/bin/flap_watch.py --table master4
User=bird
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Tests

```
python3 -m unittest discover -s tests
```
