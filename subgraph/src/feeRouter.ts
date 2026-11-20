import { BigInt } from "@graphprotocol/graph-ts"
import {
  FeeSourceAdded,
  FeeSourceRemoved,
  TreasuryUpdated,
  TreasuryBpsCeilingUpdated,
  DinSplitUpdated,
  EthSplitUpdated,
  FeeRoutedDIN,
  FeeRoutedETH,
} from "../generated/DinFeeRouter/DinFeeRouter"
import {
  FeeSource,
  FeeRouterConfig,
  FeeRoutedDIN as FeeRoutedDINEntity,
  FeeRoutedETH as FeeRoutedETHEntity,
} from "../generated/schema"
import { eventId } from "./utils"

function loadOrCreateConfig(id: string): FeeRouterConfig {
  let c = FeeRouterConfig.load(id)
  if (c == null) {
    c = new FeeRouterConfig(id)
    c.updatedAtBlock     = BigInt.zero()
    c.updatedAtTimestamp = BigInt.zero()
  }
  return c!
}

// ─── Fee sources ──────────────────────────────────────────────────────────────

export function handleFeeSourceAdded(event: FeeSourceAdded): void {
  let id = event.address.toHexString() + "-" + event.params.source.toHexString()
  let s  = new FeeSource(id)
  s.source             = event.params.source
  s.active             = true
  s.addedAtBlock       = event.block.number
  s.addedAtTimestamp   = event.block.timestamp
  s.removedAtBlock     = null
  s.removedAtTimestamp = null
  s.save()
}

export function handleFeeSourceRemoved(event: FeeSourceRemoved): void {
  let id = event.address.toHexString() + "-" + event.params.source.toHexString()
  let s  = FeeSource.load(id)
  if (s == null) return
  s.active             = false
  s.removedAtBlock     = event.block.number
  s.removedAtTimestamp = event.block.timestamp
  s.save()
}

// ─── Configuration ────────────────────────────────────────────────────────────

export function handleTreasuryUpdated(event: TreasuryUpdated): void {
  let c = loadOrCreateConfig(event.address.toHexString())
  c.treasury           = event.params.treasury
  c.updatedAtBlock     = event.block.number
  c.updatedAtTimestamp = event.block.timestamp
  c.save()
}

export function handleTreasuryBpsCeilingUpdated(event: TreasuryBpsCeilingUpdated): void {
  let c = loadOrCreateConfig(event.address.toHexString())
  c.treasuryBpsCeiling = event.params.ceiling
  c.updatedAtBlock     = event.block.number
  c.updatedAtTimestamp = event.block.timestamp
  c.save()
}

export function handleDinSplitUpdated(event: DinSplitUpdated): void {
  let c     = loadOrCreateConfig(event.address.toHexString())
  let split = event.params.split
  c.dinValidatorPoolBps = split.validatorPoolBps
  c.dinTreasuryBps      = split.treasuryBps
  c.dinBurnBps          = split.burnBps
  c.dinStorageBps       = split.storageBps
  c.dinPublicGoodsBps   = split.publicGoodsBps
  c.updatedAtBlock      = event.block.number
  c.updatedAtTimestamp  = event.block.timestamp
  c.save()
}

export function handleEthSplitUpdated(event: EthSplitUpdated): void {
  let c     = loadOrCreateConfig(event.address.toHexString())
  let split = event.params.split
  c.ethValidatorPoolBps = split.validatorPoolBps
  c.ethTreasuryBps      = split.treasuryBps
  c.ethStorageBps       = split.storageBps
  c.ethPublicGoodsBps   = split.publicGoodsBps
  c.updatedAtBlock      = event.block.number
  c.updatedAtTimestamp  = event.block.timestamp
  c.save()
}

// ─── Routed fees ──────────────────────────────────────────────────────────────

export function handleFeeRoutedDIN(event: FeeRoutedDIN): void {
  let e = new FeeRoutedDINEntity(eventId(event.transaction.hash, event.logIndex))
  e.payer           = event.params.payer
  e.amount          = event.params.amount
  e.burned          = event.params.burned
  e.toTreasury      = event.params.toTreasury
  e.toValidatorPool = event.params.toValidatorPool
  e.toStorage       = event.params.toStorage
  e.toPublicGoods   = event.params.toPublicGoods
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleFeeRoutedETH(event: FeeRoutedETH): void {
  let e = new FeeRoutedETHEntity(eventId(event.transaction.hash, event.logIndex))
  e.payer           = event.params.payer
  e.amount          = event.params.amount
  e.toTreasury      = event.params.toTreasury
  e.toValidatorPool = event.params.toValidatorPool
  e.toStorage       = event.params.toStorage
  e.toPublicGoods   = event.params.toPublicGoods
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}
