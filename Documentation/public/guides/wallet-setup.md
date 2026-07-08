# Burner Wallet Setup Guide

How to create a dedicated burner wallet for DIN Protocol participation.

---

## 1. Why a dedicated burner wallet

`dincli` loads your private key into memory to sign every on-chain transaction.
If your machine or the keystore file is compromised, every asset at that address
is exposed. Use a **disposable** address with only the funds needed for
participation — never your primary wallet.

---

## 2. Generate a burner wallet

### Option A — `eth-account` one-liner (recommended)

```bash
python3 -c "
from eth_account import Account
from getpass import getpass
import json

acct = Account.create()
pw = getpass('Keystore passphrase: ')
ks = Account.encrypt(acct.key.hex(), pw)
with open('keystore.json', 'w') as f:
    json.dump(ks, f)
print('Address:', acct.address)
"
```

This creates `keystore.json` — a standard Ethereum JSON keystore file —
in the current directory. Import it with:

```bash
dincli system connect-wallet --keystore ./keystore.json --name validator
```

Then delete the temporary file: `rm keystore.json`.

### Option B — OWS (Open Wallet Standard)

[OWS](https://openwallet.sh/) is a chain-agnostic, agent-friendly key management
tool that stores wallets encrypted with AES-256-GCM (corroborated by MoonPay's launch
press release — see [openwallet.sh](https://openwallet.sh/)). Install
it via npm:

```bash
npm install -g @open-wallet-standard/core
```

Generate a fresh wallet:

```bash
ows wallet create --name validator
```

Then check `ows --help` or [docs.openwallet.sh](https://docs.openwallet.sh/) for
the current export/import surface to export the keystore to a file. Once exported,
import it into `dincli`:

```bash
dincli system connect-wallet --keystore ./keystore.json --name validator
rm ./keystore.json
```

> **Note:** OWS direct signing delegation from `dincli` is under evaluation.
> OWS exposes MCP, REST, and SDK interfaces for agent access with scoped API
> tokens — `dincli` never sees the raw key. This is the preferred production
> path if the signing interface meets the protocol's requirements. For now,
> OWS is used as the keystore generation/export tool, and `dincli` holds the
> encrypted keystore locally.

---

## 3. Fund the burner wallet

You need the wallet's address with **ETH for gas** and **DIN for staking**.

**Minimum to participate:**
- **10 DIN** to stake (`DinValidatorStake.MIN_STAKE = 10 * 10^18`)
- A small amount of **ETH** for transaction gas fees

### Get Sepolia Optimism ETH

Send your new address to one of these faucets:

- [Optimism Faucet](https://console.optimism.io/faucet)
- [Chainlink Faucet](https://faucets.chain.link/optimism-sepolia)
- [LearnWeb3 Faucet](https://learnweb3.io/faucets/optimism_sepolia/)

### Get DIN tokens

DIN tokens are obtained by depositing ETH through the `DinCoordinator` contract
(ETH → DIN exchange). Use `dincli`:

```bash
dincli aggregator dintoken buy 0.00001
```

See [DIN-workflow.md](../workflows/din-workflow.md) for the complete token workflow.

---

## 4. What happens next

After funding the address, load the encrypted keystore into `dincli`:

```bash
dincli system connect-wallet --keystore ./keystore.json --name validator
```

You will be prompted for the keystore passphrase. `dincli` persists the encrypted
keystore in `~/.config/dincli/wallets/wallet_validator.json` — your raw private
key is **never written to disk** in plaintext.

**Password handling:**
- You will be prompted for your passphrase **each command** (dincli does not
  cache passwords across invocations).
- To avoid re-prompting, set `DIN_WALLET_PASSWORD=<your-passphrase>` in your
  `.env` file (suitable for unattended/CI runs, not for shared machines).

For detailed migration and runtime selection, see
[keystore-migration.md](./keystore-migration.md).

---

## Key management tiers

| Path | Convenience | Security | Recommended for |
|---|---|---|---|
| `ETH_PRIVATE_KEY_<n>` in `.env` | High (multi-acct, no prompts) | Low (plaintext on disk) | Local dev, automated testing |
| Interactive `getpass` + encrypted keystore | Medium (prompt per command; in-memory cache only within one process) | High (encrypted at rest, pw in memory only) | Production (current best) |
| `--keystore <path>` JSON keystore input | Medium (passphrase prompt) | High (external keystore, key never re-encoded) | Production validators w/ external key mgmt |
| `DIN_WALLET_PASSWORD` env | High (no prompts across commands) | Medium (pw plaintext in env/`.env`) | Unattended automation / CI |
| OWS delegation (if feasible) | High (named accts, no raw key in dincli) | Highest (dincli never sees the key) | Production wanting full key isolation |

---

**Next:** [Keystore Migration Guide](./keystore-migration.md)
