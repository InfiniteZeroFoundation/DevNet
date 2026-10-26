import {
  EthDepositAndDINminted,
  DinPerEthUpdated,
  ValidatorStakeContractUpdated,
  SlasherContractAdded,
  SlasherContractRemoved,
} from "../generated/DinCoordinator/DinCoordinator"
import {
  DINMintEvent,
  ExchangeRateSnapshot,
  SlasherRegistration,
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

// ─── Treasury withdrawal ──────────────────────────────────────────────────────
// ETHTreasuryWithdrawn is not yet in the ABI (audit §6.3). The handler is
// kept here as a stub; uncomment and add the import once the event lands.

// import { ETHTreasuryWithdrawn } from "../generated/DinCoordinator/DinCoordinator"
// import { TreasuryWithdrawal } from "../generated/schema"

// export function handleETHTreasuryWithdrawn(
//   event: ETHTreasuryWithdrawn
// ): void {
//   let w = new TreasuryWithdrawal(eventId(event.transaction.hash, event.logIndex))
//   w.to              = event.params.to
//   w.amount          = event.params.amount
//   w.blockNumber     = event.block.number
//   w.blockTimestamp  = event.block.timestamp
//   w.transactionHash = event.transaction.hash
//   w.save()
// }
