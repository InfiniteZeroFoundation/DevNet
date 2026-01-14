import typer
import json
import shutil
import os
from datetime import datetime, timedelta
from rich.prompt import Confirm
from rich import print
from rich.console import Console
from typing import Optional
from eth_account import Account
from decimal import Decimal
from getpass import getpass
from dincli.utils import save_config, load_config, CONFIG_DIR, CACHE_DIR, CONFIG_FILE, load_usdt_config, resolve_network, get_demo_private_key, get_w3, load_account, get_env_key
from pathlib import Path
from dincli.services.ipfs import upload_to_ipfs, retrieve_from_ipfs
import numpy as np
import torch
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, random_split
console = Console()
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
    usdt_info: bool = typer.Option(
        False,
        "--usdt-info",
        help="Display USDT, WETH, and Uniswap router addresses for the active network."
    ),
    eth_balance: bool = typer.Option(
        False,
        "--eth-balance",
        help="Show ETH balance for your wallet or a given address."
    ),
    usdt_balance: bool = typer.Option(
        False,
        "--usdt-balance",
        help="Show USDT balance for your wallet or a given address."
    ),
    address: str = typer.Option(
        None,
        "--address",
        help="Ethereum address to query. If not provided, uses your connected wallet."
    ),
    network: str = typer.Option(
        None,
        "--network",
        help="Network override: local | hardhat | sepolia | mainnet"
    ),
    
):
    
    
    effective_network = resolve_network(network)
    
    if usdt_info:
        cfg = load_config()
        

        all_cfg = load_usdt_config()

        if effective_network not in all_cfg:
            print(f"[red]Network '{effective_network}' not found in config![/red]")
            raise typer.Exit()

        data = all_cfg[effective_network]

        print(f"[bold cyan]Active Network:[/bold cyan] {effective_network}")
        print(f"[green]USDT Address:[/green] {data['usdt']}")
        print(f"[yellow]WETH Address:[/yellow] {data['weth']}")
        print(f"[magenta]Uniswap Router:[/magenta] {data['uniswap_router']}")

        raise typer.Exit()
    
    # Early exit if neither balance flag is set
    if not (eth_balance or usdt_balance):
        return  # let subcommands run, or do nothing
    
    w3 = get_w3(effective_network)
    
    if address:
        target_address = w3.to_checksum_address(address)
    else:
        target_address = load_account().address
        
    
     # Fetch ETH balance if requested
    if eth_balance:
        balance_wei = w3.eth.get_balance(target_address)
        balance_eth = w3.from_wei(balance_wei, "ether")
        print(f"[cyan]Network:[/cyan] {effective_network}")
        print(f"[yellow]Address:[/yellow] {target_address}")
        print(f"[green]ETH Balance:[/green] {balance_eth} ETH")    
        
    # Fetch USDT balance if requested
    if usdt_balance:
        usdt_cfg = load_usdt_config()
        if effective_network not in usdt_cfg:
            print(f"[red]USDT config missing for network '{effective_network}'![/red]")
            raise typer.Exit()
        
        usdt_address = w3.to_checksum_address(usdt_cfg[effective_network]["usdt"])    
        usdt_abi = [{
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        }]
        usdt_contract = w3.eth.contract(address=usdt_address, abi=usdt_abi)
        usdt_balance_raw = usdt_contract.functions.balanceOf(target_address).call()
        usdt_balance_fmt = Decimal(usdt_balance_raw) / Decimal(10**6)

        print(f"[cyan]Network:[/cyan] {effective_network}")
        print(f"[yellow]Address:[/yellow] {target_address}")
        print(f"[blue]USDT Balance:[/blue] {usdt_balance_fmt} USDT")

    raise typer.Exit()


@app.command()
def where():
    """Print where dincli is installed."""
    typer.echo(f"dincli is installed at: {Path(__file__).parent.resolve()}")
        

@app.command()
def welcome():
    """Print welcome message."""
    typer.echo("Welcome to DIN CLI!")

