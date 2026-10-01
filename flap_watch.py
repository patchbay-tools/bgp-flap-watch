#!/usr/bin/env python3
"""Watch a BIRD routing table for prefix flaps.

Polls ``birdc show route`` on an interval, compares the set of prefixes
with the previous poll and logs a flap when a prefix has changed state
more than ``--threshold`` times inside ``--window`` seconds.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

log = logging.getLogger("flap-watch")

PREFIX_RE = re.compile(r"^([0-9a-fA-F:.]+/\d{1,3})\s")
PROTOCOL_RE = re.compile(
    r"^(?P<name>\S+)\s+(?P<proto>\S+)\s+(?P<table>\S+)\s+(?P<state>\S+)"
    r"\s+(?P<since>\S+(?:\s\d{2}:\d{2}:\d{2}(?:\.\d+)?)?)\s*(?P<info>.*)$"
)


@dataclass
class Protocol:
    name: str
    proto: str
    state: str
    info: str


@dataclass
class FlapTracker:
    window: float
    threshold: int
    events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    current: set[str] = field(default_factory=set)
    reported: set[str] = field(default_factory=set)
    primed: bool = False

    def update(self, prefixes: set[str], now: float) -> list[tuple[str, int]]:
        """Record a poll and return (prefix, changes) for prefixes that just crossed the threshold.

        A prefix is reported once per flapping episode, not on every change after it
        crosses; it can be reported again once its changes drop back under the threshold.
        """
        if not self.primed:
            self.current = prefixes
            self.primed = True
            return []

        changed = prefixes ^ self.current
        self.current = prefixes
        flapping = []

        for prefix in changed:
            history = self.events[prefix]
            history.append(now)
            while history and now - history[0] > self.window:
                history.popleft()
            if len(history) < self.threshold:
                self.reported.discard(prefix)
            elif prefix not in self.reported:
                self.reported.add(prefix)
                flapping.append((prefix, len(history)))

        return sorted(flapping)


def parse_routes(output: str) -> set[str]:
    """Return the prefixes in ``birdc show route`` output.

    Continuation lines (alternative paths, ``via`` lines) start with
    whitespace and are skipped, so each prefix is counted once.
    """
    prefixes = set()
    for line in output.splitlines():
        match = PREFIX_RE.match(line)
        if match:
            prefixes.add(match.group(1))
    return prefixes


def parse_protocols(output: str) -> list[Protocol]:
    """Return the BGP sessions in ``birdc show protocols`` output."""
    sessions = []
    for line in output.splitlines():
        match = PROTOCOL_RE.match(line)
        if not match or match["proto"] != "BGP":
            continue
        sessions.append(Protocol(match["name"], match["proto"], match["state"], match["info"].strip()))
    return sessions


def birdc(socket: str | None, *command: str) -> str:
    args = ["birdc"]
    if socket:
        args += ["-s", socket]
    args += list(command)
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=30).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--protocol", help="only watch routes from this BGP session")
    parser.add_argument("--table", help="routing table to watch (default: master4)")
    parser.add_argument("--socket", help="path to the BIRD control socket")
    parser.add_argument("--interval", type=float, default=15, help="seconds between polls")
    parser.add_argument("--window", type=float, default=600, help="flap window in seconds")
    parser.add_argument("--threshold", type=int, default=4, help="changes in the window that count as a flap")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.interval <= 0 or args.window <= 0:
        parser.error("--interval and --window must be positive")
    if args.threshold < 2:
        parser.error("--threshold must be at least 2")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    command = ["show", "route"]
    if args.table:
        command += ["table", args.table]
    if args.protocol:
        command += ["protocol", args.protocol]

    tracker = FlapTracker(window=args.window, threshold=args.threshold)
    session_state: dict[str, str] = {}

    while True:
        try:
            prefixes = parse_routes(birdc(args.socket, *command))
            sessions = parse_protocols(birdc(args.socket, "show", "protocols"))
        except (subprocess.SubprocessError, OSError) as exc:
            log.error("birdc failed: %s", exc)
            time.sleep(args.interval)
            continue

        for session in sessions:
            previous = session_state.get(session.name)
            if previous and previous != session.state:
                log.warning("session %s: %s -> %s %s", session.name, previous, session.state, session.info)
            session_state[session.name] = session.state

        log.debug("%d prefixes", len(prefixes))
        for prefix, count in tracker.update(prefixes, time.monotonic()):
            log.warning("flap: %s changed %d times in %ds", prefix, count, args.window)

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
