import { BigInt, Address, Bytes, dataSource } from "@graphprotocol/graph-ts"
import {
  DINAuditorRegistered,
  AuditorsBatchAuto,
  AuditorsBatchesCreated,
  AuditScoreSubmitted,
  EligibilityVoted,
  EligibilityFinalized,
  PassScoreUpdated,
  AuditorSlashed,
} from "../generated/templates/DINTaskAuditor/DINTaskAuditor"
import {
  GlobalIteration,
  AuditorRegistration,
  AuditBatch,
  AuditScoreSubmission,
  EligibilityVote,
  EligibilityResult,
  LocalModelSubmission,
  AuditorSlashEvent,
  PassScoreUpdate,
} from "../generated/schema"
import { eventId } from "./utils"

// ─── Context helpers ──────────────────────────────────────────────────────────

function taAddress(): Address {
  return Address.fromBytes(dataSource.context().getBytes("taskAuditorAddress"))
}

function tcAddressHex(): string {
  return dataSource.context().getBytes("taskCoordinatorAddress").toHex()
}

function modelId(): BigInt {
  return dataSource.context().getBigInt("modelId")
}

/** GlobalIteration ID uses the taskCoordinator address as the stable anchor. */
function giId(gi: BigInt): string {
  return tcAddressHex() + "-" + gi.toString()
}

function loadOrCreateGI(gi: BigInt, blockNumber: BigInt, blockTimestamp: BigInt): GlobalIteration {
  let id = giId(gi)
  let entity = GlobalIteration.load(id)
  if (entity == null) {
    entity = new GlobalIteration(id)
    entity.gi               = gi
    entity.taskCoordinator  = dataSource.context().getBytes("taskCoordinatorAddress")
    entity.model            = modelId().toString()
    entity.currentState     = 5 // GIstarted — first reachable state after model registration
    entity.globalModelCID   = null
    entity.ended            = false
    entity.startedAtBlock   = blockNumber
    entity.startedAtTimestamp = blockTimestamp
    entity.endedAtBlock     = null
    entity.endedAtTimestamp = null
    entity.save()
  }
  return entity!
}

// Creates a stub LocalModelSubmission so that required relationship fields on
// AuditScoreSubmission / EligibilityVote / EligibilityResult are never null.
// The stub has zero-value client and modelCID until the LocalModelSubmitted
// event lands (audit §4.2) and populates the real values.
function loadOrCreateLMS(
  gi: BigInt,
  modelIndex: BigInt,
  giEntity: GlobalIteration,
  blockNumber: BigInt,
  blockTimestamp: BigInt,
  txHash: Bytes,
): LocalModelSubmission {
  let id = taAddress().toHex() + "-" + gi.toString() + "-" + modelIndex.toString()
  let entity = LocalModelSubmission.load(id)
  if (entity == null) {
    entity = new LocalModelSubmission(id)
    entity.globalIteration  = giEntity.id
    entity.modelIndex       = modelIndex
    entity.client           = Address.zero()
    entity.modelCID         = Bytes.fromI32(0)
    entity.eligible         = null
    entity.finalAvgScore    = null
    entity.approved         = null
    entity.blockNumber      = blockNumber
    entity.blockTimestamp   = blockTimestamp
    entity.transactionHash  = txHash
    entity.save()
  }
  return entity!
}

function auditBatchId(gi: BigInt, batchId: BigInt): string {
  return taAddress().toHex() + "-" + gi.toString() + "-" + batchId.toString()
}

function loadOrCreateAuditBatch(
  gi: BigInt,
  batchId: BigInt,
  giEntity: GlobalIteration,
  blockNumber: BigInt,
  blockTimestamp: BigInt,
): AuditBatch {
  let id = auditBatchId(gi, batchId)
  let entity = AuditBatch.load(id)
  if (entity == null) {
    entity = new AuditBatch(id)
    entity.globalIteration  = giEntity.id
    entity.batchId          = batchId
    entity.createdAtBlock   = blockNumber
    entity.createdAtTimestamp = blockTimestamp
    entity.save()
  }
  return entity!
}

// ─── Auditor registration ──────────────────────────────────────────────────────

export function handleAuditorRegistered(event: DINAuditorRegistered): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)

  let id = taAddress().toHex() + "-" + event.params.GI.toString() + "-" + event.params.auditor.toHex()
  let reg = new AuditorRegistration(id)
  reg.globalIteration  = gi.id
  reg.auditor          = event.params.auditor
  reg.blockNumber      = event.block.number
  reg.blockTimestamp   = event.block.timestamp
  reg.transactionHash  = event.transaction.hash
  reg.save()
}

