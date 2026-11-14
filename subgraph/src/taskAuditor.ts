import { BigInt, Address, Bytes, dataSource, log } from "@graphprotocol/graph-ts"
import {
  DINAuditorRegistered,
  AuditorsBatchAuto,
  AuditorsBatchesCreated,
  AuditScoreSubmitted,
  AuditScoreCommitted,
  EligibilityVoted,
  EligibilityFinalized,
  PassScoreUpdated,
  AuditorSlashed,
  LocalModelSubmitted,
  RewardDeposited,
  RewardsSettled,
  RewardsClaimed,
  RewardSplitUpdated,
  TestDataCommitmentStored,
  EncryptedTestDataKeysAssigned,
  TestDataDisputeOpened,
  TestDataDisputeUpheld,
  TestDataDisputeResolvedFalse,
  DisputeExpired,
  BatchPendingReassignment,
  AuditorScoreDeviation,
  S1SlashFractionBpsUpdated,
  S3DeviationThresholdUpdated,
  S3SlashingEnabledUpdated,
} from "../generated/templates/DINTaskAuditor/DINTaskAuditor"
import {
  GlobalIteration,
  AuditorRegistration,
  AuditBatch,
  AuditScoreSubmission,
  AuditScoreCommitment,
  EligibilityVote,
  EligibilityResult,
  LocalModelSubmission,
  AuditorSlashEvent,
  PassScoreUpdate,
  RewardDeposit,
  RewardSettlement,
  RewardClaim,
  RewardSplit,
  TestDataCommitment,
  EncryptedTestDataKeys,
  TestDataDispute,
  AuditorScoreDeviation as AuditorScoreDeviationEntity,
  TaskAuditorGovernance,
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

// Loads the LocalModelSubmission written by handleLocalModelSubmitted.
// LocalModelSubmitted always fires during the LMS phase, before any score,
// vote or eligibility event for the same model, so a missing row means the
// event stream is incomplete. Callers skip their write rather than inventing
// a placeholder entity.
function loadLMS(gi: BigInt, modelIndex: BigInt): LocalModelSubmission | null {
  let id = taAddress().toHex() + "-" + gi.toString() + "-" + modelIndex.toString()
  return LocalModelSubmission.load(id)
}

function lmsId(gi: BigInt, modelIndex: BigInt): string {
  return taAddress().toHex() + "-" + gi.toString() + "-" + modelIndex.toString()
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
    entity.globalIteration     = giEntity.id
    entity.batchId             = batchId
    entity.pendingReassignment = false
    entity.createdAtBlock      = blockNumber
    entity.createdAtTimestamp  = blockTimestamp
    entity.save()
  }
  return entity!
}

// ─── Local model submission ────────────────────────────────────────────────────

export function handleLocalModelSubmitted(event: LocalModelSubmitted): void {
  let gi  = loadOrCreateGI(event.params.GI, event.block.number, event.block.timestamp)
  let id  = lmsId(event.params.GI, event.params.modelIndex)
  let lms = LocalModelSubmission.load(id)
  if (lms == null) {
    lms = new LocalModelSubmission(id)
    lms.globalIteration = gi.id
    lms.modelIndex      = event.params.modelIndex
  }

  lms.client          = event.params.client
  lms.modelCID        = event.params.modelCID
  lms.blockNumber     = event.block.number
  lms.blockTimestamp  = event.block.timestamp
  lms.transactionHash = event.transaction.hash
  lms.save()
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

// AuditScoreSubmitted is the reveal step of commit-then-reveal scoring. The
// matching AuditScoreCommitment (written by handleAuditScoreCommitted) is
// marked revealed and the revealed score is recorded on it.
export function handleAuditScoreSubmitted(event: AuditScoreSubmitted): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadLMS(event.params.gi, event.params.modelIndex)
  if (lms == null) {
    log.warning("AuditScoreSubmitted: LocalModelSubmission missing for gi {} model {}", [
      event.params.gi.toString(), event.params.modelIndex.toString(),
    ])
    return
  }

  let id = taAddress().toHex() + "-" + event.params.gi.toString() + "-" +
           event.params.batchId.toString() + "-" + event.params.auditor.toHex() + "-" +
           event.params.modelIndex.toString()
  let sub = new AuditScoreSubmission(id)
  sub.auditBatch            = batch.id
  sub.localModelSubmission  = lms.id
  sub.auditor               = event.params.auditor
  sub.score                 = event.params.score

  let commitment = AuditScoreCommitment.load(id)
  if (commitment != null) {
    commitment.revealed            = true
    commitment.score               = event.params.score
    commitment.revealedAtBlock     = event.block.number
    commitment.revealedAtTimestamp = event.block.timestamp
    commitment.save()
    sub.commitment = commitment.id
  }

  sub.blockNumber           = event.block.number
  sub.blockTimestamp        = event.block.timestamp
  sub.transactionHash       = event.transaction.hash
  sub.save()
}

