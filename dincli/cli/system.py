import json
import os
import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from getpass import getpass
from importlib.resources import files
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import typer
from eth_account import Account
from rich.prompt import Confirm
from torchvision import datasets, transforms

from dincli.cli.contract_utils import erc20_abi, router_abi
from dincli.cli.utils import (CACHE_DIR, CONFIG_DIR, CONFIG_FILE,
                              _get_password, get_config, get_demo_private_key,
                              get_env_key, load_config, load_din_info, save_config)

dataset_app = typer.Typer(help="Manage federated datasets.")

app = typer.Typer(help="System utilities for DIN CLI.")

# Register the dataset group under system_app
app.add_typer(dataset_app, name="dataset")

WALLET_FILE = CONFIG_DIR / "wallet.json"

def initialize_directories():
    """
    Create user-level config and cache dirs if they do not exist.
    Call this explicitly (e.g. from CLI or first-run code), not on import.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    print(f"Initialized directories:\n- Config: {CONFIG_DIR}\n- Cache: {CACHE_DIR}")

@app.callback(invoke_without_command=True)
def system(
    ctx: typer.Context,
    eth_balance: bool = typer.Option(
        False,
        "--eth-balance",
        help="Show ETH balance for your wallet or a given address."
    ),
    address: str = typer.Option(
        None,
        "--address",
        help="Ethereum address to query. If not provided, uses your connected wallet."
    ),
):
    # If the subcommand is one that doesn't need an account, we skip the default setup logic
    if ctx.invoked_subcommand in ["connect-wallet", "init", "welcome", "where", "configure-network", "configure-demo", "read_wallet", "show_index", "din-info", "configure-logging", "dump-abi", "reset-all", "todo", "dataset"]:
        return

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    
    # Early exit if neither balance flag is set
    if not (eth_balance):
        return  # let subcommands run, or do nothing
    
    if address:
        target_address = w3.to_checksum_address(address)
    else:
        target_address = account.address
    console.print(f"\n[green]Target Account Address:[/green] {target_address}")
    
     # Fetch ETH balance if requested
    if eth_balance:
        balance_wei = w3.eth.get_balance(target_address)
        balance_eth = w3.from_wei(balance_wei, "ether")
        
        console.print(f"[green]ETH Balance:[/green] {balance_eth} ETH")    
        

@app.command()
def where(ctx: typer.Context):
    """Print where dincli is installed."""
    typer.secho("dincli is installed at: ", fg="green", nl=False)
    typer.secho(f"{files('dincli')}", fg="magenta")
    
@app.command()
def welcome():
    """Print welcome message."""
    typer.echo("Welcome to DIN CLI!")

@app.command("cache-dir")
def cache_dir():
    """Print the path to the cache directory."""
    typer.echo(f"[bold green]Cache Directory:[/bold green] {CACHE_DIR}")

@app.command("init")
def initialize():
    """Initialize DIN CLI by creating config/cache directories and an empty config file."""
    initialize_directories()
    if not CONFIG_FILE.exists():
        # Write an empty JSON object (valid JSON)
        CONFIG_FILE.write_text("{}\n", encoding="utf-8")
        console.print(f"[green]✅ Created empty config file at: {CONFIG_FILE}[/green]")
 
@app.command("configure-network")
def configure_network(ctx: typer.Context):
    """
    Configure the default blockchain network for DIN CLI.
    """
    
    effective_network, console = ctx.obj.network, ctx.obj.console

    config = load_config()
    config["network"] = effective_network
    save_config(config)

    console.print(f"[green]Network configured successfully: {effective_network}[/green]")

@app.command("configure-demo")
def configure_demo(ctx: typer.Context,
    mode: str = typer.Option("yes", "--mode", help="Set demo mode: yes or no")
):
    """
    Enable/disable demo mode (plaintext wallet storage, no password).
    Useful for Hardhat/local testing.
    """
    console = ctx.obj.console
    if mode.lower() not in ("yes", "no"):
        console.print("[red]Mode must be 'yes' or 'no'[/red]")
        raise typer.Exit(1)
    
    enable = mode.lower() == "yes"
    config = load_config()
    config["demo_mode"] = enable
    save_config(config)
    status = "enabled" if enable else "disabled"
    console.print(f"[green]Demo mode {status}.[/green]")
    if enable:
        console.print("[red]⚠️  Wallets will be stored in plaintext. Do NOT use with real keys![/red]")

@app.command("configure-logging")
def configure_logging(ctx: typer.Context,  
    level: str = typer.Option("info", "--level", help="Set log level: debug | info | warning | error | critical")
):
    """
    Configure the log level for DIN CLI.
    """
    console = ctx.obj.console
    if level.lower() not in ("debug", "info", "warning", "error", "critical"):
        console.print("[red]Level must be 'debug', 'info', 'warning', 'error', or 'critical'[/red]")
        raise typer.Exit(1)
    
    config = load_config()
    config["log_level"] = level.lower()
    save_config(config)
    console.print(f"[green]Log level set to {level}.[/green]")
    
    
@app.command()
def connect_wallet(ctx: typer.Context,
    privatekey: Optional[str] = typer.Argument(None, help="Your Ethereum private key (0x...)"),
    key_file: Optional[Path] = typer.Option(None, "--key-file", "-f", help="Path to file containing private key"),
    account: Optional[int] = typer.Option(None, "--account", "-a", help="Hardhat dev account index (0-69)"),
):
    """
    Connect a wallet to DIN CLI.
    
    Usage:
      # Interactive prompt (Recommended)
      dincli system connect-wallet

      # Connect using a key file (Secure)
      dincli system connect-wallet --key-file ~/.dincli/wallet.key
      
      # Connect with explicit private key (Not recommended due to logs/history)
      dincli system connect-wallet 0x123...
      
      # Connect Hardhat dev account by index (auto demo mode)
      dincli system connect-wallet --account 3
    
    Encrypt and store the user's wallet for DIN CLI.
    In demo mode (--yes), stores plaintext key for Hardhat testing.
    """

    # Validate mutual exclusivity
    auth_methods = [
        (privatekey, "private key argument"),
        (key_file, "key file"),
        (account, "account index")
    ]
    provided_methods = [name for val, name in auth_methods if val is not None]
    console = ctx.obj.console
    
    if len(provided_methods) > 1:
        console.print(f"[red]❌ Please specify only one of: {', '.join(provided_methods)}.[/red]")
        raise typer.Exit(1)

    console.print(f"[green] ⚙️  Connecting wallet... to new account[/green]")
    
    demo_mode = get_config("demo_mode")

    
    if account is not None and demo_mode:
        # Load from demo accounts
        try:
            privatekey = get_demo_private_key(account)
        except (FileNotFoundError, IndexError) as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
    elif account is not None and not demo_mode:
        privatekey = get_env_key("ETH_PRIVATE_KEY_"+str(account))
        if privatekey is None:
            raise typer.Exit(1)
            
    elif key_file is not None:
        # Load from file
        key_file = key_file.expanduser() 
        if not key_file.exists():
            console.print(f"[red]❌ Key file not found: {key_file}[/red]")
            raise typer.Exit(1)
        try:
            with open(key_file, 'r') as f:
                privatekey = f.read().strip()
            config = load_config()
            demo_mode = config.get("demo_mode", False)
        except Exception as e:
            console.print(f"[red]❌ Failed to read key file: {e}[/red]")
            raise typer.Exit(1)
            
    elif privatekey is not None:
        # Explicit argument
        console.print("[yellow]⚠️  Warning: Providing private key as argument is insecure (saved in shell history). Use interactive mode or --key-file instead.[/yellow]")
        config = load_config()
        demo_mode = config.get("demo_mode", False)
        
    else:
        # Interactive prompt
        console.print("[cyan]Enter your Ethereum private key (input will be hidden):[/cyan]")
        privatekey = getpass("Private Key: ").strip()
        config = load_config()
        demo_mode = config.get("demo_mode", False)

    # Validate format (for all methods)
    if not privatekey.startswith("0x") or len(privatekey) != 66:
        console.print("[red]❌ Invalid private key format! Must be 0x + 64 hex chars.[/red]")
        raise typer.Exit(1)
    
    # Ensure config dir exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Derive address
    acct = Account.from_key(privatekey)


    if demo_mode:
        # Save plaintext private key (for Hardhat/local testing ONLY)
        wallet_data = {
            "address": acct.address,
            "private_key": privatekey,  # ⚠️ PLAINTEXT — ONLY FOR MOCK!
            "demo_mode": True
        }
        with open(WALLET_FILE, "w") as f:
            json.dump(wallet_data, f, indent=4)
        console.print(f"[green]✅ Wallet saved in DEMO MODE (plaintext)![/green]")
        console.print(f"[yellow]Address:[/yellow] {acct.address}")
        console.print(f"[cyan]File:[/cyan] {WALLET_FILE}")
        
    else:

        password = _get_password(False)

        if password == "":
            # Ask for encryption password
            password = getpass("Create wallet password: ")
            confirm = getpass("Confirm password: ")

            if password != confirm:
                console.print("[red]Passwords do not match![/red]")
                raise typer.Exit()

        # Use eth-account to create an encrypted keystore
        keystore = Account.encrypt(privatekey, password)

        # Save encrypted wallet locally
        with open(WALLET_FILE, "w") as f:
            json.dump(keystore, f, indent=4)

        console.print(f"[green]Wallet connected successfully![/green]")
        console.print(f"[green] Active Account Address:[/green] {acct.address}")
        console.print(f"[green]Encrypted keystore saved at:[/green] {WALLET_FILE}")
    
@app.command()
def read_wallet(ctx: typer.Context):
    """
    Read and display wallet info.
    In demo mode, shows private key. Otherwise, shows only address (after decrypting).
    """
    console = ctx.obj.console
    if not WALLET_FILE.exists():
        console.print("[red]No wallet found. Run `dincli system connect-wallet` first.[/red]")
        raise typer.Exit(1)

    with open(WALLET_FILE) as f:
        data = json.load(f)

    # Check if it's demo mode (plaintext)
    if isinstance(data, dict) and data.get("demo_mode") is True:
        console.print("[bold green]🔐 Wallet (Demo Mode - Plaintext)[/bold green]")
        console.print(f"[yellow]Address:[/yellow] {data['address']}")
        console.print(f"[red]Private Key:[/red] {data['private_key']}")
        console.print("[cyan]⚠️  This key is stored in plaintext — for local testing only![/cyan]")
        return
    try:
        console.print(f"[yellow]Address:[/yellow] {ctx.obj.account.address}")
        console.print("[green]✅ Wallet decrypted successfully.[/green]")
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)


@app.command("show-index")
def show_index(ctx: typer.Context,
    address: str = typer.Option(..., "--address", "-a", help="Address of the contract"),
):
    """
    Show the index of the the account address in demo mode.
    """
    from dincli.cli.utils import get_demo_account_index
    console = ctx.obj.console
    try:
        index = get_demo_account_index(address)
        console.print(f"[green]Account Index:[/green] {index}")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

@app.command("din-info")
def din_info(ctx: typer.Context,
    coordinator: bool = typer.Option(False, "--coordinator", help="Show coordinator address"),
    token: bool = typer.Option(False, "--token", help="Show DIN token address"),
    stake: bool = typer.Option(False, "--stake", help="Show staking contract"),
    representative: bool = typer.Option(False, "--representative", help="Show representative logic"),
    registry: bool = typer.Option(False, "--registry", help="Show registry contract"),
    
):
    
    # Resolve effective network
    effective_network, _, _, console = ctx.obj.get_en_w3_account_console()

    data = load_din_info()[effective_network]

    # Print requested info
    if coordinator:
        console.print(f"[cyan]Coordinator:[/cyan] {data.get('coordinator', 'N/A')}")
    if token:
        console.print(f"[green]DIN Token:[/green] {data.get('token', 'N/A')}")
    if stake:
        console.print(f"[yellow]Staking Contract:[/yellow] {data.get('stake', 'N/A')}")
    if representative:
        console.print(f"[magenta]Representative:[/magenta] {data.get('representative', 'N/A')}")
    if registry:
        console.print(f"[magenta]Registry:[/magenta] {data.get('registry', 'N/A')}")

    if not any([coordinator, token, stake, representative, registry]):
        console.print(f"[cyan]Coordinator:[/cyan] {data.get('coordinator', 'N/A')}")
        console.print(f"[green]DIN Token:[/green] {data.get('token', 'N/A')}")
        console.print(f"[yellow]Staking Contract:[/yellow] {data.get('stake', 'N/A')}")
        console.print(f"[magenta]Representative:[/magenta] {data.get('representative', 'N/A')}")
        console.print(f"[magenta]Registry:[/magenta] {data.get('registry', 'N/A')}")


@app.command("reset-all")
def reset_all(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    cache: bool = typer.Option(False, "--cache", "-c", help="Reset cache directory"),
    config: bool = typer.Option(False, "--config", "-co", help="Reset config directory"),
):
    """
    Reset DIN CLI state.

    By default (no flags), deletes both config and cache directories.
    Use --cache or --config to delete only one.
    """

    # Decide which paths to consider
    targets = []
    if config:
        targets.append(("Config", CONFIG_DIR))
    if cache:
        targets.append(("Cache", CACHE_DIR))

    # If neither flag is given, reset both
    if not (cache or config):
        targets = [("Config", CONFIG_DIR), ("Cache", CACHE_DIR)]

    # Filter only existing paths to avoid noise
    to_delete = [(name, path) for name, path in targets if path.exists()]

    if not to_delete:
        typer.secho("[yellow]No DIN CLI data found to delete.[/yellow]", fg=typer.colors.YELLOW)
        return

    # Build confirmation message
    paths_str = "\n".join(str(path.resolve()) for _, path in to_delete)
    if not force:
        typer.secho(
            f"[red]⚠️  This will permanently delete the following:[/red]\n{paths_str}\n",
            fg=typer.colors.RED,
            bold=True,
        )
        if not typer.confirm("Are you sure?"):
            typer.secho("[cyan]Operation cancelled.[/cyan]", fg=typer.colors.CYAN)
            raise typer.Exit()

    # Perform deletion
    for name, path in to_delete:
        try:
            shutil.rmtree(path)
            typer.secho(f"[green]✅ Deleted {name} directory: {path}[/green]")
        except Exception as e:
            typer.secho(f"[red]❌ Failed to delete {path}: {e}[/red]", fg=typer.colors.RED)
            raise typer.Exit(code=1)    


@app.command("todo")
def todo(
    ctx: typer.Context,
    client: bool = typer.Option(False, "--client", "-cl", help="todo as client"),
    aggregator: bool = typer.Option(False, "--aggregator", "-ag", help="todo as aggregator"),
    auditor: bool = typer.Option(False, "--auditor", "-au", help="todo as auditor"),
    model_owner: bool = typer.Option(False, "--model-owner", "-mo", help="todo as model owner"),
    model_id: str = typer.Option(None, "--model-id", "-m", help="Model ID"),
):
    typer.secho("TODO list:", fg=typer.colors.CYAN)

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    if not CONFIG_DIR.exists():
        console.print(f"[red]❌ Config directory does not exist: {CONFIG_DIR}[/red], run 'dincli system init' to create it.")
    else:
        console.print(f"[green]✅ Config directory exists: {CONFIG_DIR}[/green]")

    if not CACHE_DIR.exists():
        console.print(f"[red]❌ Cache directory does not exist: {CACHE_DIR}[/red], run 'dincli system init' to create it.")
    else:
        console.print(f"[green]✅ Cache directory exists: {CACHE_DIR}[/green]")
    
    if not CONFIG_FILE.exists():
        console.print(f"[red]❌ Config file does not exist: {CONFIG_FILE}[/red], run 'dincli system init' to create it.")
    else:
        console.print(f"[green]✅ Config file exists: {CONFIG_FILE}[/green]")
        config = load_config()
        if config.get("network") is None: 
            console.print(f"[red]❌ Config file does not contain a network[/red], run 'dincli system configure-network' to set it.")
        else:
            console.print(f"[green]✅ Config file contains a network: {config.get('network')}[/green]")
        if config.get("log_level") is None: 
            console.print(f"[red]❌ Config file does not contain a log level[/red], run 'dincli system configure-logging' to set it.")
        else:
            console.print(f"[green]✅ Config file contains a log level: {config.get('log_level')}[/green]")
        if config.get("demo_mode") is None: 
            console.print(f"[red]❌ Config file does not contain a demo mode[/red], run 'dincli system configure-demo' to set it.")
        else:
            console.print(f"[green]✅ Config file contains a demo mode: {config.get('demo_mode')}[/green]")

    if not WALLET_FILE.exists():
        console.print(f"[red]❌ Wallet file does not exist: {WALLET_FILE}[/red], run 'dincli system connect-wallet' to create it.")
    else:
        console.print(f"[green]✅ Wallet file exists: {WALLET_FILE}[/green]")

    env_key = "DIN_WALLET_PASSWORD"
    cwd = os.getcwd()
    if get_env_key(env_key, None, False) is None:
        console.print(
            f"[red]❌ Wallet password not found.[/red]\n"
            f"Please define [bold]{env_key}[/bold] in a [.env] file in your current directory:\n"
            f"  → File path: [cyan]{cwd}/.env[/cyan]\n"
            f"  → File content:\n"
            f"      {env_key}=your_wallet_password\n"
            f"[dim]🔒 Important: Never commit [.env] to version control.[/dim]"
        )
    else:
        console.print(f"[green]✅ Wallet password found in environment variable: {env_key} in {cwd}/.env file[/green]")

    env_key = str(effective_network).upper() + "_RPC_URL"
    if get_env_key(env_key, None, False) is None:
        console.print(
            f"[red]❌ RPC URL not found for network '[bold]{effective_network}[/bold]'.[/red]\n"
            f"Please define [bold]{env_key}[/bold] in your [.env] file:\n"
            f"  → File path: [cyan]{cwd}/.env[/cyan]\n"
            f"  → Example value:\n"
            f"      {env_key}=https://rpc.sepolia.org\n"
            f"\n"
            f"[dim]💡 You can get free RPC URLs from services like Infura, Alchemy, or QuickNode.[/dim]\n"
            f"[dim]🔒 Remember: Never commit [.env] to version control.[/dim]"
        )
    else:
        console.print(f"[green]✅ RPC URL found in environment variable: {env_key} in {cwd}/.env file[/green]")

    if CONFIG_FILE.exists():
        config = load_config()
        network = config.get("network")
        if network:
            rpc_env_key = f"{network.upper()}_RPC_URL"
            if get_env_key(rpc_env_key, None, False) is None:
                console.print(
                f"[red]❌ RPC URL not found for network '[bold]{network}[/bold]'.[/red]\n"
                f"Please define [bold]{rpc_env_key}[/bold] in your [.env] file:\n"
                f"  → File path: [cyan]{cwd}/.env[/cyan]\n"
                f"  → Example value:\n"
                f"      {rpc_env_key}=https://rpc.sepolia.org\n"
                f"\n"
                f"[dim]💡 You can get free RPC URLs from services like Infura, Alchemy, or QuickNode.[/dim]\n"
                f"[dim]🔒 Remember: Never commit [.env] to version control.[/dim]"
            )
        else:
            console.print(f"[green]✅ RPC URL found in environment variable: {rpc_env_key} in {cwd}/.env file[/green]")

    if get_env_key("IPFS_API_URL_ADD", None, False) is None:
        console.print(
            f"[red]❌ IPFS API ADD URL not found.[/red]\n"
            f"Please define [bold]IPFS_API_URL_ADD[/bold] in your [.env] file:\n"
            f"  → File path: [cyan]{cwd}/.env[/cyan]\n"
            f"  → Example value:\n"
            f"      IPFS_API_URL_ADD=http://localhost:5001/api/v0\n"
            f"\n"
            f"[dim]🔒 Important: Never commit [.env] to version control.[/dim]"
        )
    else:
        console.print(f"[green]✅ IPFS API ADD URL found in environment variable: IPFS_API_URL_ADD in {cwd}/.env file with value: {get_env_key('IPFS_API_URL_ADD', None, False)}[/green]")
    if get_env_key("IPFS_API_URL_RETRIEVE", None, False) is None:
        console.print(
            f"[red]❌ IPFS API RETRIEVE URL not found.[/red]\n"
            f"Please define [bold]IPFS_API_URL_RETRIEVE[/bold] in your [.env] file:\n"
            f"  → File path: [cyan]{cwd}/.env[/cyan]\n"
            f"  → Example value:\n"
            f"      IPFS_API_URL_RETRIEVE=http://localhost:5001/api/v0\n"
            f"\n"
            f"[dim] Important: Never commit [.env] to version control.[/dim]"
        )
    else:
        console.print(f"[green]✅ IPFS API RETRIEVE URL found in environment variable: IPFS_API_URL_RETRIEVE in {cwd}/.env file with value: {get_env_key('IPFS_API_URL_RETRIEVE', None, False)}[/green]")    
    
    if client:
        if not model_id:
            console.print("[red]❌ Model ID not found in config file or cli argument.[/red]")
            raise typer.Exit(1)
        client_path =  Path(CACHE_DIR)/effective_network.lower()/ f"model_{model_id}"/ "dataset"/ "clients"/ account.address/ "data.pt"
        if client_path.exists():
            console.print(f"[green]✅ Client dataset found at: {client_path}[/green]")
        else:
            console.print(f"[red]❌ Client dataset not found at: {client_path}[/red]")

@dataset_app.command("distribute-mnist")
def distribute_mnist(
    ctx: typer.Context,
    num_clients: int = typer.Option(None, "--num-clients", "-nc", help="Number of clients"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed"),
    test_train: bool = typer.Option(False, "--test-train", "-tt", help="get test/train dataset"),
    clients: bool = typer.Option(False, "--clients", "-cl", help="get clients dataset"),
    task_coordinator_address: str = typer.Option(None, "--task-coordinator", "-tc", help="TaskCoordinator address"),
    task: bool = typer.Option(False, "--task", "-t", help="get task dataset"),
    model_id: str = typer.Option(None, "--model-id", "-m", help="Model ID"),

):
    """
    Download MNIST and distribute it across N clients (IID split).
    """

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    if (not task_coordinator_address or not task) and not model_id:

        if not task_coordinator_address:
            task_coordinator_address = get_env_key(effective_network.upper() + "_DINTaskCoordinator_Contract_Address")
            if not task_coordinator_address:
                console.print("[red]❌ Both Task coordinator address and model ID not found in cli argument. Moreover, Task coordinator address not found in environment variable.[/red]")
                raise typer.Exit(1)

    
    if model_id:
        base_dir = Path(CACHE_DIR)/effective_network.lower()/ f"model_{model_id}"
    elif task_coordinator_address:
        base_dir = Path(os.getcwd())/"tasks"/effective_network.lower()/task_coordinator_address   

    dataset_dir = base_dir / "dataset"
    clients_dir = base_dir / "dataset" / "clients"

    # Ensure directories exist
    if not test_train and not clients:
        console.print("[red]❌ Both train/test flag and clients flag not found in cli argument.[/red]")
        raise typer.Exit(1)
    if test_train:
        dataset_dir.mkdir(parents=True, exist_ok=True)
    if clients:
        clients_dir.mkdir(parents=True, exist_ok=True)

    if clients and num_clients <= 0:
        console.print("[red]Number of clients must be >= 1[/red]")
        raise typer.Exit(1)
    if clients and num_clients > 10:
        console.print("[red]Number of clients must be < 10[/red]")
        raise typer.Exit(1)

    print(f"[cyan]Using base dir:[/cyan] {base_dir}")

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Download MNIST
    train_dataset = datasets.MNIST(root=dataset_dir, train=True, download=True, transform=transform)
    test_dataset = datasets.MNIST(root=dataset_dir, train=False, download=True, transform=transform)

    # Save raw datasets
    (dataset_dir / "train").mkdir(parents=True, exist_ok=True)
    (dataset_dir / "test").mkdir(parents=True, exist_ok=True)

    if test_train:
        torch.save(train_dataset, dataset_dir / "train" / "train_dataset.pt")
        torch.save(test_dataset, dataset_dir / "test" / "test_dataset.pt")
        console.print(f"[green]Processed Train/Test Datasets saved successfully to {dataset_dir}![/green]")
    if clients:
        # IID SPLIT
        total_samples = len(train_dataset)
        indices = np.arange(total_samples)

        np.random.seed(seed)
        np.random.shuffle(indices)

        partitions = np.array_split(indices, num_clients)

        accounts_list = []

        for i in range(num_clients):
            private_key = get_demo_private_key(i+2)
            acct = Account.from_key(private_key)
            accounts_list.append(acct.address)

        for i, idxs in enumerate(partitions):
            client_path = clients_dir / accounts_list[i]
            client_path.mkdir(parents=True, exist_ok=True)

            # Extract subset
            subset_data = [(train_dataset[idx][0], train_dataset[idx][1]) for idx in idxs]

            save_path = client_path / "data.pt"
            torch.save(subset_data, save_path)

            console.print(f"[green]Saved client_{i} ({len(subset_data)} samples) → {save_path}[/green]")

        console.print(f"[bold green]✅ MNIST distributed to {num_clients} clients under {clients_dir}[/bold green]")
    
@app.command()
def dump_abi(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to contract artifact JSON (e.g., hardhat/artifacts/.../DINCoordinator.json)"),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Output name (e.g., 'DINCoordinator'). Defaults to filename stem."
    ),
    include_bytecode: bool = typer.Option(
        False,
        "--bytecode",
        "-b",
        help="Also include 'bytecode' (useful for redeploying from CLI)."
    ),
    output_dir: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Directory to save the output ABI file. Defaults to 'dincli/abis/'."
    ),
    official: bool = typer.Option(
        False,
        "--official",
        "-O",  # uppercase O to avoid conflict
        help="specify if official contract artifact.",
    ),

    
):
    """
    Extract ABI (and optionally bytecode) from a contract artifact and save it 
    in Hardhat-compatible format to dincli/abis/.
    
    Example:
      dincli dindao dump-abi --artifact "hardhat/artifacts/contracts/DINCoordinator.sol/DINCoordinator.json" --bytecode
    """

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    artifact = Path(artifact_path)
    if not artifact.exists():
        console.print(f"[red]❌ Artifact not found: {artifact}[/red]")
        raise typer.Exit(1)

     # Load full artifact
    try:
        with open(artifact) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]❌ Failed to read artifact: {e}[/red]")
        raise typer.Exit(1)

    # Validate required fields
    if "abi" not in data:
        console.print(f"[red]❌ No 'abi' field in {artifact}[/red]")
        raise typer.Exit(1)

    # Build output data
    output_data = {"abi": data["abi"]}
    
    if include_bytecode and "bytecode" in data:
        if isinstance(data["bytecode"], dict):
            output_data["bytecode"] = data["bytecode"]["object"]
        else:
            output_data["bytecode"] = data["bytecode"]
    elif include_bytecode:
        console.print(f"[yellow]⚠️  'bytecode' not found in {artifact}, skipping.[/yellow]")

    # Determine name
    output_name = name or artifact.stem

    if official and not output_dir:
        abi_dir = files("dincli").joinpath("abis")
    elif output_dir:
        abi_dir = Path(output_dir)
    else:
        # Default to ./abis in the cwd
        abi_dir = Path.cwd() / "abis"

    abi_dir.mkdir(exist_ok=True)
    output_path = abi_dir / f"{output_name}.json"

    # Save in Hardhat-compatible format
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    console.print(f"[green]✅ Artifact saved to:[/green] {output_path}")
    console.print(f"[cyan]→ ABI-only: {not include_bytecode} | Includes bytecode: {include_bytecode}[/cyan]")
    
# dincli system
@app.command("configure-ipfs")
def configure_ipfs(ctx: typer.Context,
    provider: str = typer.Option(None, "--provider", "-p", help="IPFS application name [filebase, pinata]"),
    ipfs_service_path: str = typer.Option(None, "--ipfs-service-path", "-p", help="Path to IPFS service"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key"),
    api_secret: str = typer.Option(None, "--api-secret", "-s", help="API secret"),
    delete_config: bool = typer.Option(False, "--delete", "-d", help="Delete IPFS config"),
):

    config = load_config()
    
    if not delete_config and not provider: 
        ctx.obj.console.print("[red]❌ Please specify a provider or delete config.[/red]")
        raise typer.Exit(1)

    configured_providers = {"filebase", "custom"}

    if provider:
        if provider not in configured_providers-{"custom"}:
            if not ipfs_service_path:
                ctx.obj.console.print("[red]❌ Please specify an IPFS service path for custom provider.[/red]")
                raise typer.Exit(1)
            ctx.obj.console.print(f"[red]❌ Invalid provider. Use {' , '.join(configured_providers-{"custom"})} , 'custom'.[/red]")
            raise typer.Exit(1)
        config["ipfs_provider"] = provider

    if api_key:
        config["ipfs_api_key"] = api_key
    if api_secret:
        config["ipfs_api_secret"] = api_secret

    if ipfs_service_path:
        config["ipfs_service_path"] = ipfs_service_path

    if delete_config:
        config.pop("ipfs_provider", None)
        config.pop("ipfs_api_key", None)
        config.pop("ipfs_api_secret", None)
        config.pop("ipfs_service_path", None)
    save_config(config)

    ctx.obj.console.print(f"[green]IPFS configured successfully: {provider} [/green]")
    if ipfs_service_path:
        ctx.obj.console.print(f"[green] with service path {ipfs_service_path}[/green]")






    
    