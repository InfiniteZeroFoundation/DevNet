import {
  EthDepositAndDINminted,
  DinPerEthUpdated,
  ValidatorStakeContractUpdated,
  SlasherContractAdded,
  SlasherContractRemoved,
  EmissionMinted,
  EmissionContractUpdated,
  MintCapUpdated,
  FaucetRetiredEvent,
  FeeRouterUpdated,
  FeesSweptToRouter,
} from "../generated/DinCoordinator/DinCoordinator"
import {
  DINMintEvent,
  ExchangeRateSnapshot,
  SlasherRegistration,
  EmissionMintEvent,
  EmissionContractUpdate,
  MintCapUpdate,
  FaucetRetired,
  FeeSweepToRouter,
  FeeRouterUpdate,
} from "../generated/schema"
import { eventId } from "./utils"

// ─── ETH deposits ─────────────────────────────────────────────────────────────

export function handleEthDepositAndDINminted(
  event: EthDepositAndDINminted
): void {
  let e = new DINMintEvent(eventId(event.transaction.hash, event.logIndex))
  e.user            = event.params.user
  e.ethAmount       = event.params.ethAmount
  e.dinAmount       = event.params.mintAmount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Exchange rate ────────────────────────────────────────────────────────────

export function handleDinPerEthUpdated(event: DinPerEthUpdated): void {
  let s = new ExchangeRateSnapshot(
    eventId(event.transaction.hash, event.logIndex)
  )
  s.newRate         = event.params.newRate
  s.blockNumber     = event.block.number
  s.blockTimestamp  = event.block.timestamp
  s.transactionHash = event.transaction.hash
  s.save()
}

// ─── Validator stake contract pointer ────────────────────────────────────────
// No schema entity for this — it is a one-time wiring step in the deployment
// sequence. Log at debug level so it is visible in graph-node output.

export function handleValidatorStakeContractUpdated(
  event: ValidatorStakeContractUpdated
): void {
  // Intentionally a no-op at the entity level.
  // The ValidatorStakeContractUpdated event records the address of the stake
  // contract wired into DinCoordinator. Since this is a one-time deployment
  // step (or extremely rare governance action), storing it in a dedicated
  // entity adds noise without benefit. The graph-node debug log captures it.
}

// ─── Slasher audit trail ──────────────────────────────────────────────────────
//
// DinCoordinator forwards addSlasherContract/removeSlasherContract to
// DinValidatorStake, causing both contracts to emit the same event. These
// handlers record the coordinator-sourced event as an audit-trail entry only.
// The canonical active-slasher set comes from staking.ts handlers.

export function handleCoordinatorSlasherAdded(
  event: SlasherContractAdded
): void {
  let id = event.params.slasher.toHexString() + "-" + event.address.toHexString()
  let s  = new SlasherRegistration(id)
  s.slasherAddress     = event.params.slasher
  s.sourceContract     = event.address
  s.active             = true
  s.addedAtBlock       = event.block.number
  s.addedAtTimestamp   = event.block.timestamp
  s.removedAtBlock     = null
  s.removedAtTimestamp = null
  s.save()
}

export function handleCoordinatorSlasherRemoved(
  event: SlasherContractRemoved
): void {
  let id = event.params.slasher.toHexString() + "-" + event.address.toHexString()
  let s  = SlasherRegistration.load(id)
  if (s == null) return
  s.active             = false
  s.removedAtBlock     = event.block.number
  s.removedAtTimestamp = event.block.timestamp
  s.save()
}

// ─── Emission ─────────────────────────────────────────────────────────────────

export function handleEmissionMinted(event: EmissionMinted): void {
  let e = new EmissionMintEvent(eventId(event.transaction.hash, event.logIndex))
  e.to              = event.params.to
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleEmissionContractUpdated(event: EmissionContractUpdated): void {
  let e = new EmissionContractUpdate(eventId(event.transaction.hash, event.logIndex))
  e.emissionContract = event.params.emissionContract
  e.blockNumber      = event.block.number
  e.blockTimestamp   = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Mint cap and faucet ──────────────────────────────────────────────────────

export function handleMintCapUpdated(event: MintCapUpdated): void {
  let e = new MintCapUpdate(eventId(event.transaction.hash, event.logIndex))
  e.newCap          = event.params.newCap
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleFaucetRetired(event: FaucetRetiredEvent): void {
  let e = new FaucetRetired(eventId(event.transaction.hash, event.logIndex))
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Fee routing ──────────────────────────────────────────────────────────────

export function handleCoordinatorFeeRouterUpdated(event: FeeRouterUpdated): void {
  let u = new FeeRouterUpdate(eventId(event.transaction.hash, event.logIndex))
  u.sourceContract  = event.address
  u.feeRouter       = event.params.feeRouter
  u.blockNumber     = event.block.number
  u.blockTimestamp  = event.block.timestamp
  u.transactionHash = event.transaction.hash
  u.save()
}

export function handleCoordinatorFeesSweptToRouter(event: FeesSweptToRouter): void {
  let e = new FeeSweepToRouter(eventId(event.transaction.hash, event.logIndex))
  e.sourceContract  = event.address
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}
