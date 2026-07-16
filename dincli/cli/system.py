import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from getpass import getpass
from importlib.resources import files
from pathlib import Path
from typing import Optional
from rich.console import Console
import typer
import time
from eth_account import Account
from rich.prompt import Confirm

from dincli.cli.contract_utils import erc20_abi, router_abi
from dincli.cli.utils import (CACHE_DIR, CONFIG_DIR,
                              CONFIG_FILE, WORKER_CACHE_DIR,
                              print_tx_info,
                              SUPPORTED_IPFS_PROVIDERS, _get_password,
                              _confirm_or_exit, _clean_optional_string,
                              get_config, get_demo_private_key,
                              get_env_key, is_ethereum_address,
                              load_cid_services, load_config,
                              load_din_info, normalize_ipfs_provider,
                              resolve_ipfs_config, resolve_task_coordinator_address,
                              save_config, save_din_info,
                              validate_account_name, wallet_path_for_name,
                              atomic_write_wallet, resolve_wallet_path,
                              list_accounts, get_active_account_name, load_account,
                              _extract_keystore, ensure_wallets_dir)

dataset_app = typer.Typer(help="Manage federated datasets.")

app = typer.Typer(help="System utilities for DIN CLI.")

# Register the dataset group under system_app
app.add_typer(dataset_app, name="dataset")


def _is_inside_container() -> bool:
    """Return True when running inside a Docker container (/.dockerenv is the canonical marker)."""
    return Path("/.dockerenv").exists()


