import re
import os
import pytest
import json
import shutil
import mock
from dincli.cli.context import DinContext
from dincli.cli.utils import get_env_key, CACHE_DIR
from .test_utils import get_usdt_balance
from pathlib import Path

# Define constants for paths
PROJECT_ROOT = Path("/home/azureuser/projects/DINv1MVC")
HARDHAT_ARTIFACTS = PROJECT_ROOT / Path("hardhat/artifacts/contracts")

ctx = mock.Mock()
ctx.obj = DinContext()
NETWORK = "local"
ctx.obj.select_network(NETWORK)

def test_run_g0_flow(cli_cmd):
    """
    Replicates the workflow from bashscripts/runG0.sh
    """

    # 13: show python -m dincli.main system where
    cli_cmd(["system", "where"])

    # 21: show python -m dincli.main system connect-wallet --account 0
    cli_cmd(["system", "connect-wallet", "--account", "0"])

    # 22: show python -m dincli.main dindao deploy din-coordinator --artifact ...
    din_coord_artifact = str(HARDHAT_ARTIFACTS / Path("DinCoordinator.sol/DinCoordinator.json"))
    cli_cmd(["dindao", "deploy", "din-coordinator", "--artifact", din_coord_artifact])

    # 24: show python -m dincli.main system dump-abi --official --artifact ...
    cli_cmd(["system", "dump-abi", "--official", "--artifact", din_coord_artifact])

    # 26: show python -m dincli.main system dump-abi --official --artifact ... (DinToken)
    din_token_artifact = str(HARDHAT_ARTIFACTS / Path("DinToken.sol/DinToken.json"))
    cli_cmd(["system", "dump-abi", "--official", "--artifact", din_token_artifact])

    # 28: show python -m dincli.main dindao deploy din-validator-stake --artifact ...
    din_stake_artifact = str(HARDHAT_ARTIFACTS / Path("DinValidatorStake.sol/DinValidatorStake.json"))
    cli_cmd(["dindao", "deploy", "din-validator-stake", "--artifact", din_stake_artifact])

    # 30: show python -m dincli.main system dump-abi --official --artifact ...
    cli_cmd(["system", "dump-abi", "--official", "--artifact", din_stake_artifact])

    # 32: show python -m dincli.main dindao deploy din-model-registry --artifact ...
    din_registry_artifact = str(HARDHAT_ARTIFACTS / Path("DINModelRegistry.sol/DINModelRegistry.json"))
    cli_cmd(["dindao", "deploy", "din-model-registry", "--artifact", din_registry_artifact])

    # 34: show python -m dincli.main system dump-abi --official --artifact ...
    cli_cmd(["system", "dump-abi", "--official", "--artifact", din_registry_artifact])

    # 36: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 37: show python -m dincli.main system --eth-balance --usdt-balance
    cli_cmd(["system", "--eth-balance", "--usdt-balance"])

    usdt_balance_curr = get_usdt_balance(ctx)
    target_usdt_balance = usdt_balance_curr + 3000
    
    while get_usdt_balance(ctx) < target_usdt_balance:
        # 39: show python -m dincli.main system buy-usdt 3000 --yes
        try:
            cli_cmd(["system", "buy-usdt", "3000", "--yes"])
        except Exception as e:
            print(f"[red]Error buying USDT: {e}[/red]")

        usdt_balance_new = get_usdt_balance(ctx)
        if usdt_balance_new >= target_usdt_balance:
            break
    assert get_usdt_balance(ctx) >= target_usdt_balance

    # 42: show python -m dincli.main model-owner deploy task-coordinator --artifact ...
    task_coord_artifact = str(HARDHAT_ARTIFACTS / Path("DINTaskCoordinator.sol/DINTaskCoordinator.json"))
    cli_cmd(["model-owner", "deploy", "task-coordinator", "--artifact", task_coord_artifact])

    # 44: show python -m dincli.main system dump-abi --artifact ... --official
    cli_cmd(["system", "dump-abi", "--artifact", task_coord_artifact, "--official"])

    # 46: show python -m dincli.main model-owner deploy task-auditor --artifact ...
    task_auditor_artifact = str(HARDHAT_ARTIFACTS / Path("DINTaskAuditor.sol/DINTaskAuditor.json"))
    cli_cmd(["model-owner", "deploy", "task-auditor", "--artifact", task_auditor_artifact])

    # 48: show python -m dincli.main system dump-abi --artifact ... --official
    cli_cmd(["system", "dump-abi", "--artifact", task_auditor_artifact, "--official"])

    # 52: show python -m dincli.main model-owner deposit-reward-in-dintask-auditor --amount 1000
    cli_cmd(["model-owner", "deposit-reward-in-dintask-auditor", "--amount", "1000"])

    # 54: show python -m dincli.main system connect-wallet --account 0
    cli_cmd(["system", "connect-wallet", "--account", "0"])

    # 56: show python -m dincli.main dindao add-slasher --taskCoordinator
    cli_cmd(["dindao", "add-slasher", "--taskCoordinator"])

    # 58: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 60: show python -m dincli.main model-owner add-slasher --taskCoordinator
    cli_cmd(["model-owner", "add-slasher", "--taskCoordinator"])

    # 62: show python -m dincli.main system connect-wallet --account 0
    cli_cmd(["system", "connect-wallet", "--account", "0"])

    # 64: show python -m dincli.main dindao add-slasher --taskAuditor
    cli_cmd(["dindao", "add-slasher", "--taskAuditor"])

    # 67: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 69: show python -m dincli.main model-owner add-slasher --taskAuditor
    cli_cmd(["model-owner", "add-slasher", "--taskAuditor"])

    # 74: show python -m dincli.main system connect-wallet --account 1
    cli_cmd(["system", "connect-wallet", "--account", "1"])

    # 79: show python -m dincli.main model-owner model create-genesis
    # Manual step from bash script:
    # mkdir -p /home/azureuser/projects/DINv1MVC/tasks/local/<address>
    # cp /home/azureuser/.cache/dincli/local/model_0/manifest.json ...

    # 1. Get Task Coordinator Address from .env
    task_coord_address = get_env_key(ctx.obj.network.upper() + "_DINTaskCoordinator_Contract_Address")
    if not task_coord_address:
        pytest.fail(f"Could not find {ctx.obj.network.upper()}_DINTaskCoordinator_Contract_Address in .env")
    print(f"Found Task Coordinator Address: {task_coord_address}")

    task_auditor_address = get_env_key(ctx.obj.network.upper() + "_"+task_coord_address+"_DINTaskAuditor_Contract_Address")
    if not task_auditor_address:
        pytest.fail(f"Could not find {ctx.obj.network.upper()}_"+task_coord_address+"_DINTaskAuditor_Contract_Address in .env")
    print(f"Found Task Auditor Address: {task_auditor_address}")

    # 2. Create directory

    tasks_dir = PROJECT_ROOT / Path(f"tasks/{ctx.obj.network.lower()}") / task_coord_address
    os.makedirs(tasks_dir, exist_ok=True)
    
    # 3. Copy manifest
    source_manifest =  Path(f"/home/azureuser/projects/DINv1MVC/cache_model_0/manifest.json")
    if not os.path.exists(source_manifest):
         pytest.fail(f"Source manifest not found at {source_manifest}")

    target_manifest = os.path.join(tasks_dir, "manifest.json")
    shutil.copy(source_manifest, target_manifest)
    print(f"Copied manifest to {target_manifest}")

    cli_cmd(["model-owner", "model", "create-genesis"])

    source_test_dataset =  Path(f"/home/azureuser/projects/DINv1MVC/cache_model_0/dataset/test/test_dataset.pt")
    if not os.path.exists(source_test_dataset):
         pytest.fail(f"Source test dataset not found at {source_test_dataset}")

    target_test_dataset = Path(tasks_dir) / "dataset" / "test" / "test_dataset.pt"

    target_test_dataset.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_test_dataset, target_test_dataset)
    print(f"Copied test dataset to {target_test_dataset}")


    # 88: show python -m dincli.main model-owner model submit-genesis --network local
    cli_cmd(["model-owner", "model", "submit-genesis"])

    genesis_model_ipfs_hash = get_env_key(ctx.obj.network.upper() + "_" + task_coord_address + "_GENESIS_MODEL_IPFS_HASH")
    if not genesis_model_ipfs_hash:
        pytest.fail(f"Could not find {ctx.obj.network.upper()}_{task_coord_address}_GENESIS_MODEL_IPFS_HASH in .env")
    print(f"Found Genesis Model IPFS Hash: {genesis_model_ipfs_hash}")


    with open(target_manifest, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    manifest_data["DINTaskCoordinator_Contract"] = task_coord_address
    manifest_data["DINTaskAuditor_Contract"] = task_auditor_address
    manifest_data["Genesis_Model_CID"] = genesis_model_ipfs_hash

    with open(target_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    print(f"Updated manifest at {target_manifest}")
    # 90: show python -m dincli.main task model-owner register --network local
    cli_cmd(["task", "model-owner", "register"])

    # 92: show python -m dincli.main system connect-wallet --account 0
    cli_cmd(["system", "connect-wallet", "--account", "0"])

    

    # 94: show python -m dincli.main dindao registry total-models --network local
    cli_cmd(["dindao", "registry", "total-models"])

    # 96: show python -m dincli.main task explore 0
    cli_cmd(["task", "explore", "0"])
