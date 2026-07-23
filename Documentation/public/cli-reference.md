# DIN CLI — Common Reference

The DIN CLI (`dincli`) is the primary command-line interface for interacting with the Decentralized Intelligence Network. It supports all participant roles: Clients, Auditors, Model Owners, Aggregators, and DAO administrators.

---

## Global Options

These flags can be prepended to any command:

| Option | Description |
|---|---|
| `--network <network>` | Override the default network (`local`, `sepolia_devnet`, `sepolia_op_devnet`, `mainnet`) |
| `--help` | Display help for any command |

**Check CLI version:**

```bash
dincli --version
# or
dincli -v
```

---

## System Commands

The `system` command group manages configuration, wallet connections, and general utilities.

### Initialization & Configuration

**Initialize the CLI** — creates the `config` and `cache` directories:

```bash
dincli system init
```

**Set the default network:** (`local`, `sepolia_devnet`, `sepolia_op_devnet`, `mainnet`)

```bash
dincli system configure-network --network <network>
```

> [!NOTE]
> Use `sepolia_op_devnet` for devnet. Testnet and Mainnet support will be rolled out in a future release.

**Set the log level** (`debug`, `info`, `warning`, `error`, `critical`):

```bash
dincli system configure-logging --level <level>
```

**Toggle demo mode:**

```bash
dincli system configure-demo --mode <yes|no>
```

> [!WARNING]
> Demo mode stores wallets in plaintext. **Do not use with real funds.**

> [!NOTE]
> To use your own wallet from .env file ensure demo mode is disabled first:
> ```bash
> dincli system configure-demo --mode no
> ```

---

### Wallet Management

> **⚠️ Local development only.** The `ETH_PRIVATE_KEY_<n>` pattern stores raw
> private keys in plaintext. For **production validator nodes**, use the
> encrypted keystore — see [wallet-setup.md](./guides/wallet-setup.md).

**Register a wallet** — store key material under a name (prompts for the private key if no source option is given):

```bash
dincli system register-wallet
```

Options:
- `--key-file <path>` — Import a private key from a file (dev/testing only).
- `--account <index>` — Register an account by index (dev/testing only). Reads `ETH_PRIVATE_KEY_<index>` from your `.env` file (or the bundled Hardhat dev keys in demo mode).
- `--keystore <path>` — Import a standard Ethereum JSON keystore with passphrase (production).
- `--name <name>` — Label for the saved keystore (default `default`).
- `--connect` — Also make the wallet active after registering.
- `--yes` — Skip the confirmation prompt when overwriting an existing named wallet.

**Connect (switch) the active wallet** — flips the persistent pointer between registered wallets; never touches key material and never prompts:

```bash
dincli system connect-wallet <name>
```

The active wallet is resolved per invocation with this priority: global `--wallet <name>` flag → `DIN_WALLET_NAME` env var → the config value set by `connect-wallet` → `default`. (`set-wallet` is a deprecated alias of `connect-wallet`.)

> [!IMPORTANT]
> To use your own wallet (non-demo mode), ensure demo mode is disabled first:
> ```bash
> dincli system configure-demo --mode no
> ```

**Read wallet info** — display the connected wallet address:

```bash
dincli system read-wallet
```
> In demo mode, the private key is also displayed.


**List all named accounts:**

```bash
dincli system list-accounts
```

---

### Utilities

**Check balances** — show ETH for the connected wallet:

```bash
dincli system --eth-balance
```



**Show contract addresses** — display the deployed coordinator, token, stake, and registry addresses for the current network:

```bash
dincli system din-info
```

**Reset CLI state** — clears all configuration and cache data. Use `--force` to bypass the confirmation prompt:

```bash
dincli system reset-all [--force]
```

**Show installation path:**

```bash
dincli system where
```

**Get cache dir path:**

```bash
dincli system get-cache-dir
```

**Get config dir path:**

```bash
dincli system get-config-dir
```

