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
  S5GlobalParamsUpdated,
  S5RecidivismParamsUpdated,
  S6ParamsUpdated,
  S6NoParticipationRecorded,
  S6PartialSlashFired,
  ValidatorEscalatedS5,
  ValidatorEscalatedS5Global,
  SlashTreasuryUpdated,
  EncryptionKeyRegistered,
  ActiveRegistrationIncremented,
  ActiveRegistrationDecremented,
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
  S5GlobalParams,
  S5RecidivismParams,
  S6Params,
  S6NoParticipationRecord,
  S6PartialSlashEvent,
  ValidatorEscalationS5,
  ValidatorEscalationS5Global,
  SlashTreasuryUpdate,
  EncryptionKeyRegistration,
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
  v.withdrawAvailableAt = event.params.withdrawAvailableAt
  syncValidatorStatus(v)
  v.save()

  let id = eventId(event.transaction.hash, event.logIndex)
  let u  = new UnstakeRequest(id)
  u.validator          = event.params.validator.toHexString()
  u.amount             = event.params.amount
  u.withdrawAvailableAt = event.params.withdrawAvailableAt
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
  v.jailedUntil = event.params.jailedUntil
  syncValidatorStatus(v)
  v.save()

  let j = new JailEvent(eventId(event.transaction.hash, event.logIndex))
  j.validator       = event.params.validator.toHexString()
  j.jailedUntil     = event.params.jailedUntil
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
  g.unbondingPeriod = event.params.newPeriod
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

// ─── S5/S6 penalty mechanism — governance params ──────────────────────────────

function loadOrCreateS5GlobalParams(): S5GlobalParams {
  let g = S5GlobalParams.load("singleton")
  if (g == null) {
    g = new S5GlobalParams("singleton")
    g.window             = BigInt.zero()
    g.threshold          = BigInt.zero()
    g.updatedAtBlock     = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  return g!
}

function loadOrCreateS5RecidivismParams(): S5RecidivismParams {
  let g = S5RecidivismParams.load("singleton")
  if (g == null) {
    g = new S5RecidivismParams("singleton")
    g.window             = BigInt.zero()
    g.threshold          = BigInt.zero()
    g.jailDuration       = BigInt.zero()
    g.updatedAtBlock     = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  return g!
}

function loadOrCreateS6Params(): S6Params {
  let g = S6Params.load("singleton")
  if (g == null) {
    g = new S6Params("singleton")
    g.threshold          = BigInt.zero()
    g.updatedAtBlock     = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  return g!
}

export function handleS5GlobalParamsUpdated(event: S5GlobalParamsUpdated): void {
  let g = loadOrCreateS5GlobalParams()
  g.window             = event.params.window
  g.threshold          = event.params.threshold
  g.updatedAtBlock     = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleS5RecidivismParamsUpdated(event: S5RecidivismParamsUpdated): void {
  let g = loadOrCreateS5RecidivismParams()
  g.window             = event.params.window
  g.threshold          = event.params.threshold
  g.jailDuration       = event.params.jailDuration
  g.updatedAtBlock     = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleS6ParamsUpdated(event: S6ParamsUpdated): void {
  let g = loadOrCreateS6Params()
  g.threshold          = event.params.threshold
  g.updatedAtBlock     = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

// ─── S5/S6 penalty mechanism — validator events ───────────────────────────────

export function handleS6NoParticipationRecorded(event: S6NoParticipationRecorded): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.save()

  let e = new S6NoParticipationRecord(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.count           = event.params.count
  e.reason          = event.params.reason
  e.slasherContract = event.params.slasher
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleS6PartialSlashFired(event: S6PartialSlashFired): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.save()

  let e = new S6PartialSlashEvent(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.slashedAmount   = event.params.slashedAmount
  e.slasherContract = event.params.slasher
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleValidatorEscalatedS5(event: ValidatorEscalatedS5): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.save()

  let e = new ValidatorEscalationS5(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.slashedAmount   = event.params.slashedAmount
  e.giIndex         = event.params.giIndex
  e.slasherContract = event.params.slasher
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleValidatorEscalatedS5Global(event: ValidatorEscalatedS5Global): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.save()

  let e = new ValidatorEscalationS5Global(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.slashedAmount   = event.params.slashedAmount
  e.globalCount     = event.params.globalCount
  e.slasherContract = event.params.slasher
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Slash treasury ───────────────────────────────────────────────────────────

export function handleSlashTreasuryUpdated(event: SlashTreasuryUpdated): void {
  let e = new SlashTreasuryUpdate(eventId(event.transaction.hash, event.logIndex))
  e.treasury        = event.params.treasury
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Encryption key ───────────────────────────────────────────────────────────

export function handleEncryptionKeyRegistered(event: EncryptionKeyRegistered): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.encryptionKey = event.params.pubkey
  v.save()

  let e = new EncryptionKeyRegistration(eventId(event.transaction.hash, event.logIndex))
  e.validator       = event.params.validator.toHexString()
  e.pubkey          = event.params.pubkey
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Active registration counter ─────────────────────────────────────────────

export function handleActiveRegistrationIncremented(
  event: ActiveRegistrationIncremented
): void {
  let v = loadOrCreateValidator(event.params.validator)
  v.activeRegistrations = v.activeRegistrations + 1
  v.save()
}

export function handleActiveRegistrationDecremented(
  event: ActiveRegistrationDecremented
): void {
  let v = loadOrCreateValidator(event.params.validator)
  if (v.activeRegistrations > 0) {
    v.activeRegistrations = v.activeRegistrations - 1
  }
  v.save()
}
