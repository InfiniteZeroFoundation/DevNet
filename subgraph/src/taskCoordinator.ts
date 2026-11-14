import { Address, BigInt, dataSource, log } from "@graphprotocol/graph-ts"
import {
  DINValidatorRegistered,
  Tier1BatchAuto,
  Tier2BatchAuto,
  AggregatorSlashed,
  GIStateChanged,
  T1AggregationSubmitted,
  T2AggregationSubmitted,
  T1BatchFinalized,
  T2Finalized,
  T1AggregationCommitted,
  T2AggregationCommitted,
  AuditSeedLocked,
  AggSeedLocked,
  DisputeSeedLocked,
  AuditSeedReanchored,
  AggSeedReanchored,
  DisputeSeedReanchored,
  DisputeOpened,
  DisputeResolved,
  DisputeExpired,
  DisputeBondClaimed,
  RecomputationSettled,
  ReEvaluationAssigned,
  S2SlashFractionBpsUpdated,
} from "../generated/templates/DINTaskCoordinator/DINTaskCoordinator"
import {
  GlobalIteration,
  AggregatorRegistration,
  Tier1Batch,
  Tier2Batch,
  AggregatorSlashEvent,
  GIStateTransition,
  T1AggregationSubmission,
  T2AggregationSubmission,
  T1AggregationCommitment,
  T2AggregationCommitment,
  SeedLock,
  AggregationDispute,
  DisputeBondClaim,
  TaskCoordinatorGovernance,
} from "../generated/schema"
import { eventId } from "./utils"

// ─── GI state enum ────────────────────────────────────────────────────────────

// GIstates on develop, indexed by GIStateChanged.newState (DINShared.md §2.1)
export const GI_STATES: string[] = [
  "AwaitingDINTaskAuditorToBeSet", "AwaitingDINTaskCoordinatorAsSlasher", "AwaitingDINTaskAuditorAsSlasher",
  "AwaitingGenesisModel", "GenesisModelCreated", "GIstarted",
  "DINaggregatorsRegistrationStarted", "DINaggregatorsRegistrationClosed",
  "DINauditorsRegistrationStarted", "DINauditorsRegistrationClosed",
  "LMSstarted", "LMSclosed", "AuditSeedLocked", "AuditorsBatchesCreated", "AuditTestDataAssigned",
  "LMSevaluationStarted", "LMSevaluationRevealStarted", "LMSevaluationClosed", "AggSeedLocked",
  "T1nT2Bcreated", "T1AggregationStarted", "T1AggregationRevealStarted", "T1AggregationDone",
  "T2AggregationStarted", "T2AggregationRevealStarted", "T2AggregationDone",
  "AuditorsSlashed", "AggregatorsSlashed", "GIended",
];

const GI_ENDED: i32 = 28 // GI_STATES[28] == "GIended"

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

// ─── GI state machine ──────────────────────────────────────────────────────────

export function handleGIStateChanged(event: GIStateChanged): void {
  let gi       = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let newState = event.params.newState

  if (newState < 0 || newState >= GI_STATES.length) {
    log.warning("GIStateChanged: unknown GIstates ordinal {} for GI {}", [
      newState.toString(), event.params.GI.toString(),
    ])
  }

  gi.currentState = newState
  if (newState == GI_ENDED) {
    gi.ended            = true
    gi.endedAtBlock     = event.block.number
    gi.endedAtTimestamp = event.block.timestamp
  }
  gi.save()

  let t = new GIStateTransition(gi.id + "-" + newState.toString())
  t.globalIteration = gi.id
  t.newState        = newState
  t.blockNumber     = event.block.number
  t.blockTimestamp  = event.block.timestamp
  t.transactionHash = event.transaction.hash
  t.save()
}

// ─── Aggregation submissions ───────────────────────────────────────────────────

