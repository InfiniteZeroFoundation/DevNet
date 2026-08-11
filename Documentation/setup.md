# DIN CLI — Setup Guide

This guide walks you through the complete setup process for the DIN CLI (`dincli`), from
installation to a verified ready state. Every aggregator, auditor, and client should
complete this before entering a Global Iteration.

---

## 1. Requirements

`dincli` has been tested on Linux with Python 3.10 or later. Other platforms are untested
rather than known-broken — see the note at the end of this section.

> [!NOTE]
> `pyproject.toml` currently declares `requires-python = ">=3.9"`, but `py-cid` needs 3.10
> or later, so a 3.9 host installs successfully and then fails at runtime. Use 3.10+
> regardless of what the package metadata allows. A fix for the declared floor is queued.

> [!IMPORTANT]
> **Why versions matter.** Dependency drift can change serialised output; a changed output
> produces a different CID; a CID that differs from the finalized batch CID is a
> consensus divergence. Such a divergence violates the intended aggregator duty and is
> intended to be slashable. Enforcement on the currently deployed contracts is
> non-functional and under remediation — but a mismatch can still wedge the Global
> Iteration for all participants. Not every version difference changes output, and the
> sections below record exactly what was tested.

### Tested configuration

The following configuration was verified end-to-end on `agent@10.10.20.37` in August 2026:

| | |
|---|---|
| Python | 3.13.5 |
| OS | Debian 13, kernel 6.12.96 |
| Architecture | x86_64 |
| CUDA | Not used (CPU-only) |
| `torch` | 2.6.0 |
| `numpy` | 2.2.5 |
| `dincli` | 0.1.0 (wheel from `main`) |

The wheel pins `torch==2.6.0` exactly; `numpy>=2.2.0` is open-ended in `pyproject.toml` and
is the known drift risk.

Python **3.12.3** and **3.13.5** have both been used successfully. Which one becomes the
pinned version is not yet decided.

A supported platform matrix is being finalised. If you are on macOS or ARM,
or cannot match the tested configuration, check with the team before registering
as an aggregator — a mismatch risks putting your output out of consensus with your batch.

---

## 2. Virtual Environment

Create and activate a Python virtual environment. You must re-activate it every time you
open a new terminal session.

```bash
python3 -m venv venv
source venv/bin/activate   # run this in every new session
```

---

## 3. Install `dincli`

### Option A — Install from a Downloaded Wheel (tested working)

```bash
# Download the wheel file
wget https://github.com/InfiniteZeroFoundation/DevNet/raw/refs/heads/main/dist/dincli-0.1.0-py3-none-any.whl
# Install it
pip install dincli-0.1.0-py3-none-any.whl
```

### Option B — Install Directly from GitHub

```bash
pip install git+https://github.com/InfiniteZeroFoundation/DevNet.git@main#subdirectory=dist
```

> [!WARNING]
> Option B is **not currently working** — `dist/` contains only the wheel and tarball, no
> `pyproject.toml`, so pip rejects it with *"does not appear to be a Python project"*.
> Use Option A until this is fixed.

### Reproducibility note

The repo contains `cache_model_0/requirements.txt` — a 121-line `pip freeze` of a
Linux/CUDA development machine, including 13 `nvidia-*` packages, `triton`, `pytest`,
and `ruff`. CPU-only operators should **not** install it wholesale.

If you are on a Linux/x86_64 host matching the tested configuration and want to enforce
exact package versions, you can install the pinned dependencies first, then the wheel
with `--no-deps`:

```bash
wget https://raw.githubusercontent.com/InfiniteZeroFoundation/DevNet/main/cache_model_0/requirements.txt
pip install -r requirements.txt
pip install --no-deps dincli-0.1.0-py3-none-any.whl
pip check
```

This is an *optional* extra step for operators who want the exact versions from the
recorded run. It is not a general requirement.

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

Creates the required `config` and `cache` directories and generates an empty
configuration file.

---

## 5. Configuration

