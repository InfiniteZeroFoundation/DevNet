# InfiniteZero Network — DevNet

> **Open infrastructure for training AI as a public good.**

InfiniteZero is building the commons for AI — the way the internet itself is a public good. Millions of devices contribute quietly to shared AI models, with raw data never leaving the user's device. Only anonymised, encrypted patterns join the network.

This repository contains the DevNet setup and tooling for developers building on the InfiniteZero Network protocol.

> Built on Ethereum. Governed by the community. Models belong to the commons.

---

## Overview

This project consists of multiple components:

- **CLI**: `dincli` is a command line interface for interacting with the InfiniteZero Network
- **Hardhat Node**: Runs in the background for contracts compilation
- **IPFS Daemon**: Runs in the background

---

## How to Install dincli

1. Navigate to your project directory
2. Activate your virtual environment
3. Install `dincli` via pip:

   ```bash
   pip install dincli
   ```

   or

   ```bash
   pip install git+https://github.com/InfiniteZeroFoundation/dincli.git
   ```

4. Verify the installation:

   ```bash
   dincli --version
   ```

   or

   ```bash
   dincli system welcome
   ```

---

## Configure Either Local or IPFS API

### Configure Local IPFS API

1. Install IPFS
2. Start IPFS daemon
3. Navigate to the project directory
4. Add `ipfs_api_url_add` in `.env`:

   ```bash
   IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0/add
   ```

5. Add `ipfs_api_url_retrieve` in `.env`:

   ```bash
   IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0/cat/
   ```

### Configure IPFS API

1. Navigate to the project directory
2. Add `ipfs_api_url_add` in `.env`:

   ```bash
   IPFS_API_URL_ADD=https://ipfs.infura.io:5001/api/v0/add
   ```

3. Add `ipfs_api_url_retrieve` in `.env`:

   ```bash
   IPFS_API_URL_RETRIEVE=https://ipfs.infura.io:5001/api/v0/cat/
   ```

---

## Set Log Level

1. Navigate to the project directory
2. Execute:

   ```bash
   dincli system configure-logging --level info
   ```

---

## Sample manifest_CID

```
QmQaPUfVAyQBrkRvHZWyH8tbNukmcgEmghYFGZA6LKo8tp
```

---

## IPFS Upload

```bash
python -m dincli.main ipfs upload -f /home/azureuser/projects/devnet/cache_model_0/manifest.json
```

---

## Copy Commands

```bash
cp /home/azureuser/.cache/dincli/local/model_0/manifest.json /home/azureuser/projects/devnet/cache_model_0/manifest.json

cp /home/azureuser/.cache/dincli/local/model_0/services/modelowner.py /home/azureuser/projects/devnet/cache_model_0/services/modelowner.py

cp /home/azureuser/.cache/dincli/local/model_0/services/client.py /home/azureuser/projects/devnet/cache_model_0/services/client.py

cp /home/azureuser/.cache/dincli/local/model_0/services/auditor.py /home/azureuser/projects/devnet/cache_model_0/services/auditor.py

cp /home/azureuser/.cache/dincli/local/model_0/services/aggregator.py /home/azureuser/projects/devnet/cache_model_0/services/aggregator.py

cp /home/azureuser/.cache/dincli/local/model_0/services/model.py /home/azureuser/projects/devnet/cache_model_0/services/model.py

mkdir -p /home/azureuser/projects/devnet/cache_model_0/dataset/test
cp /home/azureuser/.cache/dincli/local/model_0/dataset/test/test_dataset.pt /home/azureuser/projects/devnet/cache_model_0/dataset/test/test_dataset.pt
```

---

## DevNet Setup

### Kill existing process on port 8545

```bash
lsof -ti:8545 | xargs kill -9
```

### Start IPFS Daemon

```bash
ipfs daemon
```

### 1. Navigate to the project directory

```bash
cd /home/azureuser/projects/devnet
```

### 2. Start the Hardhat Node

**Directory:** `./hardhat`

```bash
cd ./hardhat
npx hardhat node
npx hardhat compile
```

### 3. Run dincli

```bash
source /home/azureuser/projects/pyDIN/.pyDIN/bin/activate
python -m dincli.main --help
python -m dincli.main system configure-network --network local
```

---

## How to Setup Project Directories from Scratch

```bash
cd /home/dinsystems/projects/devnet
```

### Hardhat

```bash
cd ./hardhat
npm init -y
npm install --save-dev hardhat
npx hardhat init
```

### IPFS

```bash
sudo apt update && sudo apt upgrade -y
wget https://dist.ipfs.tech/kubo/latest/kubo-linux-amd64.tar.gz
tar -xvzf kubo-linux-amd64.tar.gz
sudo mv kubo/ipfs /usr/local/bin/
ipfs --version
ipfs init
ipfs daemon
```

---

## Dependencies (Assuming Ubuntu OS)

### Install Python (if needed)

```bash
sudo apt-get install python3
```

### Installing NVM (Node Version Manager)

#### Step 1: Install NVM

Using `curl`:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
```

Or using `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
```

#### Step 2: Update Shell Configuration

Add the following lines to your shell configuration file (`~/.bashrc`, `~/.zshrc`, or `~/.bash_profile`):

```bash
export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
```

For `.bashrc` or `.zshrc`:

```bash
echo 'export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"' >> ~/.bashrc
echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.bashrc
```

Or for `zsh` users:

```bash
echo 'export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"' >> ~/.zshrc
echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.zshrc
```

#### Step 3: Reload Your Shell Configuration

For `bash`:

```bash
source ~/.bashrc
```

Or for `zsh`:

```bash
source ~/.zshrc
```

#### Step 4: Verify Installation

```bash
nvm --version
```

If everything went well, you should see the version number of NVM printed in your terminal. You're now ready to use NVM to manage different versions of Node.js!

### Install Node.js v20.18.1 via NVM

```bash
nvm install v20.18.1
node -v
```

---

## Learn More

- [White Paper](#)
- [Documentation](#)
- [API Reference](#)
- [SDK](#)
