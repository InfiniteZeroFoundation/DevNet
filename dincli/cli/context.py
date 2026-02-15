from __future__ import annotations

import importlib.util
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.log import logger, logging
from dincli.cli.utils import (GIstatestrToIndex, GIstateToStr, get_config,
                              get_manifest_key, get_w3, load_account,
                              load_config, load_din_info, resolve_network)
from dincli.services.ipfs import retrieve_from_ipfs


class DinContext:
    def __init__(self, network_arg: Optional[str] = None) -> None:
        self.console = Console()
        self._logger = logger
        self.network_arg = network_arg
        self._resolved_network: Optional[str] = None
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
                self._account = load_account()
            except Exception as e:
                self.console.print(f"[red]Error loading account: {e}[/red]")
                import sys
                sys.exit(1)
        return self._account

    @property
    def din_logger(self):
        return self._logger

    def get_en_w3_account_console(self, model_id: Optional[int] = None):
        self.console.print(f"[bold green]✓ Active Account Address:[/bold green] {self.account.address}")
        self.console.print(f"[bold green]✓ Active Web3:[/bold green] {self.w3.provider.endpoint_uri}")
        if model_id is not None:
            self.console.print(f"[bold blue]✓ Model ID:[/bold blue] {model_id}")
        return self.network, self.w3, self.account, self.console
    
    def select_network(self, network: Optional[str]):
        """Update network selection and invalidate w3 cache if changed."""
        if network:
            self.network_arg = network
            self._resolved_network = None
            self._w3 = None
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
    
    def get_deployed_din_task_coordinator_contract(self, verbose: bool = True, model_id: Optional[int] = None, taskCoordinator_address: Optional[str] = None):

        if taskCoordinator_address is None:
            if model_id is not None:
                taskCoordinator_address = get_manifest_key(self.network, "DINTaskCoordinator_Contract", model_id)
            else:
                raise ValueError("taskCoordinator_address or model_id must be provided")

        if verbose:
            self.console.print("[bold green]✓ Task Coordinator contract address:[/bold green] ", taskCoordinator_address)
        artifact_path = files("dincli").joinpath("abis", "DINTaskCoordinator.json")
        return get_contract_instance(str(artifact_path), self.network, taskCoordinator_address)

    def get_deployed_din_task_auditor_contract(self, verbose: bool = True, model_id: Optional[int] = None, taskAuditor_address: Optional[str] = None):
        if taskAuditor_address is None:
            if model_id is not None:
                taskAuditor_address = get_manifest_key(self.network, "DINTaskAuditor_Contract", model_id)
            else:
                raise ValueError("taskAuditor_address or model_id must be provided")

        if verbose:
            self.console.print("[bold green]✓ Task Auditor contract address:[/bold green] ", taskAuditor_address)
        artifact_path = files("dincli").joinpath("abis", "DINTaskAuditor.json")
        return get_contract_instance(str(artifact_path), self.network, taskAuditor_address)

    
    def load_custom_fn(self, module_path: Path, fn_name: str, ipfs_hash: str = None) -> Callable:
        """
        Dynamically load a function from a project-local service file.

        Example:
            load_custom_fn(
                Path.cwd() / "services" / "modelowner.py",
                "getGenesisModelIpfs",
                "Qma2FMYTrf9Ec4rfMdWLnVWFUniGfi2iVyh3VVYHYKym9w"
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

        return fn 

    
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
    
    def ensure_file_exists(self,
        file_path: Path, 
        ipfs_cid: str, 
        description: str
    ) -> None:
        """Retrieve file from IPFS if missing, with user-friendly feedback."""
        if not file_path.exists():
            self.console.print(f"[yellow]📥 Retrieving {description} from IPFS with CID: {ipfs_cid} to {file_path}[/yellow]")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            retrieve_from_ipfs(ipfs_cid, file_path)
            if not file_path.exists():
                self.console.print(f"[red]❌ Failed to retrieve {description} (CID: {ipfs_cid}) to {file_path}[/red]")
                raise typer.Exit(1)
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


        
