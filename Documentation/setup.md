# DIN CLI — Setup Guide

This guide walks you through the complete setup process for the DIN CLI (`dincli`) from installation to first use.

---

## 1. Virtual Environment

It is recommended to install `dincli` inside a Python virtual environment.

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

---

## 2. Install `dincli`

### Option A — Install from a Local Wheel

```bash
# Download the wheel file
wget https://github.com/InfiniteZeroFoundation/devnet/raw/dincli/dist/dincli-0.1.0-py3-none-any.whl

# Install it
pip install dincli-0.1.0-py3-none-any.whl
```

### Option B — Install Directly from GitHub

```bash
pip install git+https://github.com/InfiniteZeroFoundation/devnet.git@dincli#subdirectory=dist
```

### Verify Installation

```bash
dincli --version
# or
dincli system welcome
```

---

## 3. Initialize the CLI

```bash
dincli system init
```

Creates the required `config` and `cache` directories and generates an empty configuration file.

---

## 4. Configuration

```bash
# Disable demo mode to use your own wallet and private keys
dincli system configure-demo --mode no

# Set the default network  [local | sepolia_devnet | sepolia_testnet | mainnet]
dincli system configure-network --network sepolia_devnet

# Set the log level  [debug | info | warning | error | critical]
dincli system configure-logging --level info
```

> [!NOTE]
> Use `sepolia_devnet` for testing. Mainnet support will be rolled out in a future release.

---

## 5. Environment Variables (`.env`)

Create a `.env` file in the root directory of your project and populate it with the variables below.

### Wallet Password

The DIN CLI encrypts your private key using this password.

```bash
DIN_WALLET_PASSWORD=your_secure_password
```

### RPC URL

The CLI needs an RPC endpoint to communicate with the blockchain. The variable name follows the pattern `[NETWORK]_RPC_URL` (uppercase).

You can obtain an RPC URL from providers such as [Alchemy](https://www.alchemy.com/), [Infura](https://infura.io/), or [Ankr](https://www.ankr.com/).

```bash
# Local network (e.g. a Hardhat node)
LOCAL_RPC_URL=http://127.0.0.1:8545

# Sepolia Devnet
SEPOLIA_DEVNET_RPC_URL=https://sepolia.infura.io/v3/<auth_token>

# Sepolia Testnet
SEPOLIA_TESTNET_RPC_URL=https://sepolia.infura.io/v3/<auth_token>

# Mainnet
MAINNET_RPC_URL=https://mainnet.infura.io/v3/<auth_token>
```

### Private Key

Store private keys using the pattern `ETH_PRIVATE_KEY_<account_index>`. You can define as many accounts as needed by incrementing the index.

```bash
ETH_PRIVATE_KEY_0=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
ETH_PRIVATE_KEY_1=0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
```

Connect a stored account with:

```bash
dincli system connect-wallet --account 0
```

> [!IMPORTANT]
> To use `dincli` with your own wallet (Non-Demo Mode), you must first disable demo mode:

```bash
dincli system configure-demo --mode no
```

---

## 6. IPFS Setup

`dincli` requires an IPFS provider to store and retrieve model data. Choose one of the options below.

### Option A — Local IPFS Node

Install the [IPFS CLI](https://docs.ipfs.tech/install/) and start the daemon:

```bash
ipfs daemon
```

Then add the following to your `.env` file:

```bash
IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0/add
IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0/cat/
```

> [!IMPORTANT]
> Your local IPFS node must be running continuously to keep your data available on the network.

### Option B — Filebase (Managed IPFS)

Obtain an API key from [Filebase](https://filebase.com/) and configure it:

```bash
dincli system configure-ipfs --provider filebase --api-key <your_api_key>
```

### Option C — Custom IPFS Provider

dincli system configure-ipfs --provider custom --api-key <your_api_key> --api-secret <your_api_secret> --ipfs-service-path <your_ipfs_service_path>
