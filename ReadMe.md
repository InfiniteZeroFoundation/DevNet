# overview
This project consists of multiple components.

- **CLI**: dincli is a command line interface for interacting with the DIN P2 project
- **Hardhat Node:**: hardhat node runs in a background for contracts compilation 
- **IPFS Daemon:**: Runs in a background 


# how to install dincli

1. Navigate to your project directory
2. Activate your virtual environment
3. Install dincli via pip 
   ```bash
   pip install dincli
   ```

   or

   ```bash
   pip install git+https://github.com/InfiniteZeroFoundation/dincli.git
   ```

4. Verify the installation
   ```bash
   dincli --version
   ```

   or

   ```bash
   dincli system welcome
   ```

# Configure Either Local or IPFS API

## Configure Local IPFS API
1. Install IPFS
2. Start IPFS daemon
3. Navigate to the project directory
4. Add ipfs_api_url_add in .env. Example: 
   ```bash
   IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0/add
   ```
5. Add ipfs_api_url_retrieve in .env. Example: 
   ```bash
   IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0/cat/
   ```

## Configure IPFS API
1. Navigate to the project directory
2. Add ipfs_api_url_add in .env example 
   ```bash
   IPFS_API_URL_ADD=https://ipfs.infura.io:5001/api/v0/add
   ```
3. Add ipfs_api_url_retrieve in .env example 
   ```bash
   IPFS_API_URL_RETRIEVE=https://ipfs.infura.io:5001/api/v0/cat/
   ```


# set log level
1. Navigate to the project directory
2. execute
   ```bash
   dincli system configure-logging --level info
   ```

# Sample manifest_CID
QmQaPUfVAyQBrkRvHZWyH8tbNukmcgEmghYFGZA6LKo8tp

# ipfs upload

python -m dincli.main ipfs upload -f /home/azureuser/projects/DINv1MVC/cache_model_0/manifest.json

# cp 

cp /home/azureuser/.cache/dincli/local/model_0/manifest.json /home/azureuser/projects/DINv1MVC/cache_model_0/manifest.json

cp /home/azureuser/.cache/dincli/local/model_0/services/modelowner.py /home/azureuser/projects/DINv1MVC/cache_model_0/services/modelowner.py

cp /home/azureuser/.cache/dincli/local/model_0/services/client.py /home/azureuser/projects/DINv1MVC/cache_model_0/services/client.py

cp /home/azureuser/.cache/dincli/local/model_0/services/auditor.py /home/azureuser/projects/DINv1MVC/cache_model_0/services/auditor.py

cp /home/azureuser/.cache/dincli/local/model_0/services/aggregator.py /home/azureuser/projects/DINv1MVC/cache_model_0/services/aggregator.py

cp /home/azureuser/.cache/dincli/local/model_0/services/model.py /home/azureuser/projects/DINv1MVC/cache_model_0/services/model.py

mkdir -p /home/azureuser/projects/DINv1MVC/cache_model_0/dataset/test
cp /home/azureuser/.cache/dincli/local/model_0/dataset/test/test_dataset.pt /home/azureuser/projects/DINv1MVC/cache_model_0/dataset/test/test_dataset.pt






# DIN P2 Project Setup
lsof -ti:8545 | xargs kill -9

ipfs daemon


1. **Navigate to the project directory:**
   ```bash
   cd /home/azureuser/projects/DINv1MVC
   ```

2. **Start the Hardhat Node:**
   - **Directory:** `./hardhat`
   - **Start Command:**
     ```bash
     cd ./hardhat
     npx hardhat node
     npx hardhat compile
     ```

3. running the dincli
source /home/azureuser/projects/pyDIN/.pyDIN/bin/activate
python -m dincli.main --help
python -m dincli.main system configure-network --network local








## How to Setup Project directories from scratch

```bash
cd /home/dinsystems/projects/DINv1MVC
```

### hardhat

```bash
cd ./hardhat
npm init -y
npm install --save-dev hardhat
npx hardhat init
```

### ipfs
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


---
## Dependencies (Assuming Ubuntu OS)

- **install python if needed**
   ```bash
   sudo apt-get install python3
   ```

- Installing NVM (Node Version Manager)

    To install **NVM** (Node Version Manager), follow the steps below:

    ### Step 1: Install NVM

    Run one of the following commands in your terminal to download and install NVM:

    #### Using `curl`:
    ```bash
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
    ```

    #### Or using `wget`:
    ```bash
    wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
    ```

    ### Step 2: Update Shell Configuration

    After running the installation script, you need to add the following lines to your shell configuration file (`~/.bashrc`, `~/.zshrc`, or `~/.bash_profile` depending on your shell):

    ```bash
    export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
    ```

    ### Example for `.bashrc` or `.zshrc`:
    ```bash
    echo 'export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"' >> ~/.bashrc
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.bashrc
    ```

    Or for `zsh` users:
    ```bash
    echo 'export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"' >> ~/.zshrc
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.zshrc
    ```

    ### Step 3: Reload Your Shell Configuration

    Once you've added the necessary lines to your shell configuration file, reload it by running:

    For `bash`:
    ```bash
    source ~/.bashrc
    ```

    Or for `zsh`:
    ```bash
    source ~/.zshrc
    ```

    ### Step 4: Verify Installation

    Finally, verify that NVM was installed correctly by checking its version:

    ```bash
    nvm --version
    ```

    If everything went well, you should see the version number of NVM printed in your terminal.


    You're now ready to use NVM to manage different versions of Node.js!

- **Install Node.js v20.18.1 via NVM**
   ```bash
   nvm install v20.18.1
   node -v
   ```

   ---