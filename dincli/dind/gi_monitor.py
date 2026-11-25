"""Poll one local dind for GI stalls. Run with python -m dincli.dind.gi_monitor."""

import argparse
import json
import re
import socket
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
from threading import Timer

from dincli.dind.chain_health import CHECK_INTERVAL_S
from dincli.sdk.state import GIState

REQUEST_TIMEOUT_S = 5


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class Observation:
    gi: int
    phase: GIState
    age: int
    checked_at: datetime
    observed_since: datetime
    alerted: bool = False

    def event(self, kind, address):
        return {"event": kind, "coordinator": address, "gi": self.gi,
                "state": self.phase.name, "observed_for_s": self.age}


def parse_model(row, stamp):
    gi = row.get("gi")
    age = row.get("observed_for_s")
    phase = row.get("state")
    if "error" in row or type(gi) is not int or not 0 <= gi < 2**256:
        return None
    if type(age) is not int or age < 0:
        return None
    if not isinstance(phase, str) or phase not in GIState.__members__:
        return None
    phase = GIState[phase]
    if type(row.get("state_code")) is not int or row["state_code"] != phase:
        return None
    if (gi == 0) != (phase < GIState.GIstarted):
        return None
    since = timestamp(row.get("observed_since"))
    if since is None or since > stamp or age != int((stamp - since).total_seconds()):
        return None
    return Observation(gi, phase, age, stamp, since)


class Detector:
    def __init__(self, threshold, clock=utcnow):
        self.threshold = threshold
        self.clock = clock
        self.network = None
        self.instance = None
        self.models = {}
        self.checked_at = None

    def observe(self, payload):
        if not isinstance(payload, dict):
            return [{"event": "invalid_snapshot"}]
        stamp = timestamp(payload.get("checked_at"))
        if stamp is not None:
            age = (self.clock() - stamp).total_seconds()
            if not 0 <= age <= 4 * CHECK_INTERVAL_S:
                return [{"event": "snapshot_out_of_date"}]
            if self.checked_at is not None and stamp <= self.checked_at:
                return []
            # Even a failed refresh supersedes earlier snapshots.
            self.checked_at = stamp
        checks = payload.get("checks")
        for name in ("config", "rpc"):
            check = checks.get(name) if isinstance(checks, dict) else None
            if not isinstance(check, dict) or check.get("ok") is not True:
                return [{"event": "check_unavailable", "check": name}]
        block = checks["rpc"].get("block")
        if type(block) is not int or block < 0:
            return [{"event": "check_unavailable", "check": "rpc"}]
        rows = payload.get("models")
        network = checks["config"].get("network")
        instance = payload.get("instance_id")
        if (stamp is None or not isinstance(rows, list)
                or not isinstance(network, str) or not network.strip()
                or not isinstance(instance, str) or not re.fullmatch(r"[0-9a-f]{32}", instance)):
            return [{"event": "invalid_snapshot"}]
        if self.network is not None and network != self.network:
            return [{"event": "network_changed"}]
        self.network = network
        events = []
        if self.instance is not None and self.instance != instance:
            events.append({"event": "daemon_restarted"})
        self.instance = instance
        grouped = {}
        for row in rows:
            address = row.get("coordinator") if isinstance(row, dict) else None
            if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
                events.append({"event": "invalid_model"})
                continue
            grouped.setdefault(address.lower(), []).append(row)
        if not rows and not self.models:
            events.append({"event": "no_models"})
        for address in self.models.keys() - grouped.keys():
            events.append({"event": "model_missing", "coordinator": address})
        for address, entries in grouped.items():
            current = parse_model(entries[0], stamp) if len(entries) == 1 else None
            if current is None:
                events.append({"event": "model_unavailable", "coordinator": address})
                continue
            events.extend(self._update_model(address, current))
        return events

    def _update_model(self, address, current):
        events = []
        previous = self.models.get(address)
        if previous:
            position = (current.gi, current.phase)
            prior = (previous.gi, previous.phase)
            if position < prior:
                return [current.event("regressed_observation", address)]
            same_timer = position == prior and current.observed_since == previous.observed_since
            if not same_timer and current.observed_since <= previous.checked_at:
                return [current.event("inconsistent_observation", address)]
            if position == prior:
                current.alerted = previous.alerted
                if not same_timer:
                    events.append(current.event("observation_reset", address))
            elif previous.alerted:
                events.append(current.event("recovered", address))

        if (GIState.GIstarted <= current.phase < GIState.GIended
                and current.age >= self.threshold and not current.alerted):
            current.alerted = True
            events.append(current.event("stalled", address))
        self.models[address] = current
        return events


def poll(detector, port):
    deadline = time.monotonic() + REQUEST_TIMEOUT_S
    connection = HTTPConnection("127.0.0.1", port, timeout=REQUEST_TIMEOUT_S)
    watchdog = None
    try:
        connection.connect()
        # A socket timeout alone can be extended by a trickle of bytes.
        # Retain the socket even if HTTPConnection hands it to HTTPResponse.
        sock = connection.sock

        def interrupt_read():
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

        watchdog = Timer(max(0, deadline - time.monotonic()), interrupt_read)
        watchdog.start()
        connection.request("GET", "/health")
        response = connection.getresponse()
        if response.status not in (200, 503):
            return [{"event": "poll_failed"}]
        limit = 1024 * 1024
        body = response.read(limit + 1)
        if time.monotonic() >= deadline or response.length not in (0, None):
            return [{"event": "poll_failed"}]
        if len(body) > limit:
            return [{"event": "invalid_snapshot"}]
        return detector.observe(json.loads(body))
    except (OSError, HTTPException):
        return [{"event": "poll_failed"}]
    except (ValueError, RecursionError):
        return [{"event": "invalid_snapshot"}]
    finally:
        if watchdog is not None:
            watchdog.cancel()
            watchdog.join()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold-s", type=int, required=True)
    parser.add_argument("--interval-s", type=int, default=15)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if min(args.threshold_s, args.interval_s) < 1 or not 1 <= args.port <= 65535:
        parser.error("use positive durations and a port between 1 and 65535")
    detector = Detector(args.threshold_s)
    try:
        while True:
            for event in poll(detector, args.port):
                print(json.dumps(event), flush=True)
            time.sleep(args.interval_s)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