```bash
# Disable demo mode to use your own wallet and private keys
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
> violates the intended aggregator duty and is intended to be slashable. Enforcement on
> the currently deployed contracts is non-functional and under remediation — but a missed
> submission can still wedge the Global Iteration for all participants.

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

> [!WARNING]
> The CLI does not currently validate that the RPC is on the expected chain. One wrong
> word — `optimism-mainnet` instead of `optimism-sepolia` — is accepted silently, and the
> only symptom is `ETH Balance: 0`. A chain-id check is planned for a later release.

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

> [!WARNING]
> Disable demo mode **before** connecting a wallet. With demo mode on,
> `connect-wallet --account 0` loads a **publicly known Hardhat dev key** — one anyone can
> derive — and writes it to disk in plaintext. Funding that address means anyone can drain it.

```bash
dincli system configure-demo --mode no   # required before any connect-wallet
dincli system connect-wallet --account 0
```

Always pass `--account N`. Without it, `connect-wallet` prompts you to paste a private key,
and pasting anything other than the key already in your `.env` produces a keystore for a
**different address than the one you funded** — with a zero balance as the only symptom.

---

## 7. IPFS Setup

`dincli` requires an IPFS provider to store and retrieve model data. An aggregator needs
**upload capability** — a read-only gateway cannot submit results. Non-submission violates
the intended aggregator duty and is intended to be slashable; the enforcement caveat in
§6 applies here as well.

> [!IMPORTANT]
> `configure-ipfs` currently demands a connected wallet even though it never uses one. Set
> up your wallet (§6) **before** running any IPFS configuration.

### Option A — Filebase (tested working)

Obtain an API key from [Filebase](https://filebase.com/) and configure it:

```bash
dincli system configure-ipfs --provider filebase --api-key YOUR_FILEBASE_API_KEY
```

> [!NOTE]
> Create a bucket on Filebase and get the bucket's IPFS RPC API token from the
> [Filebase Console](https://console.filebase.com/keys). Use that as the `--api-key`
> value. The IPFS RPC API token dashboard is at the bottom of the page.

### Option B — Self-Hosted IPFS Node

A local IPFS node (`ipfs daemon`) is **not currently selectable** through the CLI.
`--provider` accepts only `filebase` and `custom`; `"ipfs node"` is rejected. A fix is
in progress.

If you set `IPFS_API_URL_ADD` and `IPFS_API_URL_RETRIEVE` in `.env` and do **not** run
`configure-ipfs`, the node path will be used — but retrieval may still fail against
public gateways (see below). This is a known limitation.

### Option C — Custom Provider

`configure-ipfs --provider custom` writes `"custom"` to the config, but the custom
provider path is **not functional on `main`** for two reasons:

1. No CLI command sets `ipfs_service_path` — the `custom` code path reads it but it is
   never written.
2. The `custom` provider loader references `importlib.util` but `importlib` is not
   imported in `dincli/services/ipfs.py`, so any `custom` provider raises a `NameError`.

These are tracked for a follow-up release.

### Provider state is machine-global

IPFS provider choice is stored in the dincli global config directory
(`platformdirs.user_config_dir("dincli")`), not per project. There is currently no
documented command to return to the default node provider once a provider has been
configured. If you change providers, you may need to hand-edit `config.json`.

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

#### Bridge procedure

The bridge is an ordinary signed transfer from your EOA to the
`L1StandardBridgeProxy` contract on **Sepolia L1**.

| | |
|---|---|
| OP Sepolia `L1StandardBridgeProxy` (on Sepolia L1) | `0xFBb0621E0B23b5478B630BD55a5f21f67730B0F1` |
| OP Sepolia `OptimismPortalProxy` (on Sepolia L1) | `0x16Fc5058F25648194471939df75CF27A2fdC48BC` |

**Mandatory preflight checks:**

1. Your L1 RPC returns `chain_id == 11155111`.
2. Your L2 RPC returns `chain_id == 11155420`.
3. The destination `L1StandardBridgeProxy` address has bytecode on L1.
4. The address is taken from the current [superchain-registry](https://github.com/ethereum-optimism/superchain-registry)
   entry for chain `11155420`.
5. Your sender is an EOA and matches the intended L2 recipient.

> [!NOTE]
> `OTHER_BRIDGE()` returns the same `0x4200…0010` L2StandardBridge predeploy on every
> OP-Stack chain and confirms nothing about which chain you are on. The checks above are
> what matters — `OTHER_BRIDGE()` supplements them, it does not replace them.

**Transaction:** estimate gas and apply a buffer. Expect roughly 600,000 gas (observed:
616,165). A 21,000 gas limit will fail — this is a contract call, not a plain transfer.
Optimism documents L1→L2 deposits as typically 1–3 minutes (observed: ~75 s).

**Post-flight:** verify the receipt status and confirm the resulting L2 balance.

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