def initialize_directories():
    """
    Create user-level config and cache dirs if they do not exist.
    Call this explicitly (e.g. from CLI or first-run code), not on import.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(WORKER_CACHE_DIR, exist_ok=True)
    print(f"Initialized directories:\n- Config: {CONFIG_DIR}\n- Cache: {CACHE_DIR} \n- Worker Cache: {WORKER_CACHE_DIR}")

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
    if ctx.invoked_subcommand in ["register-wallet", "connect-wallet", "init", "welcome", "where", "configure-network", "configure-demo", "read-wallet", "show-index", "din-info", "import-deployments", "configure-logging", "dump-abi", "reset-all", "todo", "dataset", "send-eth", "run-worker-counting", "run-node-counting", "list-accounts", "set-wallet"]:
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

@app.command("run-node-counting")
def run_node_counting():
    """Run the counting task."""
    typer.echo("Running the counting task...")
    n = 0
    while True:
        n += 1
        time.sleep(1)
        typer.echo(f"DIN Node Count: {n}")


@app.command("run-worker-counting")
def run_worker_counting(
    count: int = typer.Option(10, "--count", "-n", help="Number of counts (0 for infinite)"),
    delay: float = typer.Option(1.0, "--delay", "-d", help="Seconds between counts"),
):
    """Run a counting task inside the DIN worker container."""
    from dincli.cli.worker import ensure_worker_image, write_worker_job, WORKER_IMAGE

    console = Console()

    try:
        ensure_worker_image(console)
    except RuntimeError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(1)

    
    model_dir = Path(CACHE_DIR / "model_tmp")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "manifest.json").write_text("{}\n", encoding="utf-8")

    svc_dir = model_dir / "services"
    svc_dir.mkdir()
    svc_src = Path(str(files("dincli"))) / "services" / "counting_service.py"
    shutil.copy(svc_src, svc_dir / "counting_service.py")

    job_path, output_dir = write_worker_job(
        model_dir / "jobs",
        "counting",
        {
            "network": "local",
            "model_base_dir": "/din/model",
            "manifest_path": "/din/model/manifest.json",
            "role": "system",
            "service_path": "services/counting_service.py",
            "function_name": "run_counting",
            "kwargs": {"count": count, "delay": delay},
        },
    )

    cmd = [
        "docker", "run", "--rm",
        "--name", "din-worker-counting",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/tmp",
        "--network", "none",
        "-v", f"{model_dir.resolve()}:/din/model:ro",
        "-v", f"{job_path.resolve()}:/din/job/job.json:ro",
        "-v", f"{output_dir.resolve()}:/din/output:rw",
        WORKER_IMAGE,
    ]

    console.print("[bold cyan]Starting worker counting container (Ctrl+C to stop)...[/bold cyan]")
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker counting stopped.[/yellow]")


@app.command()
def welcome():
    """Print welcome message."""
    typer.echo("Welcome to DIN CLI!")

@app.command("get-cache-dir")
def get_cache_dir():
    """Print cache directory paths used by dincli."""
    if _is_inside_container():
        typer.echo("Environment: DIN node container")
        typer.echo("(DIN_STATE_DIR is bind-mounted at the identical host path, so paths below are valid on the host daemon too)")
    else:
        typer.echo("Environment: host")
    typer.echo(f"Cache Directory:        {CACHE_DIR}")
    typer.echo(f"Worker Node Cache Directory: {WORKER_CACHE_DIR}")

@app.command("get-config-dir")
def get_config_dir():
    """Print config directory path used by dincli."""
    if _is_inside_container():
        typer.echo("Environment: DIN node container")
        typer.echo("(DIN_STATE_DIR is bind-mounted at the identical host path, so path below is valid on the host daemon too)")
    else:
        typer.echo("Environment: host")
    typer.echo(f"Config Directory: {CONFIG_DIR}")



@app.command("init")
def initialize():
    """Initialize DIN CLI by creating config/cache directories and an empty config file."""
    initialize_directories()
    if not CONFIG_FILE.exists():
        # Write an empty JSON object (valid JSON)
        CONFIG_FILE.write_text("{}\n", encoding="utf-8")
        Console().print(f"[green]✅ Created empty config file at: {CONFIG_FILE}[/green]")
 
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

# ---------------------------------------------------------------------------
# Wallet model — registration vs. connection
# ---------------------------------------------------------------------------
# Wallets are *registered* once (key material stored under a name) and then
# *connected* (made the active wallet) as often as needed:
#
#   dincli system register-wallet ...    write key material to
#                                        <CONFIG_DIR>/wallets/wallet_<name>.json
#   dincli system connect-wallet NAME    flip the persistent active-wallet
#                                        pointer (config "wallet_name");
#                                        never touches key material, never
#                                        prompts for a secret
#
# Every command resolves the active wallet via utils.get_active_account_name()
# with this precedence (first hit wins):
#
#   1. dincli --wallet <name>    global flag — this invocation only
#   2. DIN_WALLET_NAME           environment variable
#   3. config "wallet_name"      persisted by connect-wallet (or set-wallet)
#   4. "default"                 wallets/wallet_default.json, falling back to
#                                the legacy single-wallet <CONFIG_DIR>/wallet.json
#
# The private key is only decrypted (DIN_WALLET_PASSWORD or password prompt)
# when a command actually needs to sign — see utils.load_account().


def _connect_registered_wallet(console, name: str) -> str:
    """Persist `name` as the active wallet (config "wallet_name").

    Pure pointer flip: requires the wallet file to already exist, never writes
    key material, never prompts for a secret. Returns the validated name.
    """
    try:
        resolved = validate_account_name(name)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)

    wallet_path, exists = resolve_wallet_path(resolved)
    if not exists:
        console.print(
            f"[red]❌ Wallet '{resolved}' not found. "
            f"Run `dincli system register-wallet --name {resolved}` first.[/red]"
        )
        registered = [e["name"] for e in list_accounts(resolved)]
        if registered:
            console.print(f"[yellow]Registered wallets:[/yellow] {', '.join(registered)}")
        raise typer.Exit(1)

    config = load_config()
    config["wallet_name"] = resolved
    save_config(config)

    # Show the address without decrypting (present in demo, wrapper, and
    # legacy-keystore formats; fall back gracefully if unreadable).
    try:
        with open(wallet_path) as f:
            address = json.load(f).get("address", "unknown")
    except (json.JSONDecodeError, OSError):
        address = "unknown"

    console.print(f"[green]✅ Active wallet set to '{resolved}'[/green] ({address})")
    console.print("[dim]`dincli --wallet <name>` or DIN_WALLET_NAME still override this per invocation.[/dim]")
    return resolved


@app.command("connect-wallet")
def connect_wallet(ctx: typer.Context,
    name: str = typer.Argument("default", help="Registered wallet name to make active (default: 'default')"),
):
    """
    Connect (activate) a registered named wallet.

    Persists the choice in config ("wallet_name") so every subsequent dincli
    invocation on this machine uses that wallet. This is purely a pointer
    flip: no key material is read, written, or decrypted, and nothing is
    prompted — so switching between named wallets is always safe and silent.

    Active-wallet resolution priority (first hit wins):

    
      1. dincli --wallet <name>   global flag, this invocation only
      2. DIN_WALLET_NAME          environment variable
      3. config "wallet_name"     <- what this command sets
      4. 'default'

    The wallet must already be registered:

    
      dincli system register-wallet --name validator --keystore ks.json
      dincli system connect-wallet validator     # switch to it
      dincli system connect-wallet               # switch back to 'default'
    """
    # Direct callers (e.g. tests) may omit the argument; Typer then passes an
    # ArgumentInfo object — normalize to the CLI default.
    if not isinstance(name, str):
        name = "default"

    # Guard against a common trap: `--wallet X` is the global per-invocation
    # override (GlobalOptionsGroup hoists it to the root callback), so it never
    # reaches this command — `connect-wallet --wallet X` just falls back to the
    # positional default. If the override names a different wallet than the
    # argument, the user almost certainly meant the positional form.
    override = ctx.obj.wallet_name
    if override and override != name:
        ctx.obj.console.print(
            f"[red]❌ `--wallet {override}` overrides the active wallet for this "
            f"invocation only — it does not choose the wallet to connect.[/red]"
        )
        ctx.obj.console.print(
            f"[yellow]Did you mean:[/yellow] dincli system connect-wallet {override}"
        )
        raise typer.Exit(1)

    resolved = _connect_registered_wallet(ctx.obj.console, name)
    # Keep the in-process context consistent for the rest of this invocation.
    ctx.obj.select_wallet(resolved)


@app.command("set-wallet", deprecated=True)
def set_wallet(ctx: typer.Context, name: str = typer.Argument(..., help="Wallet name to set as the persistent default")):
    """(Deprecated) Alias of `connect-wallet`."""
    console = ctx.obj.console
    console.print("[yellow]`set-wallet` is deprecated — use `dincli system connect-wallet <name>`.[/yellow]")
    _connect_registered_wallet(console, name)

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
    
    
@app.command("register-wallet")
def register_wallet(ctx: typer.Context,
    privatekey: Optional[str] = typer.Argument(None, help="Your Ethereum private key (0x...)"),
    key_file: Optional[Path] = typer.Option(None, "--key-file", "-f", help="Path to file containing private key"),
    account: Optional[int] = typer.Option(None, "--account", "-a", help="Hardhat dev account index (0-69)"),
    keystore: Optional[Path] = typer.Option(None, "--keystore", help="Import a standard Ethereum JSON keystore file"),
    name: Optional[str] = typer.Option("default", "--name", "-n", help="Label for the saved keystore (default 'default')"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt when overwriting an existing named wallet"),
    connect: bool = typer.Option(False, "--connect", "-c", help="Also make this wallet the active one (same as running `connect-wallet <name>` afterwards)"),
):
    """
    Register a wallet: store key material under a name (create or import).

    The key comes from exactly ONE of the following sources — passing more
    than one is an error, passing none falls through to the hidden prompt:

    
      --keystore FILE   import a standard Ethereum JSON keystore
      --account N       dev-account index: in demo mode reads the bundled
                        Hardhat dev keys, otherwise reads ETH_PRIVATE_KEY_<N>
                        from the environment/.env
      --key-file FILE   read the raw private key (0x...) from a file
      PRIVATEKEY        positional argument (insecure: shell history/logs)
      (none)            interactive hidden prompt  <- recommended

    
    Storage (at <CONFIG_DIR>/wallets/wallet_<name>.json):
      demo mode ON   -> plaintext JSON — local Hardhat testing ONLY
      demo mode OFF  -> encrypted keystore; the encryption password comes
                        from DIN_WALLET_PASSWORD if set, else a create/confirm
                        prompt

    Registering does NOT switch the active wallet — pass --connect, or run
    `dincli system connect-wallet <name>` afterwards. (--name defaults to
    'default', which is also the final fallback of the active-wallet
    resolution, so a plain `register-wallet` sets up the wallet used when
    nothing else is selected.)

    An existing wallet with the same name is only overwritten after
    confirmation (skip with --yes).

    
    Examples:
      dincli system register-wallet                          # prompt, save as 'default'
      dincli system register-wallet --keystore ks.json --name validator
      dincli system register-wallet --key-file ~/.dincli/wallet.key
      dincli system register-wallet --account 3 --name acct3 --connect
    """

    console = ctx.obj.console
    # Direct callers (e.g. tests) may omit --yes/--connect; Typer then passes an
    # OptionInfo object (truthy), which would silently bypass the overwrite guard
    # below (or trigger an unwanted connect). Normalize to real bools so the
    # behavior is the same on direct calls.
    yes = yes if isinstance(yes, bool) else False
    connect = connect if isinstance(connect, bool) else False

    # Validate account name
    try:
        resolved_name = validate_account_name(name or "default")
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)

    # Validate mutual exclusivity
    auth_methods = [
        (privatekey, "private key argument"),
        (key_file, "key file"),
        (account, "account index"),
        (keystore, "keystore file"),
    ]
    provided_methods = [n for val, n in auth_methods if val is not None]

    if len(provided_methods) > 1:
        console.print(f"[red]❌ Please specify only one of: {', '.join(provided_methods)}.[/red]")
        raise typer.Exit(1)

    demo_mode = get_config("demo_mode")
    source = "created"

    # --- keystore import: non-secret validation only ---
    # Runs before the overwrite guard so a missing/malformed keystore fails fast
    # without prompting, and so no secret (passphrase) is requested before the
    # overwrite decision. The passphrase/decrypt happen after the guard, below.
    inner_keystore = None
    if keystore is not None:
        keystore = keystore.expanduser()
        if not keystore.exists():
            console.print(f"[red]❌ Keystore file not found: {keystore}[/red]")
            raise typer.Exit(1)
        try:
            with open(keystore, 'r') as f:
                imported_ks = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            console.print(f"[red]❌ Failed to read keystore file: {e}[/red]")
            raise typer.Exit(1)
        try:
            inner_keystore = _extract_keystore(imported_ks)
        except ValueError:
            console.print("[red]❌ File does not contain a recognisable keystore.[/red]")
            raise typer.Exit(1)
        source = "imported"

    # --- overwrite guard ---
    # Confirm before overwriting an existing named keystore, and before any secret
    # prompt. Keys on the exact file to be written (a legacy wallet.json for the
    # 'default' name is a non-destructive migration and intentionally not guarded).
    target_path = wallet_path_for_name(resolved_name)
    if target_path.exists() and not yes:
        console.print(f"[yellow]A wallet named '{resolved_name}' already exists at {target_path}.[/yellow]")
        if not typer.confirm("Overwrite it?"):
            console.print("[yellow]Aborted. Existing wallet left unchanged.[/yellow]")
            raise typer.Exit(0)

    console.print(f"[green] ⚙️  Registering wallet...[/green]")
    console.print(f"[cyan]Saving as:[/cyan] {resolved_name}")

    # --- resolve secret material ---
    if keystore is not None:
        # Uses the keystore already extracted above — no re-read/re-parse.
        passphrase = getpass("Keystore passphrase: ")
        try:
            decrypted_key = Account.decrypt(inner_keystore, passphrase)
        except ValueError:
            console.print("[red]❌ Wrong passphrase or corrupted keystore.[/red]")
            raise typer.Exit(1)
        acct = Account.from_key(decrypted_key)
        address = acct.address

    elif account is not None and demo_mode:
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

    # For non-keystore paths: validate key format and derive address
    if keystore is None:
        if not privatekey.startswith("0x") or len(privatekey) != 66:
            console.print("[red]❌ Invalid private key format! Must be 0x + 64 hex chars.[/red]")
            raise typer.Exit(1)
    
    # Ensure config dir exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if keystore is None:
        acct = Account.from_key(privatekey)
        address = acct.address


    if demo_mode  and keystore is None:
        # Save plaintext private key (for Hardhat/local testing ONLY)
        wallet_data = {
            "address": address,
            "private_key": privatekey,  # ⚠️ PLAINTEXT — ONLY FOR MOCK!
            "demo_mode": True
        }

        ensure_wallets_dir()
        wallet_path = wallet_path_for_name(resolved_name)

        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f, indent=4)
        console.print(f"[green]✅ Wallet saved in DEMO MODE (plaintext)![/green]")
        console.print(f"[yellow]Address:[/yellow] {address}")
        console.print(f"[cyan]Wallet File:[/cyan] {wallet_path}")
        
    else:

        if keystore is not None:
            ks_payload = inner_keystore
        else:
            # is_new_wallet=True: never reuse a stale in-memory-cached password when
            # creating/overwriting a wallet; force the create/confirm flow (env var
            # DIN_WALLET_PASSWORD is still honored for automation).
            password = _get_password(resolved_name, False, is_new_wallet=True)
            if password == "":
                password = getpass("Create wallet password: ")
                confirm = getpass("Confirm password: ")
                if password != confirm:
                    console.print("[red]Passwords do not match![/red]")
                    raise typer.Exit()
            ks_payload = Account.encrypt(privatekey, password)

        wrapper = {
            "version": 1,
            "address": address,
            "keystore": ks_payload,
            "source": source,
            "name": resolved_name,
        }

        wallet_path = wallet_path_for_name(resolved_name)
        atomic_write_wallet(wallet_path, wrapper)

        console.print(f"[green]Wallet {resolved_name} registered successfully![/green]")
        console.print(f"[green]Wallet Account Address:[/green] {address}")
        console.print(f"[green]Encrypted keystore saved at:[/green] {wallet_path}")

    # Registration never switches the active wallet implicitly — only via
    # --connect (see the wallet-model comment above for the resolution order).
    if connect:
        _connect_registered_wallet(console, resolved_name)
    elif resolved_name != "default":
        console.print(
            f"[dim]Run `dincli system connect-wallet {resolved_name}` to make it the active wallet.[/dim]"
        )


@app.command("read-wallet")
def read_wallet(ctx: typer.Context, 
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Wallet name")
):
    """
    Read and display wallet info.
    In demo mode, shows private key. Otherwise, shows only address (after decrypting).
    """
    console = ctx.obj.console
    if not isinstance(name, str):
        name = None

    if name is not None:
        wallet_to_read_name = name
        active = False
    else:
        wallet_to_read_name = ctx.obj.resolved_wallet_name
        active = True
    wallet_path, exists = resolve_wallet_path(wallet_to_read_name)

    if not exists:
        console.print(f"[red]No wallet found for '{wallet_to_read_name}'. Run `dincli system register-wallet` first.[/red]")
        raise typer.Exit(1)

    with open(wallet_path) as f:
        data = json.load(f)

    # Check if it's demo mode (plaintext)
    if isinstance(data, dict) and data.get("demo_mode") is True:
        console.print("[bold green]🔐 Wallet (Demo Mode - Plaintext)[/bold green]")
        console.print(f"[green]Wallet Name:[/green] {wallet_to_read_name} {'[bold green](active)[/bold green]' if active else ''}")
        console.print(f"[yellow]Address:[/yellow] {data['address']}")
        console.print(f"[red]Private Key:[/red] {data['private_key']}")
        console.print("[cyan]⚠️  This key is stored in plaintext — for local testing only![/cyan]")
        return
    try:
        # Decrypt the *requested* wallet, not the active one — ctx.obj.account
        # always resolves the active wallet and would ignore --name.
        acct = load_account(wallet_to_read_name)
        console.print(f"[green]Wallet Name:[/green] {wallet_to_read_name} {'[bold green](active)[/bold green]' if active else ''}")
        console.print(f"[green]Address:[/green] {acct.address}")
        console.print("[green]✅ Wallet decrypted successfully.[/green]")
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)


@app.command("list-accounts")
def list_managed_accounts(ctx: typer.Context):
    """
    List all named wallet accounts and their addresses (no decrypt needed).
    Marks the currently active wallet.
    """
    console = ctx.obj.console
    active_name = ctx.obj.resolved_wallet_name
    accounts = list_accounts(active_name)

    if not accounts:
        console.print("[yellow]No wallets found. Run `dincli system register-wallet` to create one.[/yellow]")
        return

    console.print("[bold cyan]Named wallets:[/bold cyan]")
    for e in accounts:
        marker = "[green](active)[/green]" if e["active"] else ""
        source_tag = f" ({e['source']})" if e.get("source") not in ("unknown",) else ""
        console.print(f"  [bold]{e['name']}[/bold] → {e['address']}{source_tag} {marker}")

    console.print(f"\n[dim]Active wallet name:[/dim] {active_name}")

@app.command("send-eth")
def send_eth(
    ctx: typer.Context,
    amount: str = typer.Option(..., "--amount", "-a", help="Amount of ETH to send (in ETH)"),
    to: str = typer.Option(..., "--to", "-t", help="Recipient address"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """
    Send ETH to an address.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Validate recipient address
    try:
        to = w3.to_checksum_address(to)
    except Exception:
        console.print(f"[bold red]✗ Invalid recipient address: {to}[/bold red]")
        raise typer.Exit(1)

    # Convert amount to wei
    try:
        amount_wei = w3.to_wei(amount, "ether")
    except Exception as e:
        console.print(f"[bold red]✗ Invalid amount '{amount}': {e}[/bold red]")
        raise typer.Exit(1)

    # Check sender balance
    balance_wei = w3.eth.get_balance(account.address)
    if balance_wei < amount_wei:
        balance_eth = w3.from_wei(balance_wei, "ether")
        console.print(f"[bold red]✗ Insufficient balance. Have {balance_eth} ETH, tried to send {amount} ETH.[/bold red]")
        raise typer.Exit(1)

    # Confirmation prompt
    if not yes:
        console.print(f"\n[bold yellow]  From:[/bold yellow] {account.address}")
        console.print(f"[bold yellow]    To:[/bold yellow] {to}")
        console.print(f"[bold yellow]Amount:[/bold yellow] {amount} ETH")
        console.print(f"[bold yellow]   Net:[/bold yellow] {effective_network}\n")
        confirmed = typer.confirm("Confirm transaction?")
        if not confirmed:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Build and send raw ETH transfer
    try:
        tx_params = ctx.obj.get_tx_params()
        tx_params.update({"to": to, "value": amount_wei, "from": account.address})

        tx_params["gas"] = int(w3.eth.estimate_gas(tx_params) * 1.1)

        signed_tx = account.sign_transaction(tx_params)
        console.print(f"[bold green]Sending {amount} ETH to {to}...[/bold green]")

        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print_tx_info(tx_hash, effective_network)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            console.print(f"[bold green] ✓ Successfully sent {amount} ETH to {to}[/bold green]")
        else:
            console.print(f"[bold red]✗ Transaction failed (reverted)[/bold red]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]✗ Transaction failed: {e}[/bold red]")
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


