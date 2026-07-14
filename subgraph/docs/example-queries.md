# DIN Protocol subgraph — example queries

All queries run against the local GraphQL playground at
`http://localhost:8000/subgraphs/name/din-protocol/graphql` once the stack
from `subgraph/docker-compose.yml` is up and the subgraph is deployed.

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
