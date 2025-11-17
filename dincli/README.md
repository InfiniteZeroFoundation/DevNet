
# DIN CLI structured:

```
dincli <role> <command> [options]
```

Where `<role>` ∈ { `model-owner`, `validator`, `auditor`, `aggregator`, `dindao` }

That’s the **Typer multi-app pattern**, which allows subcommands for each stakeholder role, e.g.:

```
dincli model-owner train
dincli validator onboard
dincli auditor verify
dincli aggregator aggregate
dincli dindao status
```

---

### ✅ Here’s how to implement it cleanly

#### **1. Modify `fastapi/pyapp/cli/main.py`**

```python
import typer
from rich import print

# Import role-specific subcommands
from aggregator import app as aggregator_app
from auditor import app as auditor_app
from dindao import app as dindao_app
from model_owner import app as model_owner_app

app = typer.Typer(help="DIN Command Line Interface (DIN CLI)")

# Add subcommands for roles
app.add_typer(model_owner_app, name="model-owner")
app.add_typer(aggregator_app, name="aggregator")
app.add_typer(auditor_app, name="auditor")
app.add_typer(dindao_app, name="dindao")

@app.command()
def version():
    """Show current DIN CLI version."""
    print("[bold cyan]DIN CLI[/bold cyan] version 0.1.0")

if __name__ == "__main__":
    app()
```

---

#### **2. Example of `model_owner.py`**

```python
import typer
from rich import print

app = typer.Typer(help="Commands for Model Owners in DIN.")

@app.command()
def train(dataset_path: str, dp_mode: str = "disabled"):
    """
    Train a local model with optional Differential Privacy (DP) mode.
    """
    print(f"[green]Training model with dataset:[/green] {dataset_path}")
    print(f"[blue]DP Mode:[/blue] {dp_mode}")
    # TODO: integrate fastapi/pyapp/services/client_services.py logic here

@app.command()
def upload(model_path: str):
    """
    Upload model to IPFS and register with DIN network.
    """
    print(f"Uploading model from path: {model_path}")
    # TODO: integrate IPFS + smart contract registration logic
```

---

#### **3. Example of `validator.py`**

You can create this new file later, but here’s the template:

```python
import typer
from rich import print

app = typer.Typer(help="Commands for Validators in DIN.")

@app.command()
def onboard():
    """Register as a validator and stake tokens."""
    print("[cyan]Initializing validator onboarding...[/cyan]")
    # TODO: call smart contract (DinValidatorStake.sol) for staking

@app.command()
def status():
    """Check validator staking status."""
    print("Fetching staking and validator status...")
    # TODO: query on-chain state and display
```

---

#### **4. Update `pyproject.toml`**

Your CLI entry point doesn’t change — still:

```toml
[project.scripts]
dincli = "main:app"
```

---

#### **5. Test it**

Reinstall the CLI in editable mode:

```bash
pip install -e .
```

Now test your role-aware CLI:

```bash
dincli --help
dincli model-owner --help
dincli model-owner train ./Dataset/clients/clientDataset_1.pt --dp-mode afterTraining
dincli validator onboard
```

---

✅ **Result Example:**

```
Usage: dincli [OPTIONS] COMMAND [ARGS]...

DIN Command Line Interface (DIN CLI)

Commands:
  version        Show current DIN CLI version.
  model-owner    Commands for Model Owners in DIN.
  validator      Commands for Validators in DIN.
  auditor        Commands for Auditors in DIN.
  aggregator     Commands for Aggregators in DIN.
  dindao         Commands for DIN DAO governance.
```

---

Would you like me to help you define **role-specific command sets** (like what each role can do from CLI: e.g., `train`, `submit`, `audit`, `stake`, etc.) next?
That will make your `dincli` a full operational command-line interface for the devnet phase.
