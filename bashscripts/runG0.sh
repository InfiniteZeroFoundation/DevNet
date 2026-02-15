#!/bin/bash

show() {
    set -x
    "$@"
    { set +x; } 2>/dev/null
}



# show python -m dincli.main system dataset distribute-mnist --seed 42 --network local --test-train 
# show python -m dincli.main system --eth-balance --usdt-balance  --usdt-info --network local
show python -m dincli.main system where
# show python -m dincli.main system reset-all
# show python -m dincli.main system init
# show python -m dincli.main system configure-network  --network local
# show python -m dincli.main system configure-logging --level debug
# show python -m dincli.main system configure-demo --mode yes
# show python -m dincli.main system todo

show python -m dincli.main system connect-wallet --account 0
show python -m dincli.main dindao deploy din-coordinator --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DinCoordinator.sol/DinCoordinator.json"

show python -m dincli.main system dump-abi --official --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DinCoordinator.sol/DinCoordinator.json"

show python -m dincli.main system dump-abi --official --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DinToken.sol/DinToken.json"

show python -m dincli.main dindao deploy din-validator-stake --network local --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DinValidatorStake.sol/DinValidatorStake.json"

show python -m dincli.main system dump-abi --official --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DinValidatorStake.sol/DinValidatorStake.json"

show python -m dincli.main dindao deploy din-model-registry --network local --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINModelRegistry.sol/DINModelRegistry.json"

show python -m dincli.main system dump-abi --official --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINModelRegistry.sol/DINModelRegistry.json"

show python -m dincli.main system connect-wallet --account 1
show python -m dincli.main system --eth-balance --usdt-balance 

show python -m dincli.main system buy-usdt 3000 --network local --yes


show python -m dincli.main model-owner deploy task-coordinator --network local --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINTaskCoordinator.sol/DINTaskCoordinator.json"

show python -m dincli.main system dump-abi --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINTaskCoordinator.sol/DINTaskCoordinator.json" --official

show python -m dincli.main model-owner deploy task-auditor --network local --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINTaskAuditor.sol/DINTaskAuditor.json"

show python -m dincli.main system dump-abi --artifact "/home/azureuser/projects/DINv1MVC/hardhat/artifacts/contracts/DINTaskAuditor.sol/DINTaskAuditor.json" --official



show python -m dincli.main model-owner deposit-reward-in-dintask-auditor --network local --amount 1000 

show python -m dincli.main system connect-wallet --account 0

show python -m dincli.main dindao add-slasher --taskCoordinator --network local

show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner add-slasher --taskCoordinator --network local 

show python -m dincli.main system connect-wallet --account 0

show python -m dincli.main dindao add-slasher --taskAuditor --network local


show python -m dincli.main system connect-wallet --account 1

show python -m dincli.main model-owner add-slasher --taskAuditor --network local 




show python -m dincli.main system connect-wallet --account 1




show python -m dincli.main model-owner model create-genesis --network local 

# mkdir -p /home/azureuser/projects/DINv1MVC/tasks/local/0xB52A53a86Aec43Efc597EBdf338502ab8635c769

# cp /home/azureuser/.cache/dincli/local/model_0/manifest.json /home/azureuser/projects/DINv1MVC/tasks/local/0xB52A53a86Aec43Efc597EBdf338502ab8635c769/manifest.json

# show python -m dincli.main system dataset distribute-mnist --seed 42 --network local --test-train --task 


show python -m dincli.main model-owner model submit-genesis --network local 

show python -m dincli.main task model-owner register --network local 

show python -m dincli.main system connect-wallet --account 0

show python -m dincli.main dindao registry total-models --network local

show python -m dincli.main task explore 0 


