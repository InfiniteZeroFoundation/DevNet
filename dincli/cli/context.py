from __future__ import annotations
import functools
import inspect
from urllib.parse import urlparse

import json

import importlib.util
from importlib.resources import files
from pathlib import Path
from typing import Callable, Optional

import typer
from rich.console import Console

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.log import logger, logging
from dincli.cli.utils import (CACHE_DIR, GIstatestrToIndex, GIstateToStr,
                              get_config, get_manifest, get_manifest_key, get_w3,
                              load_account, load_config, load_din_info,
                              resolve_network, get_active_account_name,
                              validate_account_name, resolve_wallet_path)
from dincli.services.ipfs import retrieve_from_ipfs
from dincli.services.runtime import ServiceRuntimeContext, build_service_runtime_context

def sanitize_rpc_url(url: str) -> str:
    parsed = urlparse(url)

    # Remove last path segment if it looks like an API key
    path_parts = parsed.path.rstrip("/").split("/")
    
    if len(path_parts) > 1:
        path_parts[-1] = "****"
    
    safe_path = "/".join(path_parts)

    return f"{parsed.scheme}://{parsed.netloc}{safe_path}"


class DinContext:
    def __init__(self, network_arg: Optional[str] = None) -> None:
        self.console = Console()
        self._logger = logger
        self.network_arg = network_arg
        self.wallet_name: Optional[str] = None
        self._resolved_network: Optional[str] = None
        self._resolved_wallet_name: Optional[str] = None
        self._w3 = None
        self._account = None
        self._config = None

        # Initialize logging
        log_level_str = get_config("log_level", default="INFO")
        self._logger.setLevel(getattr(logging, log_level_str.upper(), logging.INFO))

    @property
    def network(self) -> str:
        if self._resolved_network is None:
            self._resolved_network = resolve_network(self.network_arg)
        return self._resolved_network

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = load_config()
        return self._config

    @property
    def w3(self):
        if self._w3 is None:
            self._w3 = get_w3(self.network)
        return self._w3

    @property
    def account(self):
        if self._account is None:
            try:
                name = self.resolved_wallet_name
                self._account = load_account(name=name)
            except Exception as e:
                self.console.print(f"[red]Error loading account: {e}[/red]")
                import sys
                sys.exit(1)
        return self._account

    @property
    def resolved_wallet_name(self) -> str:
        if self._resolved_wallet_name is None:
            try:
                self._resolved_wallet_name = get_active_account_name(self)
            except ValueError as e:
                self.console.print(f"[red]Error loading account: {e}[/red]")
                import sys
                sys.exit(1)
        return self._resolved_wallet_name

    @property
    def din_logger(self):
        return self._logger

    def get_en_w3_account_console(self, model_id: Optional[int] = None):
        self.console.print(f"[bold green]✓ Active Wallet:[/bold green] {self.resolved_wallet_name} ({self.account.address})")
        endpoint = self.w3.provider.endpoint_uri
        if endpoint:
            safe_endpoint = sanitize_rpc_url(endpoint)
        self.console.print(f"[bold green]✓ Active Web3:[/bold green] {safe_endpoint}")
        if model_id is not None:
            self.console.print(f"[bold blue]✓ Model ID:[/bold blue] {model_id}")
        return self.network, self.w3, self.account, self.console
    
    def get_tx_params(self):
        return {
            "from": self.account.address,  
            "maxFeePerGas": self.w3.eth.gas_price * 2, # Strategy to ensure inclusion
            "maxPriorityFeePerGas": self.w3.eth.max_priority_fee, # The "tip" to the miner/validator
            "chainId": self.w3.eth.chain_id,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        } 
    
    def select_network(self, network: Optional[str]):
        """Update network selection and invalidate w3 cache if changed."""
        if network:
            self.network_arg = network
            self._resolved_network = None
            self._w3 = None
        return self

    def select_wallet(self, name: Optional[str]):
        """Update wallet selection and invalidate account cache if changed."""
        if name:
            try:
                validate_account_name(name)
            except ValueError as e:
                self.console.print(f"[red]{e}[/red]")
                raise typer.Exit(1)
            wallet_path, exists = resolve_wallet_path(name)
            if not exists:
                self.console.print(
                    f"[red]No wallet found for name '{name}' at {wallet_path}. "
                    f"Run `dincli system register-wallet --name {name}` first.[/red]"
                )
                raise typer.Exit(1)
            self.wallet_name = name
            self._resolved_wallet_name = None
            self._account = None
        return self

    def select_demo_account(self, index: Optional[int]):
        """DEMO MODE ONLY: sign this invocation with Hardhat dev account `index`.

        Loads the private key straight from the bundled demo accounts file and
        caches the Account on the context — the named-wallet machinery
        (wallet files, keystore encryption/decryption, password prompts) is
        bypassed entirely. Takes precedence over every wallet-name source
        (--wallet / DIN_WALLET_NAME / config wallet_name) because it fills the
        account cache directly. Refuses to run outside demo mode so raw-key
        loading can never be reached with production configuration.
        """
        if index is None:
            return self
        if not get_config("demo_mode"):
            self.console.print(
                "[red]--demokey works only in demo mode. "
                "Enable it with `dincli system configure-demo` (local testing only).[/red]"
            )
            raise typer.Exit(1)
        from dincli.cli.utils import get_demo_private_key
        try:
            private_key = get_demo_private_key(index)
        except (FileNotFoundError, IndexError) as e:
            self.console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        from eth_account import Account
        self._account = Account.from_key(private_key)
        # Display-only label; never resolved against wallet files.
        self._resolved_wallet_name = f"demo-{index}"
        return self
    
    def get_deployed_din_coordinator_contract(self, verbose: bool = True):
        dincoordinator_address = load_din_info()[self.network]["coordinator"]
        if verbose:
            self.console.print("[bold green]✓ DIN Coordinator contract address:[/bold green] ", dincoordinator_address)
        artifact_path = files("dincli").joinpath("abis", "DinCoordinator.json")
        return get_contract_instance(str(artifact_path), self.network, dincoordinator_address)

    def get_deployed_din_token_contract(self, verbose: bool = True):
        dintoken_address = load_din_info()[self.network]["token"]
        if verbose:
            self.console.print("[bold green]✓ DIN Token contract address:[/bold green] ", dintoken_address)
        artifact_path = files("dincli").joinpath("abis", "DinToken.json")
        return get_contract_instance(str(artifact_path), self.network, dintoken_address)

    def get_deployed_din_stake_contract(self, verbose: bool = True):
        dinstake_address = load_din_info()[self.network]["stake"]
        if verbose:
            self.console.print("[bold green]✓ DIN Stake contract address:[/bold green] ", dinstake_address)
        artifact_path = files("dincli").joinpath("abis", "DinValidatorStake.json")
        return get_contract_instance(str(artifact_path), self.network, dinstake_address)
    
    def get_deployed_din_registry_contract(self, verbose: bool = True):
        dinregistry_address = load_din_info()[self.network]["registry"]
        if verbose:
            self.console.print("[bold green]✓ DIN Registry contract address:[/bold green] ", dinregistry_address)
        artifact_path = files("dincli").joinpath("abis", "DINModelRegistry.json")
        return get_contract_instance(str(artifact_path), self.network, dinregistry_address)

    def _get_task_manifest_context(
        self,
        model_id: Optional[int],
        taskCoordinator_address: Optional[str],
    ) -> tuple[Optional[dict], Optional[Path]]:
        # There are two places a task manifest can live, depending on how the
        # command identifies the task:
        #
        # 1. model_id:
        #    This is the normal "registered model" path. The manifest is cached
        #    under the dincli cache directory after being resolved from the
        #    model registry / manifest CID.
        #
        # 2. taskCoordinator_address:
        #    This is the local task-authoring path used before or around task
        #    registration. The manifest lives in the user's current workspace
        #    under tasks/<network>/<coordinator-address>/manifest.json.
        #
        # Returning the base path alongside the manifest lets later code resolve
        # manifest-relative paths such as contracts/abis/DINTaskCoordinator.json.
        if model_id is not None:
            # Registered model flow. get_manifest() also handles cache freshness
            # checks for model IDs, so callers do not need to know whether the
            # local manifest was already present or had to be refreshed first.
            return (
                get_manifest(self.network, model_id=model_id),
                Path(CACHE_DIR) / self.network / f"model_{model_id}",
            )

        if taskCoordinator_address is not None:
            # Local task flow. Here get_manifest() reads directly from the
            # current project's tasks directory; the base path mirrors that
            # location so manifest paths can be joined without special cases.
            # Return (None, None) when the manifest doesn't exist yet so that
            # callers can fall back to bundled ABIs (e.g. during early deploy).
            try:
                manifest_data = get_manifest(
                    self.network,
                    task_coordinator_address=taskCoordinator_address,
                )
            except FileNotFoundError:
                return None, None
            return (
                manifest_data,
                Path.cwd() / "tasks" / self.network.lower() / taskCoordinator_address,
            )

        # Some callers still pass only a raw contract address, especially for
        # default system contracts. In that case there is no task manifest to
        # consult, so the contract resolver must fall back to bundled ABIs.
        return None, None

    def _resolve_task_contract_artifact_path(
        self,
        contract_key: str,
        default_abi_filename: str,
        model_id: Optional[int],
        taskCoordinator_address: Optional[str],
    ) -> Path:
        # Resolve the manifest and the directory that relative manifest paths
        # should be based from. If neither a model_id nor a task coordinator is
        # available, this returns (None, None) and we use the default ABI.
        manifest_data, model_base_path = self._get_task_manifest_context(
            model_id,
            taskCoordinator_address,
        )

        # Bundled ABI fallback. This keeps old manifests working and prevents
        # custom-contract support from breaking the default DIN task contracts.
        default_artifact_path = files("dincli").joinpath("abis", default_abi_filename)

        if not manifest_data or model_base_path is None:
            return Path(str(default_artifact_path))

        artifact_entry = None

        # Preferred schema for custom task-level contracts:
        #
        # "task_contracts": {
        #   "DINTaskCoordinator_Contract": {
        #     "artifact": {"path": "contracts/abis/DINTaskCoordinator.json", ...},
        #     "source": {...},
        #     "compilation": {...}
        #   }
        # }
        #
        # The "artifact" key is preferred because these files may be full
        # Hardhat artifacts, not only raw ABI JSON. "abi" is accepted as a
        # friendly alias for manifests that name the same thing more narrowly.
        task_contracts = manifest_data.get("task_contracts")
        if isinstance(task_contracts, dict):
            contract_entry = task_contracts.get(contract_key)
            if isinstance(contract_entry, dict):
                artifact_entry = (
                    contract_entry.get("artifact")
                    or contract_entry.get("abi")
                )

        if not isinstance(artifact_entry, dict):
            # No structured manifest artifact was provided. This includes the
            # legacy string-CID form, missing keys, or malformed entries.
            return Path(str(default_artifact_path))

        artifact_rel_path = artifact_entry.get("path")
        if not artifact_rel_path:
            # A custom artifact entry must provide a manifest-relative path.
            # Without it, dincli cannot know where to cache/read the artifact.
            return Path(str(default_artifact_path))

        artifact_path = model_base_path / artifact_rel_path

        # Ensure the artifact exists locally before constructing the Web3
        # contract. If "ipfs" is present, ensure_file_exists also refreshes the
        # file when the CID changes. If "ipfs" is None, it acts as a local file
        # presence check, which is useful for task directories and local caches.
        # Fall back to the bundled ABI when the file is missing and no CID is
        # available to fetch it (e.g. model_id-based access before ABI cache is
        # populated).
        try:
            self.ensure_file_exists(
                artifact_path,
                artifact_entry.get("ipfs"),
                f"{contract_key} ABI",
            )
        except FileNotFoundError:
            return Path(str(default_artifact_path))

        # get_contract_instance() accepts either a Hardhat artifact or a minimal
        # {"abi": [...]} JSON file, so the resolver only needs to return the
        # selected JSON path.
        return artifact_path
    
    def get_deployed_din_task_coordinator_contract(self, verbose: bool = True, model_id: Optional[int] = None, taskCoordinator_address: Optional[str] = None):

        if taskCoordinator_address is None:
            if model_id is not None:
                taskCoordinator_address = get_manifest_key(self.network, "DINTaskCoordinator_Contract", model_id)
            else:
                raise ValueError("taskCoordinator_address or model_id must be provided")

        if verbose:
            self.console.print("[bold green]✓ Task Coordinator contract address:[/bold green] ", taskCoordinator_address)
        artifact_path = self._resolve_task_contract_artifact_path(
            "DINTaskCoordinator_Contract",
            "DINTaskCoordinator.json",
            model_id,
            taskCoordinator_address,
        )
        return get_contract_instance(str(artifact_path), self.network, taskCoordinator_address)

    def get_deployed_din_task_auditor_contract(self, verbose: bool = True, model_id: Optional[int] = None, taskAuditor_address: Optional[str] = None):
        if taskAuditor_address is None:
            if model_id is not None:
                taskAuditor_address = get_manifest_key(self.network, "DINTaskAuditor_Contract", model_id)
            else:
                raise ValueError("taskAuditor_address or model_id must be provided")

        if verbose:
            self.console.print("[bold green]✓ Task Auditor contract address:[/bold green] ", taskAuditor_address)
        artifact_path = self._resolve_task_contract_artifact_path(
            "DINTaskAuditor_Contract",
            "DINTaskAuditor.json",
            model_id,
            None,
        )
        return get_contract_instance(str(artifact_path), self.network, taskAuditor_address)

    def build_service_runtime(
        self,
        *,
        role: Optional[str] = None,
        model_id: Optional[int] = None,
        task_coordinator_address: Optional[str] = None,
    ) -> ServiceRuntimeContext:
        return build_service_runtime_context(
            self.network,
            model_id=model_id,
            task_coordinator_address=task_coordinator_address,
            role=role,
        )

    
    def load_custom_fn(
        self,
        module_path: Path,
        fn_name: str,
        ipfs_hash: str = None,
        runtime: Optional[ServiceRuntimeContext] = None,
    ) -> Callable:
        """
        Dynamically load a function from a project-local service file.

        Example:
            load_custom_fn(
                Path.cwd() / "services" / "modelowner.py",
                "getGenesisModelIpfs",
                "bafybeifnsvq2stiisi2xv3ocpqjmmmbccrvykq5v5ti62fyzz56vyyhl6y"
            )
        """

        self.ensure_file_exists(module_path, ipfs_hash, "Custom service file")

        spec = importlib.util.spec_from_file_location(
            module_path.stem,
            module_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, fn_name):
            raise AttributeError(
                f"{fn_name} not found in custom service {module_path}"
                 )

        fn = getattr(module, fn_name)

        if not callable(fn):
            raise TypeError(
                f"{fn_name} in {module_path} is not callable"
            )

        if runtime is None:
            return fn

        signature = inspect.signature(fn)
        accepts_runtime = (
            "runtime" in signature.parameters
            or any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
        )

        if not accepts_runtime:
            return fn

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            kwargs.setdefault("runtime", runtime)
            return fn(*args, **kwargs)

        return wrapped

    
    def get_current_gi_and_state(self, task_coordinator_contract, verbose_gi: bool = True, verbose_state: bool = False, verbose_state_name: bool = False) -> tuple[int, int]:
        """Get the current global iteration from the Task Coordinator contract."""
        curr_gi = task_coordinator_contract.functions.GI().call()
        curr_GIstate = task_coordinator_contract.functions.GIstate().call()
        if verbose_gi:
            self.console.print(f"[bold green]✓ Current global iteration:[/bold green] {curr_gi}")
        if verbose_state:
            self.console.print(f"[bold green]✓ Current global iteration numerical state:[/bold green] {curr_GIstate}")
        if verbose_state_name:
            self.console.print(f"[bold green]✓ Current global iteration state:[/bold green] {GIstateToStr(curr_GIstate)}")
        return curr_gi, curr_GIstate
    
    # ------------------------------------------------------------------ #
    #  CID store helpers  (one local.json.cid per directory)             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read_local_cid_store(directory: Path) -> dict:
        """Load the local CID registry for *directory* (returns {} if missing/corrupt)."""
        store_path = directory / "local.json.cid"
        if store_path.exists():
            try:
                with open(store_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _write_local_cid_store(directory: Path, store: dict) -> None:
        """Persist the CID registry for *directory*."""
        store_path = directory / "local.json.cid"
        directory.mkdir(parents=True, exist_ok=True)
        with open(store_path, "w") as f:
            json.dump(store, f, indent=2)

    def ensure_file_exists(self,
        file_path: Path,
        ipfs_cid: str | None,
        description: str
    ) -> None:
        """
        Retrieve *file_path* from IPFS if it is missing or its stored CID
        no longer matches *ipfs_cid* (i.e. the manifest was updated).

        CIDs are tracked in ``<file_path.parent.parent>/local.json.cid`` under the
        key ``file_path.name`` so a single registry file covers all service
        files for a given model directory.

        If *ipfs_cid* is None, only a presence check is done (no CID comparison).
        """
        directory = file_path.parent.parent
        filename  = file_path.name

        # --- presence-only fallback when no CID is provided ---
        if ipfs_cid is None:
            if not file_path.exists():
                raise FileNotFoundError(
                    f"{description} not found at {file_path} and no IPFS CID was provided to download it."
                )
            return

        store = self._read_local_cid_store(directory)
        stored_cid = store.get(filename)

        needs_download = (
            not file_path.exists()
            or stored_cid != ipfs_cid
        )

        if stored_cid and stored_cid != ipfs_cid and file_path.exists():
            self.console.print(
                f"[yellow]🔄 {description} CID changed "
                f"({stored_cid[:12]}… → {ipfs_cid[:12]}…), re-downloading…[/yellow]"
            )

        if needs_download:
            self.console.print(f"[yellow]📥 Retrieving {description} from IPFS with CID: {ipfs_cid} to {file_path}[/yellow]")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            retrieve_from_ipfs(ipfs_cid, file_path)
            if not file_path.exists():
                self.console.print(f"[red]❌ Failed to retrieve {description} (CID: {ipfs_cid}) to {file_path}[/red]")
                raise typer.Exit(1)
            # Update the store
            store[filename] = ipfs_cid
            self._write_local_cid_store(directory, store)
            self.console.print(f"[green]✓ {description.capitalize()} ready with path:[/green] {file_path}")

    
    def validate_gi_LTE_curr_GI(self, gi: int, curr_gi: int) -> int:
        """Validate that the given global iteration is less than or equal to the current global iteration."""
        
        if gi is None:
            return curr_gi
        elif gi==0 or gi > curr_gi or gi < 1:
            self.console.print(f"[bold red]✗ Requested GI: {gi}[/bold red]")
            self.console.print(f"[red]Error:[/red] Invalid global iteration {gi} given in command: gi > curr_GI ({curr_gi})")
            raise typer.Exit(1)
        return gi

    def validate_gi_ET_curr_GI(self, gi: int, curr_gi: int) -> int:
        if gi is None:
            return curr_gi
        elif gi==0 or gi != curr_gi or gi < 1:
            self.console.print(f"[bold red]✗ Requested GI: {gi}[/bold red]")
            self.console.print(f"[red]Error:[/red] Invalid global iteration {gi} given in command: Global iteration does not match current GI ({curr_gi})")
            raise typer.Exit(1)
        return gi

    def validate_GIstate_ET_given_GIstate(self, curr_GIstate: int, given_GIstate: str, msg: str) -> bool:
        if GIstateToStr(curr_GIstate) != given_GIstate:
            self.console.print(f"[bold red]✗ {msg}. Current state: {GIstateToStr(curr_GIstate)} [/bold red]")
            raise typer.Exit(1)
        return True

    def validate_GIstate_LTE_given_GIstate(self, target_gi: int, curr_gi: int, curr_GIstate: int, given_GIstate: str, msg: str) -> bool:
        if target_gi == curr_gi and curr_GIstate < GIstatestrToIndex(given_GIstate):
            self.console.print(f"[bold red]✗ {msg}. Current state: {GIstateToStr(curr_GIstate)} [/bold red]")
            raise typer.Exit(1)
        return True

    def get_model_base_dir(self, model_id: int) -> Path:
        return Path(CACHE_DIR) / self.network / f"model_{model_id}"
