# DIN Protocol

In this guide we will describe the workflow of the DIN Protocol.

DIN-Representative (later DIN-DAO) is an entity that is authorized to perform certain actions on behalf of the DIN Protocol. 

The DIN-Representative deploys the seven DIN platform contracts, each behind a transparent proxy (`foundry/script/DeployPlatform.s.sol`), and imports their addresses into dincli with `dincli system import-deployments`:

1. DinCoordinator
2. DinToken
3. DinValidatorStake
4. DinModelRegistry
5. DinTreasury — custodial holding contract for ETH and ERC20 assets
6. DinFeeRouter — splits the protocol fees swept to it (ETH and DIN) between the treasury and the other fee buckets
7. DinEmission — the per-GI protocol reward subsidy, on a geometric decay schedule; a model owner can fund a GI's reward pool from it (`dincli model-owner rewards fund-emission`)

`dincli system din-info` prints the deployed addresses for the active network.


## DinCoordinator

DinCoordinator is the main contract that coordinates the DIN Protocol. 

1. It sets the exchange rate between ETH and DIN tokens (1 ETH = 1M DIN by default; a tentative workaround for now).
2. It mints DIN tokens to users (e.g. auditors / clients / aggregators) who deposit ETH (`depositAndMint`, `dincli dintoken buy`).
3. It allows DIN-Representative to sweep the ETH received from DIN purchases to the fee router (`dincli dinrep coordinator sweep-fees`).
4. It allows DIN-Representative to add/remove slasher contracts (Model / Task level Contracts) on validator stake contract.
5. It allows DIN-Representative to update the exchange rate, cap the total DIN that can be minted, and permanently retire the ETH faucet.
6. It allows DIN-Representative to set the validator stake, fee router and emission contracts.


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
5. It allows the stake contract owner to blacklist and unblacklist certain validator addresses directly on `DinValidatorStake`.
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
3. Registration is a request that the DIN-Representative approves; approval assigns the model ID. Each request pays a fee in ETH, whether it is approved or rejected (spam protection). Proprietary models pay more: by default 0.00001 ETH to register (0.000001 ETH per manifest update), against 0.000001 ETH (0.0000001 ETH) for open-source models. The fees are used to improve the ecosystem of the DIN Protocol. The trained proprietary models are owned by the model-owner and can be used for commercial purposes, while trained open-source models may be free for universal usage.
4. It allows DIN-Representative to update all four fees (`dincli dinrep registry set-fees`). `dincli system get-registry-fee` shows the current values.
5. It allows model-owners to request an update to the manifestCID of their models (potentially changing the model training logic, parameters, etc.), which the DIN-Representative approves.
6. It allows to see the total number of models registered with the DIN ModelRegistry contract.
7. It allows DIN-Representative to sweep the accumulated fees from the DIN ModelRegistry contract to the fee router (`dincli dinrep registry sweep-fees`).
