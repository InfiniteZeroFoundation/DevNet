# Running `dincli` as a container: the `din-node` operator runbook

`din-node` packages **`dincli`** — the *trusted* DIN host process — as a Docker
image plus a Compose run path, so you can operate a DIN client / auditor /
aggregator without installing Python and `dincli` on the host directly.

This is **Phase 1: Devnet Operator Baseline** of the validator-operations
roadmap. It is for **devnet**. Read the **Security tradeoff** section below
before deploying anywhere you care about.

---

## How it works (and why it needs the Docker socket)

`dincli` does two kinds of work:

- **Trusted control plane** — holds your wallet/config, talks to the chain and
  IPFS, decides what to submit. This is what runs *inside* `din-node`.
- **Untrusted execution** — each training/scoring/aggregation job runs the model
  owner's Python code, which is treated as hostile. `dincli` already isolates
  this by spawning a short-lived **worker container** (`din-worker:dev`) per job
  with `--network none`, CPU/memory limits, and read-only mounts. **`din-node`
  does not change this layer** — it just keeps doing it from inside a container.

Because `din-node` itself needs to run `docker run` to spawn those workers, the
host's Docker socket (`/var/run/docker.sock`) is mounted into it and the image
ships the Docker **client** (no daemon). Worker containers therefore launch as
**siblings** of `din-node` on the host daemon — not nested inside it.

```
        Host Docker daemon  ◄──────── /var/run/docker.sock (mounted into din-node)
          │            │                       │
          ▼            ▼                 ┌──────┴─────┐
   ┌────────────┐ ┌────────────┐         │  din-node  │  dincli runs `docker run`
   │ din-worker │ │ din-worker │ ◄───────┤  (dincli)  │  → host daemon → sibling
   └────────────┘ └────────────┘         └────────────┘
```

---

## ⚠️ Security tradeoff: the Docker socket

Mounting `/var/run/docker.sock` gives `din-node` **root-equivalent control of the
host's Docker daemon**. Anything that can talk to that socket can start a
container that mounts the whole host filesystem as root. So:

- **Anyone who compromises `din-node` effectively owns the host.**
- **Do not run `din-node` on a host whose operator you do not trust**, and do not
  run it next to unrelated sensitive workloads.

This is a deliberate simplification for devnet, not a solved problem. The new
exposure is specifically the `din-node` container itself. The untrusted **worker
job** containers are still sandboxed as before: they run with `--network none`,
no socket, and no wallet/config.