# ---------------------------------------------------------------------------
# Platform deployments import
# ---------------------------------------------------------------------------
# The platform contracts (DinToken, DinCoordinator, DinValidatorStake,
# DINModelRegistry) are transparent proxies (PR 13). INTERIM bootstrap flow:
# proxy deployment + initialize + wiring is done by the toolchain script,
# which runs through the OpenZeppelin upgrades plugin:
#
#     cd hardhat && npx hardhat run scripts/deploy-platform.ts --network <net>
#
# That script records the proxy addresses in hardhat/deployments/<net>.json;
# `dincli system import-deployments` maps that file into din_info.json so all
# dincli commands resolve the deployed platform.
#
# NOTE — this is not the target architecture. The decision record
# Documentation/technical/upgradable-contracts/proxy-deployment-architecture.md
# chose native web3.py proxy deployment inside `dindao deploy` (its Option C;
# backlog: Developer/issues/dincli-native-proxy-deployment.md). Once that
# lands, this command demotes to a secondary sync utility for script-driven
# deployments/upgrades and for adopting already-deployed networks.
#
# Foundry migration note: foundry/ carries the same contracts but has no
# deploy scripts yet. Whatever produces the addresses next (forge script for
# upgrades, native dincli deploys for bootstrap), keep this command as the
# single import interface — either have the forge script write the same
# deployments/<network>.json shape (preferred, trivial with vm.writeJson), or
# extend _DEPLOYMENTS_TO_DIN_INFO parsing with a reader for foundry's
# broadcast/<Script>.s.sol/<chainid>/run-latest.json. Only the producer of the
# addresses changes; din_info.json stays the contract with the rest of dincli.

