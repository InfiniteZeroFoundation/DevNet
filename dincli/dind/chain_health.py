"""Background chain checks for /health (issue #345, P3-T0.2c).

Config, RPC and signer checks, plus the GI number and phase of each
configured model. A background thread refreshes them every
``interval_s`` seconds and the /health handler only reads the latest
snapshot, so a slow or hanging RPC never delays a health probe and the
handler itself never touches the network.

The snapshot carries error *codes* only, never exception text: RPC URLs
routinely embed API keys, and nothing here may echo key or keystore
contents.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from importlib.resources import files

from dincli.sdk.errors import DinError
from dincli.sdk.session import DinSession
from dincli.sdk.state import GIstateToStr

logger = logging.getLogger("dincli")

CHECK_INTERVAL_S = 15.0


def _error_code(exc: Exception, fallback: str) -> str:
    if isinstance(exc, DinError) and exc.code:
        return exc.code
    return fallback


def _load_coordinator_abi() -> list:
    path = files("dincli").joinpath("abis", "DINTaskCoordinator.json")
    data = json.loads(path.read_text())
    return data["abi"] if isinstance(data, dict) else data


class ChainHealthMonitor:
    def __init__(
        self,
        models: list[str],
        session: DinSession | None = None,
        interval_s: float = CHECK_INTERVAL_S,
    ):
        self.models = list(models)
        self.interval_s = interval_s
        self._session = session if session is not None else DinSession()
        # (snapshot, monotonic time taken), swapped as one tuple so a reader
        # never pairs a new snapshot with an old timestamp.
        self._latest: tuple[dict, float] | None = None
        # (coordinator) -> ((gi, state), first_seen_iso): when this daemon
        # first saw the model's current GI + state. Survives refreshes.
        self._seen: dict[str, tuple[tuple[int, int], str]] = {}
        self._abi: list | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="dind-chain-health", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.refresh()
            self._stop.wait(self.interval_s)

    # -- reads ------------------------------------------------------------

    def snapshot(self) -> dict:
        """Latest snapshot. A missing or stale one fails every check, so a
        hung refresh thread surfaces as non-healthy instead of freezing the
        last good answer forever."""
        latest = self._latest
        if latest is None:
            return self._failed_snapshot("checks_pending")
        snap, taken = latest
        if time.monotonic() - taken > self.interval_s * 4:
            return self._failed_snapshot("checks_stale")
        return snap

    def _failed_snapshot(self, code: str) -> dict:
        failed = {"ok": False, "error": code}
        return {
            "checked_at": None,
            "checks": {"config": failed, "rpc": failed, "signer": failed},
            "models": [],
        }

    # -- refresh ----------------------------------------------------------

    def refresh(self) -> dict:
        try:
            snap = self._collect()
        except Exception as exc:  # never let the refresh thread die
            logger.warning("chain health refresh failed: %s", type(exc).__name__)
            snap = self._failed_snapshot("internal_error")
            snap["checked_at"] = datetime.now(timezone.utc).isoformat()
        self._latest = (snap, time.monotonic())
        return snap

    def _collect(self) -> dict:
        now = datetime.now(timezone.utc)
        checks = {}

        # Config: the network and its RPC endpoint resolve.
        try:
            network = self._session.network
            from dincli.sdk.config import resolve_network_value

            resolve_network_value(network, "rpc_url")
            checks["config"] = {"ok": True, "network": network}
        except Exception as exc:
            checks["config"] = {"ok": False, "error": _error_code(exc, "config_error")}

        # RPC: the node answers (and get_w3 checks the chain id on connect).
        w3 = None
        block = None
        if checks["config"]["ok"]:
            try:
                w3 = self._session.w3
                block = w3.eth.block_number
                checks["rpc"] = {"ok": True, "block": block}
            except Exception as exc:
                w3 = None
                checks["rpc"] = {"ok": False, "error": _error_code(exc, "rpc_unreachable")}
        else:
            checks["rpc"] = {"ok": False, "error": "config_error"}

        # Signer: can sign non-interactively. can_decrypt() is the
        # SignerProvider check; it returns a bool and never exposes the key.
        try:
            ok = bool(self._session.signer.can_decrypt())
            checks["signer"] = {"ok": True} if ok else {"ok": False, "error": "signer_unavailable"}
        except Exception as exc:
            checks["signer"] = {"ok": False, "error": _error_code(exc, "signer_unavailable")}

        models = [self._read_model(w3, addr, now, block) for addr in self.models]

        return {"checked_at": now.isoformat(), "checks": checks, "models": models}

    def _read_model(self, w3, coordinator: str, now: datetime, block: int | None) -> dict:
        entry: dict = {"coordinator": coordinator}
        if block is None or w3 is None:
            entry["error"] = "rpc_unavailable"
            return entry
        try:
            if self._abi is None:
                self._abi = _load_coordinator_abi()
            contract = w3.eth.contract(address=coordinator, abi=self._abi)
            # A rollover between latest-block reads would mix two GIs.
            gi = int(contract.functions.GI().call(block_identifier=block))
            state = int(contract.functions.GIstate().call(block_identifier=block))
        except Exception as exc:
            entry["error"] = _error_code(exc, "model_read_failed")
            return entry

        key = (gi, state)
        seen = self._seen.get(coordinator)
        if seen is None or seen[0] != key:
            seen = (key, now.isoformat())
            self._seen[coordinator] = seen
        first_seen = datetime.fromisoformat(seen[1])

        entry.update(
            gi=gi,
            state=GIstateToStr(state),
            state_code=state,
            # Since THIS daemon first saw the current GI + state: a lower
            # bound on time in state, not the on-chain transition time.
            observed_since=seen[1],
            observed_for_s=int((now - first_seen).total_seconds()),
        )
        return entry


def snapshot_is_healthy(snap: dict) -> bool:
    if not all(check.get("ok") for check in snap["checks"].values()):
        return False
    return not any("error" in model for model in snap["models"])