export function handleT1AggregationSubmitted(event: T1AggregationSubmitted): void {
  let tcAddress = dataSource.context().getBytes("taskCoordinatorAddress")
  let batchId   = tcAddress.toHex() + "-" + event.params.GI.toString() + "-" + event.params.batchId.toString()

  let sub = new T1AggregationSubmission(batchId + "-" + event.params.aggregator.toHex())
  sub.tier1Batch      = batchId
  sub.aggregator      = event.params.aggregator
  sub.cid             = event.params.cid
  sub.blockNumber     = event.block.number
  sub.blockTimestamp  = event.block.timestamp
  sub.transactionHash = event.transaction.hash
  sub.save()
}

export function handleT2AggregationSubmitted(event: T2AggregationSubmitted): void {
  // T2 batchId is always 0 — Tier2Batch ID is keyed on gi only.
  let batchId = giEntityId(event.params.GI)

  let sub = new T2AggregationSubmission(batchId + "-" + event.params.aggregator.toHex())
  sub.tier2Batch      = batchId
  sub.aggregator      = event.params.aggregator
  sub.cid             = event.params.cid
  sub.blockNumber     = event.block.number
  sub.blockTimestamp  = event.block.timestamp
  sub.transactionHash = event.transaction.hash
  sub.save()
}

// ─── Aggregation finalization ──────────────────────────────────────────────────

export function handleT1BatchFinalized(event: T1BatchFinalized): void {
  let tcAddress = dataSource.context().getBytes("taskCoordinatorAddress")
  let id = tcAddress.toHex() + "-" + event.params.GI.toString() + "-" + event.params.batchId.toString()
  let batch = Tier1Batch.load(id)
  if (batch == null) {
    log.warning("T1BatchFinalized: Tier1Batch {} not found", [id])
    return
  }
  batch.finalized            = true
  batch.winningCID           = event.params.winningCID
  batch.finalizedAtBlock     = event.block.number
  batch.finalizedAtTimestamp = event.block.timestamp
  batch.save()
}

export function handleT2Finalized(event: T2Finalized): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  gi.globalModelCID = event.params.globalModelCID
  gi.save()

  let batch = Tier2Batch.load(gi.id)
  if (batch == null) {
    log.warning("T2Finalized: Tier2Batch {} not found", [gi.id])
    return
  }
  batch.finalized            = true
  batch.globalModelCID       = event.params.globalModelCID
  batch.finalizedAtBlock     = event.block.number
  batch.finalizedAtTimestamp = event.block.timestamp
  batch.save()
}

// ─── Commit-reveal aggregation ─────────────────────────────────────────────────

function tcAddressHex(): string {
  return dataSource.context().getBytes("taskCoordinatorAddress").toHex()
}

export function handleT1AggregationCommitted(event: T1AggregationCommitted): void {
  let gi        = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let batchId   = tcAddressHex() + "-" + event.params.GI.toString() + "-" + event.params.batchId.toString()
  let c         = new T1AggregationCommitment(batchId + "-" + event.params.aggregator.toHex())
  c.globalIteration = gi.id
  c.tier1Batch      = batchId
  c.aggregator      = event.params.aggregator
  c.commitHash      = event.params.commitHash
  c.blockNumber     = event.block.number
  c.blockTimestamp  = event.block.timestamp
  c.transactionHash = event.transaction.hash
  c.save()
}

export function handleT2AggregationCommitted(event: T2AggregationCommitted): void {
  let gi      = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let batchId = giEntityId(event.params.GI)
  let c       = new T2AggregationCommitment(batchId + "-" + event.params.aggregator.toHex())
  c.globalIteration = gi.id
  c.tier2Batch      = batchId
  c.aggregator      = event.params.aggregator
  c.commitHash      = event.params.commitHash
  c.blockNumber     = event.block.number
  c.blockTimestamp  = event.block.timestamp
  c.transactionHash = event.transaction.hash
  c.save()
}

// ─── Seed locks ────────────────────────────────────────────────────────────────

function auditSeedId(gi: BigInt): string {
  return tcAddressHex() + "-" + gi.toString() + "-Audit"
}

