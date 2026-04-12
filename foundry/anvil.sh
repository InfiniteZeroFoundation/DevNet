#!/bin/bash
anvil \
  --accounts 70 \
  --balance 10000 \
  --chain-id 1337 \
  --code-size-limit 4294967295 \
  --mnemonic "test test test test test test test test test test test junk" 
#   --code-size-limit 4294967295

#   chmod +x anvil.sh &&
#  ./anvil.sh