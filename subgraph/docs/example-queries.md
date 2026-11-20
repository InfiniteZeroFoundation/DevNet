# DIN Protocol subgraph — example queries

All queries run against the local GraphQL playground at
`http://localhost:8000/subgraphs/name/din-protocol/graphql` once the stack
from `subgraph/docker-compose.yml` is up and the subgraph is deployed. The
subgraph indexes six platform contracts plus the per-model
`DINTaskCoordinator`/`DINTaskAuditor` templates.

---

## 1. Validator registry

### All active validators with stake summary

```graphql
{
  validators(
    where: { status: "Active" }
    orderBy: activeStake
    orderDirection: desc
    first: 50
  ) {
    id
    activeStake
    totalStaked
    totalSlashed
    status
  }
}
```

### Validators currently in the exit queue (unbonding)

```graphql
{
  validators(where: { status: "Exiting" }) {
    id
    activeStake
    pendingWithdrawal
    withdrawAvailableAt
  }
}
```

### All blacklisted validators

```graphql
{
  validators(where: { blacklisted: true }) {
    id
    totalSlashed
    status
  }
}
```

---

## 2. Model registry

### All pending model registration requests

```graphql
{
  modelRegistrationRequests(
    where: { processed: false }
    orderBy: submittedAtTimestamp
    orderDirection: asc
    first: 100
  ) {
    requestId
    requester
    isOpenSource
    feePaid
    submittedAtTimestamp
  }
}
```

### All approved models (open-source only)

```graphql
{
  models(
    where: { isOpenSource: true, disabled: false }
    orderBy: createdAtTimestamp
    orderDirection: desc
    first: 50
  ) {
    modelId
    owner
    manifestCID
    taskCoordinator
    createdAtTimestamp
  }
}
```

### Pending manifest update requests for a specific model owner

```graphql
{
  manifestUpdateRequests(
    where: {
      processed: false
      requester: "0xYOUR_ADDRESS_HERE"
    }
    orderBy: submittedAtTimestamp
    orderDirection: asc
  ) {
    requestId
    model { modelId }
    feePaid
    newManifestCID
    submittedAtTimestamp
  }
}
```

### Full request lifecycle for model 0

```graphql
{
  model(id: "0") {
    modelId
    owner
    isOpenSource
    disabled
    registrationRequest {
      requestId
      feePaid
      submittedAtTimestamp
      processedAtTimestamp
    }
    manifestHistory(orderBy: submittedAtTimestamp, orderDirection: asc) {
      requestId
      approved
      submittedAtTimestamp
      processedAtTimestamp
    }
  }
}
```

---

## 3. Slash and reward history

### Full slash history — most recent first

```graphql
{
  slashEvents(
    orderBy: blockTimestamp
    orderDirection: desc
    first: 50
  ) {
    validator { id }
    amount
    reason
    slasherContract
    blockTimestamp
    transactionHash
  }
}
```

### Slash history for a specific validator

```graphql
{
  validator(id: "0xVALIDATOR_ADDRESS_HERE") {
    id
    totalSlashed
    slashEvents(orderBy: blockTimestamp, orderDirection: desc) {
      amount
      reason
      slasherContract
      blockTimestamp
    }
  }
}
```

### All slashes issued by a specific task contract

```graphql
{
  slashEvents(
    where: { slasherContract: "0xTASK_COORDINATOR_ADDRESS_HERE" }
    orderBy: blockTimestamp
    orderDirection: desc
  ) {
    validator { id }
    amount
    reason
    blockTimestamp
  }
}
```

### DIN mint history (ETH deposits) — all time

```graphql
{
  dINMintEvents(
    orderBy: blockTimestamp
    orderDirection: desc
    first: 100
  ) {
    user
    ethAmount
    dinAmount
    blockTimestamp
  }
}
```

### Exchange rate timeline

```graphql
{
  exchangeRateSnapshots(
    orderBy: blockTimestamp
    orderDirection: asc
  ) {
    newRate
    blockTimestamp
    transactionHash
  }
}
```

---

## 4. Authorized slashers

### Currently active slasher contracts (canonical set from DinValidatorStake)

```graphql
{
  slasherRegistrations(
    where: {
      active: true
      sourceContract: "0xDINVALIDATORSTAKE_ADDRESS_HERE"
    }
  ) {
    slasherAddress
    addedAtBlock
    addedAtTimestamp
  }
}
```

### Full slasher audit trail (both DinCoordinator and DinValidatorStake events)

```graphql
{
  slasherRegistrations(orderBy: addedAtTimestamp, orderDirection: asc) {
    slasherAddress
    sourceContract
    active
    addedAtTimestamp
    removedAtTimestamp
  }
}
```