export function handleAuditScoreCommitted(event: AuditScoreCommitted): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadLMS(event.params.gi, event.params.modelIndex)
  if (lms == null) {
    log.warning("AuditScoreCommitted: LocalModelSubmission missing for gi {} model {}", [
      event.params.gi.toString(), event.params.modelIndex.toString(),
    ])
    return
  }

  let id = taAddress().toHex() + "-" + event.params.gi.toString() + "-" +
           event.params.batchId.toString() + "-" + event.params.auditor.toHex() + "-" +
           event.params.modelIndex.toString()
  let c = new AuditScoreCommitment(id)
  c.globalIteration       = gi.id
  c.auditBatch            = batch.id
  c.localModelSubmission  = lms.id
  c.auditor               = event.params.auditor
  c.modelIndex            = event.params.modelIndex
  c.commitHash            = event.params.commitHash
  c.revealed              = false
  c.score                 = null
  c.revealedAtBlock       = null
  c.revealedAtTimestamp   = null
  c.blockNumber           = event.block.number
  c.blockTimestamp        = event.block.timestamp
  c.transactionHash       = event.transaction.hash
  c.save()
}

// ─── Eligibility ───────────────────────────────────────────────────────────────

export function handleEligibilityVoted(event: EligibilityVoted): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadLMS(event.params.gi, event.params.modelIndex)
  if (lms == null) {
    log.warning("EligibilityVoted: LocalModelSubmission missing for gi {} model {}", [
      event.params.gi.toString(), event.params.modelIndex.toString(),
    ])
    return
  }

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
  let lms   = loadLMS(event.params.gi, event.params.modelIndex)
  if (lms == null) {
    log.warning("EligibilityFinalized: LocalModelSubmission missing for gi {} model {}", [
      event.params.gi.toString(), event.params.modelIndex.toString(),
    ])
    return
  }

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

// ─── Rewards ───────────────────────────────────────────────────────────────────

