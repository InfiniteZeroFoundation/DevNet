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

>[!NOTE]
> Recommended python version is 3.12.3

---

## 2. Install `dincli`

### Option A — Install from a Local Wheel

```bash
# Download the wheel file
wget https://github.com/InfiniteZeroFoundation/DevNet/raw/refs/heads/main/dist/dincli-0.1.0-py3-none-any.whl
# Install it
pip install dincli-0.1.0-py3-none-any.whl
```

### Option B — Install Directly from GitHub

```bash
pip install git+https://github.com/InfiniteZeroFoundation/devnet.git@main#subdirectory=dist
```

> for any missing dependency please install it using pip. Please see a complete dependency list in [requirements.txt](../cache_model_0/requirements.txt)

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

# Set the default network  [local | sepolia_devnet | sepolia_op_devnet | mainnet]
dincli system configure-network --network sepolia_op_devnet

> [!NOTE]
> Use `sepolia_op_devnet` for devnet. Testnet and Mainnet support will be rolled out in a future release.

# Set the log level  [debug | info | warning | error | critical]
dincli system configure-logging --level info
```


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

# Sepolia - Optimism Devnet
# must set this for devnet usage
SEPOLIA_OP_DEVNET_RPC_URL=https://optimism-sepolia.infura.io/v3/<auth_token>


# Local network (e.g. a Hardhat node)
LOCAL_RPC_URL=http://127.0.0.1:8545

```

### Private Key

Store private keys using the pattern `ETH_PRIVATE_KEY_<account_index>`. You can define as many accounts as needed by incrementing the index.

```bash
ETH_PRIVATE_KEY_0 = 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
ETH_PRIVATE_KEY_1 = 0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
```

Connect a stored account with:

```bash
dincli system connect-wallet --account 0
```

> [!IMPORTANT]
> To use `dincli` with your own wallet (Non-Demo Mode from .env file), you must first disable demo mode:

```bash
dincli system configure-demo --mode no
```

---

## 6. IPFS Setup

`dincli` requires an IPFS provider to store and retrieve model data. Choose one of the options below.


### Option A — Filebase (Managed IPFS)

Obtain an API key from [Filebase](https://filebase.com/) and configure it:

```bash
dincli system configure-ipfs --provider filebase --api-key <your_api_key>
```

> [!NOTE]
> Please create a bucket on Filebase and get bucket's IPFS RPC API token from [Filebase Console](https://console.filebase.com/keys). Use that as `your_api_key` in the command above.
> IPFS RPC API token dashboard is located at bottom of the page.

### Option B — Custom IPFS Provider

You may use `ipfs daemon` or any other provider. ust  add the following in `.env` file at root of your project folder.

```bash
IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0/add
IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0/cat/
```
> Ensure your IPFS provider is configured to pin uploaded artifacts. If using a local node, garbage collection must be managed to prevent the loss of registered artifacts. 

also configure IPFS provider in dincli using `dincli system configure-ipfs` command.

```bash
dincli system configure-ipfs --provider custom
```