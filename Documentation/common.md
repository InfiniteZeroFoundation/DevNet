# DIN CLI Common Documentation

The DIN CLI (`dincli`) is the primary tool for interacting with the Decentralized Intelligence Network. It supports various roles including Clients, Auditors, Model Owners, and Aggregators.

## Global Options

These options can be used with any command:

- `--network <network>`: Specify the network to use (e.g., `local`, `sepolia_devnet`, `sepolia_testnet`, `mainnet`). Overrides the configured default.
- `--help`: Show help message for a command.

version command:

```bash
dincli --version

or 

dincli -v
```

## System Commands

The `system` command group manages configuration, wallet connection, and general utilities.

### Initialization & Configuration

- **Initialize CLI**:
  ```bash
  dincli system init
  ```
  Creates the necessary `config` and `cache` directories.

- **Configure Network**:
  ```bash
  dincli system configure-network --network <network>
  ```
  Sets the default network (e.g., `local`).

- **Configure Logging**:
  ```bash
  dincli system configure-logging --level <level>
  ```
  Sets the log level (`debug`, `info`, `warning`, `error`, `critical`).

- **Configure Demo Mode**:
  ```bash
  dincli system configure-demo --mode <yes|no>
  ```
  Enables or disables demo mode. **Warning**: Demo mode stores wallets in plaintext. Do not use with real funds.

### Wallet Management

- **Connect Wallet**:
  ```bash
  dincli system connect-wallet
  ```
  Interactive prompt to import your private key.
  
  Options:
  - `--key-file <path>`: Import from a key file.
  - `--account <index>`: (Demo/Hardhat only in demo m) Connect a dev account by index (0-9).

- **Read Wallet Info**:
  ```bash
  dincli system read-wallet
  ```
  Displays current wallet address (and private key if in demo mode).

- **Utilities**:

- **Check Balances**:
  ```bash
  dincli system --eth-balance --usdt-balance
  ```
  Shows ETH and USDT balances for the connected wallet.

- **Buy USDT** (Testnets/Local):
  ```bash
  dincli system buy-usdt <usdt-amount>
  ```
  Swaps ETH for USDT via Uniswap router.

- **Show Contract Info**:
  ```bash
  dincli system din-info
  ```
  Displays deployed contract addresses for the current network (Coordinator, Token, Stake, Registry).

- **Reset CLI State**:
  ```bash
  dincli system reset-all
  ```
  Clears configuration and cache. Use `--force` to skip confirmation.

- **Check Installation Location**:
  ```bash
  dincli system where
  ```
  Prints the installation path of `dincli`.