# dincli network name → hardhat network name (standalone `npx hardhat node`
# is hardhat's "localhost"); networks not listed map to themselves.
_HARDHAT_NETWORK_FOR = {"local": "localhost"}

# deployments/<network>.json keys (savePlatformAddresses in deploy/helpers.ts)
# → din_info.json keys. proxy_admin is informational; the four contract keys
# are required.
_DEPLOYMENTS_TO_DIN_INFO = {
    "dinCoordinator": "coordinator",
    "dinToken": "token",
    "dinValidatorStake": "stake",
    "dinModelRegistry": "registry",
    "proxyAdmin": "proxy_admin",
}
_REQUIRED_DEPLOYMENT_KEYS = ("dinToken", "dinCoordinator", "dinValidatorStake", "dinModelRegistry")


@app.command("import-deployments")
def import_deployments(ctx: typer.Context,
    file: Optional[Path] = typer.Option(
        None, "--file", "-f",
        help="Explicit deployments JSON path. Mutually exclusive with --foundry.",
    ),
    foundry: bool = typer.Option(
        False, "--foundry",
        help="Load from foundry/deployments/<network>.json (dincli 'local' maps to 'localhost'). Mutually exclusive with --file.",
    ),
):
    """
    Import platform proxy addresses from a deployments JSON into din_info.json.

    Hardhat flow (default):

      cd hardhat && npx hardhat run scripts/deploy-platform.ts --network localhost
      dincli system import-deployments

    Foundry flow:

      forge script foundry/script/DeployPlatform.s.sol --rpc-url http://127.0.0.1:8545 --broadcast ...
      dincli system import-deployments --foundry

    Both flows write the same address schema; this command reads either.
    Pass --file to supply an explicit path (mutually exclusive with --foundry).

    Only the platform address keys of the active network's din_info entry are
    updated (coordinator, token, stake, registry, proxy_admin); everything
    else (representative, explorer, default CIDs, ...) is preserved.
    """
    console = ctx.obj.console
    effective_network = ctx.obj.network

    if file is not None and foundry:
        console.print("[red]❌ --file and --foundry are mutually exclusive.[/red]")
        raise typer.Exit(1)

    if file is None:
        network_key = _HARDHAT_NETWORK_FOR.get(effective_network, effective_network)
        if foundry:
            file = Path("foundry") / "deployments" / f"{network_key}.json"
        else:
            file = Path("hardhat") / "deployments" / f"{network_key}.json"

    file = file.expanduser()
    if not file.exists():
        console.print(f"[red]❌ Deployments file not found: {file}[/red]")
        if foundry:
            console.print("[yellow]Run the Foundry deploy script first:[/yellow] forge script foundry/script/DeployPlatform.s.sol --rpc-url http://127.0.0.1:8545 --broadcast ...")
        else:
            console.print("[yellow]Run the platform deploy script first:[/yellow] cd hardhat && npx hardhat run scripts/deploy-platform.ts --network <net>")
        raise typer.Exit(1)

    try:
        with open(file) as f:
            deployments = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]❌ Failed to read deployments file: {e}[/red]")
        raise typer.Exit(1)

    missing = [k for k in _REQUIRED_DEPLOYMENT_KEYS if k not in deployments]
    if missing:
        console.print(f"[red]❌ Deployments file is missing keys: {', '.join(missing)}[/red]")
        raise typer.Exit(1)
    bad = [k for k in _DEPLOYMENTS_TO_DIN_INFO if k in deployments and not is_ethereum_address(deployments[k])]
    if bad:
        console.print(f"[red]❌ Not a valid Ethereum address for: {', '.join(bad)}[/red]")
        raise typer.Exit(1)

    din_info = load_din_info()
    entry = din_info.setdefault(effective_network, {})
    for src_key, dst_key in _DEPLOYMENTS_TO_DIN_INFO.items():
        if src_key in deployments:
            entry[dst_key] = deployments[src_key]
    save_din_info(din_info)

    console.print(f"[green]✅ Imported platform deployments into din_info.json[/green] (network: {effective_network})")
    console.print(f"[cyan]Source:[/cyan] {file}")
    console.print(f"[cyan]Coordinator:[/cyan] {entry.get('coordinator')}")
    console.print(f"[green]DIN Token:[/green] {entry.get('token')}")
    console.print(f"[yellow]Staking Contract:[/yellow] {entry.get('stake')}")
    console.print(f"[magenta]Registry:[/magenta] {entry.get('registry')}")
    if entry.get("proxy_admin"):
        console.print(f"[magenta]Proxy Admin:[/magenta] {entry.get('proxy_admin')}")


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

    active_name = ctx.obj.resolved_wallet_name
    wallet_path, wallet_exists = resolve_wallet_path(active_name)
    if not wallet_exists:
        console.print(f"[red]❌ No wallet found for '{active_name}' at {wallet_path}.[/red]\n  Run 'dincli system connect-wallet' to create one.")
    else:
        console.print(f"[green]✅ Wallet exists for '{active_name}': {wallet_path}[/green]")

    accounts = list_accounts(active_name)
    if len(accounts) > 1:
        console.print("[cyan]Named wallets:[/cyan]")
        for e in accounts:
            marker = "[green](active)[/green]" if e["active"] else ""
            console.print(f"  [bold]{e['name']}[/bold] → {e['address']}{marker}")

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

    ipfs_config = resolve_ipfs_config()
    console.print(f"[green]✅ Active IPFS provider: {ipfs_config.provider}[/green]")

    if ipfs_config.provider == "env":
        if ipfs_config.api_url_add is None:
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
            console.print(f"[green]✅ IPFS API ADD URL found in environment variable: IPFS_API_URL_ADD in {cwd}/.env file with value: {ipfs_config.api_url_add}[/green]")

        if ipfs_config.api_url_retrieve is None:
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
            console.print(f"[green]✅ IPFS API RETRIEVE URL found in environment variable: IPFS_API_URL_RETRIEVE in {cwd}/.env file with value: {ipfs_config.api_url_retrieve}[/green]")
    elif ipfs_config.provider == "filebase":
        if ipfs_config.api_key is None:
            console.print("[red]❌ Filebase API key not found in dincli config. Run `dincli system configure-ipfs --provider filebase --api-key <token>`.[/red]")
        else:
            console.print("[green]✅ Filebase API key found in dincli config.[/green]")
    elif ipfs_config.provider == "custom":
        if ipfs_config.service_path is None:
            console.print("[red]❌ Custom IPFS service path not found in dincli config. Run `dincli system configure-ipfs --provider custom --service-path <path>`.[/red]")
        elif not ipfs_config.service_path.exists():
            console.print(f"[red]❌ Custom IPFS service path does not exist: {ipfs_config.service_path}[/red]")
        else:
            console.print(f"[green]✅ Custom IPFS service found at: {ipfs_config.service_path}[/green]")
    else:
        console.print(f"[red]❌ Unsupported IPFS provider in config: {ipfs_config.provider}[/red]")
    
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
    start_client_index: int = typer.Option(2, "--start-client-index", "-sci", help="Start client index of ETH_PRIVATE_KEY_i"),
):
    """
    Download MNIST and distribute it across N clients (IID split).
    """

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    if (not task_coordinator_address or not task) and not model_id:
        if not task_coordinator_address:
            task_coordinator_address = resolve_task_coordinator_address(
                effective_network, None, console, exit_on_failure=True
            )

    if model_id:
        base_dir = ctx.obj.get_model_base_dir(model_id)
    elif task_coordinator_address:
        base_dir = Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address
    else:
        console.print("[red]❌ Model ID or task coordinator address is required.[/red]")
        raise typer.Exit(1)


    if not test_train and not clients:
        console.print("[red]❌ Both train/test flag and clients flag not found in cli argument.[/red]")
        raise typer.Exit(1)

    if clients and num_clients <= 0:
        console.print("[red]Number of clients must be >= 1[/red]")
        raise typer.Exit(1)
    if clients and num_clients > 10:
        console.print("[red]Number of clients must be < 10[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Using base dir:[/cyan] {base_dir}")

    dataset_dir = base_dir / "dataset"
    clients_dir = dataset_dir / "clients"

    accounts_list = []
    if clients:
        demo_mode = get_config("demo_mode")
        if not start_client_index:
            start_client_index = 2

        for i in range(num_clients):
            if demo_mode:
                private_key = get_demo_private_key(i + start_client_index)
            else:
                private_key = get_env_key("ETH_PRIVATE_KEY_" + str(i + start_client_index))

            acct = Account.from_key(private_key)
            accounts_list.append(acct.address)


    service_entry = load_cid_services()["services"]["distribute_mnist"]
    service_path = base_dir / service_entry["path"].lstrip("/")
    requirements_path = base_dir / "requirements" / "distribute_mnist.txt"

    ctx.obj.ensure_file_exists(service_path, service_entry["ipfs"], "distribute_mnist service")
    ctx.obj.ensure_file_exists(requirements_path, service_entry["requirements"], "distribute_mnist requirements")

    _confirm_or_exit(
        f"Have you installed the required dependencies via `pip install -r {requirements_path}`?",
        f"Please install the required dependencies first: pip install -r {requirements_path}",
        console,
    )

    # -----------------------------------------------------------------------
    # Scenario A – save raw train/test datasets
    # -----------------------------------------------------------------------
    if test_train:
        console.print("[cyan]Processing Train/Test Datasets...[/cyan]")
        try:
            save_test_train_fn = ctx.obj.load_custom_fn(service_path, "save_test_train_datasets")
            save_test_train_fn(base_dir=base_dir)
        except Exception as e:
            console.print(f"[bold red]Error saving train/test datasets: {e}[/bold red]")
            raise typer.Exit(1)
        console.print(f"[green]Processed Train/Test Datasets saved successfully to {dataset_dir}![/green]")

    # -----------------------------------------------------------------------
    # Scenario B – distribute data to clients
    # -----------------------------------------------------------------------
    if clients:
        console.print("[cyan]Processing Client Datasets... This may take a while.[/cyan]")
        try:
            distribute_to_clients_fn = ctx.obj.load_custom_fn(service_path, "distribute_to_clients")
            result = distribute_to_clients_fn(
                base_dir=base_dir,
                accounts_list=accounts_list,
                num_clients=num_clients,
                seed=seed,
            )
        except Exception as e:
            console.print(f"[bold red]Error distributing MNIST to clients: {e}[/bold red]")
            raise typer.Exit(1)
        for item in result["client_datasets"]:
            console.print(
                f"[green]Saved client_{item['client_index']} ({item['num_samples']} samples) → {item['path']}[/green]"
            )
        console.print(f"[bold green]✅ MNIST distributed to {num_clients} clients under {clients_dir}[/bold green]")