@app.command("init")
def initialize():
    """Initialize DIN CLI by creating config/cache directories and an empty config file."""
    initialize_directories()
    if not CONFIG_FILE.exists():
        # Write an empty JSON object (valid JSON)
        CONFIG_FILE.write_text("{}\n", encoding="utf-8")
        console.print(f"[green]✅ Created empty config file at: {CONFIG_FILE}[/green]")

@app.command()
def buy_usdt(
    amount: float = typer.Argument(..., help="Amount of USDT to buy"),
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)")
):
    """
    Buy USDT tokens by swapping ETH via Uniswap.

    Prompts user for confirmation within 1 minute after showing live exchange rate.
    Aborts if not confirmed. Actual received USDT may vary due to slippage and volatility.
    """
    effective_network = resolve_network(network)
    print(f"[bold green]Buying {amount} USDT on network:[/bold green] {effective_network}")
    
    w3 = get_w3(effective_network)
    account = load_account()
    
     # Load USDT config
    usdt_config = load_usdt_config()
    if effective_network not in usdt_config:
        print(f"[red]Network '{effective_network}' not configured for USDT![/red]")
        raise typer.Exit(1)
    
    usdt_address = usdt_config[effective_network]["usdt"]
    router_address = usdt_config[effective_network]["uniswap_router"]
    weth_address = usdt_config[effective_network]["weth"]
    
    # Minimal ABIs
    erc20_abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        }
    ]
    router_abi = [
        # For estimating input ETH needed
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"}
            ],
            "name": "getAmountsIn",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "view",
            "type": "function"
        },
        # For executing the swap (ETH -> exact USDT)
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "swapETHForExactTokens",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "payable",
            "type": "function"
        }
    ]

    usdt_contract = w3.eth.contract(address=usdt_address, abi=erc20_abi)
    router_contract = w3.eth.contract(address=router_address, abi=router_abi)
    
    try:
        decimals = usdt_contract.functions.decimals().call()
    except:
        decimals = 6  # USDT standard
        
    amount_wei = int(amount * (10 ** decimals))
    path = [weth_address, usdt_address]
    
     # Get required ETH
    try:
        amounts_in = router_contract.functions.getAmountsIn(amount_wei, path).call()
        eth_required_wei = amounts_in[0]
        eth_required = w3.from_wei(eth_required_wei, 'ether')
    except Exception as e:
        print(f"[red]Failed to fetch swap rate: {e}[/red]")
        raise typer.Exit(1)

    print(f"\n[bold cyan]Estimated ETH needed:[/bold cyan] {eth_required:.6f} ETH")
    print(f"[bold yellow]⚠️  Disclaimer:[/bold yellow] Actual USDT received may differ due to price volatility and slippage.")
    print(f"[bold yellow]You have 60 seconds to confirm.[/bold yellow]\n")

    # Wait for confirmation with timeout
    deadline = datetime.now() + timedelta(seconds=60)
    confirmed = None
    while datetime.now() < deadline:
        try:
            confirmed = Confirm.ask(f"Confirm swap of ~{eth_required:.6f} ETH for {amount} USDT?")
            break
        except KeyboardInterrupt:
            print("\n[red]Cancelled by user.[/red]")
            raise typer.Exit(1)
        except Exception:
            time.sleep(0.5)  # brief pause before retrying input

    if confirmed is not True:
        print("[red]Confirmation timeout or declined. Aborting.[/red]")
        raise typer.Exit(1)

    # Final balance & gas check
    eth_balance = w3.eth.get_balance(account.address)
    if eth_balance < eth_required_wei:
        print(f"[red]Insufficient ETH. Have: {w3.from_wei(eth_balance, 'ether'):.6f}, Need: {eth_required:.6f}[/red]")
        raise typer.Exit(1)

    # Add 10% slippage on ETH input (i.e., allow up to 10% more ETH to ensure USDT amount is met)
    eth_with_slippage = int(eth_required_wei * 1.10)
    deadline_ts = w3.eth.get_block('latest')['timestamp'] + 300  # 5 min deadline
    w3.provider.make_request("evm_mine", [])

    # Build transaction
    try:
        swap_tx = router_contract.functions.swapETHForExactTokens(
            amount_wei,
            path,
            account.address,
            deadline_ts
        ).build_transaction({
            'from': account.address,
            'value': eth_with_slippage,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 300000,
            'gasPrice': w3.to_wei('5', 'gwei'),
            'chainId': w3.eth.chain_id,
        })

        signed_tx = account.sign_transaction(swap_tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"[cyan]Transaction sent: {tx_hash.hex()}[/cyan]")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            print("[red]Transaction failed on-chain.[/red]")
            raise typer.Exit(1)

        final_usdt_balance = usdt_contract.functions.balanceOf(account.address).call()
        final_formatted = final_usdt_balance / (10 ** decimals)
        print(f"[bold green]✅ USDT purchase successful![/bold green]")
        print(f"[cyan]Your USDT balance:[/cyan] {final_formatted:.6f} USDT")

    except Exception as e:
        print(f"[red]Transaction error: {e}[/red]")
        raise typer.Exit(1)
    
    


