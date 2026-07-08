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

This creates `keystore.json` — a standard Ethereum JSON keystore file — in the current
directory and prints the address. **Note the address; you will connect the keystore to
`dincli` in step 3 and delete the file then.** Do not delete `keystore.json` yet.

### Option B — OWS (Open Wallet Standard)

[OWS](https://openwallet.sh/) is a chain-agnostic, agent-friendly key management
tool that stores wallets in a local vault (`~/.ows/`) encrypted with AES-256-GCM
(scrypt KDF). Install it via the official one-liner (a global
`npm install -g @open-wallet-standard/core` also provides the `ows` CLI):

```bash
curl -fsSL https://docs.openwallet.sh/install.sh | bash
```

Generate a fresh wallet (a single mnemonic derives an Ethereum address plus
addresses for every other supported chain):

```bash
ows wallet create --name validator
ows wallet list                     # shows the eip155 (Ethereum) address
```

**Important:** OWS does **not** export an Ethereum JSON keystore. `ows wallet export`
prints the **raw mnemonic / private key** (interactive terminal only). So there are two
ways to use an OWS-managed key with `dincli`:

1. **Export the raw private key from OWS and import it interactively** — simple, but the key
   leaves the OWS vault, which forfeits OWS's main benefit. `ows wallet export` runs **only in
   an interactive terminal** (it refuses piped input) and prints the raw secret to the screen;
   then connect it in step 3 by pasting the key when prompted:
   ```bash
   ows wallet export --wallet validator     # interactive; prints the raw private key / mnemonic
   ```
2. **Signing delegation (planned, not yet shipped)** — a *future* `dincli` integration would
   ask OWS to sign each transaction so the key never leaves the vault. EVM signing without key
   exposure is confirmed feasible (see `Developer/discussion/ows-delegation-feasibility.md`),
   but a `--wallet-backend ows` option is a planned follow-up and is **not available today**.

> **Note:** OWS also exposes a scoped API-key + policy model and Node/Python SDKs for
> programmatic access. Any future delegation integration **must verify and require policy-scoped
> signing — do not rely on unscoped OWS keys.** OWS lets API keys be created with no policy, and
> its EVM signer will sign arbitrary payloads without validating them, so the policy layer's
> enforcement must be proven before it is trusted.

---

## 3. Connect the wallet to `dincli` and make it active

Import the wallet once, then set it active so later commands use it.

**If you used Option A (`eth-account` keystore):**

```bash
dincli system connect-wallet --keystore ./keystore.json --name validator
rm ./keystore.json      # remove the temporary keystore file once imported
```

**If you used Option B path 1 (OWS raw-key export):** paste the exported private key when prompted:

```bash
dincli system connect-wallet --name validator
```

Then make `validator` the active wallet:

```bash
dincli system set-wallet validator
```

`connect-wallet` prompts for a keystore passphrase (Option A) and persists the encrypted
keystore at `~/.config/dincli/wallets/wallet_validator.json` — your raw private key is
**never written to disk in plaintext**.

**Password handling:**
- You are prompted for your passphrase **each command** (`dincli` does not cache passwords
  across invocations).
- To avoid re-prompting, set `DIN_WALLET_PASSWORD=<your-passphrase>` in your `.env` file
  (suitable for unattended/CI runs, not for shared machines).

For detailed migration and runtime selection, see
[keystore-migration.md](./keystore-migration.md).

---

## 4. Fund the burner wallet

Your wallet needs **ETH for gas** and **DIN for staking**.

**Minimum to participate:**
- **10 DIN** to stake (`DinValidatorStake.MIN_STAKE = 10 * 10^18`)
- A small amount of **ETH** for transaction gas fees

### Get Sepolia Optimism ETH

Send your address to one of these faucets:

- [Optimism Faucet](https://console.optimism.io/faucet)
- [Chainlink Faucet](https://faucets.chain.link/optimism-sepolia)
- [LearnWeb3 Faucet](https://learnweb3.io/faucets/optimism_sepolia/)

### Get DIN tokens

With `validator` connected and active (step 3) and holding some ETH, buy DIN by depositing
ETH through the `DinCoordinator` contract (ETH → DIN exchange):

```bash
dincli aggregator dintoken buy 0.00001      # uses the active wallet; or add --wallet validator
```

See [DIN-workflow.md](../DIN-workflow.md) for the complete token workflow.

---

## Key management tiers

| Path | Convenience | Security | Recommended for |
|---|---|---|---|
| `ETH_PRIVATE_KEY_<n>` in `.env` | High (multi-acct, no prompts) | Low (plaintext on disk) | Local dev, automated testing |
| Interactive `getpass` + encrypted keystore | Medium (prompt per command; in-memory cache only within one process) | High (encrypted at rest, pw in memory only) | Production (current best) |
| `--keystore <path>` JSON keystore input | Medium (passphrase prompt) | High (external keystore, key never re-encoded) | Production validators w/ external key mgmt |
| `DIN_WALLET_PASSWORD` env | High (no prompts across commands) | Medium (pw plaintext in env/`.env`) | Unattended automation / CI |
| OWS signing delegation (planned; not yet shipped) | High (named accts, no raw key in dincli) | Potentially high, but **unproven** — key isn't exposed to dincli, yet the tested path is unscoped and not passphrase-gated; needs verified policy-scoped signing first | Production wanting full key isolation (future) |

---

**Next:** [Keystore Migration Guide](./keystore-migration.md)
