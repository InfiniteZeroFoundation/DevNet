#!/bin/bash
anvil \
  --accounts 70 \
  --balance 10000 \
  --chain-id 1337 \
  --code-size-limit 4294967295 \
  --block-time 2 \
  --mnemonic "test test test test test test test test test test test junk"
#   --code-size-limit 4294967295
#   --block-time 2: without a block-time, anvil only mines when a tx
#   arrives, so an idle chain sits at block 0 forever. dincli's
#   ensure_batch_seed_locked (issue #156 H-2) polls w3.eth.block_number
#   waiting for a future anchor block and hangs indefinitely without this
#   -- see PR #191 review, finding No. 3.

#   chmod +x anvil.sh &&
#  ./anvil.sh