// ─── Audit batch creation ──────────────────────────────────────────────────────

export function handleAuditBatchCreated(event: AuditorsBatchAuto): void {
  let gi = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  loadOrCreateAuditBatch(event.params.GI, event.params.batchId, gi, event.block.number, event.block.timestamp)
}

// AuditorsBatchesCreated is a summary event — all individual batches are
// already created by handleAuditBatchCreated above. No new entity needed.
export function handleAuditorsBatchesCreated(event: AuditorsBatchesCreated): void {
  // Ensure the GI anchor exists even if no AuditorsBatchAuto fired yet
  // (defensive; in practice they are emitted in the same tx).
  loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
}

// ─── Scoring ───────────────────────────────────────────────────────────────────

export function handleAuditScoreSubmitted(event: AuditScoreSubmitted): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadOrCreateLMS(event.params.gi, event.params.modelIndex, gi, event.block.number, event.block.timestamp, event.transaction.hash)

  let id = taAddress().toHex() + "-" + event.params.gi.toString() + "-" +
           event.params.batchId.toString() + "-" + event.params.auditor.toHex() + "-" +
           event.params.modelIndex.toString()
  let sub = new AuditScoreSubmission(id)
  sub.auditBatch            = batch.id
  sub.localModelSubmission  = lms.id
  sub.auditor               = event.params.auditor
  sub.score                 = event.params.score
  sub.blockNumber           = event.block.number
  sub.blockTimestamp        = event.block.timestamp
  sub.transactionHash       = event.transaction.hash
  sub.save()
}

// ─── Eligibility ───────────────────────────────────────────────────────────────

export function handleEligibilityVoted(event: EligibilityVoted): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadOrCreateLMS(event.params.gi, event.params.modelIndex, gi, event.block.number, event.block.timestamp, event.transaction.hash)

  let id = taAddress().toHex() + "-" + event.params.gi.toString() + "-" +
           event.params.batchId.toString() + "-" + event.params.modelIndex.toString() + "-" +
           event.params.auditor.toHex()
  let vote = new EligibilityVote(id)
  vote.auditBatch           = batch.id
  vote.localModelSubmission = lms.id
  vote.auditor              = event.params.auditor
  vote.vote                 = event.params.vote
  vote.blockNumber          = event.block.number
  vote.blockTimestamp       = event.block.timestamp
  vote.transactionHash      = event.transaction.hash
  vote.save()
}

export function handleEligibilityFinalized(event: EligibilityFinalized): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadOrCreateLMS(event.params.gi, event.params.modelIndex, gi, event.block.number, event.block.timestamp, event.transaction.hash)

  let id = taAddress().toHex() + "-" + event.params.gi.toString() + "-" +
           event.params.batchId.toString() + "-" + event.params.modelIndex.toString()
  let result = new EligibilityResult(id)
  result.auditBatch           = batch.id
  result.localModelSubmission = lms.id
  result.eligible             = event.params.eligible
  result.totalVotes           = event.params.totalVotes
  result.blockNumber          = event.block.number
  result.blockTimestamp       = event.block.timestamp
  result.transactionHash      = event.transaction.hash
  result.save()

  // Propagate eligible flag back to the LocalModelSubmission.
  lms.eligible = event.params.eligible
  lms.save()
}

// ─── Pass score governance ─────────────────────────────────────────────────────

export function handlePassScoreUpdated(event: PassScoreUpdated): void {
  let e = new PassScoreUpdate(eventId(event.transaction.hash, event.logIndex))
  e.taskAuditor     = event.address
  e.oldScore        = event.params.oldScore
  e.newScore        = event.params.newScore
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// ─── Auditor slashing ──────────────────────────────────────────────────────────

export function handleAuditorSlashed(event: AuditorSlashed): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)

  let e = new AuditorSlashEvent(eventId(event.transaction.hash, event.logIndex))
  e.globalIteration  = gi.id
  e.auditBatch       = batch.id
  e.auditor          = event.params.auditor
  e.reason           = event.params.reason
  e.requestedAmount  = event.params.requested
  e.actualAmount     = event.params.actual
  e.blockNumber      = event.block.number
  e.blockTimestamp   = event.block.timestamp
  e.transactionHash  = event.transaction.hash
  e.save()
}
