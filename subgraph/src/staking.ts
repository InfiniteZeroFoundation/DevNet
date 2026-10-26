import { BigInt, Bytes } from "@graphprotocol/graph-ts"
import {
  ValidatorStaked,
  ValidatorSlashed,
  ValidatorUnstakeRequested,
  ValidatorWithdrawalClaimed,
  ValidatorBlacklisted,
  ValidatorUnblacklisted,
  ValidatorJailed,
  ValidatorReactivated,
  MinStakeUpdated,
  UnbondingPeriodUpdated,
  ModelStakeBoundsUpdated,
  MaxConcurrentRegistrationsPerStakeUnitUpdated,
  SlasherContractAdded,
  SlasherContractRemoved,
} from "../generated/DinValidatorStake/DinValidatorStake"
import {
  StakeEvent,
  SlashEvent,
  UnstakeRequest,
  WithdrawalClaim,
  JailEvent,
  SlasherRegistration,
  StakeGovernance,
  ModelStakeBounds,
} from "../generated/schema"
import { eventId, loadOrCreateValidator, syncValidatorStatus } from "./utils"

// ─── Stake ────────────────────────────────────────────────────────────────────

export function handleValidatorStaked(event: ValidatorStaked): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.activeStake  = v.activeStake.plus(event.params.amount)
  v.totalStaked  = v.totalStaked.plus(event.params.amount)
  syncValidatorStatus(v)
  v.save()

  let e = new StakeEvent(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Slash ────────────────────────────────────────────────────────────────────

export function handleValidatorSlashed(event: ValidatorSlashed): void {
  let v      = loadOrCreateValidator(event.params.validator)
  let amount = event.params.amount

  // Mirror DinValidatorStake.slash(): active stake is consumed first, then
  // pending withdrawals.
  if (v.activeStake.ge(amount)) {
    v.activeStake = v.activeStake.minus(amount)
  } else {
    let remainder = amount.minus(v.activeStake)
    v.activeStake       = BigInt.zero()
    v.pendingWithdrawal = v.pendingWithdrawal.gt(remainder)
      ? v.pendingWithdrawal.minus(remainder)
      : BigInt.zero()
    if (v.pendingWithdrawal.equals(BigInt.zero())) {
      v.withdrawAvailableAt = null
    }
  }

  v.totalSlashed = v.totalSlashed.plus(amount)
  syncValidatorStatus(v)
  v.save()

  let e = new SlashEvent(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.amount          = amount
  e.reason          = event.params.reason
  e.slasherContract = event.params.slasher
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Unstake ──────────────────────────────────────────────────────────────────

export function handleValidatorUnstakeRequested(
  event: ValidatorUnstakeRequested
): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.activeStake       = v.activeStake.minus(event.params.amount)
  v.pendingWithdrawal = event.params.amount
  v.withdrawAvailableAt = BigInt.fromI64(
    event.params.withdrawAvailableAt as i64
  )
  syncValidatorStatus(v)
  v.save()

  let id = eventId(event.transaction.hash, event.logIndex)
  let u  = new UnstakeRequest(id)
  u.validator          = event.params.validator.toHexString()
  u.amount             = event.params.amount
  u.withdrawAvailableAt = BigInt.fromI64(
    event.params.withdrawAvailableAt as i64
  )
  u.claimed         = false
  u.blockNumber     = event.block.number
  u.blockTimestamp  = event.block.timestamp
  u.transactionHash = event.transaction.hash
  u.save()
}

export function handleValidatorWithdrawalClaimed(
  event: ValidatorWithdrawalClaimed
): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.totalWithdrawn    = v.totalWithdrawn.plus(event.params.amount)
  v.pendingWithdrawal = BigInt.zero()
  v.withdrawAvailableAt = null
  syncValidatorStatus(v)
  v.save()

  let w = new WithdrawalClaim(eventId(event.transaction.hash, event.logIndex))
  w.validator       = event.params.validator.toHexString()
  w.amount          = event.params.amount
  w.blockNumber     = event.block.number
  w.blockTimestamp  = event.block.timestamp
  w.transactionHash = event.transaction.hash
  w.save()
}

// ─── Blacklist ────────────────────────────────────────────────────────────────

export function handleValidatorBlacklisted(event: ValidatorBlacklisted): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.blacklisted = true
  syncValidatorStatus(v)
  v.save()
}

