import { BigInt, DataSourceContext, Address } from "@graphprotocol/graph-ts"
import {
  ModelRegistrationRequested,
  ModelApproved,
  ModelRejected,
  ManifestUpdateRequested,
  ManifestUpdated,
  ManifestUpdateRejected,
  ModelDisabled,
  ModelEnabled,
  OpenSourceFeeUpdated,
  ProprietaryFeeUpdated,
  OpenSourceUpdateFeeUpdated,
  ProprietaryUpdateFeeUpdated,
  FeesUpdated,
  FeesWithdrawn,
  DAOAdminUpdated,
  DINModelRegistry,
} from "../generated/DINModelRegistry/DINModelRegistry"
import {
  ModelRegistrationRequest,
  Model,
  ManifestUpdateRequest,
  ModelKillSwitchEvent,
  FeeSnapshot,
  RegistryFeeWithdrawal,
  DAOAdminTransfer,
} from "../generated/schema"
import { eventId } from "./utils"
import {
  DINTaskCoordinator as DINTaskCoordinatorTemplate,
  DINTaskAuditor as DINTaskAuditorTemplate,
} from "../generated/templates"

// ─── Registration request lifecycle ──────────────────────────────────────────

export function handleModelRegistrationRequested(
  event: ModelRegistrationRequested
): void {
  let id = event.params.requestId.toString()
  let req = new ModelRegistrationRequest(id)

  req.requestId  = event.params.requestId
  req.requester  = event.params.requester

  // isOpenSource and fee are not in the event until audit §6.1 addition lands.
  // Bridge: read from contract storage at this block.
  let registry   = DINModelRegistry.bind(event.address)
  let stored     = registry.modelRequests(event.params.requestId)
  req.isOpenSource      = stored.getIsOpenSource()
  req.feePaid           = stored.getFeePaid()
  req.manifestCID       = stored.getManifestCID()
  req.taskCoordinator   = stored.getTaskCoordinator()
  req.taskAuditor       = stored.getTaskAuditor()

  req.processed  = false
  req.approved   = null
  req.model      = null

  req.submittedAtBlock     = event.block.number
  req.submittedAtTimestamp = event.block.timestamp
  req.processedAtBlock     = null
  req.processedAtTimestamp = null

  req.save()
}

export function handleModelApproved(event: ModelApproved): void {
  let reqId = event.params.requestId.toString()
  let req   = ModelRegistrationRequest.load(reqId)
  if (req == null) return

  req.processed        = true
  req.approved         = true
  req.processedAtBlock     = event.block.number
  req.processedAtTimestamp = event.block.timestamp

  let modelId = event.params.modelId.toString()
  req.model   = modelId
  req.save()

  // Build the approved Model entity from storage — all fields are available
  // via getModel() at this block without a separate event.
  let registry = DINModelRegistry.bind(event.address)
  let stored   = registry.getModel(event.params.modelId)

  let model              = new Model(modelId)
  model.modelId          = event.params.modelId
  model.owner            = stored.getOwner()
  model.isOpenSource     = stored.getIsOpenSource()
  model.manifestCID      = stored.getManifestCID()
  model.taskCoordinator  = stored.getTaskCoordinator()
  model.taskAuditor      = stored.getTaskAuditor()
  model.disabled         = false
  model.registrationRequest = reqId
  model.createdAtBlock      = event.block.number
  model.createdAtTimestamp  = event.block.timestamp
  model.save()

  // Spin up dynamic data source instances for this model's task contracts.
  // Both templates receive the same context so handlers on either side can
  // resolve the modelId and the paired contract address.
  let ctx = new DataSourceContext()
  ctx.setBigInt("modelId", event.params.modelId)
  ctx.setBytes("taskCoordinatorAddress", model.taskCoordinator)
  ctx.setBytes("taskAuditorAddress", model.taskAuditor)

  DINTaskCoordinatorTemplate.createWithContext(
    Address.fromBytes(model.taskCoordinator),
    ctx,
  )
  DINTaskAuditorTemplate.createWithContext(
    Address.fromBytes(model.taskAuditor),
    ctx,
  )
}

export function handleModelRejected(event: ModelRejected): void {
  let req = ModelRegistrationRequest.load(event.params.requestId.toString())
  if (req == null) return
  req.processed        = true
  req.approved         = false
  req.processedAtBlock     = event.block.number
  req.processedAtTimestamp = event.block.timestamp
  req.save()
}

// ─── Manifest update lifecycle ────────────────────────────────────────────────

export function handleManifestUpdateRequested(
  event: ManifestUpdateRequested
): void {
  let id  = event.params.requestId.toString()
  let mur = new ManifestUpdateRequest(id)

  mur.requestId = event.params.requestId
  mur.model     = event.params.modelId.toString()

  // requester is not in the event until audit §6.2 addition lands.
  // Bridge: derive from Model.owner — only the model owner can call
  // requestManifestUpdate (onlyModelOwner modifier).
  let model = Model.load(event.params.modelId.toString())
  mur.requester = model != null ? model.owner : event.transaction.from

  // Read fee and CID from storage.
  let registry = DINModelRegistry.bind(event.address)
  let stored   = registry.manifestRequests(event.params.requestId)
  mur.feePaid       = stored.getFeePaid()
  mur.newManifestCID = stored.getNewManifestCID()

  mur.processed = false
  mur.approved  = null

  mur.submittedAtBlock     = event.block.number
  mur.submittedAtTimestamp = event.block.timestamp
  mur.processedAtBlock     = null
  mur.processedAtTimestamp = null

  mur.save()
}

