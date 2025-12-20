import typer
import json
import shutil
from datetime import datetime, timedelta
from rich.prompt import Confirm
from rich import print
from typing import Optional
from eth_account import Account
from decimal import Decimal
from getpass import getpass
from dincli.utils import save_config, load_config, CONFIG_DIR, CONFIG_FILE, load_usdt_config, resolve_network, get_demo_private_key, get_w3, load_account
from pathlib import Path

dataset_app = typer.Typer(help="Manage federated datasets.")

app = typer.Typer(help="System utilities for DIN CLI.")

# Register the dataset group under system_app
app.add_typer(dataset_app, name="dataset")

WALLET_FILE = CONFIG_DIR / "wallet.json"


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
    
    


@app.command()
def configure_network(network: str = typer.Option(..., help="Network: local | sepolia | mainnet")):
    """
    Configure the network for the CLI
    """
    
    """
    Configure the default blockchain network for DIN CLI.
    """
    allowed = ["local", "sepolia", "mainnet"]

    if network not in allowed:
        print(f"[red]Invalid network! Must be one of: {allowed}[/red]")
        raise typer.Exit()

    config = load_config()
    config["network"] = network
    save_config(config)

    print(f"[green]Network configured successfully: {network}[/green]")

@app.command()
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
    print(f"[green]Mock mode {status}.[/green]")
    if enable:
        print("[yellow]⚠️  Wallets will be stored in plaintext. Do NOT use with real keys![/yellow]")
    
    
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

    # Otherwise: encrypted keystore (standard format)
    print("[bold green]🔐 Wallet (Encrypted Keystore)[/bold green]")
    password = getpass("Enter wallet password: ")
    try:
        private_key = Account.decrypt(data, password)
        acct = Account.from_key(private_key)
        print(f"[yellow]Address:[/yellow] {acct.address}")
        print("[green]✅ Wallet decrypted successfully.[/green]")
    except ValueError:
        print("[red]❌ Incorrect password or corrupted keystore.[/red]")
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


@app.command()
def reset_all(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
):
    """
    Delete the entire DIN CLI config directory (~/.din).
    This removes wallets, client datasets, network config, and more.
    """
    config_path = Path(CONFIG_DIR).resolve()

    if not config_path.exists():
        print(f"[yellow]Config directory does not exist: {config_path}[/yellow]")
        return

    if not force:
        confirm = typer.confirm(
            f"[red]⚠️  This will permanently delete:[/red]\n{config_path}\n\nAre you sure?"
        )
        if not confirm:
            print("[cyan]Operation cancelled.[/cyan]")
            raise typer.Exit()

    try:
        shutil.rmtree(config_path)
        print(f"[green]✅ Successfully deleted config directory: {config_path}[/green]")
    except Exception as e:
        print(f"[red]❌ Failed to delete {config_path}: {e}[/red]")
        raise typer.Exit(code=1)    

import numpy as np
import torch
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, random_split
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
    abi_dir = Path(__file__).parent / "abis"
    abi_dir.mkdir(exist_ok=True)
    output_path = abi_dir / f"{output_name}.json"

    # Save in Hardhat-compatible format
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"[green]✅ Artifact saved to:[/green] {output_path}")
    print(f"[cyan]→ ABI-only: {not include_bytecode} | Includes bytecode: {include_bytecode}[/cyan]")
    
    
    