@app.command("configure-network")
def configure_network(network: str = typer.Option(..., help="Network")):
    """
    Configure the default blockchain network for DIN CLI.
    """
    
    effective_network = resolve_network(network)

    config = load_config()
    config["network"] = effective_network
    save_config(config)

    print(f"[green]Network configured successfully: {network}[/green]")

@app.command("configure-demo")
def configure_demo(
    mode: str = typer.Option("no", "--mode", help="Set demo mode: yes or no")
):
    """
    Enable/disable demo mode (plaintext wallet storage, no password).
    Useful for Hardhat/local testing.
    """
    
    if mode.lower() not in ("yes", "no"):
        print("[red]Mode must be 'yes' or 'no'[/red]")
        raise typer.Exit(1)
    
    enable = mode.lower() == "yes"
    config = load_config()
    config["demo_mode"] = enable
    save_config(config)
    status = "enabled" if enable else "disabled"
    print(f"[green]Demo mode {status}.[/green]")
    if enable:
        print("[yellow]⚠️  Wallets will be stored in plaintext. Do NOT use with real keys![/yellow]")

@app.command("configure-logging")
def configure_logging(  
    level: str = typer.Option("info", "--level", help="Set log level: debug | info | warning | error | critical")
):
    """
    Configure the log level for DIN CLI.
    """
    
    if level.lower() not in ("debug", "info", "warning", "error", "critical"):
        print("[red]Level must be 'debug', 'info', 'warning', 'error', or 'critical'[/red]")
        raise typer.Exit(1)
    
    config = load_config()
    config["log_level"] = level.lower()
    save_config(config)
    print(f"[green]Log level set to {level}.[/green]")
    
    
