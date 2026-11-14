import { TokensMinted, TokensBurned, Transfer } from "../generated/DinToken/DinToken"
import { TokenMintEvent, TokenBurnEvent, TokenTransferEvent } from "../generated/schema"
import { eventId } from "./utils"

export function handleTokensMinted(event: TokensMinted): void {
  let e = new TokenMintEvent(eventId(event.transaction.hash, event.logIndex))
  e.to              = event.params.to
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

export function handleTokensBurned(event: TokensBurned): void {
  let e = new TokenBurnEvent(eventId(event.transaction.hash, event.logIndex))
  e.from            = event.params.from
  e.amount          = event.params.amount
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}

// Standard ERC20 Transfer — covers mints (from = 0x0) and normal transfers.
export function handleTransfer(event: Transfer): void {
  let e = new TokenTransferEvent(eventId(event.transaction.hash, event.logIndex))
  e.from            = event.params.from
  e.to              = event.params.to
  e.amount          = event.params.value
  e.blockNumber     = event.block.number
  e.blockTimestamp  = event.block.timestamp
  e.transactionHash = event.transaction.hash
  e.save()
}
