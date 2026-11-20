import {
  EthReceived,
  EthWithdrawn,
  ERC20Withdrawn,
} from "../generated/DinTreasury/DinTreasury"
import {
  TreasuryEthReceived,
  TreasuryEthWithdrawn,
  TreasuryERC20Withdrawn,
} from "../generated/schema"
import { eventId } from "./utils"

export function handleTreasuryEthReceived(event: EthReceived): void {
  let e = new TreasuryEthReceived(eventId(event.transaction.hash, event.logIndex))
  e.from            = event.params.from
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleTreasuryEthWithdrawn(event: EthWithdrawn): void {
  let e = new TreasuryEthWithdrawn(eventId(event.transaction.hash, event.logIndex))
  e.to              = event.params.to
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleTreasuryERC20Withdrawn(event: ERC20Withdrawn): void {
  let e = new TreasuryERC20Withdrawn(eventId(event.transaction.hash, event.logIndex))
  e.token           = event.params.token
  e.to              = event.params.to
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}