@app.command("dump-abi")
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
    provider: str = typer.Option(None, "--provider", "-p", help="IPFS provider [env, filebase, custom]"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key for the selected provider"),
    api_secret: str = typer.Option(None, "--api-secret", "-s", help="Optional API secret for the selected provider"),
    service_path: Path = typer.Option(None, "--service-path", help="Python module implementing upload_to_ipfs and retrieve_from_ipfs for the custom provider"),
   ):

    config = load_config()
    configured_provider = normalize_ipfs_provider(config.get("ipfs_provider"))

    if provider is None and api_key is None and api_secret is None and service_path is None:
        active = resolve_ipfs_config()
        ctx.obj.console.print(f"[green]Active IPFS provider:[/green] {active.provider}")
        if active.provider == "env":
            ctx.obj.console.print("[cyan]Source:[/cyan] `IPFS_API_URL_ADD` and `IPFS_API_URL_RETRIEVE` from the current shell or .env")
        elif active.provider == "filebase":
            ctx.obj.console.print("[cyan]Source:[/cyan] Filebase token stored in dincli config")
        elif active.provider == "custom":
            ctx.obj.console.print(f"[cyan]Source:[/cyan] {active.service_path}")
        raise typer.Exit()

    selected_provider = normalize_ipfs_provider(provider) if provider is not None else configured_provider
    if selected_provider not in SUPPORTED_IPFS_PROVIDERS:
        ctx.obj.console.print(f"[red]❌ Invalid provider. Use {', '.join(SUPPORTED_IPFS_PROVIDERS)}.[/red]")
        raise typer.Exit(1)

    resolved_existing_api_key = _clean_optional_string(config.get(f"ipfs_api_key_{selected_provider}"))
    if not resolved_existing_api_key and selected_provider == "filebase":
        resolved_existing_api_key = _clean_optional_string(config.get("ipfs_api_key"))
    existing_service_path = config.get("ipfs_service_path")

    if selected_provider == "filebase" and not (api_key or resolved_existing_api_key):
        ctx.obj.console.print(f"[red]❌ Please specify an API key for the {selected_provider} provider.[/red]")
        raise typer.Exit(1)
    if selected_provider == "custom" and not (service_path or existing_service_path):
        ctx.obj.console.print("[red]❌ Please specify --service-path for the custom provider.[/red]")
        raise typer.Exit(1)

    config["ipfs_provider"] = selected_provider

    if api_key is not None:
        config[f"ipfs_api_key_{selected_provider}"] = api_key.strip()
        if selected_provider == "filebase":
            config["ipfs_api_key"] = api_key.strip()
    if api_secret is not None:
        config[f"ipfs_api_secret_{selected_provider}"] = api_secret.strip()
        if selected_provider == "filebase":
            config["ipfs_api_secret"] = api_secret.strip()
    if service_path is not None:
        config["ipfs_service_path"] = str(service_path.expanduser().resolve())

    save_config(config)

    ctx.obj.console.print(f"[green] ✅ Current IPFS provider: {selected_provider}[/green]")
    if selected_provider == "env":
        ctx.obj.console.print("[cyan] IPFS Runtime source:[/cyan] `IPFS_API_URL_ADD` and `IPFS_API_URL_RETRIEVE` from the current shell or .env")
    elif selected_provider == "filebase":
        ctx.obj.console.print("[cyan]Runtime source:[/cyan] Filebase RPC API token stored in dincli config")
    elif selected_provider == "custom":
        ctx.obj.console.print(f"[cyan]Runtime source:[/cyan] {config['ipfs_service_path']}")
   
