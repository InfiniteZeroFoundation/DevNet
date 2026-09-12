

Here is how to build your images, run the `din-node` container, and monitor Docker in real time.

---

### Step 1: First-Time Setup & Configuration

1. **Navigate to the node docker directory:**
   ```bash
   cd /path/to/devnet/dincli/docker/node
   ```

2. **Configure the environment file:**
   Copy the example file to `.env`:
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` and fill in your host values:**
   * **`DIN_STATE_DIR`**: Set this to an **absolute** path on your host (e.g., `/home/<user>/.din-node`).
   * **`DOCKER_GID`**: Retrieve the GID of `/var/run/docker.sock` by running:
     ```bash
     stat -c '%g' /var/run/docker.sock
     ```
   * **`DIN_UID` / `DIN_GID`**: Retrieve your host user's UID and GID by running:
     ```bash
     id -u
     id -g
     ```

4. **Create the state directory and set proper ownership:**
   ```bash
   source .env
   mkdir -p "$DIN_STATE_DIR"
   sudo chown -R "$DIN_UID:$DIN_GID" "$DIN_STATE_DIR"
   ```

---

### Step 2: Building the Images

1. **Pre-build the Worker Image (`din-worker:dev`):**
   Run the build from the repository root `/path/to/devnet`. Doing this on the host is highly recommended to speed up execution:
   ```bash
   cd /path/to/devnet
   docker build -f dincli/docker/worker/Dockerfile -t din-worker:dev .
   ```

2. **Build the Node Image (`din-node:dev`):**
   Navigate back and build the `din-node` container using Docker Compose:
   ```bash
   cd /path/to/devnet/dincli/docker/node
   docker compose build
   ```

---

### Step 3: Running the Node Container

1. **Start the container in detached mode:**
   ```bash
   docker compose up -d
   ```

2. **Verify it is running:**
   ```bash
   docker compose ps
   ```

3. **Initialize and configure `dincli` inside the container:**
   ```bash
   # Initialize system
   docker compose exec din-node dincli system init
   
   # Set the network
   docker compose exec din-node dincli system configure-network --network sepolia_devnet 

   # Configure demo wallet (or use register-wallet for your own keys)
   docker compose exec din-node dincli system configure-demo --mode yes
   ```
   > **Production validators:** Import an encrypted keystore instead of demo mode.
   > See [wallet-setup.md](../../public/guides/wallet-setup.md) and
   > [keystore-migration.md](../../public/guides/keystore-migration.md).
   
---

### Step 4: Monitoring Docker in Real Time

Choose one or more of these options to monitor activity:

1. **Monitor `din-node` logs in real time:**
   ```bash
   docker compose logs -f din-node
   ```

2. **Monitor container lists in real time (shows active jobs/workers):**
   ```bash
   watch -n 1 'docker ps -a --filter "name=din-"'
   ```

3. **Monitor CPU, memory, and network usage in real time:**
   ```bash
   docker stats
   ```

4. **Monitor Docker daemon engine events (creations, destructions, and starts):**
   ```bash
   docker events
   ```

---


## Hardhat Configuration

in ~/.din-node

run

```bash
cd ~/.din-node
mkdir hardhat
cd hardhat
npm init

npm install hardhat --save-dev
npx hardhat init

mkdir contracts


```

### Summary of Files Read
* [dincli/docker/node/README.md](../../../dincli/docker/node/README.md) — The operator runbook with architecture overview and commands.
* [dincli/docker/node/Dockerfile](../../../dincli/docker/node/Dockerfile) — Standard multi-stage build configuration mapping `dincli` control plane.
* [dincli/docker/node/docker-compose.yml](../../../dincli/docker/node/docker-compose.yml) — Compose specification detailing environment variable interpolation and bind mounts.