---

## 5. GI lifecycle, commit-reveal, and disputes

### Latest global iterations and their state transitions

```graphql
{
  globalIterations(orderBy: gi, orderDirection: desc, first: 10) {
    gi
    currentState
    ended
    globalModelCID
    startedAtTimestamp
    endedAtTimestamp
    stateTransitions(orderBy: blockTimestamp, orderDirection: asc) {
      newState
      blockTimestamp
    }
  }
}
```

`currentState` is the raw `GIstates` ordinal (`0..28`, `GIended = 28`);
`stateTransitions` gives the full phase timeline.

### Unrevealed audit-score commitments

```graphql
{
  auditScoreCommitments(where: { revealed: false }) {
    auditor
    modelIndex
    commitHash
    blockTimestamp
    globalIteration { gi }
    auditBatch { id }
  }
}
```

### Open test-data disputes

```graphql
{
  testDataDisputes(where: { status: "Open" }) {
    disputer
    bond
    expiresAtBlock
    openedAtTimestamp
    globalIteration { gi }
    auditBatch { id }
  }
}
```

### Open aggregation disputes (T1/T2)

```graphql
{
  aggregationDisputes(where: { status: "Open" }) {
    tierKind
    batchId
    challenger
    bond
    freshAggregators
    openedAtTimestamp
    globalIteration { gi }
  }
}
```

### Auditor score deviations flagged by S3

```graphql
{
  auditorScoreDeviations(where: { exceedsThreshold: true }, orderBy: blockTimestamp, orderDirection: desc) {
    auditor
    modelIndex
    auditorScore
    medianScore
    deviation
    globalIteration { gi }
    auditBatch { id }
  }
}
```

### Seed locks for a GI

```graphql
{
  seedLocks(orderBy: blockTimestamp, orderDirection: asc) {
    kind
    tierKind
    batchId
    seed
    reanchoredAtBlock
    globalIteration { gi }
  }
}
```

---

## 6. Rewards

### Reward deposits and settlement for a GI

```graphql
{
  globalIteration(id: "0xTASK_COORDINATOR_ADDRESS_HERE-0") {
    gi
    rewardDeposits(orderBy: blockTimestamp) {
      depositor
      amount
    }
    rewardSettlements {
      clientPool
      auditorPool
      aggregatorPool
      treasuryShare
    }
  }
}
```

### Reward claims — most recent first

```graphql
{
  rewardClaims(orderBy: blockTimestamp, orderDirection: desc, first: 100) {
    claimant
    amount
    blockTimestamp
    transactionHash
  }
}
```

### Current reward split per task auditor

```graphql
{
  rewardSplits {
    id
    clientBps
    auditorBps
    aggregatorBps
    treasuryBps
    updatedAtTimestamp
  }
}
```

---

## 7. Fee router and treasury

### Current fee-router configuration

```graphql
{
  feeRouterConfigs {
    id
    treasury
    treasuryBpsCeiling
    dinValidatorPoolBps
    dinTreasuryBps
    dinBurnBps
    dinStorageBps
    dinPublicGoodsBps
    ethValidatorPoolBps
    ethTreasuryBps
    ethStorageBps
    ethPublicGoodsBps
    updatedAtTimestamp
  }
}
```

### Recently routed DIN and ETH fees

```graphql
{
  feeRoutedDINs(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    payer
    amount
    burned
    toTreasury
    toValidatorPool
    toStorage
    toPublicGoods
    blockTimestamp
  }
  feeRoutedETHs(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    payer
    amount
    toTreasury
    toValidatorPool
    toStorage
    toPublicGoods
    blockTimestamp
  }
}
```

### Treasury balance movements

```graphql
{
  treasuryEthReceiveds(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    from
    amount
    blockTimestamp
  }
  treasuryEthWithdrawns(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    to
    amount
    blockTimestamp
  }
  treasuryERC20Withdrawns(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    token
    to
    amount
    blockTimestamp
  }
}
```

### Active fee sources

```graphql
{
  feeSources(where: { active: true }) {
    source
    addedAtBlock
    addedAtTimestamp
  }
}
```

---

## 8. Emission and burns

```graphql
{
  emissionMintEvents(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    to
    amount
    blockTimestamp
  }
  mintCapUpdates(orderBy: blockTimestamp, orderDirection: desc, first: 10) {
    newCap
    blockTimestamp
  }
  tokenBurnEvents(orderBy: blockTimestamp, orderDirection: desc, first: 50) {
    from
    amount
    blockTimestamp
  }
}
```