@app.command()
def connect_wallet(
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
    
    if len(provided_methods) > 1:
        print(f"[red]❌ Please specify only one of: {', '.join(provided_methods)}.[/red]")
        raise typer.Exit(1)
    
    # Resolve private key
    demo_mode = False
    
    if account is not None:
        # Load from demo accounts
        try:
            privatekey = get_demo_private_key(account)
            demo_mode = True  # auto-enable demo mode
        except (FileNotFoundError, IndexError) as e:
            print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
            
    elif key_file is not None:
        # Load from file
        key_file = key_file.expanduser() 
        if not key_file.exists():
            print(f"[red]❌ Key file not found: {key_file}[/red]")
            raise typer.Exit(1)
        try:
            with open(key_file, 'r') as f:
                privatekey = f.read().strip()
            config = load_config()
            demo_mode = config.get("demo_mode", False)
        except Exception as e:
            print(f"[red]❌ Failed to read key file: {e}[/red]")
            raise typer.Exit(1)
            
    elif privatekey is not None:
        # Explicit argument
        print("[yellow]⚠️  Warning: Providing private key as argument is insecure (saved in shell history). Use interactive mode or --key-file instead.[/yellow]")
        config = load_config()
        demo_mode = config.get("demo_mode", False)
        
    else:
        # Interactive prompt
        print("[cyan]Enter your Ethereum private key (input will be hidden):[/cyan]")
        privatekey = getpass("Private Key: ").strip()
        config = load_config()
        demo_mode = config.get("demo_mode", False)

    # Validate format (for all methods)
    if not privatekey.startswith("0x") or len(privatekey) != 66:
        print("[red]❌ Invalid private key format! Must be 0x + 64 hex chars.[/red]")
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
        print(f"[green]✅ Wallet saved in DEMO MODE (plaintext)![/green]")
        print(f"[yellow]Address:[/yellow] {acct.address}")
        print(f"[cyan]File:[/cyan] {WALLET_FILE}")
        
    else:

        # Ask for encryption password
        password = getpass("Create wallet password: ")
        confirm = getpass("Confirm password: ")

        if password != confirm:
            print("[red]Passwords do not match![/red]")
            raise typer.Exit()

    

        # Use eth-account to create an encrypted keystore
        keystore = Account.encrypt(privatekey, password)

        # Save encrypted wallet locally
        with open(WALLET_FILE, "w") as f:
            json.dump(keystore, f, indent=4)

        print(f"[green]Wallet connected successfully![/green]")
        print(f"[yellow]Address:[/yellow] {acct.address}")
        print(f"[cyan]Encrypted keystore saved at:[/cyan] {WALLET_FILE}")
    
@app.command()
def read_wallet():
    """
    Read and display wallet info.
    In demo mode, shows private key. Otherwise, shows only address (after decrypting).
    """
    if not WALLET_FILE.exists():
        print("[red]No wallet found. Run `dincli system connect-wallet` first.[/red]")
        raise typer.Exit(1)

    with open(WALLET_FILE) as f:
        data = json.load(f)

    # Check if it's demo mode (plaintext)
    if isinstance(data, dict) and data.get("demo_mode") is True:
        print("[bold green]🔐 Wallet (Demo Mode - Plaintext)[/bold green]")
        print(f"[yellow]Address:[/yellow] {data['address']}")
        print(f"[red]Private Key:[/red] {data['private_key']}")
        print("[cyan]⚠️  This key is stored in plaintext — for local testing only![/cyan]")
        return
    try:

        acct = load_account()
        print(f"[yellow]Address:[/yellow] {acct.address}")
        print("[green]✅ Wallet decrypted successfully.[/green]")
    except Exception as e:
        print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)

@app.command()
def din_info(
    coordinator: bool = typer.Option(False, "--coordinator", help="Show coordinator address"),
    token: bool = typer.Option(False, "--token", help="Show DIN token address"),
    stake: bool = typer.Option(False, "--stake", help="Show staking contract"),
    representative: bool = typer.Option(False, "--representative", help="Show representative logic"),
    network: str = typer.Option(None, "--network", help="Override active network (local|sepolia|mainnet)"),
):
    
    # Resolve effective network
    effective_network = resolve_network(network)

    # Validate
    allowed_networks = {"local", "hardhat","sepolia", "mainnet"}
    if effective_network not in allowed_networks:
        print(f"[red]Invalid network: {effective_network}. Must be one of: {sorted(allowed_networks)}[/red]")
        raise typer.Exit(1)

    # Load address config (you can move this to utils too)
    

    data = din_addresses.get(effective_network, {})

    # Print requested info
    if coordinator:
        print(f"[cyan]Coordinator:[/cyan] {data.get('coordinator', 'N/A')}")
    if token:
        print(f"[green]DIN Token:[/green] {data.get('token', 'N/A')}")
    if stake:
        print(f"[yellow]Staking Contract:[/yellow] {data.get('stake', 'N/A')}")
    if representative:
        print(f"[magenta]Representative:[/magenta] {data.get('representative', 'N/A')}")

    if not any([coordinator, token, stake, representative]):
        print(f"[cyan]Coordinator:[/cyan] {data.get('coordinator', 'N/A')}")
        print(f"[green]DIN Token:[/green] {data.get('token', 'N/A')}")
        print(f"[yellow]Staking Contract:[/yellow] {data.get('stake', 'N/A')}")
        print(f"[magenta]Representative:[/magenta] {data.get('representative', 'N/A')}")


