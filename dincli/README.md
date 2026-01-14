
# DIN CLI structured:

```
dincli <role> <command> [options] --network <network>
```

Where `<role>` ∈ { `model-owner`, `auditor`, `aggregator`, `client`, `dindao` }

where `<network>` ∈ { `local`, `sepolia_devnet`, `sepolia_testnet`, `mainnet` }

That’s the **Typer multi-app pattern**, which allows subcommands for each stakeholder role, e.g.:

```
dincli model-owner train
dincli validator onboard
dincli auditor verify
dincli aggregator aggregate
dincli dindao status
```

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
