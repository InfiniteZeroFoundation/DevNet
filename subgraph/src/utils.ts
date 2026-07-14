import { BigInt, Bytes } from "@graphprotocol/graph-ts"
import { Validator } from "../generated/schema"

export const MIN_STAKE = BigInt.fromString("10000000000000000000") // 10 DIN (18 decimals)

/** Stable entity ID for event-based entities: txHash-logIndex. */
export function eventId(txHash: Bytes, logIndex: BigInt): string {
  return txHash.toHex() + "-" + logIndex.toString()
}

/** Load a Validator aggregate entity, initialising it on first encounter. */
export function loadOrCreateValidator(address: Bytes): Validator {
  let id = address.toHexString()
  let v = Validator.load(id)
  if (v == null) {
    v = new Validator(id)
    v.address           = address
    v.activeStake       = BigInt.zero()
    v.pendingWithdrawal = BigInt.zero()
    v.withdrawAvailableAt = null
    v.totalStaked       = BigInt.zero()
    v.totalSlashed      = BigInt.zero()
    v.totalWithdrawn    = BigInt.zero()
    v.status            = "None"
    v.blacklisted       = false
  }
  return v!
}

/**
 * Derive the validator status string from the aggregate's current field
 * values, mirroring DinValidatorStake._syncValidatorStatus().
 * Called after every mutation that can change stake or withdrawal state.
 */
export function syncValidatorStatus(v: Validator): void {
  if (v.blacklisted) {
    v.status = "Blacklisted"
    return
  }
  if (v.pendingWithdrawal.gt(BigInt.zero())) {
    v.status = "Exiting"
    return
  }
  if (v.activeStake.ge(MIN_STAKE)) {
    v.status = "Active"
    return
  }
  if (v.activeStake.gt(BigInt.zero())) {
    v.status = "Exiting"
    return
  }
  v.status = "None"
}