@app.command("reset-all")
def reset_all(
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
def todo():
    typer.secho("TODO list:", fg=typer.colors.CYAN)

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

    if get_env_key(env_key) is None:
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

    if CONFIG_FILE.exists():
        config = load_config()
        network = config.get("network")
        if network:
            rpc_env_key = f"{network.upper()}_RPC_URL"
            if get_env_key(rpc_env_key) is None:
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

    if get_env_key("IPFS_API_URL_ADD") is None:
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
        console.print(f"[green]✅ IPFS API ADD URL found in environment variable: IPFS_API_URL_ADD in {cwd}/.env file with value: {get_env_key('IPFS_API_URL_ADD')}[/green]")
    if get_env_key("IPFS_API_URL_RETRIEVE") is None:
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
        console.print(f"[green]✅ IPFS API RETRIEVE URL found in environment variable: IPFS_API_URL_RETRIEVE in {cwd}/.env file with value: {get_env_key('IPFS_API_URL_RETRIEVE')}[/green]")    
    
    

@dataset_app.command()
def distribute_mnist(
    clients: int = typer.Option(..., "--clients", "-c", help="Number of clients"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed")
):
    """
    Download MNIST and distribute it across N clients (IID split).
    Saves data under CONFIG_DIR/clients/client_i/data.pt
    """

    if clients <= 0:
        print("[red]Number of clients must be >= 1[/red]")
        raise typer.Exit(1)

    base_dir = CONFIG_DIR
    dataset_dir = base_dir / "dataset"
    clients_dir = base_dir / "clients"

    # Ensure directories exist
    dataset_dir.mkdir(parents=True, exist_ok=True)
    clients_dir.mkdir(parents=True, exist_ok=True)

    print(f"[cyan]Using config dir:[/cyan] {base_dir}")

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Download MNIST
    train_dataset = datasets.MNIST(root=dataset_dir, train=True, download=True, transform=transform)
    test_dataset = datasets.MNIST(root=dataset_dir, train=False, download=True, transform=transform)

    # Save raw datasets
    (dataset_dir / "train").mkdir(exist_ok=True)
    (dataset_dir / "test").mkdir(exist_ok=True)

    torch.save(train_dataset, dataset_dir / "train/train_dataset.pt")
    torch.save(test_dataset, dataset_dir / "test/test_dataset.pt")

    print(f"[green]Processed Datasets saved successfully to {dataset_dir}![/green]")

    # IID SPLIT
    total_samples = len(train_dataset)
    indices = np.arange(total_samples)

    np.random.seed(seed)
    np.random.shuffle(indices)

    partitions = np.array_split(indices, clients)

    for i, idxs in enumerate(partitions):
        client_path = clients_dir / f"client_{i}"
        client_path.mkdir(parents=True, exist_ok=True)

        # Extract subset
        subset_data = [(train_dataset[idx][0], train_dataset[idx][1]) for idx in idxs]

        save_path = client_path / "data.pt"
        torch.save(subset_data, save_path)

        print(f"[green]Saved client_{i} ({len(subset_data)} samples) → {save_path}[/green]")

    print(f"[bold green]✅ MNIST distributed to {clients} clients under {clients_dir}[/bold green]")
    
@app.command()
def dump_abi(
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
    
    artifact = Path(artifact_path)
    if not artifact.exists():
        print(f"[red]❌ Artifact not found: {artifact}[/red]")
        raise typer.Exit(1)

     # Load full artifact
    try:
        with open(artifact) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[red]❌ Failed to read artifact: {e}[/red]")
        raise typer.Exit(1)

    # Validate required fields
    if "abi" not in data:
        print(f"[red]❌ No 'abi' field in {artifact}[/red]")
        raise typer.Exit(1)

    # Build output data
    output_data = {"abi": data["abi"]}
    
    if include_bytecode and "bytecode" in data:
        output_data["bytecode"] = data["bytecode"]
    elif include_bytecode:
        print(f"[yellow]⚠️  'bytecode' not found in {artifact}, skipping.[/yellow]")

    # Determine name
    output_name = name or artifact.stem

    if official and not output_dir:
        abi_dir = Path(__file__).parent / "abis"
    elif output_dir:
        abi_dir = Path(output_dir)
    else:
        # Default to ./abis in the current working directory (project root)
        abi_dir = Path.cwd() / "abis"

    abi_dir.mkdir(exist_ok=True)

    output_path = abi_dir / f"{output_name}.json"

    # Save in Hardhat-compatible format
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"[green]✅ Artifact saved to:[/green] {output_path}")
    print(f"[cyan]→ ABI-only: {not include_bytecode} | Includes bytecode: {include_bytecode}[/cyan]")
    
    

@app.command("upload-to-ipfs")
def upload_file_to_ipfs(
    file_path: str = typer.Option(..., "--filepath", "-f", help="Path to file to upload to IPFS"),
    name: str = typer.Option(None, "--name", "-n", help="Name for the file on IPFS"),
):
    """
    Upload a file to IPFS and return the IPFS hash.
    """
    if name is None:
        name = Path(file_path).name
    
    try:
        ipfs_hash = upload_to_ipfs(file_path, name)
        print(f"[green]✅ File uploaded to IPFS:[/green] {ipfs_hash}")
    except Exception as e:
        print(f"[red]❌ Failed to upload file to IPFS: {e}[/red]")
        raise typer.Exit(1)

@app.command("download-from-ipfs")
def download_file_from_ipfs(
    ipfs_hash: str = typer.Option(..., "--hash", "-h", help="IPFS hash of file to download"),
    file_path: str = typer.Option(..., "--filepath", "-f", help="Path to save downloaded file"),
):
    """
    Download a file from IPFS using its hash.
    """
    try:
        retrieve_from_ipfs(ipfs_hash, file_path)
        print(f"[green]✅ File downloaded from IPFS:[/green] {file_path}")
    except Exception as e:
        print(f"[red]❌ Failed to download file from IPFS: {e}[/red]")
        raise typer.Exit(1)



@app.command("add-role")    
def add_role(
    role: str = typer.Option(..., "--role", "-r", help="Role to add (e.g., 'auditor, aggregator, client')"),
    model_id: int = typer.Option(..., "--model-id", "-m", help="Model ID to add role to"),
):
    if role not in ["auditor", "aggregator", "client"]:
        print(f"[red]❌ Invalid role: {role}[/red]")
        raise typer.Exit(1)

    if model_id < 0:
        print(f"[red]❌ Invalid model ID: {model_id}[/red]")
        raise typer.Exit(1)

    config_path = Path(CONFIG_DIR).resolve()
    if not config_path.exists():
        os.makedirs(config_path)
    
    role_dir_path = config_path / "roles"
    if not role_dir_path.exists():
        os.makedirs(role_dir_path)
        
    role_path = role_dir_path / f"{role}.json"

    if role_path.exists():
        with open(role_path, "r") as f:
            data = json.load(f)
        
        if model_id in data["models"]:
            print(f"[red]❌ Model ID {model_id} already exists for role {role}[/red]")
            raise typer.Exit(1)
        
        data["models"].append(model_id)
        with open(role_path, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"[green]✅ Added model ID {model_id} to role {role}[/green]")
        return
    
    with open(role_path, "w") as f:
        json.dump({"models": [model_id]}, f, indent=2)
    
    print(f"[green]✅ Added model ID {model_id} to role {role}[/green]")

    



    