function aggSeedId(gi: BigInt): string {
  return tcAddressHex() + "-" + gi.toString() + "-Agg"
}

function disputeSeedId(gi: BigInt, tierKind: i32, batchId: BigInt): string {
  return tcAddressHex() + "-" + gi.toString() + "-Dispute-" +
         tierKind.toString() + "-" + batchId.toString()
}

export function handleAuditSeedLocked(event: AuditSeedLocked): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let s  = new SeedLock(auditSeedId(event.params.GI))
  s.globalIteration = gi.id
  s.kind            = "Audit"
  s.seed            = event.params.seed
  s.blockNumber     = event.block.number
  s.blockTimestamp  = event.block.timestamp
  s.transactionHash = event.transaction.hash
  s.save()
}

export function handleAggSeedLocked(event: AggSeedLocked): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let s  = new SeedLock(aggSeedId(event.params.GI))
  s.globalIteration = gi.id
  s.kind            = "Agg"
  s.seed            = event.params.seed
  s.blockNumber     = event.block.number
  s.blockTimestamp  = event.block.timestamp
  s.transactionHash = event.transaction.hash
  s.save()
}

export function handleDisputeSeedLocked(event: DisputeSeedLocked): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let s  = new SeedLock(disputeSeedId(event.params.GI, event.params.tierKind, event.params.batchId))
  s.globalIteration = gi.id
  s.kind            = "Dispute"
  s.tierKind        = event.params.tierKind
  s.batchId         = event.params.batchId
  s.seed            = event.params.seed
  s.blockNumber     = event.block.number
  s.blockTimestamp  = event.block.timestamp
  s.transactionHash = event.transaction.hash
  s.save()
}

export function handleAuditSeedReanchored(event: AuditSeedReanchored): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let id = auditSeedId(event.params.GI)
  let s  = SeedLock.load(id)
  if (s == null) {
    s = new SeedLock(id)
    s.globalIteration = gi.id
    s.kind            = "Audit"
  }
  s.reanchoredAtBlock = event.params.newSeedBlock
  s.blockNumber       = event.block.number
  s.blockTimestamp    = event.block.timestamp
  s.transactionHash   = event.transaction.hash
  s.save()
}

export function handleAggSeedReanchored(event: AggSeedReanchored): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let id = aggSeedId(event.params.GI)
  let s  = SeedLock.load(id)
  if (s == null) {
    s = new SeedLock(id)
    s.globalIteration = gi.id
    s.kind            = "Agg"
  }
  s.reanchoredAtBlock = event.params.newSeedBlock
  s.blockNumber       = event.block.number
  s.blockTimestamp    = event.block.timestamp
  s.transactionHash   = event.transaction.hash
  s.save()
}

export function handleDisputeSeedReanchored(event: DisputeSeedReanchored): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let id = disputeSeedId(event.params.GI, event.params.tierKind, event.params.batchId)
  let s  = SeedLock.load(id)
  if (s == null) {
    s = new SeedLock(id)
    s.globalIteration = gi.id
    s.kind            = "Dispute"
    s.tierKind        = event.params.tierKind
    s.batchId         = event.params.batchId
  }
  s.reanchoredAtBlock = event.params.newSeedBlock
  s.blockNumber       = event.block.number
  s.blockTimestamp    = event.block.timestamp
  s.transactionHash   = event.transaction.hash
  s.save()
}

// ─── Aggregation disputes ──────────────────────────────────────────────────────

function aggregationDisputeId(gi: BigInt, tierKind: i32, batchId: BigInt): string {
  return tcAddressHex() + "-" + gi.toString() + "-" +
         tierKind.toString() + "-" + batchId.toString()
}

export function handleDisputeOpened(event: DisputeOpened): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let d  = new AggregationDispute(aggregationDisputeId(event.params.GI, event.params.tierKind, event.params.batchId))
  d.globalIteration = gi.id
  d.tierKind        = event.params.tierKind
  d.batchId         = event.params.batchId
  d.challenger      = event.params.challenger
  d.bond            = event.params.bond
  d.status          = "Open"
  d.openedAtBlock   = event.block.number
  d.openedAtTimestamp = event.block.timestamp
  d.blockNumber     = event.block.number
  d.blockTimestamp  = event.block.timestamp
  d.transactionHash = event.transaction.hash
  d.save()
}

