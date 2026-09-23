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
> To use your own wallet from your `.env` file, ensure demo mode is disabled first
> (`register-wallet` refuses to run while it's on):
> ```bash
> dincli system configure-demo --mode no
> ```
> With demo mode on, use `dincli system connect-demo-wallet --account <n>` for a
> well-known Hardhat dev account instead — see [Wallet Management](#wallet-management).

---

### Wallet Management

> **⚠️ Local development only.** The `ETH_PRIVATE_KEY_<n>` pattern stores raw
> private keys in plaintext. For **production validator nodes**, use the
> encrypted keystore — see [wallet-setup.md](./guides/wallet-setup.md).

Demo accounts (well-known Hardhat dev keys) are fully separate from your own real
wallets: `register-wallet` / `connect-wallet` only ever touch real key material, and
`connect-demo-wallet` is the only command that touches a demo account. Each refuses if
you point it at the wrong kind of wallet, so there's no way to end up signing with a demo
key by accident.

**Register a wallet** — store your own real key material under a name (prompts for the
private key if no source option is given):

```bash
dincli system register-wallet
```

Options:
- `--key-file <path>` — Import a private key from a file (dev/testing only).
- `--account <index>` — Register an account by index. Reads `ETH_PRIVATE_KEY_<index>` from your `.env` file.
- `--keystore <path>` — Import a standard Ethereum JSON keystore with passphrase (production).
- `--name <name>` — Label for the saved keystore (default `default`).
- `--connect` — Also make the wallet active after registering.
- `--yes` — Skip the confirmation prompt when overwriting an existing named wallet.

> [!IMPORTANT]
> `register-wallet` refuses to run while demo mode is on (`dincli system init` defaults
> it off). Disable it first if you'd turned it on:
> ```bash
> dincli system configure-demo --mode no
> ```

**Connect (switch) the active wallet** — flips the persistent pointer between registered wallets; never touches key material and never prompts:

```bash
dincli system connect-wallet <name>
```

The active wallet is resolved per invocation with this priority: global `--wallet <name>` flag → `DIN_WALLET_NAME` env var → the config value set by `connect-wallet` → `default`. (`set-wallet` is a deprecated alias of `connect-wallet`.) Refuses to activate a demo wallet — use `connect-demo-wallet` for those.

**Connect a demo wallet** — local Hardhat testing only, with the well-known dev keys. One-shot: creates (or recreates) the named wallet from a dev-account index and connects it, all in one command — no separate registration step:

```bash
dincli system connect-demo-wallet --account 0            # creates+connects 'demo-default'
dincli system connect-demo-wallet bob --account 1         # creates+connects as 'bob'
dincli system connect-demo-wallet bob                     # reconnect an already-connected demo wallet by name
```

Requires demo mode on (`dincli system configure-demo --mode yes`) and refuses to connect a
real wallet — use `connect-wallet` for those. Stores the key in **plaintext**; these keys
are publicly known, never fund this address on a real network.

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

