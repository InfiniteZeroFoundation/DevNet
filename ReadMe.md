# DIN v1 MVC Project Setup
This project consists of multiple components. Follow the instructions below to start each service. you can do it following instructions in the dependency section below. Project description is also available in a section below.

## Project Structure

- **React App:** `./frontend`
- **FastAPI Server:** `./fastapi/pyapp`
- **Hardhat Node:** `./hardhat`
- **IPFS Daemon:** Runs as a background process

---

## How to Start the Project Services

1. **Navigate to the project directory:**
   ```bash
   cd /home/audumlabs/projects/DINv1MVC
   ```

2. **Start the React App:**
   - **Directory:** `./frontend`
   - **Start Command:**
     ```bash
     cd ./frontend
     npm start
     ```
   - **Access:** Open your browser and navigate to [http://localhost:3000](http://localhost:3000).

3. **Start the FastAPI Server:**
   - **Directory:** `./fastapi/pyapp`
   - **Start Command:**
     ```bash
     source /home/audumlabs/projects/pyDIN/.pyDIN/bin/activate
     cd ./fastapi/pyapp
     uvicorn main:app --host 0.0.0.0 --port 8000 --reload
     ```
   - **Access:** API available at [http://localhost:8000](http://localhost:8000).

4. **Start the Hardhat Node:**
   - **Directory:** `./hardhat`
   - **Start Command:**
     ```bash
     cd ./hardhat
     npx hardhat node
     npx hardhat compile
     ```
   - **RPC Port:** The Hardhat node will start a blockchain node with RPC available at port **8545** ([http://localhost:8545](http://localhost:8545)).

5. **Start the IPFS Daemon:**
   - **Start Command:**
     ```bash
     ipfs daemon
     ```
   - **The IPFS daemon will run as a background process and will use the default port 5001** ([http://localhost:5001](http://localhost:5001)).

---

## How to Setup Project directories from scratch

```bash
cd /home/audumlabs/projects/DINv1MVC
```

### hardhat

```bash
cd ./hardhat
npm init -y
npm install --save-dev hardhat
npx hardhat init
```

### fastapi

```bash
python3 --version
cd /home/audumlabs/projects/pyDIN
python -m venv .pyDIN
cd /home/audumlabs/projects/DINv1MVC/fastapi/
source /home/audumlabs/projects/pyDIN/.pyDIN/bin/activate
pip install fastapi uvicorn 
pip freeze > requirements.txt
pip install -r requirements.txt
mkdir pyapp
cd ./pyapp
mkdir Dataset
mkdir Dataset/clients
mkdir Dataset/train
mkdir Dataset/test
mkdir data
mkdir models
mkdir models/clients
mkdir models/modelowner
mkdir models/validators
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

### react
```bash
cd ./DINv1MVC
npx create-react-app frontend
cd ./frontend
npm install
```
---

### Reset Dataset

```bash
cd /home/audumlabs/projects/DINv1MVC/fastapi/pyapp
rm -rf Dataset/clients/*
rm -rf Dataset/train/*
rm -rf Dataset/test/*
rm -rf data/*
```

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