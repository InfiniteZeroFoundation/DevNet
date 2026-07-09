import time

import typer
from web3 import Web3

from dincli.cli.utils import MIN_STAKE, build_and_send_tx

app = typer.Typer(help="Commands for DIN Token in DIN.")


def buy_dintokens(
    ctx: typer.Context,
    amount: float,
    name: str = "Account"
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    din_token_contract = ctx.obj.get_deployed_din_token_contract()
    din_coordinator_contract = ctx.obj.get_deployed_din_coordinator_contract()

    console.print(
        f"[bold green] {name} ETH balance:[/bold green] ",
        Web3.from_wei(w3.eth.get_balance(account.address), "ether"),
    )
    console.print(
        f"[bold green] {name} DINToken balance:[/bold green] ",
        Web3.from_wei(din_token_contract.functions.balanceOf(account.address).call(), "ether"),
    )
    console.print(f"[bold green]Buying DINTokens... for {amount} ETH[/bold green]")

    try:
        tx_receipt = build_and_send_tx(
            ctx,
            din_coordinator_contract.functions.depositAndMint(),
            f"Buying DINTokens... for {amount} ETH",
            "DINTokens bought.",
            "Transaction failed! Could not buy DINTokens",
            tx_params={"value": w3.to_wei(amount, "ether")},
            exit_on_failure=False,
        )
        console.print(f"[bold green]✓ DINTokens bought at:[/bold green] {tx_receipt.transactionHash.hex()}")
        console.print(
            f"[bold green] {name} DINToken balance:[/bold green] ",
            Web3.from_wei(din_token_contract.functions.balanceOf(account.address).call(), "ether"),
        )
    except Exception as e:
        console.print(f"[bold red]✗ Error buying DINTokens: {e}[/bold red]")


def stake_dintokens(
    ctx: typer.Context,
    amount: int,
    name: str = "Account"
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    din_token_contract = ctx.obj.get_deployed_din_token_contract()
    din_stake_contract = ctx.obj.get_deployed_din_stake_contract()
    

    din_token_balance = din_token_contract.functions.balanceOf(account.address).call()

    stake_amount = Web3.to_wei(amount, "ether")

    console.print(
        "[bold green]ETH balance:[/bold green] ",
        Web3.from_wei(w3.eth.get_balance(account.address), "ether"),
    )
    console.print(
        "[bold green]DINToken balance:[/bold green] ",
        Web3.from_wei(din_token_balance, "ether"),
    )

    if stake_amount < MIN_STAKE:
        console.print(
            f"[bold red]✗ Could not stake DINTokens. Minimum stake is {Web3.from_wei(MIN_STAKE, "ether")} DINTokens. But you intent to stake {amount} DINTokens.[/bold red]"
        )
        raise typer.Exit(1)

    if din_token_balance < stake_amount:
        console.print("[bold red]✗ Could not stake DINTokens. Not enough DINTokens.[/bold red]")
        raise typer.Exit(1)

    console.print("[bold green]✓ Enough DINTokens to stake.[/bold green]")
    console.print(f"[bold green]Staking {amount} DINTokens...[/bold green]")

    try:
        build_and_send_tx(
            ctx,
            din_token_contract.functions.approve(din_stake_contract.address, stake_amount),
            "Approving DINTokens for staking",
            "DINTokens approved for staking.",
            "Could not approve DINTokens for staking.",
            exit_on_failure=True,
        )

        time.sleep(5)

        build_and_send_tx(
            ctx,
            din_stake_contract.functions.stake(stake_amount),
            "Staking DINTokens",
            "DINTokens staked.",
            "Could not stake DINTokens.",
            exit_on_failure=True,
        )
    except Exception as e:
        console.print(f"[bold red]✗ Error staking DINTokens: {e}[/bold red]")


def read_dintoken_stake(ctx: typer.Context, name ="Account"):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    din_stake_contract = ctx.obj.get_deployed_din_stake_contract()

    stake = din_stake_contract.functions.getStake(account.address).call()
    console.print(f"[bold green] {name}'s DIN token stake:[/bold green] ", Web3.from_wei(stake, "ether"), "DinTokens")


@app.command(help="Buy DINTokens where amount is ETH to exchange for DINTokens")
def buy(
    ctx: typer.Context,
    amount: float = typer.Argument(..., help="Amount of ETH to exchange for DINTokens"),
):
    buy_dintokens(ctx, amount)


@app.command(help="Stake DINTokens")
def stake(
    ctx: typer.Context,
    amount: float = typer.Argument(..., help="Amount of DINTokens to stake"),
):
    stake_dintokens(ctx, amount)


@app.command("read-stake", help="Check stake")
def read_stake(ctx: typer.Context):
    read_dintoken_stake(ctx)
