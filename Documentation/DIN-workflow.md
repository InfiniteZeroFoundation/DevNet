# DIN Protocol

In this guide we will describe the workflow of the DIN Protocol.

DIN-Representative (later DIN-DAO) is a entity that is authorized to perform certain actions on behalf of the DIN Protocol. 

DIN-Representative has deployed the following DIN Protocol contracts on Sepolia-Optimism testnet as part of DIN-devnet:

1. DinCoordinator
2. DinToken
3. DinValidatorStake
4. DinModelRegistry


## DinCoordinator

DinCoordinator is the main contract that coordinates the DIN Protocol. 

1. It sets the exchange rate (1 ETH = 1M DIN tokens) between ETH and DIN tokens.(tentative workaround for now)
2. It mints DIN tokens to users (e.g. auditors / clients / aggregators) who deposit ETH via DinToken contract.
3. It allows DIN-Representative to withdraw ETH.
4. It allows DIN-Representative to add/remove slasher contracts (Model / Task level Contracts) on validator stake contract.
5. It allows DIN-Representative to update the exchange rate.
6. It allows DIN-Representative to set the validator stake contract.


## DinToken

DinToken is an ERC20-compliant token that is used in the DIN Protocol. 

1. It allows users to deposit ETH on the DinCoordinator contract and mint DIN tokens.

> [!NOTE]
> In future, we are planning to use a DEX (e.g. Uniswap V3) for the exchange of ETH and DIN tokens.

## DinValidatorStake

DinValidatorStake is a contract that allows validators to stake DIN tokens as collateral.

1. It allows validators (e.g. auditors / aggregators) to stake DIN tokens.
2. The minimum stake amount `MIN_STAKE` is 10 DIN tokens as of now.
3. It allows validators to unstake (withdraw their staked) DIN tokens.
4. If the validator's stake falls below the minimum stake amount, the validator will be automatically unregistered.
5. It can blacklist certain addresses (validators)
6. It allows DIN-Representative to add/remove slasher contracts (Model / Task level Contracts) via dinCoordinator contract.
7. It allows the authorized slasher contracts to slash the staked DIN tokens if the validator violates the terms of the DIN Protocol.
8. It allows to query the stake amount of a validator.
9. It allows to check if a contract is registered/ authorized slasher contract.

## DinModelRegistry

DinModelRegistry is a contract that allows users to register their models with the DIN Protocol.

1. It allows model-owners to register their models with the DIN Protocol, where each model is assigned a unique ID. The taskCoordinator and taskAuditor cotracts coressponding to the model must be registered as authorized slasher contracts with the DinValidatorStake contract before registering the model. 
2. The models have two types: 
    a. Open-source models
    b. Proprietary models
3. Proprietary models have a proprietaryFee which is paid by the model-owner to the DIN Protocol, for now it is set to 0.000001 ETH. The fee is used to improve the ecosystem of the DIN Protocol. The trained proprietary models are owned by the model-owner and can be used for commercial purposes.
4. It allows DIN-Representative to update the proprietaryFee.
5. Open-source models do not have any proprietaryFee. They are free to be trained using DIN Protocol. The trained open-source models may be free for universal usage.
6. It allows model-owners to update the manifestCID of their models, potentially changing the model training logic, parameters, etc.
7. It allows to see the total number of models registered with the DIN ModelRegistry contract.
8. It allows DIN-Representative to withdraw the accumulated proprietaryFee from the DIN ModelRegistry contract.
