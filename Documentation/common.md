# DIN CLI — Common Reference

The DIN CLI (`dincli`) is the primary command-line interface for interacting with the Decentralized Intelligence Network. It supports all participant roles: Clients, Auditors, Model Owners, Aggregators, and DAO administrators.

---

## Global Options

These flags can be prepended to any command:

| Option | Description |
|---|---|
| `--network <network>` | Override the default network (`local`, `sepolia_devnet`, `sepolia_testnet`, `mainnet`) |
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

**Set the default network:** (`local`, `sepolia_devnet`, `sepolia_testnet`, `mainnet`)

```bash
dincli system configure-network --network <network>
```


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

---

### Wallet Management

**Connect a wallet:**

```bash
dincli system connect-wallet
```

Options:
- `--key-file <path>` — Import a private key from a file.
- `--account <index>` — Connect an account by index. Reads `ETH_PRIVATE_KEY_<index>` from your `.env` file.

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

---

### Utilities

**Check balances** — show ETH and USDT for the connected wallet:

```bash
dincli system --eth-balance --usdt-balance
```

**Buy USDT** (testnets / local only) — swap ETH for USDT via the Uniswap router:

```bash
dincli system buy-usdt <usdt_amount>
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