One caveat worth knowing: the **dependency-install step** (`pip install` of the
model owner's pinned `requirements.txt`) runs in a separate container that
**does** have network access — it has to, in order to download packages — and
`pip` can execute arbitrary build hooks from those packages. So model-owner
requirements are not network-isolated during install, only during the actual
job. This is existing behaviour in `dincli/cli/worker.py` (out of scope to change
here), flagged so the threat model is accurate. Hardening options (rootless
Docker, a socket proxy, Podman, a locked-down/offline install path) are future
work.

---

## Prerequisites

- Docker Engine + the Compose plugin on the host (`docker compose version`).
- The host user can use Docker (member of the `docker` group, or root).
- This repository checked out (the image builds from source in it).

---

## First-time setup

All commands run from `dincli/docker/node/` unless noted.

**1. Configure the environment.**

```bash
cp .env.example .env
```

Edit `.env` and set, for your host:

| Var | How to find it | Why |
| --- | --- | --- |
| `DIN_STATE_DIR` | choose an **absolute** path, e.g. `/home/you/.din-node` | holds all persistent state; bind-mounted at the identical path (see [volumes](#what-state-lives-where)) |
| `DOCKER_GID` | `stat -c '%g' /var/run/docker.sock` | lets the non-root container user use the socket |
| `DIN_UID` / `DIN_GID` | `id -u` / `id -g` | runs the container (and its worker children) as you, so files stay yours |

**2. Create the state directory, owned by `DIN_UID:DIN_GID`.**

```bash
source .env
mkdir -p "$DIN_STATE_DIR"
sudo chown -R "$DIN_UID:$DIN_GID" "$DIN_STATE_DIR"
```

**3. Pre-build the worker image on the host.**

`dincli` spawns `din-worker:dev` on the host daemon, so build it on the host once
(from the repo root). If you skip this, `dincli` will try to build it from
*inside* `din-node`, which works but streams a large build context — building on
the host is faster and recommended.

```bash
cd ../../..                                                   # repo root
docker build -f dincli/docker/worker/Dockerfile -t din-worker:dev .
cd dincli/docker/node
```

**4. Build and start `din-node`.**

```bash
docker compose up -d --build
docker compose ps                 # din-node should be "Up"
```

**5. Configure `dincli` inside the container** (writes into `DIN_STATE_DIR`, so it
survives restarts/upgrades).

```bash
docker compose exec din-node dincli system init
# configure-network saves the network from the global --network flag (it is not
# interactive; with no flag it defaults to "local"):
docker compose exec din-node dincli --network sepolia_devnet system configure-network
docker compose exec din-node dincli system connect-wallet         # set up your wallet
# For a local Hardhat devnet you can instead use a plaintext demo wallet:
#   docker compose exec din-node dincli system configure-demo --mode yes
```

You're set. Run role commands the same way, e.g.:

```bash
docker compose exec din-node dincli client train-lms ...
```

---

## Migrating from a host install

If you previously ran `dincli` directly on the host (`pip install -e .`), your
state lives at the platformdirs defaults. `din-node` reads the **same**
`platformdirs` names but redirected under `$DIN_STATE_DIR`, so you must copy the
three directories across **before** first start. Do this while `din-node` is
stopped.

```bash
source .env                       # so $DIN_STATE_DIR is set

# Create the destination dirs first so the copy is idempotent (re-runnable
# without producing nested config/dincli/dincli paths).
mkdir -p "$DIN_STATE_DIR/config/dincli" \
         "$DIN_STATE_DIR/cache/dincli" \
         "$DIN_STATE_DIR/cache/dincli-worker"

# Copy *contents* into the existing dirs (trailing /. ), preserving perms/links.
# 1. Wallet + config  (MUST succeed — this is your keys)
cp -a ~/.config/dincli/.        "$DIN_STATE_DIR/config/dincli/"
# 2. Manifests / models / job files
cp -a ~/.cache/dincli/.         "$DIN_STATE_DIR/cache/dincli/"
# 3. Worker package cache (optional — re-downloaded if skipped)
cp -a ~/.cache/dincli-worker/.  "$DIN_STATE_DIR/cache/dincli-worker/"

# Re-own everything as the container user
sudo chown -R "$DIN_UID:$DIN_GID" "$DIN_STATE_DIR"
```

Verify before trusting it:

```bash
docker compose up -d
docker compose exec din-node dincli system read-wallet   # should print your wallet address
```

> If your wallet is **encrypted** (the normal case, not demo mode),
> `read-wallet` decrypts the keystore and will **prompt for your wallet
> password** before showing the address — that prompt means migration worked.
> (Demo-mode plaintext wallets print the address with no prompt.)

> Use `cp -a … /.` (copy contents), not `mv`, until you've confirmed the wallet
> shows up — keep the host copy as a backup. Only the `config/dincli` move is
> critical; the two cache dirs are regenerated on demand if missing.

---

## Day-to-day lifecycle

Run from `dincli/docker/node/`.

| Action | Command |
| --- | --- |
| **Start** | `docker compose up -d` |
| **Stop** | `docker compose down` |
| **Upgrade** | `git pull && docker compose up -d --build` |
| **Logs** | `docker compose logs -f din-node` |
| **Run any dincli command** | `docker compose exec din-node dincli <args>` |
| **Open a shell** | `docker compose exec din-node bash` |
| **List DIN containers** | `docker ps -a --filter "name=din-"` |

This shows `din-node` plus any worker containers currently running. Workers are
named `din-worker-<role>-model-<id>-gi-<n>...` and normally self-remove (`--rm`)
the moment their job finishes, so in steady state you'll usually see only
`din-node`. Seeing a `din-worker-*` container means a job is in flight.

> The worker **dependency-install** step runs in a separate, *unnamed* container
> (also `--rm`). It won't match the `name=din-` filter; if you want to catch it,
> use `docker ps -a --filter "ancestor=din-worker:dev"` while an install is
> running.

> `din-node` currently idles (`sleep infinity`) and you `exec` into it, because
> `dincli` is a CLI, not yet a daemon. When the `dind` daemon lands it becomes the
> container's main process and logs will carry real activity.

### Upgrades and your data

`docker compose up -d --build` rebuilds the image with the new code and replaces
the container. **Your state is untouched** because it lives in `DIN_STATE_DIR` on
the host, not in the container. The wallet, config, and caches all survive.

---

## What state lives where

All persistent state is one host directory, `DIN_STATE_DIR`, **bind-mounted at the
identical path inside the container**.

> **Why bind mounts and not named volumes?** The task offered either, but they are
> *not* interchangeable here. `din-node` spawns worker containers through the host
> Docker daemon (via the mounted socket), so when `dincli` runs
> `docker run -v <path>:/din/model`, the **host** daemon resolves `<path>` against
> the **host** filesystem. A named volume's data lives under Docker's internal
> storage (`/var/lib/docker/volumes/.../_data`), not at the in-container path
> `dincli` knows — so the host daemon would find nothing there, create an empty
> directory, and mount *that* into the worker. The worker would get no
> manifests/models and fail **silently**. Bind-mounting one host directory at the
> **identical absolute path** makes that path valid from both the container's and
> the host's point of view at once (it's literally the same directory on disk),
> so worker mounts resolve to the real data. This is a known constraint of the
> "Docker-outside-of-Docker" pattern, not specific to DIN.

```
$DIN_STATE_DIR/
├── config/dincli/            → CONFIG_DIR        wallets/, config.json, (legacy) .session
├── cache/dincli/             → CACHE_DIR         manifests, downloaded models, job files
└── cache/dincli-worker/      → WORKER_CACHE_DIR  pip-installed worker packages (can be large)
```

> **`.session` removed.** Earlier versions of `dincli` wrote a plaintext password
> cache at `config/dincli/.session`. This file is no longer created — if it still
> exists from an older version, `dincli` deletes it automatically on first run.
> The file is safe to remove manually.

| Directory | Survives upgrade? | Safe to delete? |
| --- | --- | --- |
| `config/dincli/` | **Yes — and you must keep it** | ❌ **No.** This is your **wallet and config.** Losing it loses your keys. Back it up. |
| `cache/dincli/` | Yes | ⚠️ Mostly. Re-downloaded from chain/IPFS on next use. Don't delete mid-job. |
| `cache/dincli-worker/` | Yes | ✅ **Yes.** Worker package cache; reclaim disk freely. Reinstalled on next job. |

### Dev vs production key management

- **Development/testing:** Configure demo mode (`dincli system configure-demo --mode yes`)
  or use `ETH_PRIVATE_KEY_<n>` in `.env`. These are plaintext paths — convenient,
  but **not for production**.
- **Production:** Import an **encrypted keystore** using `--keystore` into a named
  account, then select it via `--wallet` or `DIN_WALLET_NAME`. See
  [wallet-setup.md](../../../Documentation/guides/wallet-setup.md) and
  [keystore-migration.md](../../../Documentation/guides/keystore-migration.md).

> The commands below use `$DIN_STATE_DIR`. `docker compose` reads `.env`
> internally, but your shell does not — so in a fresh shell run `source .env`
> first (from this directory), or substitute the literal path.

**Reclaim disk (safe):**
```bash
source .env        # so $DIN_STATE_DIR is set in your shell
rm -rf "$DIN_STATE_DIR/cache/dincli-worker"
```

**Full teardown (DESTROYS YOUR WALLET — back up `config/` first):**
```bash
source .env
docker compose down
rm -rf "$DIN_STATE_DIR"
```

You can also remove the images if you no longer need them:
```bash
docker image rm din-node:dev din-worker:dev
```

### Cleaning up a stuck or orphaned worker

Workers self-remove on exit via `--rm`. That cleanup does **not** fire if the
job is killed abnormally — e.g. the Docker daemon restarts mid-job, or the host
is hard-rebooted. You may then find a leftover `din-worker-*` container.

```bash
# 1. See what's there
docker ps -a --filter "name=din-worker-"

# 2. Stop it if still running, then remove it
docker stop <container-name>      # only if STATUS shows it Up
docker rm   <container-name>

# Or clear all *exited* DIN workers at once (does not touch running ones):
docker ps -aq --filter "name=din-worker-" --filter "status=exited" | xargs -r docker rm
```

Removing an **exited or orphaned** worker is safe: workers are stateless and
write all output to the bind-mounted state dir, not into the container, so a new
job just spawns a fresh worker. **But do not blindly `docker stop` a *running*
worker** — that kills the active job and can leave partial/half-written output in
the state dir. Only stop a running worker once you've confirmed no job should
still be in flight (check `docker ps --filter "name=din-worker-"` and your own
job status first).

---

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `docker compose` aborts: *"set DIN_STATE_DIR…"* | `DIN_STATE_DIR` unset in `.env`. Set it to an absolute path. |
| Worker mounts behave oddly / state in an unexpected place | `DIN_STATE_DIR` must be an **absolute** path. Compose requires the var but does not check absoluteness — a relative value resolves unpredictably. Use a full path like `/home/you/.din-node`. |
| Inside the container: `permission denied … /var/run/docker.sock` | `DOCKER_GID` doesn't match the host. Re-run `stat -c '%g' /var/run/docker.sock`, fix `.env`, `docker compose up -d`. |
| Worker runs but sees no model files / empty inputs | A path mismatch — `DIN_STATE_DIR` must be bind-mounted at the identical path (don't switch it to a named volume). |
| Worker output / state files owned by `root` on the host | `DIN_UID`/`DIN_GID` don't match your host user. Set them to `id -u`/`id -g`, recreate the container, `chown` the dir. |
| First job is slow / streams a huge build context | `din-worker:dev` wasn't pre-built on the host. See setup step 3. |

---

## Scope and limitations (devnet)

- Not included (later roadmap phases): `/health` endpoint, structured JSON logs,
  graceful `SIGTERM` handling, `systemd`/`launchd` units, vault / remote-signer
  integration.
- The `docker.sock` exposure above is accepted for devnet, not solved.
- Image pins Python (`3.12-slim`) and `dincli` (built from source, deps pinned via
  `dincli/requirements.txt`). For stricter reproducibility, pin the base image by
  digest and `docker-ce-cli` to an exact version.
