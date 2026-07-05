# Keystore Migration Guide

How to migrate from the old `.env` plaintext-key pattern to the new encrypted
named-keystore system.

---

## 1. What changed

### Before (legacy)

- Private keys stored in plaintext in `.env` (`ETH_PRIVATE_KEY_0=0x...`)
- Single wallet at `~/.config/dincli/wallet.json`
- Password cached on disk in `~/.config/dincli/.session` (15-min TTL, since removed)

### After (current)

- **Encrypted named keystores** at `~/.config/dincli/wallets/wallet_<name>.json`
- Each keystore is a standard eth-account keystore wrapped with metadata (address, source, name)
- **No disk-based password caching** — passphrase entered per command or via `DIN_WALLET_PASSWORD`
- **Runtime selection** via `--wallet <name>` or `DIN_WALLET_NAME` env var
- Legacy `wallet.json` still loads as the `default` account for back-compat

### Password caching removed (design decision)

`dincli` no longer caches passwords across command invocations. The old on-disk
`CONFIG_DIR/.session` file stored plaintext passwords — this has been replaced
with an **in-memory** cache that lasts only for the duration of a single process.

**To avoid re-prompting across commands**, set `DIN_WALLET_PASSWORD` in your `.env`:

```env
DIN_WALLET_PASSWORD=your_secure_passphrase
```

This is the only supported no-prompt-across-commands option.

---

## 2. How to migrate an existing key

### Step 1: Create a temporary standard keystore

Use the `eth-account` Python library to export your existing private key as a
standard Ethereum keystore (this is a one-time operation):

```bash
python3 -c "
from eth_account import Account
from getpass import getpass
import json

key = getpass('Existing private key (0x...): ')
pw = getpass('Keystore passphrase: ')
ks = Account.encrypt(key, pw)
with open('keystore.json', 'w') as f:
    json.dump(ks, f)
print('Keystore exported to ./keystore.json')
"
```

### Step 2: Import into dincli

```bash
dincli system connect-wallet --keystore ./keystore.json --name validator
```

`dincli` will:
1. Prompt for the keystore passphrase
2. Decrypt the key to derive and verify the address
3. Write the wrapped keystore to `~/.config/dincli/wallets/wallet_validator.json`
4. Set file permissions to `0o600`

### Step 3: Clean up

```bash
rm keystore.json
```

**Do not** hand-create or hand-edit files in `wallets/` — the internal wrapper
schema is managed by `dincli`.

---

## 3. How to update operator setup

### Docker / din-node

If you run `dincli` via `din-node`, the keystore lives on the bind-mounted volume
at `$DIN_STATE_DIR/config/dincli/wallets/`. No changes are needed to
`docker-compose.yml` — the `config/dincli/` directory is already mounted.

To select a named wallet at runtime, add `DIN_WALLET_NAME` to the `.env` used by
`docker-compose`, or pass `--wallet` with each command:

```bash
docker compose exec din-node dincli --wallet validator client train-lms 0 --submit
```

### Host install

Set `DIN_WALLET_NAME` in your project `.env`:

```env
DIN_WALLET_NAME=validator
```

Or use the top-level flag:

```bash
dincli --wallet validator client train-lms 0 --submit
```

---

## 4. What persists across container restarts

| Artifact | Location | Survives restart? |
|---|---|---|
| Encrypted keystore | `$DIN_STATE_DIR/config/dincli/wallets/` | Yes (bind-mounted volume) |
| Passphrase | (never stored) | No — entered each command |
| `DIN_WALLET_PASSWORD` | `.env` file on bind-mounted volume | Yes |

> The passphrase is **never stored on disk**. Each `connect-wallet` or command
> that needs to unlock the wallet will prompt you, unless `DIN_WALLET_PASSWORD`
> is set.

---

## 5. Named wallet precedence

When resolving the `default` wallet:

1. `~/.config/dincli/wallets/wallet_default.json` (new named default) — **wins**
2. `~/.config/dincli/wallet.json` (legacy) — used only as fallback when no named
   default exists

If you run `connect-wallet --name default`, the new `wallets/wallet_default.json`
is created and the legacy file is **not** overwritten.

---

## 6. Runtime selection

| Mechanism | Scope | Example |
|---|---|---|
| `--wallet <name>` | Per-command override | `dincli --wallet validator dintoken buy 0.001` |
| `DIN_WALLET_NAME` env var | Process-level default | `export DIN_WALLET_NAME=validator` |
| Config `wallet_name` | Persistent default | Set via `dincli system set-wallet <name>` |
| None of the above | Fallback to `default` | Legacy `wallet.json` or `wallets/wallet_default.json` |

**See also:** [Wallet Setup Guide](./wallet-setup.md) for creating and funding a
new burner wallet.

---

## 7. Listing accounts

```bash
dincli system list-accounts
```

Shows all named keystores with their addresses (read from metadata — no decrypt
needed) and marks the currently active wallet.

---

## 8. Removing the old `.session` file

If a stale `~/config/dincli/.session` file exists from a previous `dincli`
version, it is safe to delete:

```bash
rm ~/.config/dincli/.session
```

`dincli` also deletes it automatically on first run after upgrade.
