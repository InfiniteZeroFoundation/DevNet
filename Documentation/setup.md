# DIN CLI — Setup Guide

This guide walks you through the complete setup process for the DIN CLI (`dincli`), from
installation to a verified ready state. Every aggregator, auditor, and client should
complete this before entering a Global Iteration for any model.

---

## 1. Requirements

- Python **3.12+** (`pyproject.toml` sets `requires-python = ">=3.12"`)

## 2. Virtual Environment

Create and activate a Python virtual environment. You must re-activate it every time you
open a new terminal session.

```bash

# Create a virtual environment once
python3 -m venv venv

# Activate the virtual environment, run this in every new session
source venv/bin/activate  
```

---

## 3. Install `dincli` from a Downloaded Wheel

```bash
# Download the wheel file
wget https://github.com/InfiniteZeroFoundation/DevNet/raw/refs/heads/main/dist/dincli-0.1.0-py3-none-any.whl
# Install it
pip install dincli-0.1.0-py3-none-any.whl
```

> For any missing dependency, install it with pip. Full dependency list:
> [requirements-cpu.txt](../cache_model_0/requirements-cpu.txt) (default) or
> [requirements-cuda.txt](../cache_model_0/requirements-cuda.txt) (NVIDIA GPU hosts).

### Verify Installation

```bash
dincli --version
# or
dincli system welcome
```

---

## 4. Initialise the CLI

```bash
dincli system init
```

Creates the required `config` and `cache` directories and generates a configuration file with demo mode off.

---

## 5. Configuration

```bash
# Make sure that demo mode is disabled to use your own wallet and private keys
dincli system configure-demo --mode no

# Set the default network
dincli system configure-network --network sepolia_op_devnet
```

> [!NOTE]
> Use `sepolia_op_devnet` for devnet. Testnet and Mainnet support will be rolled out in
> a future release. The only currently implemented networks are `local` and
> `sepolia_op_devnet`.

```bash
# Set the log level  [debug | info | warning | error | critical]
dincli system configure-logging --level info
```

---

## 6. Environment Variables (`.env`)

Create a `.env` file in the directory **you run `dincli` from**. The CLI reads `.env`
from `Path(os.getcwd())` — it does **not** walk parent directories, so running `dincli`
from the wrong folder means it cannot find your wallet password, RPC URL, or private keys.

```bash
chmod 600 .env
```

> [!WARNING]
> A missing or wrong `.env` means no submission reaches the chain. Non-submission
> violates the intended aggregator duty and is intended to be slashable. 

### Wallet Password

The DIN CLI encrypts your private key using this password.

```bash
DIN_WALLET_PASSWORD=your_secure_password
```

### RPC URL

The CLI needs an RPC endpoint to communicate with the blockchain. The variable name
follows the pattern `[NETWORK]_RPC_URL` (uppercase).