@app.command("get-registry-fee")
def get_registry_fee(
    ctx: typer.Context,
    fee_type: str = typer.Option(None, "--fee-type", "-f", help="Type of fee to retrieve [model-registry, manifest-update]"),
    model_type: str = typer.Option(None, "--model-type", "-m", help="Type of model [proprietary, open-source]"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    if fee_type == "model-registry" or fee_type is None:
        if model_type == "proprietary" or model_type is None:
            proprietary_fee = DINModelRegistry_Contract.functions.proprietaryFee().call()
            wei_to_eth = w3.from_wei(proprietary_fee, 'ether')
            console.print(f"[bold green]Proprietary fee for model-registry: {wei_to_eth} ETH[/bold green]")
        if model_type == "open-source" or model_type is None:
            open_source_fee = DINModelRegistry_Contract.functions.openSourceFee().call()
            wei_to_eth = w3.from_wei(open_source_fee, 'ether')
            console.print(f"[bold green]Open-source fee for model-registry: {wei_to_eth} ETH[/bold green]")
    if fee_type == "manifest-update" or fee_type is None:
        if model_type == "proprietary" or model_type is None:
            proprietary_update_fee = DINModelRegistry_Contract.functions.proprietaryUpdateFee().call()
            wei_to_eth = w3.from_wei(proprietary_update_fee, 'ether')
            console.print(f"[bold green]Proprietary update fee for manifest-update: {wei_to_eth} ETH[/bold green]")
        if model_type == "open-source" or model_type is None:
            open_source_update_fee = DINModelRegistry_Contract.functions.openSourceUpdateFee().call()
            wei_to_eth = w3.from_wei(open_source_update_fee, 'ether')
            console.print(f"[bold green]Open-source update fee for manifest-update: {wei_to_eth} ETH[/bold green]")





    
    