export function handleValidatorUnblacklisted(
  event: ValidatorUnblacklisted
): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.blacklisted = false
  syncValidatorStatus(v)
  v.save()
}

// ─── Jail / reactivate ────────────────────────────────────────────────────────

export function handleValidatorJailed(event: ValidatorJailed): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.jailedUntil = BigInt.fromI64(event.params.jailedUntil as i64)
  syncValidatorStatus(v)
  v.save()

  let j = new JailEvent(eventId(event.transaction.hash, event.logIndex))
  j.validator       = event.params.validator.toHexString()
  j.jailedUntil     = BigInt.fromI64(event.params.jailedUntil as i64)
  j.reason          = event.params.reason
  j.slasherContract = event.params.slasher
  j.blockNumber     = event.block.number
  j.blockTimestamp  = event.block.timestamp
  j.transactionHash = event.transaction.hash
  j.save()
}

export function handleValidatorReactivated(
  event: ValidatorReactivated
): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.jailedUntil = null
  syncValidatorStatus(v)
  v.save()
}

// ─── Governable parameters ────────────────────────────────────────────────────

/** Load the StakeGovernance singleton, seeding initialize() defaults. */
function loadOrCreateStakeGovernance(): StakeGovernance {
  let g = StakeGovernance.load("singleton")
  if (g == null) {
    g = new StakeGovernance("singleton")
    g.minStake = BigInt.fromString("10000000000000000000") // 10 DIN — initialize() default
    g.unbondingPeriod = BigInt.fromI64(7 * 24 * 60 * 60 as i64) // 7 days
    g.maxConcurrentRegistrationsPerStakeUnit = BigInt.zero()
    g.updatedAtBlock = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  return g!
}

export function handleMinStakeUpdated(event: MinStakeUpdated): void {
  let g = loadOrCreateStakeGovernance()
  g.minStake = event.params.newMinStake
  g.updatedAtBlock = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleUnbondingPeriodUpdated(
  event: UnbondingPeriodUpdated
): void {
  let g = loadOrCreateStakeGovernance()
  g.unbondingPeriod = BigInt.fromI64(event.params.newPeriod as i64)
  g.updatedAtBlock = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleMaxConcurrentRegistrationsPerStakeUnitUpdated(
  event: MaxConcurrentRegistrationsPerStakeUnitUpdated
): void {
  let g = loadOrCreateStakeGovernance()
  g.maxConcurrentRegistrationsPerStakeUnit = event.params.value
  g.updatedAtBlock = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleModelStakeBoundsUpdated(
  event: ModelStakeBoundsUpdated
): void {
  let id = event.params.modelId.toString()
  let b = ModelStakeBounds.load(id)
  if (b == null) {
    b = new ModelStakeBounds(id)
    b.modelId = event.params.modelId
  }
  b.min = event.params.min
  b.max = event.params.max
  b.updatedAtBlock = event.block.number
  b.updatedAtTimestamp = event.block.timestamp
  b.save()
}

// ─── Slasher registry ─────────────────────────────────────────────────────────
//
// DinValidatorStake is the canonical source of the active slasher set.
// The entity ID encodes both the slasher address and the source contract so
// it stays distinct from the DinCoordinator audit-trail records.

export function handleSlasherContractAdded(event: SlasherContractAdded): void {
  let id = event.params.slasher.toHexString() + "-" + event.address.toHexString()
  let s  = new SlasherRegistration(id)
  s.slasherAddress    = event.params.slasher
  s.sourceContract    = event.address
  s.active            = true
  s.addedAtBlock      = event.block.number
  s.addedAtTimestamp  = event.block.timestamp
  s.removedAtBlock    = null
  s.removedAtTimestamp = null
  s.save()
}

export function handleSlasherContractRemoved(
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
