import { BigInt, Bytes } from "@graphprotocol/graph-ts"
import {
  ValidatorStaked,
  ValidatorSlashed,
  ValidatorUnstakeRequested,
  ValidatorWithdrawalClaimed,
  ValidatorBlacklisted,
  ValidatorUnblacklisted,
  SlasherContractAdded,
  SlasherContractRemoved,
} from "../generated/DinValidatorStake/DinValidatorStake"
import {
  StakeEvent,
  SlashEvent,
  UnstakeRequest,
  WithdrawalClaim,
  SlasherRegistration,
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
