"""Poll one local dind for GI stalls. Run with python -m dincli.dind.gi_monitor."""

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPConnection, HTTPException

from dincli.sdk.state import GIState


@dataclass
class Observation:
    gi: int
    phase: GIState
    age: int
    alerted: bool = False

    def event(self, kind, address):
        return {"event": kind, "coordinator": address, "gi": self.gi,
                "state": self.phase.name, "observed_for_s": self.age}


def parse_model(row):
    gi = row.get("gi")
    age = row.get("observed_for_s")
    phase = row.get("state")
    if "error" in row or type(gi) is not int or gi < 0 or type(age) is not int or age < 0:
        return None
    if not isinstance(phase, str) or phase not in GIState.__members__:
        return None
    phase = GIState[phase]
    if type(row.get("state_code")) is not int or row["state_code"] != phase:
        return None
    if (gi == 0) != (phase < GIState.GIstarted):
        return None
    return Observation(gi, phase, age)


class Detector:
    def __init__(self, threshold):
        self.threshold = threshold
        self.models = {}
        self.checked_at = None

    def observe(self, payload):
        if not isinstance(payload, dict):
            return [{"event": "invalid_snapshot"}]
        checks = payload.get("checks")
        for name in ("config", "rpc"):
            check = checks.get(name) if isinstance(checks, dict) else None
            if not isinstance(check, dict) or check.get("ok") is not True:
                return [{"event": "check_unavailable", "check": name}]
        rows = payload.get("models")
        try:
            stamp = datetime.fromisoformat(payload["checked_at"])
        except (KeyError, TypeError, ValueError):
            return [{"event": "invalid_snapshot"}]
        if stamp.tzinfo is None or not isinstance(rows, list):
            return [{"event": "invalid_snapshot"}]
        if self.checked_at is not None and stamp <= self.checked_at:
            return []
        self.checked_at = stamp
        events = []
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
            current = parse_model(entries[0]) if len(entries) == 1 else None
            if current is None:
                events.append({"event": "model_unavailable", "coordinator": address})
                continue
            previous = self.models.get(address)
            if previous:
                position = (current.gi, current.phase)
                prior = (previous.gi, previous.phase)
                if position < prior:
                    events.append(current.event("regressed_observation", address))
                    continue
                if position == prior:
                    current.alerted = previous.alerted
                    if current.age < previous.age:
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
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        if response.status not in (200, 503):
            return [{"event": "poll_failed"}]
        limit = 1024 * 1024
        body = response.read(limit + 1)
        if len(body) > limit:
            return [{"event": "invalid_snapshot"}]
        return detector.observe(json.loads(body))
    except (OSError, HTTPException):
        return [{"event": "poll_failed"}]
    except (ValueError, RecursionError):
        return [{"event": "invalid_snapshot"}]
    finally:
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
