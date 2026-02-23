# DIN Setup Guide

This guide walks through the complete setup process for a DIN environment

# virtual environment setup

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

## install dincli

### Option 1: install from local file

```bash
# Download the wheel
wget https://github.com/InfiniteZeroFoundation/DINv1MVC/raw/dincli/dist/dincli-0.1.0-py3-none-any.whl

# Install from local file
pip install dincli-0.1.0-py3-none-any.whl
```

### Option 2: install from GitHub Releases

```bash
# Check if package is in GitHub Releases
pip install git+https://github.com/InfiniteZeroFoundation/DINv1MVC.git@dincli#subdirectory=dist
```

## verify installation

```bash
dincli --version
```

or 

```bash
dincli system welcome
```

## Initialize DIN CLI

```bash
# Initialize DIN CLI, create config/cache directories and an empty config file.
dincli system init
```

## config setup

```bash
# Configure demo mode to no to use your own wallet with your own private keys
dincli system configure-demo --mode no

# Configure network to [local|sepolia_devnet|sepolia_testnet|mainnet]
# use sepolia_devnet for testing
# will roll out to sepolia_testnet and then mainnet later
dincli system configure-network --network sepolia_devnet

# Configure logging level to [debug|info|warning|error|critical]
dincli system configure-logging --level info
```

## .env setup

In the root directory of the project, create a .env file:


### DIN WALLET PASSWORD

DIN wallet password to encrypt your private key

```bash
# .env
DIN_WALLET_PASSWORD=your_password
```

### RPC URL

Configure the RPC URL for the network you intend to use. This allows the CLI to send transactions and read data from the blockchain.

You can obtain an RPC URL and auth token from providers such as [Alchemy](https://www.alchemy.com/), [Infura](https://infura.io/), or [Ankr](https://ankr.com/).

The CLI looks for environment variables in the format `[NETWORK]_RPC_URL` (uppercase). You only need to set the variable for the network you are connecting to.

Supported networks: `local`, `sepolia_devnet`, `sepolia_testnet`, `mainnet`.

```bash
# .env

# Local network (e.g. Hardhat node)
LOCAL_RPC_URL=http://127.0.0.1:8545

# Sepolia Devnet (e.g. Alchemy, Infura, or Ankr endpoint)
SEPOLIA_DEVNET_RPC_URL=https://sepolia.infura.io/v3/[auth_token]

# Sepolia Testnet
SEPOLIA_TESTNET_RPC_URL=https://sepolia.infura.io/v3/[auth_token]

# Mainnet
MAINNET_RPC_URL=https://mainnet.infura.io/v3/[auth_token]
```

### ETH PRIVATE KEY

To use `dincli` with your own wallet (Non-Demo Mode), you must first disable demo mode:

```bash
dincli system configure-demo --mode no
```

Then, you can connect using a specific account index. This requires the private key to be set in your `.env` file using the format `ETH_PRIVATE_KEY_<account_index>`.

```bash
# Connect to Account 0
dincli system connect-wallet --account 0
```

**Configuration in `.env`:**

```bash
# .env
ETH_PRIVATE_KEY_0=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
ETH_PRIVATE_KEY_1=0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
```

You can define multiple private keys by incrementing the account index (e.g., `0`, `1`, `2`...).

### IPFS setup

you either need to run your own IPFS node or use a public IPFS gateway or use a paid IPFS service such as [Pinata](https://www.pinata.cloud/) or [Infura](https://infura.io/) 

you need to run the ipfs 24/7 to make sure your data is available on the network. 

or you can pin your data to a paid IPFS service such as [Pinata](https://www.pinata.cloud/) or [Infura](https://infura.io/) 


#### run your own IPFS node

To run your own IPFS node, you can install  ipfs, and run the following command:

```bash
# Run IPFS node
ipfs daemon
```

you need to add the upload and retrieve url in .env file

```bash
# .env
IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0/add
IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0/cat/
```


#### filebase ipfs

You can use filebase as ipfs provider. Filebase IPFS service is implemented in dincli. Ypu can get your api key from [filebase](https://filebase.co/). and configure it in dincli as follows:
``` bash
dincli system configure-ipfs --provider filebase --api-key <your_api_key>
```

#### infura ipfs

``` bash
# .env
# Get from https://infura.io/dashboard/ipfs
INFURA_PROJECT_ID=your_project_id
INFURA_PROJECT_SECRET=your_project_secret

# Construct URLs with Basic Auth embedded
IPFS_API_URL_ADD=https://${INFURA_PROJECT_ID}:${INFURA_PROJECT_SECRET}@ipfs.infura.io:5001/api/v0/add?pin=true
IPFS_API_URL_RETRIEVE=https://ipfs.infura.io:5001/api/v0/cat/

```











