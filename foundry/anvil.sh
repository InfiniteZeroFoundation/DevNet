#!/bin/bash
# The single source of the local chain's flags. The isolated test harness
# (tests/dincli/conftest.py, DIN_TEST_ISOLATED=1) starts Anvil through this
# script as well: it sets ANVIL_BIN to the binary it resolved and appends
# --host 127.0.0.1. Any extra arguments are forwarded to anvil.
exec "${ANVIL_BIN:-anvil}" \
  --accounts 70 \
  --balance 10000 \
  --chain-id 1337 \
  --code-size-limit 4294967295 \
  --block-time 2 \
  --mnemonic "test test test test test test test test test test test junk" \
  "$@"
#   --code-size-limit 4294967295: lifts the EIP-170 24,576-byte runtime
#   limit, so local deploys accept contracts a real chain would reject.
#   CI enforces the limit instead: .github/scripts/contract_size_gate.py
#   fails any foundry/src contract with < 1,024 B margin (issue #201).
#   --block-time 2: without a block-time, anvil only mines when a tx
#   arrives, so an idle chain sits at block 0 forever. dincli's
#   ensure_batch_seed_locked (issue #156 H-2) polls w3.eth.block_number
#   waiting for a future anchor block and hangs indefinitely without this
#   -- see PR #191 review, finding No. 3.

#   chmod +x anvil.sh &&
#  ./anvil.sh