export function handleManifestUpdated(event: ManifestUpdated): void {
  let mur = ManifestUpdateRequest.load(event.params.requestId.toString())
  if (mur != null) {
    mur.processed        = true
    mur.approved         = true
    mur.processedAtBlock     = event.block.number
    mur.processedAtTimestamp = event.block.timestamp
    mur.save()
  }

  let model = Model.load(event.params.modelId.toString())
  if (model != null) {
    model.manifestCID = event.params.newCID
    model.save()
  }
}

export function handleManifestUpdateRejected(
  event: ManifestUpdateRejected
): void {
  let mur = ManifestUpdateRequest.load(event.params.requestId.toString())
  if (mur == null) return
  mur.processed        = true
  mur.approved         = false
  mur.processedAtBlock     = event.block.number
  mur.processedAtTimestamp = event.block.timestamp
  mur.save()
}

// ─── Kill switch ──────────────────────────────────────────────────────────────

export function handleModelDisabled(event: ModelDisabled): void {
  _applyKillSwitch(event.params.modelId, true, event)
}

export function handleModelEnabled(event: ModelEnabled): void {
  _applyKillSwitch(event.params.modelId, false, event)
}

function _applyKillSwitch(
  modelId: BigInt,
  disabled: boolean,
  event: ModelDisabled | ModelEnabled
): void {
  let model = Model.load(modelId.toString())
  if (model != null) {
    model.disabled = disabled
    model.save()
  }

  let ks = new ModelKillSwitchEvent(
    eventId(event.transaction.hash, event.logIndex)
  )
  ks.model          = modelId.toString()
  ks.disabled       = disabled
  ks.blockNumber    = event.block.number
  ks.blockTimestamp = event.block.timestamp
  ks.transactionHash = event.transaction.hash
  ks.save()
}

// ─── Fee governance ───────────────────────────────────────────────────────────

// For the four individual setters we read the full current fee schedule from
// storage so each FeeSnapshot always carries a complete picture.

export function handleOpenSourceFeeUpdated(
  event: OpenSourceFeeUpdated
): void {
  _saveGranularFeeSnapshot(event.address, "granular", event)
}

export function handleProprietaryFeeUpdated(
  event: ProprietaryFeeUpdated
): void {
  _saveGranularFeeSnapshot(event.address, "granular", event)
}

export function handleOpenSourceUpdateFeeUpdated(
  event: OpenSourceUpdateFeeUpdated
): void {
  _saveGranularFeeSnapshot(event.address, "granular", event)
}

export function handleProprietaryUpdateFeeUpdated(
  event: ProprietaryUpdateFeeUpdated
): void {
  _saveGranularFeeSnapshot(event.address, "granular", event)
}

function _saveGranularFeeSnapshot(
  contractAddress: import("@graphprotocol/graph-ts").Address,
  kind: string,
  event: OpenSourceFeeUpdated | ProprietaryFeeUpdated | OpenSourceUpdateFeeUpdated | ProprietaryUpdateFeeUpdated
): void {
  let registry = DINModelRegistry.bind(contractAddress)
  let snap     = new FeeSnapshot(eventId(event.transaction.hash, event.logIndex))
  snap.openSourceFee       = registry.openSourceFee()
  snap.proprietaryFee      = registry.proprietaryFee()
  snap.openSourceUpdateFee = registry.openSourceUpdateFee()
  snap.proprietaryUpdateFee = registry.proprietaryUpdateFee()
  snap.updateKind          = kind
  snap.blockNumber         = event.block.number
  snap.blockTimestamp      = event.block.timestamp
  snap.transactionHash     = event.transaction.hash
  snap.save()
}

// FeesUpdated carries all four new values directly — no storage call needed.
export function handleFeesUpdated(event: FeesUpdated): void {
  let snap = new FeeSnapshot(eventId(event.transaction.hash, event.logIndex))
  snap.openSourceFee        = event.params.openSourceFee
  snap.proprietaryFee       = event.params.proprietaryFee
  snap.openSourceUpdateFee  = event.params.openSourceUpdateFee
  snap.proprietaryUpdateFee = event.params.proprietaryUpdateFee
  snap.updateKind           = "atomic"
  snap.blockNumber          = event.block.number
  snap.blockTimestamp       = event.block.timestamp
  snap.transactionHash      = event.transaction.hash
  snap.save()
}

export function handleFeesWithdrawn(event: FeesWithdrawn): void {
  let w = new RegistryFeeWithdrawal(
    eventId(event.transaction.hash, event.logIndex)
  )
  w.to              = event.params.to
  w.amount          = event.params.amount
  w.blockNumber     = event.block.number
  w.blockTimestamp  = event.block.timestamp
  w.transactionHash = event.transaction.hash
  w.save()
}

export function handleDAOAdminUpdated(event: DAOAdminUpdated): void {
  let t = new DAOAdminTransfer(
    eventId(event.transaction.hash, event.logIndex)
  )
  t.oldAdmin        = event.params.oldAdmin
  t.newAdmin        = event.params.newAdmin
  t.blockNumber     = event.block.number
  t.blockTimestamp  = event.block.timestamp
  t.transactionHash = event.transaction.hash
  t.save()
}