export function handleRewardDeposited(event: RewardDeposited): void {
  let gi = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let e  = new RewardDeposit(eventId(event.transaction.hash, event.logIndex))
  e.globalIteration = gi.id
  e.depositor       = event.params.depositor
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleRewardsSettled(event: RewardsSettled): void {
  let gi = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let e  = new RewardSettlement(eventId(event.transaction.hash, event.logIndex))
  e.globalIteration = gi.id
  e.clientPool      = event.params.clientPool
  e.auditorPool     = event.params.auditorPool
  e.aggregatorPool  = event.params.aggregatorPool
  e.treasuryShare   = event.params.treasuryShare
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleRewardsClaimed(event: RewardsClaimed): void {
  let e = new RewardClaim(eventId(event.transaction.hash, event.logIndex))
  e.claimant        = event.params.claimant
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleRewardSplitUpdated(event: RewardSplitUpdated): void {
  let id = event.address.toHexString()
  let s  = RewardSplit.load(id)
  if (s == null) {
    s = new RewardSplit(id)
  }
  let split = event.params.split
  s.clientBps     = split.clientBps
  s.auditorBps    = split.auditorBps
  s.aggregatorBps = split.aggregatorBps
  s.treasuryBps   = split.treasuryBps
  s.updatedAtBlock     = event.block.number
  s.updatedAtTimestamp = event.block.timestamp
  s.save()
}

// ─── Test-data flow and disputes ───────────────────────────────────────────────

function testDataId(gi: BigInt, batchId: BigInt): string {
  return taAddress().toHex() + "-" + gi.toString() + "-" + batchId.toString()
}

export function handleTestDataCommitmentStored(event: TestDataCommitmentStored): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let e     = new TestDataCommitment(testDataId(event.params.gi, event.params.batchId))
  e.globalIteration = gi.id
  e.auditBatch      = batch.id
  e.commitment      = event.params.commitment
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleEncryptedTestDataKeysAssigned(event: EncryptedTestDataKeysAssigned): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let e     = new EncryptedTestDataKeys(testDataId(event.params.gi, event.params.batchId))
  e.globalIteration = gi.id
  e.auditBatch      = batch.id
  e.testDataCID     = event.params.testDataCID
  e.auditorCount    = event.params.auditorCount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleTestDataDisputeOpened(event: TestDataDisputeOpened): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let d     = new TestDataDispute(testDataId(event.params.gi, event.params.batchId))
  d.globalIteration = gi.id
  d.auditBatch      = batch.id
  d.disputer        = event.params.disputer
  d.bond            = event.params.bond
  d.expiresAtBlock  = event.params.expiresAtBlock
  d.status          = "Open"
  d.openedAtBlock   = event.block.number
  d.openedAtTimestamp = event.block.timestamp
  d.blockNumber     = event.block.number
  d.blockTimestamp  = event.block.timestamp
  d.transactionHash = event.transaction.hash
  d.save()
}

export function handleTestDataDisputeUpheld(event: TestDataDisputeUpheld): void {
  let id = testDataId(event.params.gi, event.params.batchId)
  let d  = TestDataDispute.load(id)
  if (d == null) {
    log.warning("TestDataDisputeUpheld: TestDataDispute {} not found", [id])
    return
  }
  d.status              = "Upheld"
  d.bondReturned        = event.params.bondReturned
  d.ownerPenalty        = event.params.ownerPenalty
  d.resolvedAtBlock     = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleTestDataDisputeResolvedFalse(event: TestDataDisputeResolvedFalse): void {
  let id = testDataId(event.params.gi, event.params.batchId)
  let d  = TestDataDispute.load(id)
  if (d == null) {
    log.warning("TestDataDisputeResolvedFalse: TestDataDispute {} not found", [id])
    return
  }
  d.status              = "ResolvedFalse"
  d.bondForfeited       = event.params.bondForfeited
  d.resolvedAtBlock     = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleTestDataDisputeExpired(event: DisputeExpired): void {
  let id = testDataId(event.params.gi, event.params.batchId)
  let d  = TestDataDispute.load(id)
  if (d == null) {
    log.warning("DisputeExpired: TestDataDispute {} not found", [id])
    return
  }
  d.status              = "Expired"
  d.resolvedAtBlock     = event.block.number
  d.resolvedAtTimestamp = event.block.timestamp
  d.save()
}

export function handleBatchPendingReassignment(event: BatchPendingReassignment): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  batch.pendingReassignment = true
  batch.save()
}

// ─── S3 score deviation ────────────────────────────────────────────────────────

export function handleAuditorScoreDeviation(event: AuditorScoreDeviation): void {
  let gi    = loadOrCreateGI(event.params.gi, event.block.number, event.block.timestamp)
  let batch = loadOrCreateAuditBatch(event.params.gi, event.params.batchId, gi, event.block.number, event.block.timestamp)
  let lms   = loadLMS(event.params.gi, event.params.modelIndex)
  if (lms == null) {
    log.warning("AuditorScoreDeviation: LocalModelSubmission missing for gi {} model {}", [
      event.params.gi.toString(), event.params.modelIndex.toString(),
    ])
    return
  }

  let e = new AuditorScoreDeviationEntity(eventId(event.transaction.hash, event.logIndex))
  e.globalIteration      = gi.id
  e.auditBatch           = batch.id
  e.localModelSubmission = lms.id
  e.auditor              = event.params.auditor
  e.modelIndex           = event.params.modelIndex
  e.auditorScore         = event.params.auditorScore
  e.medianScore          = event.params.medianScore
  e.deviation            = event.params.deviation
  e.exceedsThreshold     = event.params.exceedsThreshold
  e.blockNumber          = event.block.number
  e.blockTimestamp       = event.block.timestamp
  e.transactionHash      = event.transaction.hash
  e.save()
}

// ─── S1/S3 governance parameters ───────────────────────────────────────────────

function loadOrCreateTaskAuditorGovernance(id: string): TaskAuditorGovernance {
  let g = TaskAuditorGovernance.load(id)
  if (g == null) {
    g = new TaskAuditorGovernance(id)
    g.updatedAtBlock     = BigInt.zero()
    g.updatedAtTimestamp = BigInt.zero()
  }
  return g!
}

export function handleS1SlashFractionBpsUpdated(event: S1SlashFractionBpsUpdated): void {
  let g = loadOrCreateTaskAuditorGovernance(event.address.toHexString())
  g.s1SlashFractionBps = event.params.newBps
  g.updatedAtBlock     = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}

export function handleS3DeviationThresholdUpdated(event: S3DeviationThresholdUpdated): void {
  let g = loadOrCreateTaskAuditorGovernance(event.address.toHexString())
  g.s3DeviationThreshold = event.params.newThreshold
  g.updatedAtBlock       = event.block.number
  g.updatedAtTimestamp   = event.block.timestamp
  g.save()
}

export function handleS3SlashingEnabledUpdated(event: S3SlashingEnabledUpdated): void {
  let g = loadOrCreateTaskAuditorGovernance(event.address.toHexString())
  g.s3SlashingEnabled = event.params.newValue
  g.updatedAtBlock    = event.block.number
  g.updatedAtTimestamp = event.block.timestamp
  g.save()
}