export function handleDisputeResolved(event: DisputeResolved): void {
  let id = aggregationDisputeId(event.params.GI, event.params.tierKind, event.params.batchId)
  let d  = AggregationDispute.load(id)
  if (d == null) {
    log.warning("DisputeResolved: AggregationDispute {} not found", [id])
    return
  }
  d.status            = event.params.upheld ? "Upheld" : "Rejected"
  d.upheld            = event.params.upheld
  d.resolvedAtBlock   = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleCoordinatorDisputeExpired(event: DisputeExpired): void {
  let id = aggregationDisputeId(event.params.GI, event.params.tierKind, event.params.batchId)
  let d  = AggregationDispute.load(id)
  if (d == null) {
    log.warning("DisputeExpired: AggregationDispute {} not found", [id])
    return
  }
  d.status            = "Expired"
  d.resolvedAtBlock   = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleDisputeBondClaimed(event: DisputeBondClaimed): void {
  let c = new DisputeBondClaim(eventId(event.transaction.hash, event.logIndex))
  c.challenger      = event.params.challenger
  c.amount          = event.params.amount
  c.blockNumber     = event.block.number
  c.blockTimestamp  = event.block.timestamp
  c.transactionHash = event.transaction.hash
  c.save()
}

export function handleRecomputationSettled(event: RecomputationSettled): void {
  let id = aggregationDisputeId(event.params.GI, event.params.tierKind, event.params.batchId)
  let d  = AggregationDispute.load(id)
  if (d == null) {
    let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
    d = new AggregationDispute(id)
    d.globalIteration = gi.id
    d.tierKind        = event.params.tierKind
    d.batchId         = event.params.batchId
    d.challenger      = Address.zero()
    d.bond            = BigInt.zero()
    d.status          = "Open"
    d.openedAtBlock   = event.block.number
    d.openedAtTimestamp = event.block.timestamp
    d.blockNumber     = event.block.number
    d.blockTimestamp  = event.block.timestamp
    d.transactionHash = event.transaction.hash
  }
  d.confirmed = event.params.confirmed
  if (d.status == "Open") {
    d.status = event.params.confirmed ? "Upheld" : "Rejected"
  }
  d.resolvedAtBlock   = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleReEvaluationAssigned(event: ReEvaluationAssigned): void {
  let id = aggregationDisputeId(event.params.GI, event.params.tierKind, event.params.batchId)
  let d  = AggregationDispute.load(id)
  if (d == null) {
    let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
    d = new AggregationDispute(id)
    d.globalIteration = gi.id
    d.tierKind        = event.params.tierKind
    d.batchId         = event.params.batchId
    d.challenger      = Address.zero()
    d.bond            = BigInt.zero()
    d.status          = "Open"
    d.openedAtBlock   = event.block.number
    d.openedAtTimestamp = event.block.timestamp
    d.blockNumber     = event.block.number
    d.blockTimestamp  = event.block.timestamp
    d.transactionHash = event.transaction.hash
  }
  let fresh = event.params.freshAggregators
  let out = new Array<string>()
  for (let i = 0; i < fresh.length; i++) {
    out.push(fresh[i].toHexString())
  }
  d.freshAggregators = out
  d.save()
}

// ─── Governance parameters ─────────────────────────────────────────────────────

export function handleS2SlashFractionBpsUpdated(event: S2SlashFractionBpsUpdated): void {
  let id = event.address.toHexString()
  let g  = TaskCoordinatorGovernance.load(id)
  if (g == null) {
    g = new TaskCoordinatorGovernance(id)
    g.updatedAtBlock     = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  g.s2SlashFractionBps = event.params.newBps
  g.updatedAtBlock     = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}
