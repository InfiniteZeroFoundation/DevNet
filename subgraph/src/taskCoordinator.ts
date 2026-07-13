import { BigInt, dataSource } from "@graphprotocol/graph-ts"
import {
  DINValidatorRegistered,
  Tier1BatchAuto,
  Tier2BatchAuto,
  AggregatorSlashed,
} from "../generated/templates/DINTaskCoordinator/DINTaskCoordinator"
import {
  GlobalIteration,
  AggregatorRegistration,
  Tier1Batch,
  Tier2Batch,
  AggregatorSlashEvent,
} from "../generated/schema"
import { eventId } from "./utils"

// ─── Context helpers ──────────────────────────────────────────────────────────

function modelId(): BigInt {
  return dataSource.context().getBigInt("modelId")
}

function giEntityId(gi: BigInt): string {
  return dataSource.context().getBytes("taskCoordinatorAddress").toHex() + "-" + gi.toString()
}

function loadOrCreateGI(gi: BigInt, blockNumber: BigInt, blockTimestamp: BigInt): GlobalIteration {
  let id = giEntityId(gi)
  let entity = GlobalIteration.load(id)
  if (entity == null) {
    entity = new GlobalIteration(id)
    entity.gi                = gi
    entity.taskCoordinator   = dataSource.context().getBytes("taskCoordinatorAddress")
    entity.model             = modelId().toString()
    entity.currentState      = 5 // GIstarted — first reachable state after model registration
    entity.globalModelCID    = null
    entity.ended             = false
    entity.startedAtBlock    = blockNumber
    entity.startedAtTimestamp = blockTimestamp
    entity.endedAtBlock      = null
    entity.endedAtTimestamp  = null
    entity.save()
  }
  return entity!
}

// ─── Aggregator registration ───────────────────────────────────────────────────

export function handleAggregatorRegistered(event: DINValidatorRegistered): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)

  let tcAddress = dataSource.context().getBytes("taskCoordinatorAddress")
  let id = tcAddress.toHex() + "-" + event.params.GI.toString() + "-" + event.params.validator.toHex()
  let reg = new AggregatorRegistration(id)
  reg.globalIteration  = gi.id
  reg.validator        = event.params.validator
  reg.blockNumber      = event.block.number
  reg.blockTimestamp   = event.block.timestamp
  reg.transactionHash  = event.transaction.hash
  reg.save()
}

// ─── Batch creation ────────────────────────────────────────────────────────────

export function handleTier1BatchCreated(event: Tier1BatchAuto): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)

  let tcAddress = dataSource.context().getBytes("taskCoordinatorAddress")
  let id = tcAddress.toHex() + "-" + event.params.GI.toString() + "-" + event.params.batchId.toString()
  let batch = new Tier1Batch(id)
  batch.globalIteration    = gi.id
  batch.batchId            = event.params.batchId
  batch.finalized          = false
  batch.winningCID         = null
  batch.createdAtBlock     = event.block.number
  batch.createdAtTimestamp = event.block.timestamp
  batch.finalizedAtBlock   = null
  batch.finalizedAtTimestamp = null
  batch.save()
}

export function handleTier2BatchCreated(event: Tier2BatchAuto): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)

  // batchId is always 0 — ID uses gi only to stay unique per model iteration
  let tcAddress = dataSource.context().getBytes("taskCoordinatorAddress")
  let id = tcAddress.toHex() + "-" + event.params.GI.toString()
  let batch = new Tier2Batch(id)
  batch.globalIteration    = gi.id
  batch.finalized          = false
  batch.globalModelCID     = null
  batch.createdAtBlock     = event.block.number
  batch.createdAtTimestamp = event.block.timestamp
  batch.finalizedAtBlock   = null
  batch.finalizedAtTimestamp = null
  batch.save()
}

// ─── Aggregator slashing ───────────────────────────────────────────────────────

export function handleAggregatorSlashed(event: AggregatorSlashed): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)

  let e = new AggregatorSlashEvent(eventId(event.transaction.hash, event.logIndex))
  e.globalIteration  = gi.id
  e.batchId          = event.params.batchId
  e.aggregator       = event.params.aggregator
  e.reason           = event.params.reason
  e.requestedAmount  = event.params.requested
  e.actualAmount     = event.params.actual
  e.blockNumber      = event.block.number
  e.blockTimestamp   = event.block.timestamp
  e.transactionHash  = event.transaction.hash
  e.save()
}