You can obtain an RPC URL from providers such as [Alchemy](https://www.alchemy.com/),
[Infura](https://infura.io/), or [Ankr](https://www.ankr.com/). You must set the RPC
URL for `optimism-sepolia` network as `SEPOLIA_OP_DEVNET_RPC_URL` in your `.env` file.

```bash
# Sepolia - Optimism Devnet
# must set this for devnet usage
SEPOLIA_OP_DEVNET_RPC_URL=https://optimism-sepolia.infura.io/v3/YOUR_AUTH_TOKEN


# Local network (e.g. a Hardhat node) - OPTIONAL
# LOCAL_RPC_URL=http://127.0.0.1:8545

```

### Generate a Private Key

If you do not already have an Ethereum private key, generate one:

```bash
python -c "
from eth_account import Account
a = Account.create()
print('Address:              ', a.address)
print('ETH_PRIVATE_KEY_0=0x' + a.key.hex().removeprefix('0x'))
"
```

### Private Key

Store private keys using the pattern `ETH_PRIVATE_KEY_N` in your `.env` file. You can
define as many accounts as needed by incrementing the index.

```bash
ETH_PRIVATE_KEY_0=0x...
ETH_PRIVATE_KEY_1=0x...
```

> [!NOTE]
> Use your own private keys only. The keys shown in examples are for illustration.

### Connect Your Wallet

```bash
dincli system configure-demo --mode no   # required before connect-wallet
dincli system connect-wallet --account 0
```

> [!NOTE]
> `connect-wallet` refuses to run while demo mode is on, so a real key can never be written to disk unencrypted by accident. 

Always pass `--account N`. Without it, `connect-wallet` prompts you to paste a private key,
and pasting anything other than the key already in your `.env` produces a keystore for a
**different address than the one you funded** — with a zero balance as the only symptom.

---

## 7. IPFS Setup

`dincli` requires an IPFS provider to store and retrieve model data. An aggregator or client needs
**upload capability** — a read-only gateway cannot submit results. Non-submission violates
the intended aggregator duty and is intended to be slashable; the enforcement caveat in
§6 applies here as well.

> [!TIP]
> **Install the `ipfs` (kubo) binary too, regardless of which provider you pick below.**
> `dincli` uses it to verify downloaded content against its requested CID before saving —
> this is a separate, lightweight use of the binary purely for offline hashing, **not**
> the same as pointing `dincli` at IPFS API URLs directly (that's Option B). Install
> kubo ([docs.ipfs.tech/install/command-line](https://docs.ipfs.tech/install/command-line/))
> and run `ipfs init` once — both steps are fast and fully offline; no daemon needs to run
> afterward, and no data needs to sync. If the binary isn't present, `dincli` logs a
> warning and skips verification rather than failing — it's a recommended hardening step,
> not a hard requirement.

### Option A — Filebase (Recommended)

Obtain an API key from [Filebase](https://filebase.com/) and configure it:

```bash
dincli system configure-ipfs --provider filebase --api-key YOUR_FILEBASE_API_KEY
```

> [!NOTE]
> Create a bucket on Filebase and get the bucket's IPFS RPC API token from the
> [Filebase Console](https://console.filebase.com/keys). Use that as the `--api-key`
> value. The IPFS RPC API token dashboard is at the bottom of the page at filebase bucket URL.

### Option B — Direct IPFS API URLs (`.env`)

Set `IPFS_API_URL_ADD` and `IPFS_API_URL_RETRIEVE` in `.env`, then select this path
explicitly:

```bash
dincli system configure-ipfs --provider env
```

This is also the default if you never run `configure-ipfs` at all — but retrieval may
still fail against public gateways (see below).

> [!WARNING]
> If `IPFS_API_URL_ADD` points at your own `ipfs daemon`, pinning and uptime are your
> responsibility — a node that goes offline or garbage-collects unpinned content makes
> your submitted CIDs unretrievable. Filebase (Option A) is a managed pinning service and
> doesn't have this failure mode; use it unless you're deliberately accepting the tradeoff.

### Provider state is machine-global

IPFS provider choice is stored in the dincli global config directory —
run `dincli system get-config-dir` to see its path. Run
`dincli system configure-ipfs --provider env` to switch back to the default `.env`-based
path from `filebase`.

---

## 8. Fund the Address

The DIN contracts are deployed on **Optimism Sepolia (L2, chain 11155420)**, not
Ethereum Sepolia (L1, chain 11155111). Ethereum Sepolia ETH **cannot** pay `dincli`
transactions — it must be bridged first (§8.2).

### 8.1 OP Sepolia Faucets (direct)

You can request Optimism Sepolia ETH from these faucets:

- [Optimism Faucet](https://console.optimism.io/faucet)
- [Chainlink Faucet (Optimism Sepolia)](https://faucets.chain.link/optimism-sepolia)
- [LearnWeb3 Faucet](https://learnweb3.io/faucets/optimism_sepolia/)
- [ETHGlobal OP Sepolia Faucet](https://ethglobal.com/faucet/op-sepolia-11155420)
- [Alchemy Optimism Sepolia Faucet](https://www.alchemy.com/faucets/optimism-sepolia)

> [!WARNING]
> As of August 2026, all of the above require connecting a browser wallet (MetaMask,
> Coinbase, WalletConnect, or similar), and several demand mobile verification. A
> headless server operator may not be able to self-fund through any of them. If none
> work, use the bridge route below.

### 8.2 Fund on Ethereum Sepolia, then Bridge

Ethereum Sepolia (L1) faucets are less gated. You can fund there and bridge to
Optimism Sepolia using OP's `L1StandardBridge`, which deposits ETH to the **same
address** on L2 — no ABI encoding or browser needed.

#### Funding sources for Ethereum Sepolia (L1)

- [Google Cloud Web3 Faucet — Ethereum Sepolia](https://cloud.google.com/application/web3/faucet/ethereum/sepolia)

Funds arrive on **chain 11155111** and must be bridged before they can pay `dincli`
transactions on **chain 11155420**.

#### Bridge with `dincli system bridge-eth`

`dincli` automates the bridging procedure — preflight checks, gas estimation, and
posting the deposit — in one command:

```bash
# add to .env (or pass --l1-rpc-url instead):
# SEPOLIA_L1_RPC_URL=https://ethereum-sepolia.infura.io/v3/YOUR_AUTH_TOKEN

dincli --network sepolia_op_devnet system bridge-eth --amount 0.01
```

Add `--dry-run` first to print the unsigned transaction without sending it. By default
the command waits for the L2 balance to increase; pass `--no-wait` to return right after
L1 inclusion, or `--yes` to skip the confirmation prompt. `--network` selects the L2
(must be `sepolia_op_devnet`) — the L1 side is controlled independently via
`SEPOLIA_L1_RPC_URL`/`--l1-rpc-url`.

Deposits only — withdrawals go L2→L1, take about 7 days, and aren't supported by this
command.

### 8.3 Community Funding

If you are unable to obtain funds through faucets or bridging, you may also request
Sepolia Optimism ETH through the Infinite Zero Foundation Telegram and Signal community
groups (see Appendix).

---

## 9. Readiness Checklist

Before entering a Global Iteration, verify **every** item:

```bash
# 1. Wallet is connected and address matches the funded one
dincli system read-wallet

# 2. RPC chain ID is 11155420
#    dincli does not check this, and `din-info` reads local config rather than the
#    chain, so it cannot catch a wrong-chain RPC. This prints PASS or FAIL either way.
RPC=$(grep -E '^SEPOLIA_OP_DEVNET_RPC_URL=' .env | cut -d= -f2-)
if [ -z "$RPC" ]; then
  echo "FAIL: SEPOLIA_OP_DEVNET_RPC_URL not found in ./.env"
else
  CHAIN=$(curl -s -X POST -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' "$RPC" \
    | grep -o '"result":"[^"]*"' | cut -d'"' -f4)
  if [ "$CHAIN" = "0xaa37dc" ]; then
    echo "PASS: chain 11155420 (OP Sepolia)"
  else
    echo "FAIL: got '$CHAIN', expected 0xaa37dc (11155420)"
  fi
fi

# 3. ETH balance is non-zero
dincli system --eth-balance

# 4. Manifest retrieval works — requires a configured IPFS provider
#    The --update flag is mandatory: without it, explore can pass against
#    a cached manifest without proving retrieval works at all.
dincli task explore 0 --update
```

All four must pass. The last one in particular exercises the full chain: wallet → RPC →
on-chain manifest CID read → IPFS retrieval.

**You are now ready.** Proceed to `Documentation/GettingStarted.md` for role-specific
operations.

---

## Appendix — Community Channels

### Telegram
- Announcements, coordination, community support
- https://t.me/+I4Tl7foCVwwwM2Vk

### Signal
- Technical discussions, coordination, protocol updates
- https://signal.group/#CjQKICVqJ0Ri3KGCZOsf8A3dhmg8GC_vc1MBmBrq0JV7lIr6EhBCOwElVHvE0swjO8kSk7ky

> ⚠️ Global Iteration updates and onboarding assistance are shared regularly.