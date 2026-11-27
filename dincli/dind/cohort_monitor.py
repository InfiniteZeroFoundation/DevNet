"""Route finalized DIN chain alerts and local dind GI alerts to one JSON webhook."""
import argparse
import json
import os
import sqlite3
import sys
import time
from itertools import groupby
from urllib.parse import urlsplit

import requests
from web3 import Web3

from dincli.dind.gi_monitor import Detector, poll

MINT = Web3.keccak(text="TokensMinted(address,uint256)")
SLASH = Web3.keccak(text="ValidatorSlashed(address,uint256,bytes32,address)")


def initialize(db, settings, start):
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS progress (settings TEXT PRIMARY KEY, next_block INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS slashes (block INTEGER, count INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, payload TEXT, sent INTEGER DEFAULT 0)")
        config = json.dumps(settings, sort_keys=True)
        row = db.execute("SELECT settings FROM progress").fetchone()
        if row and row[0] != config:
            raise ValueError("use a separate state file for a different deployment or detection policy")
        db.execute("INSERT OR IGNORE INTO progress VALUES (?, ?)", (config, start))


def enqueue(db, key, event):
    db.execute("INSERT OR IGNORE INTO alerts(id,payload) VALUES (?,?)", (key, json.dumps(event)))


def scan(db, eth, args):
    start = db.execute("SELECT next_block FROM progress").fetchone()[0]
    end = min(start + args.batch_blocks - 1, eth.get_block("finalized").number)
    if start > end:
        return
    logs = eth.get_logs({"fromBlock": start, "toBlock": end, "address": [args.token, args.stake],
                         "topics": [[Web3.to_hex(MINT), Web3.to_hex(SLASH)]]})
    ordered = sorted(logs, key=lambda log: (log.blockNumber, log.logIndex))
    seen = set()
    with db:
        for block, entries in groupby(ordered, key=lambda log: log.blockNumber):
            if not start <= block <= end:
                raise ValueError("unexpected log block")
            count = 0
            for log in entries:
                key = f"{args.chain_id}:{Web3.to_hex(log.transactionHash)}:{log.logIndex}"
                if key in seen:
                    continue
                seen.add(key)
                if log.topics[0] == MINT and log.address == args.token:
                    amount = int.from_bytes(log.data, "big")
                    if amount >= args.mint_wei:
                        enqueue(db, key, {"event": "large_mint", "amount_wei": str(amount), "block": block})
                elif log.topics[0] == SLASH and log.address == args.stake:
                    count += 1
            if count:
                db.execute("DELETE FROM slashes WHERE block < ?", (block - args.window_blocks,))
                previous = db.execute("SELECT COALESCE(SUM(count),0) FROM slashes").fetchone()[0]
                db.execute("DELETE FROM slashes WHERE block = ?", (block - args.window_blocks,))
                current = db.execute("SELECT COALESCE(SUM(count),0) FROM slashes").fetchone()[0] + count
                db.execute("INSERT INTO slashes VALUES (?,?)", (block, count))
                if previous < args.slash_count <= current:
                    enqueue(db, f"{args.chain_id}:slash:{block}", {
                        "event": "slashing_spike", "block": block, "count": current,
                        "window_blocks": args.window_blocks})
        db.execute("UPDATE progress SET next_block = ?", (end + 1,))


def route_gi(db, detector, port, chain_id):
    with db:
        for event in poll(detector, port):
            if event["event"] in ("stalled", "recovered"):
                model = detector.models[event["coordinator"]]
                key = ":".join(map(str, (chain_id, event["coordinator"], event["gi"],
                                         event["state"], event["event"], model.observed_since.isoformat())))
                enqueue(db, key, event)
            else:
                print(json.dumps(event), flush=True)


def deliver(db, destination, post=requests.post):
    for key, body in db.execute("SELECT id,payload FROM alerts WHERE sent=0 ORDER BY rowid"):
        response = post(destination, json={"id": key, **json.loads(body)},
                        headers={"Idempotency-Key": key}, timeout=5, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise ValueError("alert destination rejected delivery")
        with db:
            db.execute("UPDATE alerts SET sent=1 WHERE id=?", (key,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("chain-id", "start-block", "mint-wei", "slash-count", "window-blocks",
                 "batch-blocks", "gi-threshold-s", "interval-s"):
        parser.add_argument("--" + flag, type=int, required=True)
    for flag in ("token", "stake", "state"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if args.start_block < 0 or min(args.chain_id, args.mint_wei, args.slash_count, args.window_blocks,
                                   args.batch_blocks, args.gi_threshold_s, args.interval_s) < 1:
        parser.error("use positive settings and a nonnegative starting block")
    if not 1 <= args.port <= 65535:
        parser.error("invalid health port")
    destination = os.environ.get("DIN_ALERT_URL", "")
    rpc = os.environ.get("DIN_MONITOR_RPC_URL")
    if not rpc or urlsplit(destination).scheme != "https" or not urlsplit(destination).hostname:
        parser.error("set DIN_MONITOR_RPC_URL and an HTTPS DIN_ALERT_URL")
    args.token, args.stake = map(Web3.to_checksum_address, (args.token, args.stake))
    eth = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10})).eth
    db = sqlite3.connect(args.state)
    initialize(db, {k: getattr(args, k) for k in ("chain_id", "start_block", "token", "stake",
                                                   "mint_wei", "slash_count", "window_blocks",
                                                   "gi_threshold_s")}, args.start_block)
    detector = Detector(args.gi_threshold_s)
    while True:
        try:
            if eth.chain_id != args.chain_id:
                raise ValueError("unexpected chain")
            scan(db, eth, args)
        except Exception:
            print("chain poll failed", file=sys.stderr, flush=True)
        route_gi(db, detector, args.port, args.chain_id)
        try:
            deliver(db, destination)
        except (requests.RequestException, ValueError):
            print("alert delivery failed; queued for retry", file=sys.stderr, flush=True)
        time.sleep(args.interval_s)


if __name__ == "__main__":
    main()
